from __future__ import annotations

import csv
import json
import shutil
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib import request

from audio_similarity.cli.stage5b1b_review_server import make_review_handler
from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1i_artifacts import write_artifacts
from audio_similarity.stage5b1i_human_oracle import (
    AWAITING_REVIEW,
    COMPLETE,
    build_review_queue,
    evaluate_human_oracle,
    load_stage5b1i_config,
    replay_human_oracle_universe,
)
from audio_similarity.stage5b1i_review import (
    REVIEW_COLUMNS,
    build_review_rows,
    load_human_review,
)
from audio_similarity.stage5b1i_review_store import Stage5B1IReviewStore


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1i_human_oracle_tail.json"
REPORT = ROOT / "reports/stage5b1i_human_oracle_tail"
EXPECTED_IDS = [
    "s5b1c_021", "s5b1c_029", "s5b1c_030", "s5b1c_032",
    "s5b1c_033", "s5b1c_034", "s5b1c_040", "s5b1c_041",
]


def _universe():
    return replay_human_oracle_universe(load_stage5b1i_config(CONFIG))


def _all_wrong_rows() -> list[dict[str, str]]:
    rows = [{name: str(row[name]) for name in REVIEW_COLUMNS} for row in build_review_rows(_universe())]
    for row in rows:
        row["candidate_review_label"] = "WRONG"
    return rows


def test_frozen_stage5b1h_replay_derives_exact_unresolved_universe() -> None:
    before = file_sha256(
        ROOT / "reports/stage5b1h_canonical_source_semantics/source_semantics.json"
    )
    universe = _universe()
    assert universe["baseline"] == {
        "stage5b1h_auto_match_count": 42,
        "stage5b1h_match_uncertain_count": 8,
        "coverage": 0.84,
        "resolver_outputs_mutated": False,
    }
    assert [row["track"]["stable_track_id"] for row in universe["tracks"]] == EXPECTED_IDS
    assert universe["candidate_count"] == 25
    assert universe["tracks_with_candidates"] == 5
    assert universe["tracks_without_candidates"] == 3
    assert file_sha256(
        ROOT / "reports/stage5b1h_canonical_source_semantics/source_semantics.json"
    ) == before


def test_every_frozen_q0_candidate_is_present_once_and_zero_pools_are_explicit() -> None:
    universe = _universe()
    identities = [
        (row["track"]["stable_track_id"], candidate["candidate"]["video_id"])
        for row in universe["tracks"] for candidate in row["candidates"]
    ]
    assert len(identities) == len(set(identities)) == 25
    assert [
        row["track"]["stable_track_id"]
        for row in universe["tracks"] if not row["candidates"]
    ] == ["s5b1c_021", "s5b1c_032", "s5b1c_034"]
    queue = build_review_queue(universe)
    assert queue["track_count"] == 8
    assert queue["candidate_count"] == 25
    assert all(
        row["candidate_availability"] == (
            "AVAILABLE" if row["candidate_video_ids"] else "NO_Q0_CANDIDATES"
        )
        for row in queue["cases"]
    )


def test_review_rows_preserve_rank_raw_metadata_and_private_evidence() -> None:
    rows = build_review_rows(_universe())
    assert len(rows) == 25
    assert list(rows[0]) == REVIEW_COLUMNS
    assert [int(row["candidate_rank"]) for row in rows[:5]] == [1, 2, 3, 4, 5]
    assert all(row["candidate_url"].startswith("https://www.youtube.com/watch?v=") for row in rows)
    assert all("resolver" not in name and "source_semantics" not in name for name in REVIEW_COLUMNS)
    assert rows[0]["candidate_review_label"] == ""


def test_incomplete_review_defers_oracle_metrics() -> None:
    universe = _universe()
    rows = _all_wrong_rows()
    rows[-1]["candidate_review_label"] = ""
    documents = evaluate_human_oracle(universe, rows)
    assert all(document["status"] == AWAITING_REVIEW for document in documents)
    assert all(document["completed_candidate_judgments"] == 24 for document in documents)
    assert all("safe_recall_at_5" not in document for document in documents)


def test_oracle_recall_safe_definition_best_candidate_and_ceiling() -> None:
    universe = _universe()
    rows = _all_wrong_rows()
    rows[0]["candidate_review_label"] = "ACCEPTABLE"  # rank 1, track 029
    rows[5 + 2]["candidate_review_label"] = "IDEAL"  # rank 3, track 030
    rows[10 + 4]["candidate_review_label"] = "ACCEPTABLE"  # rank 5, track 033
    results, comparisons, gap, taxonomy, rules = evaluate_human_oracle(universe, rows)
    assert results["status"] == COMPLETE
    assert results["tail_metrics"] == {
        "denominator_tracks": 8,
        "safe_recall_at_1": 1 / 8,
        "safe_recall_at_3": 2 / 8,
        "safe_recall_at_5": 3 / 8,
        "tracks_with_at_least_one_safe_candidate": 3,
        "tracks_without_safe_candidate": 5,
    }
    assert results["human_oracle_top5_ceiling"]["ceiling_tracks"] == 45
    assert results["human_oracle_top5_ceiling"]["achieved_coverage_claimed"] is False
    assert len(comparisons["comparisons"]) == 3
    assert gap["safe_but_unselected_count"] == 3
    assert sum(taxonomy["category_counts"].values()) == 8
    assert all(row["production_rule_implemented"] is False for row in rules["hypotheses"])


