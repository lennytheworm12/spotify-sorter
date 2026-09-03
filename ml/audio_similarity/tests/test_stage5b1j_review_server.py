from __future__ import annotations

from pathlib import Path

from audio_similarity.stage5b1b_challenge import load_challenge_config, load_challenge_manifest
from audio_similarity.stage5b1j_representation_rediscovery import load_stage5b1j_config
from audio_similarity.stage5b1j_review_store import Stage5B1JReviewStore


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1j_representation_fallback.json"


def _store() -> Stage5B1JReviewStore:
    config = load_stage5b1j_config(CONFIG)
    challenge = load_challenge_config(config.challenge_config)
    manifest = load_challenge_manifest(
        challenge.manifest_path, expected_sha256=challenge.manifest_sha256
    )
    return Stage5B1JReviewStore(
        manifest,
        config.artifacts["audit_queue"],
        config.artifacts["human_review"],
    )


def test_fallback_review_session_exposes_product_semantics() -> None:
    session = _store().session()
    assert session["mode"] == "stage5b1j_representation_fallback_review"
    assert session["export_filename"] == (
        "stage5b1j-representation-fallback-human-review.csv"
    )
    assert session["progress"]["total_tracks"] == 1
    assert session["progress"]["total_candidates"] == 1
    modes = {case["fallback"]["match_mode"] for case in session["cases"]}
    assert modes == {"REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK"}
    assert all(case["fallback"]["not_exact_recording"] for case in session["cases"])
    assert all(len(case["candidates"]) == 1 for case in session["cases"])
