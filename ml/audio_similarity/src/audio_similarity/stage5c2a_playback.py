"""HTTP playback verification for the retained Stage 5C.2A corpus."""
from __future__ import annotations

import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .cli.stage5b1b_review_server import make_review_handler
from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c2_review import Stage5C2ReviewStore
from .stage5c2a_retention import (
    EXPERIMENT_ID,
    MEDIA_ROOT,
    REPORT_DIRECTORY,
    SOURCE_EXPERIMENT_ID,
    SOURCE_REPORT_DIRECTORY,
)


def validate_local_playback(project_root: str | Path) -> dict[str, Any]:
    """Exercise full and range responses against the real indexed corpus."""
    root = Path(project_root).resolve()
    source_report = root / SOURCE_REPORT_DIRECTORY
    store = Stage5C2ReviewStore(
        source_report / "review_queue.json",
        source_report / "human_similarity_review.csv",
        source_report / "selected_sources.json",
        root / MEDIA_ROOT / "index.json",
    )
    session = store.session()
    if len(session["cases"]) != 100 or any(
        case["playback"]["provider"] != "LOCAL_RESEARCH_AUDIO"
        for case in session["cases"]
    ):
        raise Stage5B1AValidationError("review session is not the amended local 100")
    ids = list(
        dict.fromkeys(
            (
                session["cases"][0]["spotify_track_id"],
                session["cases"][49]["spotify_track_id"],
                session["cases"][-1]["spotify_track_id"],
                "5quFr5s5PXYfUX5jV2EBZ1",
                "5l45vVLs4JKkhzN0tvkWJv",
            )
        )
    )
    handler = make_review_handler(store, mode="stage5c2_similarity_review")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def request(spotify_id: str, byte_range: str | None = None):
        req = urllib.request.Request(f"{base}/audio/track/{spotify_id}")
        if byte_range:
            req.add_header("Range", byte_range)
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(req, timeout=30)

    checks: list[dict[str, Any]] = []
    try:
        full_id = ids[0]
        full_source, _ = store.local_audio_for_request(full_id) or (None, None)
        if full_source is None:
            raise Stage5B1AValidationError("full-response playback source missing")
        with request(full_id) as response:
            full_body = response.read()
            full_ok = response.status == 200 and full_body == full_source.read_bytes()
        if not full_ok:
            raise Stage5B1AValidationError("ordinary full audio response failed")
        for spotify_id in ids:
            source, _content_type = store.local_audio_for_request(spotify_id) or (
                None,
                None,
            )
            if source is None:
                raise Stage5B1AValidationError("indexed playback source missing")
            size = source.stat().st_size
            ranges = {
                "beginning": "bytes=0-1023",
                "mid_song": f"bytes={size // 2}-{size // 2 + 1023}",
                "near_end": "bytes=-1024",
            }
            track_checks: dict[str, Any] = {
                "spotify_track_id": spotify_id,
                "source_sha256": file_sha256(source),
                "checks": {},
            }
            mid_body: bytes | None = None
            for label, requested in ranges.items():
                expected_start = {
                    "beginning": 0,
                    "mid_song": size // 2,
                    "near_end": size - 1024,
                }[label]
                with source.open("rb") as source_handle:
                    source_handle.seek(expected_start)
                    expected_body = source_handle.read(1024)
                with request(spotify_id, requested) as response:
                    body = response.read()
                    content_range = response.headers.get("Content-Range")
                    ok = (
                        response.status == 206
                        and response.headers.get("Accept-Ranges") == "bytes"
                        and bool(content_range and content_range.startswith("bytes "))
                        and len(body) == 1024
                        and body == expected_body
                    )
                if not ok:
                    raise Stage5B1AValidationError(
                        f"HTTP range validation failed: {spotify_id} {label}"
                    )
                track_checks["checks"][label] = {
                    "status": 206,
                    "requested_range": requested,
                    "content_range": content_range,
                    "bytes_received": len(body),
                }
                if label == "mid_song":
                    mid_body = body
            with request(spotify_id, ranges["mid_song"]) as response:
                repeated = response.read()
            track_checks["repeated_seek_identical"] = repeated == mid_body
            if repeated != mid_body:
                raise Stage5B1AValidationError(
                    f"repeated HTTP range changed bytes: {spotify_id}"
                )
            checks.append(track_checks)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    distinct = len({row["source_sha256"] for row in checks}) == len(checks)
    result = {
        "schema_version": "stage5c2a-playback-validation-v1",
        "experiment_id": EXPERIMENT_ID,
        "source_experiment_id": SOURCE_EXPERIMENT_ID,
        "review_query_count": len(session["cases"]),
        "review_directional_relationship_count": session["progress"]["raw_top5_rows"],
        "review_unique_pair_count": session["progress"]["total_unique_pairs"],
        "review_queue_sha256": file_sha256(source_report / "review_queue.json"),
        "ordinary_full_response": "PASS",
        "http_206_range_response": "PASS",
        "content_range": "PASS",
        "beginning_seek": "PASS",
        "mid_song_seek": "PASS",
        "near_end_seek": "PASS",
        "repeated_seek": "PASS",
        "query_neighbor_switching": "PASS" if distinct else "FAIL",
        "distinct_source_sha256": distinct,
        "browser_validation": "PENDING",
        "tracks": checks,
    }
    atomic_json(root / REPORT_DIRECTORY / "playback_validation.json", result)
    return result
