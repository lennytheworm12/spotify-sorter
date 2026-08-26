from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from audio_similarity.stage2b_audio import canonical_pcm, float32_le_bytes
from audio_similarity.stage2b_collection import validate_collection_bundle
from audio_similarity.stage2b_store import RatingPolicyError, Stage2BStore, normalize_rater_id
from tests.helpers import save_wav, synth_waveform


@pytest.fixture
def stage2b_store(tmp_path: Path) -> Stage2BStore:
    reports = tmp_path / "reports"
    reports.mkdir()
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    rows = []
    identities = {}
    for track_id in (1, 2, 3, 4):
        path = save_wav(audio_root / f"{track_id}.wav", synth_waveform(30.0, seed=track_id), 24000)
        _, excerpt, _, _ = canonical_pcm(path)
        digest = hashlib.sha256(float32_le_bytes(excerpt)).hexdigest()
        identities[track_id] = {"center5_v1_pcm_sha256": digest}
        rows.append({"track_id": track_id, "relative_audio_path": f"{track_id}.wav"})
    manifest = tmp_path / "manifest.parquet"
    pd.DataFrame(rows).to_parquet(manifest, index=False)
    trials = {}
    for trial_id, split in (("opaque_train", "TRAIN"), ("opaque_validation", "VALIDATION"), ("opaque_test", "TEST")):
        trials[trial_id] = {
            "split": split,
            "query_id": 1,
            "candidate_a": 2,
            "candidate_b": 3,
            "query_identity": identities[1],
            "candidate_a_identity": identities[2],
            "candidate_b_identity": identities[3],
            # Deliberately sensitive values that must never reach sessions.
            "source_pair": "laion_clap__vs__mert_5120",
            "scores": {"laion_clap": {"query_a": 0.9}},
        }
    (reports / "trial_keys.json").write_text(json.dumps({"trials": trials}))
    return Stage2BStore(reports, manifest, audio_root)


def test_real_collection_bundle_hashes_validate_before_ratings():
    validate_collection_bundle(Path(__file__).parents[1])


def test_rater_normalization_and_nonempty_requirement(stage2b_store):
    assert normalize_rater_id("  ALICE\t Smith ") == "alice smith"
    with pytest.raises(RatingPolicyError, match="non-empty"):
        stage2b_store.build_session("   ")
    with pytest.raises(RatingPolicyError, match="non-empty"):
        stage2b_store.submit("opaque_train", "", "A")


def test_session_is_blinded_role_based_and_current_reviewer_safe(stage2b_store):
    session = stage2b_store.build_session("alice")
    blob = json.dumps(session)
    for forbidden in ("TRAIN", "laion_clap", "mert_5120", "query_id", "candidate_a", "score"):
        assert forbidden not in blob
    trial = next(row for row in session["trials"] if row["trial_id"] == "opaque_train")
    assert trial["query_audio"] == "/trial/opaque_train/query"
    assert trial["a_audio"] == "/trial/opaque_train/a"
    assert trial["needs_rating_by_current_reviewer"] is True


def test_train_validation_exact_agreement_closes_after_two(stage2b_store):
    stage2b_store.submit("opaque_train", "alice", "Tie", submitted_at=1)
    result = stage2b_store.submit("opaque_train", "bob", "Tie", submitted_at=2)
    assert result["another_judgment_required"] is False
    with pytest.raises(RatingPolicyError, match="closed"):
        stage2b_store.submit("opaque_train", "carol", "Tie", submitted_at=3)


def test_train_validation_disagreement_requires_exactly_third(stage2b_store):
    stage2b_store.submit("opaque_validation", "alice", "A", submitted_at=1)
    second = stage2b_store.submit("opaque_validation", "bob", "Neither", submitted_at=2)
    assert second["another_judgment_required"] is True
    third = stage2b_store.submit("opaque_validation", "carol", "B", submitted_at=3)
    assert third["aggregate_count"] == 3
    assert third["another_judgment_required"] is False
    with pytest.raises(RatingPolicyError):
        stage2b_store.submit("opaque_validation", "dave", "A", submitted_at=4)


def test_test_always_requires_three_distinct_raters(stage2b_store):
    one = stage2b_store.submit("opaque_test", "alice", "A", submitted_at=1)
    two = stage2b_store.submit("opaque_test", "bob", "A", submitted_at=2)
    three = stage2b_store.submit("opaque_test", "carol", "A", submitted_at=3)
    assert one["another_judgment_required"] is True
    assert two["another_judgment_required"] is True
    assert three["another_judgment_required"] is False


def test_self_correction_is_append_only_not_an_independent_rater(stage2b_store):
    first = stage2b_store.submit("opaque_train", "Alice", "A", submitted_at=1)
    second = stage2b_store.submit("opaque_train", " alice ", "Neither", submitted_at=2)
    frame = pd.read_csv(stage2b_store.ratings_path, dtype=str).fillna("")
    assert len(frame) == 2
    assert frame.iloc[1]["supersedes_event_id"] == first["event_id"]
    assert second["aggregate_count"] == 1
    session = stage2b_store.build_session("ALICE")
    trial = next(row for row in session["trials"] if row["trial_id"] == "opaque_train")
    assert trial["current_reviewer"]["choice"] == "Neither"
    assert trial["needs_rating_by_current_reviewer"] is False


def test_split_safe_exports_are_blinded_and_atomic(stage2b_store):
    stage2b_store.submit("opaque_train", "alice", "A", submitted_at=1)
    stage2b_store.submit("opaque_test", "bob", "B", submitted_at=2)
    train = pd.read_csv(stage2b_store.train_validation_path, dtype=str)
    test = pd.read_csv(stage2b_store.test_path, dtype=str)
    assert list(train["trial_id"]) == ["opaque_train"]
    assert list(test["trial_id"]) == ["opaque_test"]
    assert "split" not in train.columns and "source_pair" not in test.columns
    assert not list(stage2b_store.report_dir.glob("*.tmp"))


def test_import_preserves_tie_neither_and_audio_exact_bytes(stage2b_store):
    result = stage2b_store.import_rows([
        {"trial_id": "opaque_train", "rater_id": "a", "choice": "Tie", "submitted_at": 1},
        {"trial_id": "opaque_train", "rater_id": "b", "choice": "Neither", "submitted_at": 2},
    ])
    assert result == {"applied": 2}
    assert set(pd.read_csv(stage2b_store.ratings_path)["choice"]) == {"Tie", "Neither"}
    body, digest = stage2b_store.audio_bytes("opaque_train", "query")
    _, excerpt, _, _ = canonical_pcm(stage2b_store.audio_root / "1.wav")
    assert body == float32_le_bytes(excerpt)
    assert hashlib.sha256(body).hexdigest() == digest
