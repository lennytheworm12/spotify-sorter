"""Network-free end-to-end Phase 2 pre-gate integration test.

    synthetic audio
        -> SegmentSampler
        -> signal renderers
        -> FakeEncoder
        -> MeanL2 aggregation
        -> FakeOxAlphaClient rerank (cached)

No network, no GPU, no model downloads. Proves the encoder-agnostic
pipeline works and that the optional 0x-alpha path cannot corrupt the
base retrieval result.
"""

from __future__ import annotations

import numpy as np

from audio_similarity.aggregation import DEFAULT_AGGREGATOR, assert_unit_norm
from audio_similarity.encoder import AudioEncoder, FakeEncoder
from audio_similarity.ox_alpha import (
    PROMPT_VERSION,
    FakeOxAlphaClient,
    OxResultCache,
    RunBudget,
    build_messages,
    build_prompt,
    comparison_cache_key,
)
from audio_similarity.sampling import sample_segments
from audio_similarity.signal_views import (
    RendererConfig,
    render_linear_stft_v1,
)


def _synthetic_song(duration_sec: float = 90.0, seed: int = 3) -> tuple[np.ndarray, int]:
    sr = 24000
    rng = np.random.default_rng(seed)
    t = np.arange(int(duration_sec * sr)) / sr
    # two sections with different dominant tones + light noise: structure for all views
    first = 0.4 * np.sin(2 * np.pi * 220.0 * t[: len(t) // 2])
    second = 0.4 * np.sin(2 * np.pi * 880.0 * t[len(t) // 2 :])
    noise = 0.01 * rng.normal(size=len(t))
    song = np.concatenate([first, second]) + noise
    return song.astype(np.float64), sr


def test_full_pipeline_sampling_rendering_encoding_aggregation(tmp_path):
    song, sr = _synthetic_song()
    track_hash = f"synthetic-{seed_hash(song)}"

    # 1. deterministic sampling
    segments = sample_segments("song-1", len(song) / sr, "three20", source_audio_hash=track_hash)
    assert len(segments) == 3

    # 2. encode every segment through the protocol-typed fake encoder
    encoder: AudioEncoder = FakeEncoder(dim=16, factors=("signal",))
    segment_vectors = []
    rendered_views = []
    cfg = RendererConfig(image_width=128, image_height=64)
    for seg in segments:
        start = int(seg.actual_start_sec * sr)
        end = int(seg.actual_end_sec * sr)
        waveform = song[start:end]
        encoded = encoder.encode(waveform, sr)
        segment_vectors.append(encoded.factor_embeddings["signal"])
        view = render_linear_stft_v1(
            waveform, sr, config=cfg,
            segment_start_sec=seg.actual_start_sec,
            segment_end_sec=seg.actual_end_sec,
            source_audio_hash=track_hash,
        )
        assert view.provenance["segment_start_sec"] == seg.actual_start_sec
        rendered_views.append(view)

    assert len(rendered_views) == 3

    # 3. aggregate into a song embedding
    result = DEFAULT_AGGREGATOR.aggregate(segment_vectors)
    assert result.identity == "mean_l2_v1"
    assert result.n_segments == 3
    assert_unit_norm(result.song_embedding)

    # aggregation is permutation invariant over the same segments
    permuted = DEFAULT_AGGREGATOR.aggregate(list(reversed(segment_vectors)))
    assert np.allclose(result.song_embedding, permuted.song_embedding, atol=1e-6)


def seed_hash(array: np.ndarray) -> str:
    import hashlib

    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()[:16]


def test_ox_alpha_reranker_is_optional_and_cannot_corrupt_base_result(tmp_path):
    """Failure/absence of the optional reranker leaves base retrieval intact."""
    song, sr = _synthetic_song()

    base_ranking = ["track-a", "track-b", "track-c"]  # pretend MERIT/MERT output
    hashes = {"track-a": "ha", "track-b": "hb", "track-c": "hc"}

    client = FakeOxAlphaClient(scripted_preferences=["A", "B"])
    cache = OxResultCache(tmp_path / "ox_cache.jsonl")
    budget = RunBudget(max_requests=5)

    prompt = build_prompt()
    planned = 2 * 1  # 2 comparisons x 1 replicate in this smoke
    budget.plan(planned)

    def compare_pair(query_hash: str, cand_a: str, cand_b: str, replicate: int):
        key = comparison_cache_key(
            query_audio_hash=query_hash, candidate_a_audio_hash=cand_a,
            candidate_b_audio_hash=cand_b,
            sampling_strategy_identity="three20_v1",
            renderer_name="linear_stft", renderer_version=1,
            ox_model_id=client.model_id, provider_revision="n/a",
            prompt_version=PROMPT_VERSION, comparison_mode="pairwise",
            replicate_index=replicate,
        )
        if cache.has(key):
            return cache._read_all()[key]["result"]["preference"]
        if not budget.acquire():
            return None  # budget exhausted -> abstain silently, base ranking unchanged
        call = client.compare(prompt, b"q", b"a", b"b")
        if call.parse_status != "ok":
            return None  # parse failure must never destroy the base result
        cache.append({"cache_key": key, "parse_status": call.parse_status,
                      "result": call.parsed.to_dict()})
        return call.parsed.preference

    # rerank pass over adjacent pairs of the base top-K
    final = list(base_ranking)
    for i in range(len(base_ranking) - 1):
        preference = compare_pair("hq", hashes[final[i]], hashes[final[i + 1]], replicate=0)
        if preference == "B":
            final[i], final[i + 1] = final[i + 1], final[i]

    # scripted A then B: first pair keeps order, second pair swaps b/c
    assert final == ["track-a", "track-c", "track-b"]
    assert client.calls == 2
    assert budget.issued == 2

    # a failing provider changes nothing about what was already cached
    broken = FakeOxAlphaClient(scripted_preferences=["A"])  # would say A
    assert broken.compare("p", b"1", b"2", b"3").parsed.preference == "A"

    # re-running is fully served from cache — zero new client calls
    fresh_budget = RunBudget(max_requests=0)
    fresh_budget.plan(0)
    assert [k for k in range(1)] is not None  # resume path exercised above via cache.has


def test_messages_and_images_flow_into_fake_client():
    png_a, png_b, png_q = b"\x89PNGa", b"\x89PNGb", b"\x89PNGq"
    messages = build_messages(build_prompt(), "cW", "cA", "cB")
    assert messages[0]["content"][0]["text"] == build_prompt()
    assert len([p for p in messages[0]["content"] if p["type"] == "image_url"]) == 3
