"""0x-alpha schema, prompt, fake client, cache, and budget guardrail tests.

No network. No live model calls (design sections 46.18, 51.8).
"""

from __future__ import annotations

import json

import pytest

from audio_similarity.ox_alpha import (
    ALLOWED_PREFERENCES,
    PROMPT_VERSION,
    FakeOxAlphaClient,
    OxCallResult,
    OxComparisonResult,
    OxJsonParseError,
    OxResponseError,
    OxResultCache,
    RunBudget,
    build_messages,
    build_prompt,
    comparison_cache_key,
    parse_ox_response,
)

VALID_A = json.dumps({
    "preference": "A",
    "confidence": 0.82,
    "dimensions": {
        "temporal_pattern": "A",
        "spectral_texture": "A",
        "harmonic_structure": "tie",
        "transient_structure": "B",
    },
    "observations": {
        "temporal_pattern_similarity": 0.78,
        "spectral_texture_similarity": 0.81,
        "harmonic_structure_similarity": 0.63,
        "transient_structure_similarity": 0.52,
        "dynamic_envelope_similarity": 0.71,
    },
    "abstain": False,
    "reason": "candidate A shows denser harmonic stacks",
})


def test_valid_preference_a():
    result = parse_ox_response(VALID_A)
    assert isinstance(result, OxComparisonResult)
    assert result.preference == "A"
    assert result.confidence == pytest.approx(0.82)
    assert result.dimensions["transient_structure"] == "B"
    assert result.observations["dynamic_envelope_similarity"] == pytest.approx(0.71)
    assert result.abstain is False


@pytest.mark.parametrize("preference", ["A", "B", "Tie"])
def test_valid_preferences_roundtrip(preference):
    payload = {
        "preference": preference,
        "confidence": 0.5,
        "dimensions": {k: "Tie" for k in (
            "temporal_pattern", "spectral_texture", "harmonic_structure", "transient_structure")},
        "observations": {},
        "abstain": False,
        "reason": "",
    }
    result = parse_ox_response(json.dumps(payload))
    assert result.preference == preference


def test_valid_abstain():
    payload = {
        "preference": "Abstain",
        "confidence": 0.1,
        "dimensions": {k: "Tie" for k in (
            "temporal_pattern", "spectral_texture", "harmonic_structure", "transient_structure")},
        "observations": {},
        "abstain": True,
        "reason": "images too dark",
    }
    result = parse_ox_response(json.dumps(payload))
    assert result.preference == "Abstain" and result.abstain is True


@pytest.mark.parametrize("confidence", [-0.1, 1.5, float("nan"), float("inf"), "high", True])
def test_invalid_confidence_rejected(confidence):
    payload = json.loads(VALID_A)
    payload["confidence"] = confidence
    with pytest.raises(OxResponseError):
        parse_ox_response(json.dumps(payload))


def test_missing_required_field_rejected():
    payload = json.loads(VALID_A)
    del payload["confidence"]
    with pytest.raises(OxResponseError, match="missing required"):
        parse_ox_response(json.dumps(payload))


def test_missing_dimension_rejected():
    payload = json.loads(VALID_A)
    del payload["dimensions"]["spectral_texture"]
    with pytest.raises(OxResponseError, match="missing"):
        parse_ox_response(json.dumps(payload))


def test_invalid_enum_rejected():
    payload = json.loads(VALID_A)
    payload["preference"] = "CANDIDATE_A"
    with pytest.raises(OxResponseError, match="invalid preference"):
        parse_ox_response(json.dumps(payload))


def test_invalid_dimension_value_rejected():
    payload = json.loads(VALID_A)
    payload["dimensions"]["temporal_pattern"] = "maybe"
    with pytest.raises(OxResponseError, match="invalid dimensions"):
        parse_ox_response(json.dumps(payload))


def test_malformed_json_raises_typed_error():
    with pytest.raises(OxJsonParseError):
        parse_ox_response("this is not json at all {")


def test_non_json_top_level_rejected():
    with pytest.raises(OxResponseError, match="must be an object"):
        parse_ox_response("[1,2,3]")


def test_schema_incompatibility_extra_keys_rejected():
    payload = json.loads(VALID_A)
    payload["dimensions"]["rhythm_feel"] = "A"
    with pytest.raises(OxResponseError, match="schema incompatibility"):
        parse_ox_response(json.dumps(payload))


def test_abstain_conflict_rejected():
    payload = json.loads(VALID_A)
    payload["abstain"] = True
    with pytest.raises(OxResponseError, match="conflict"):
        parse_ox_response(json.dumps(payload))


# ---------------------------------------------------------------------------
# prompt contract
# ---------------------------------------------------------------------------


