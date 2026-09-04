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
from audio_similarity.stage5b1a_models import file_sha256
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
    sources_path = tmp_path / "selected_sources.json"
    sources_path.write_text(
        json.dumps(
            {
                "schema_version": "stage5c2-selected-sources-v1",
                "tracks": [
                    {
                        "spotify_track_id": row["spotify_track_id"],
                        "selected_youtube_video_id": f"video{index:06d}",
                    }
                    for index, row in enumerate(tracks, start=1)
                ],
            }
        ),
        encoding="utf-8",
    )
    return Stage5C2ReviewStore(queue_path, review_path, sources_path)


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
    resumed = Stage5C2ReviewStore(
        store.queue_path,
        store.review_path,
        tmp_path / "selected_sources.json",
    ).session()
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


def test_review_session_uses_frozen_sources_for_full_and_segment_playback(
    tmp_path: Path,
) -> None:
    session = _write_review_fixture(tmp_path).session()
    query = session["cases"][0]
    neighbor = query["neighbors"][0]
    assert query["playback"] == {
        "provider": "YOUTUBE_FROZEN_SELECTED_SOURCE",
        "youtube_video_id": "video000001",
        "watch_url": "https://www.youtube.com/watch?v=video000001",
        "segment_windows": [
            {"index": 1, "start_seconds": 2.5, "end_seconds": 7.5},
            {"index": 2, "start_seconds": 12.5, "end_seconds": 17.5},
            {"index": 3, "start_seconds": 22.5, "end_seconds": 27.5},
        ],
    }
    assert neighbor["playback"]["youtube_video_id"] == "video000002"


def test_reused_http_workspace_serves_complete_queue_and_autosaves(tmp_path: Path) -> None:
    store = _write_review_fixture(tmp_path)
    handler = make_review_handler(
        store,
        static=STATIC,
        mode="stage5c2_similarity_review",
        export_filename="stage5c2-human-similarity-review.csv",
        frame_sources=("https://www.youtube-nocookie.com",),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        html_response = _request(base, "/")
        html = html_response.read().decode()
        assert "Unified Similarity Review" in html
        assert "Full song" in html and "segment_windows" in html
        assert 'id="local-player"' in html
        assert "LOCAL_RESEARCH_AUDIO" in html
        assert 'id="previous"' in html and 'id="next"' in html
        assert 'id="jump"' in html and 'id="filter"' in html
        assert (
            "frame-src https://www.youtube-nocookie.com"
            in html_response.headers["Content-Security-Policy"]
        )
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


def test_local_audio_index_drives_range_playback_and_seek(tmp_path: Path) -> None:
    base_store = _write_review_fixture(tmp_path)
    selected_path = tmp_path / "selected_sources.json"
    tracks = {}
    for spotify_id, video_id in (
        ("A", "video000001"),
        ("B", "video000002"),
        ("C", "video000003"),
    ):
        directory = tmp_path / "media" / spotify_id
        directory.mkdir(parents=True)
        source = directory / "source.webm"
        source.write_bytes((spotify_id.encode() * 4000)[:8192])
        tracks[spotify_id] = {
            "spotify_track_id": spotify_id,
            "youtube_video_id": video_id,
            "retained_relative_path": f"{spotify_id}/source.webm",
            "file_size_bytes": source.stat().st_size,
            "source_sha256": file_sha256(source),
            "content_type": "audio/webm",
        }
    index_path = tmp_path / "media" / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_version": "stage5c2a-local-research-audio-index-v1",
                "selected_sources_sha256": file_sha256(selected_path),
                "tracks": tracks,
            }
        ),
        encoding="utf-8",
    )
    store = Stage5C2ReviewStore(
        base_store.queue_path,
        base_store.review_path,
        selected_path,
        index_path,
    )
    session = store.session()
    assert session["cases"][0]["playback"]["provider"] == "LOCAL_RESEARCH_AUDIO"
    assert session["cases"][0]["playback"]["audio_url"] == "/audio/track/A"
    handler = make_review_handler(store, static=STATIC)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        full = _request(base, "/audio/track/A")
        assert full.status == 200
        assert full.headers["Accept-Ranges"] == "bytes"
        request = urllib.request.Request(base + "/audio/track/A")
        request.add_header("Range", "bytes=100-199")
        partial = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(request)
        assert partial.status == 206
        assert partial.headers["Content-Range"].startswith("bytes 100-199/")
        assert len(partial.read()) == 100
        near_end = urllib.request.Request(base + "/audio/track/A")
        near_end.add_header("Range", "bytes=-64")
        response = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(near_end)
        assert response.status == 206
        assert len(response.read()) == 64
        distinct = _request(base, "/audio/track/B").read()
        assert distinct != _request(base, "/audio/track/A").read()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_existing_stage5b_review_static_remains_unchanged() -> None:
    existing = ROOT / "evaluation/static/stage5b1b_review.html"
    assert existing.is_file()
    assert "Recording cue sheet" in existing.read_text(encoding="utf-8")
