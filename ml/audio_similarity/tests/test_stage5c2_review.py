from __future__ import annotations

import csv
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from audio_similarity.cli.stage5b1b_review_server import make_review_handler
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5c2_analysis import REVIEW_COLUMNS, canonical_pair_id
from audio_similarity.stage5c2_review import Stage5C2ReviewStore


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "evaluation/static/stage5c2_similarity_review.html"


def _write_review_fixture(tmp_path: Path) -> Stage5C2ReviewStore:
    tracks = [
        {"spotify_track_id": "A", "title": "Alpha", "artists": ["Artist A"]},
        {"spotify_track_id": "B", "title": "Beta", "artists": ["Artist B"]},
        {"spotify_track_id": "C", "title": "Gamma", "artists": ["Artist C"]},
    ]
    cases = []
    directions = [("A", "B"), ("A", "C"), ("B", "A"), ("B", "C"), ("C", "A")]
    by_id = {row["spotify_track_id"]: row for row in tracks}
    for query in tracks:
        neighbors = []
        for index, (left, right) in enumerate(
            [pair for pair in directions if pair[0] == query["spotify_track_id"]], start=1
        ):
            neighbors.append(
                by_id[right]
                | {
                    "rank": index,
                    "pair_id": canonical_pair_id(left, right),
                    "clap_similarity": 0.7,
                    "muq_similarity": 0.6,
                    "combined_similarity": 0.67,
                }
            )
        cases.append(query | {"stage5c2_track_id": f"stage5c2_{len(cases)+1:03d}", "album": "Album", "neighbors": neighbors})
    queue = {
        "schema_version": "stage5c2-similarity-review-queue-v1",
        "experiment_id": "stage5c2_representative_100",
        "status": "HUMAN_REVIEW_PENDING",
        "cases": cases,
    }
    queue_path = tmp_path / "review_queue.json"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    review_path = tmp_path / "human_similarity_review.csv"
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for left, right in directions:
            writer.writerow(
                {
                    "review_schema_version": "stage5c2-human-similarity-review-v1",
                    "pair_id": canonical_pair_id(left, right),
                    "query_spotify_id": left,
                    "neighbor_spotify_id": right,
                    "neighbor_rank": "1",
                    "clap_similarity": "0.7",
                    "muq_similarity": "0.6",
                    "combined_similarity": "0.67",
                    "human_label": "",
                    "human_note": "",
                    "review_timestamp": "",
                }
            )
    return Stage5C2ReviewStore(queue_path, review_path)


def _request(base: str, path: str, *, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(base + path, data=body, method="POST" if body else "GET")
    if body:
        request.add_header("Content-Type", "application/json")
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)


def test_canonical_unordered_pair_identity_is_direction_independent() -> None:
    assert canonical_pair_id("spotify-a", "spotify-b") == canonical_pair_id(
        "spotify-b", "spotify-a"
    )
    with pytest.raises(Stage5B1AValidationError):
        canonical_pair_id("same", "same")


def test_review_store_resumes_and_reuses_reciprocal_pair_label(tmp_path: Path) -> None:
    store = _write_review_fixture(tmp_path)
    before = store.session()
    assert before["status"] == "HUMAN_REVIEW_PENDING"
    saved = store.submit("A", "B", "2", "shared sonic relationship")
    assert saved["reciprocal_rows_updated"] == 2
    resumed = Stage5C2ReviewStore(store.queue_path, store.review_path).session()
    a_to_b = resumed["cases"][0]["neighbors"][0]
    b_to_a = resumed["cases"][1]["neighbors"][0]
    assert a_to_b["review"]["label"] == "2"
    assert b_to_a["review"]["label"] == "2"
    assert resumed["progress"]["reviewed_unique_pairs"] == 1


def test_review_store_rejects_invalid_labels_and_unknown_pairs(tmp_path: Path) -> None:
    store = _write_review_fixture(tmp_path)
    with pytest.raises(Stage5B1AValidationError, match="human label"):
        store.submit("A", "B", "IDEAL")
    with pytest.raises(Stage5B1AValidationError, match="unknown"):
        store.submit("A", "missing", "3")


def test_reused_http_workspace_serves_complete_queue_and_autosaves(tmp_path: Path) -> None:
    store = _write_review_fixture(tmp_path)
    handler = make_review_handler(
        store,
        static=STATIC,
        mode="stage5c2_similarity_review",
        export_filename="stage5c2-human-similarity-review.csv",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        html = _request(base, "/").read().decode()
        assert "Unified Similarity Review" in html
        assert 'id="previous"' in html and 'id="next"' in html
        assert 'id="jump"' in html and 'id="filter"' in html
        session = json.loads(_request(base, "/api/session").read())
        assert len(session["cases"]) == 3
        saved = json.loads(
            _request(
                base,
                "/api/review",
                payload={
                    "stable_track_id": "A",
                    "video_id": "B",
                    "label": "3",
                    "candidate_note": "very close",
                },
            ).read()
        )
        assert saved["ok"] is True
        assert saved["reciprocal_rows_updated"] == 2
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_existing_stage5b_review_static_remains_unchanged() -> None:
    existing = ROOT / "evaluation/static/stage5b1b_review.html"
    assert existing.is_file()
    assert "Recording cue sheet" in existing.read_text(encoding="utf-8")