def test_prompt_is_versioned_and_contains_required_instructions():
    prompt = build_prompt()
    assert PROMPT_VERSION == "ox_pairwise_v1"
    lowered = prompt.lower()
    for phrase in ("supplied images", "prior knowledge", "identify",
                   "abstain", "json object and nothing else"):
        assert phrase in lowered, f"prompt missing instruction: {phrase}"


def test_build_messages_attaches_three_images_with_opaque_labels():
    messages = build_messages("p", "AAA", "BBB", "CCC")
    content = messages[0]["content"]
    assert content[0]["type"] == "text"
    labels = [part["image_url"]["url"] for part in content[1:]]
    assert [u.count("base64,") for u in labels] == [1, 1, 1]
    # opaque identifiers only — nothing song-specific in the text portion
    assert "artist" not in content[0]["text"].lower()


# ---------------------------------------------------------------------------
# fake client + cache + budget
# ---------------------------------------------------------------------------


def _png(i: int) -> bytes:
    return b"\x89PNG" + bytes([i]) * 16


def test_fake_client_scripted_sequence_and_parse_status(tmp_path):
    client = FakeOxAlphaClient(scripted_preferences=["A", "B", "Abstain"])
    results: list[OxCallResult] = []
    for _ in range(3):
        call = client.compare("p", _png(1), _png(2), _png(3))
        results.append(call)
    statuses = [r.parse_status for r in results]
    assert statuses == ["ok", "ok", "ok"]
    preferences = [r.parsed.preference for r in results]
    assert preferences == ["A", "B", "Abstain"]
    assert all(r.latency_ms >= 0 for r in results)


def test_cache_resume_skips_completed_jobs(tmp_path):
    cache = OxResultCache(tmp_path / "cache.jsonl")

    def key(replicate: int) -> str:
        return comparison_cache_key(
            query_audio_hash="q", candidate_a_audio_hash="a", candidate_b_audio_hash="b",
            sampling_strategy_identity="three20_v1", renderer_name="log_mel", renderer_version=1,
            ox_model_id="fake-ox-alpha", provider_revision="r0", prompt_version=PROMPT_VERSION,
            comparison_mode="pairwise", replicate_index=replicate,
        )

    assert not cache.has(key(0))
    client = FakeOxAlphaClient(scripted_preferences=["A"])
    pending = [key(r) for r in range(3) if not cache.has(key(r))]
    for k in pending:
        call = client.compare("p", _png(1), _png(2), _png(3))
        cache.append({"cache_key": k, "parse_status": call.parse_status,
                      "result": call.parsed.to_dict()})
    assert len(cache.records()) == 3

    # interrupted run restarts: completed keys are skipped
    remaining = [key(r) for r in range(3) if not cache.has(key(r))]
    assert remaining == []

    # different renderer version invalidates the cache identity
    other = key(0)
    changed = comparison_cache_key(
        query_audio_hash="q", candidate_a_audio_hash="a", candidate_b_audio_hash="b",
        sampling_strategy_identity="three20_v1", renderer_name="log_mel", renderer_version=2,
        ox_model_id="fake-ox-alpha", provider_revision="r0", prompt_version=PROMPT_VERSION,
        comparison_mode="pairwise", replicate_index=0,
    )
    assert changed != other


def test_cache_key_changes_when_any_identity_component_changes():
    base = dict(
        query_audio_hash="q", candidate_a_audio_hash="a", candidate_b_audio_hash="b",
        sampling_strategy_identity="three20_v1", renderer_name="linear_stft", renderer_version=1,
        ox_model_id="m", provider_revision="r", prompt_version="v1",
        comparison_mode="pairwise", replicate_index=0,
    )
    baseline = comparison_cache_key(**base)
    variants = [
        {**base, "query_audio_hash": "q2"},
        {**base, "sampling_strategy_identity": "first30_v1"},
        {**base, "renderer_name": "waveform"},
        {**base, "renderer_version": 2},
        {**base, "ox_model_id": "m2"},
        {**base, "provider_revision": "r2"},
        {**base, "prompt_version": "v2"},
        {**base, "comparison_mode": "listwise"},
        {**base, "replicate_index": 1},
    ]
    for variant in variants:
        assert comparison_cache_key(**variant) != baseline


def test_budget_planning_guardrail():
    budget = RunBudget(max_requests=10)
    budget.plan(10)
    acquired = sum(1 for _ in iter(budget.acquire, False))
    assert acquired == 10
    assert budget.acquire() is False  # cap reached

    with pytest.raises(ValueError, match="--max-requests"):
        RunBudget(max_requests=5).plan(6)


def test_all_allowed_preferences_constant():
    assert ALLOWED_PREFERENCES == ("A", "B", "Tie", "Abstain")