def test_review_store_includes_all_tracks_autosaves_and_hides_decisions(tmp_path: Path) -> None:
    queue = tmp_path / "queue.json"
    review = tmp_path / "review.csv"
    shutil.copyfile(REPORT / "human_review_queue.json", queue)
    shutil.copyfile(REPORT / "human_review.csv", review)
    store = Stage5B1IReviewStore(queue, review, _universe())
    session = store.session()
    assert session["progress"] == {
        "reviewed_candidates": 0,
        "remaining_candidates": 25,
        "total_candidates": 25,
        "completed_tracks": 0,
        "reviewable_tracks": 5,
        "unavailable_tracks": 3,
        "total_tracks": 8,
    }
    assert len(session["cases"]) == 8
    assert session["cases"][0]["candidates"] == []
    assert "selected_video_id" not in str(session)
    assert "sol_evidence" not in str(session)

    case = next(row for row in session["cases"] if row["candidates"])
    candidate = case["candidates"][0]
    saved = store.submit(
        case["stable_track_id"], candidate["video_id"], "ideal",
        "verbatim candidate reason", "verbatim track reason",
    )
    assert saved["review"]["label"] == "IDEAL"
    updated = store.session()
    assert updated["progress"]["reviewed_candidates"] == 1
    with review.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["candidate_note"] == "verbatim candidate reason"
    assert row["track_note"] == "verbatim track reason"


def test_shared_frontend_supports_oracle_mode_zero_results_and_post_label_reveal() -> None:
    html = (ROOT / "evaluation/static/stage5b1b_review.html").read_text(encoding="utf-8")
    assert "stage5b1i_human_oracle_tail" in html
    assert "Audit the complete Q0 pool" in html
    assert "Reveal frozen resolver evidence (label saved)" in html
    assert "details.hidden = !candidate.review.label" in html
    assert "No frozen candidates are available" in html


def test_http_session_autosave_and_export_round_trip(tmp_path: Path) -> None:
    queue = tmp_path / "queue.json"
    review = tmp_path / "review.csv"
    shutil.copyfile(REPORT / "human_review_queue.json", queue)
    shutil.copyfile(REPORT / "human_review.csv", review)
    store = Stage5B1IReviewStore(queue, review, _universe())
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_review_handler(
            store,
            mode="stage5b1i_human_oracle_tail",
            export_filename="stage5b1i-human-oracle-tail-review.csv",
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        session = json.loads(request.urlopen(f"{base}/api/session").read())
        case = next(row for row in session["cases"] if row["candidates"])
        candidate = case["candidates"][0]
        payload = json.dumps({
            "stable_track_id": case["stable_track_id"],
            "video_id": candidate["video_id"],
            "label": "IDEAL",
            "candidate_note": "browser round trip",
            "track_note": "track round trip",
        }).encode()
        save = request.Request(
            f"{base}/api/review",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        assert json.loads(request.urlopen(save).read())["ok"] is True
        exported = request.urlopen(f"{base}/api/export")
        assert "stage5b1i-human-oracle-tail-review.csv" in exported.headers[
            "Content-Disposition"
        ]
        assert b"browser round trip" in exported.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_committed_artifacts_are_awaiting_review_and_hash_bound() -> None:
    config = load_stage5b1i_config(CONFIG)
    manifest = json.loads(config.artifacts["manifest"].read_text(encoding="utf-8"))
    assert manifest["status"] == AWAITING_REVIEW
    assert manifest["scope_guards"]["stage5b1h_auto_match_count"] == 42
    assert manifest["scope_guards"]["production_resolver_mutated"] is False
    for item in manifest["frozen_inputs"].values():
        assert file_sha256(config.project_root / item["path"]) == item["sha256"]
    for name, item in manifest["artifacts"].items():
        assert file_sha256(config.project_root / item["path"]) == item["sha256"], name


def test_artifact_writer_is_idempotent_before_review() -> None:
    config = load_stage5b1i_config(CONFIG)
    before = file_sha256(config.artifacts["human_review"])
    first = write_artifacts(config)
    second = write_artifacts(config)
    assert first["status"] == second["status"] == AWAITING_REVIEW
    assert file_sha256(config.artifacts["human_review"]) == before
    assert load_human_review(config.artifacts["human_review"])[0]["candidate_review_label"] == ""
