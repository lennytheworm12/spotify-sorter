from __future__ import annotations

import csv
import shutil
from pathlib import Path

from audio_similarity.stage5b1b_challenge import load_challenge_config, load_challenge_manifest
from audio_similarity.stage5b1e_queries import load_stage5b1e_config
from audio_similarity.stage5b1e_review import Stage5B1EReviewStore


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1e_natural_query_evaluation.json"
REPORT = ROOT / "reports/stage5b1e_natural_query_evaluation"


def store(tmp_path: Path) -> Stage5B1EReviewStore:
    config = load_stage5b1e_config(CONFIG)
    challenge = load_challenge_config(config.challenge_config_path)
    manifest = load_challenge_manifest(
        challenge.manifest_path, expected_sha256=challenge.manifest_sha256
    )
    queue = tmp_path / "queue.json"
    review = tmp_path / "review.csv"
    shutil.copyfile(REPORT / "human_audit_queue.json", queue)
    shutil.copyfile(REPORT / "human_review.csv", review)
    return Stage5B1EReviewStore(manifest, queue, review)


def test_session_is_blinded_and_has_exact_targeted_progress(tmp_path):
    session = store(tmp_path).session()
    assert session["progress"] == {
        "reviewed_candidates": 0,
        "remaining_candidates": 10,
        "total_candidates": 10,
        "completed_tracks": 0,
        "total_tracks": 9,
    }
    assert session["labels"] == ["IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"]
    serialized = str(session)
    assert "audit_reasons" not in serialized
    assert "strategy_ids" not in serialized
    assert all(candidate["url"].startswith("https://www.youtube.com/watch?v=") for case in session["cases"] for candidate in case["candidates"])


def test_label_and_notes_autosave_atomically(tmp_path):
    review_store = store(tmp_path)
    case = review_store.session()["cases"][0]
    candidate = case["candidates"][0]
    result = review_store.submit(
        case["stable_track_id"], candidate["video_id"], "acceptable",
        "candidate note", "track note",
    )
    assert result["review"]["label"] == "ACCEPTABLE"
    session = review_store.session()
    assert session["progress"]["reviewed_candidates"] == 1
    saved = next(
        item for item in session["cases"][0]["candidates"]
        if item["video_id"] == candidate["video_id"]
    )
    assert saved["review"] == {"label": "ACCEPTABLE", "note": "candidate note"}
    assert session["cases"][0]["track_note"] == "track note"
    with review_store.review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = next(item for item in rows if item["candidate_video_id"] == candidate["video_id"])
    assert row["candidate_review_label"] == "ACCEPTABLE"
    assert row["candidate_note"] == "candidate note"
