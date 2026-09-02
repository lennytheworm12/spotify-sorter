from __future__ import annotations

import csv
import json
import shutil
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from audio_similarity.cli.stage5b1b_challenge_review_server import (
    EXPORT_FILENAME,
    MODE,
    handler_for,
)
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b1b_challenge import (
    load_challenge_config,
    load_challenge_manifest,
)
from audio_similarity.stage5b1b_challenge_audit import REVIEW_COLUMNS
from audio_similarity.stage5b1b_challenge_review_store import (
    Stage5B1BChallengeReviewStore,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs" / "stage5b1b_fresh_challenge.json"


def request(base: str, path: str, method: str = "GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    value = urllib.request.Request(base + path, data=body, method=method)
    if payload is not None:
        value.add_header("Content-Type", "application/json")
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(value)


@pytest.fixture
def review_store(tmp_path):
    config = load_challenge_config(CONFIG)
    manifest = load_challenge_manifest(
        config.manifest_path,
        expected_sha256=config.manifest_sha256,
    )
    review = tmp_path / "review.csv"
    shutil.copyfile(config.artifacts["human_review"], review)
    return Stage5B1BChallengeReviewStore(
        manifest,
        config.artifacts["audit_queue"],
        review,
    )


@pytest.fixture
def review_server(review_store):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(review_store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join()
    server.server_close()


def test_session_is_blinded_and_matches_targeted_audit_accounting(review_store):
    session = review_store.session()
    assert session["mode"] == MODE
    assert session["manifest_sha256"] == (
        "e2e9a1ab43f568dd9de853c2964f341ee0d0e2631ca87f732d0d4326ab990f79"
    )
    assert session["export_filename"] == EXPORT_FILENAME
    assert session["progress"] == {
        "reviewed_candidates": 0,
        "remaining_candidates": 41,
        "total_candidates": 41,
        "completed_tracks": 0,
        "total_tracks": 28,
    }
    assert len(session["cases"]) == 28
    first = session["cases"][0]
    assert first["track"]["title"] == "Flowers"
    assert first["candidates"][0]["display_index"] == 1
    assert first["candidates"][0]["description"]
    assert set(first) == {"stable_track_id", "track", "track_note", "candidates"}
    assert set(first["candidates"][0]) == {
        "display_index",
        "video_id",
        "url",
        "title",
        "uploader",
        "channel",
        "duration_seconds",
        "view_count",
        "description",
        "review",
    }
    serialized = json.dumps(session).lower()
    for forbidden in (
        "selection_reason",
        "case_rationale",
        "search_rank",
        "source_type",
        "recording_eligible",
        "sol_label",
        "policy_rule",
    ):
        assert forbidden not in serialized


def test_submit_atomically_persists_label_and_verbatim_notes(review_store):
    first_case = review_store.session()["cases"][0]
    first = first_case["candidates"][0]
    saved = review_store.submit(
        first_case["stable_track_id"],
        first["video_id"],
        "acceptable",
        "  candidate note stays spaced  ",
        "track-wide observation",
    )
    assert saved["review"] == {
        "label": "ACCEPTABLE",
        "note": "  candidate note stays spaced  ",
    }
    with review_store.review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    track_rows = [
        row for row in rows if row["stable_track_id"] == first_case["stable_track_id"]
    ]
    assert track_rows[0]["candidate_review_label"] == "ACCEPTABLE"
    assert track_rows[0]["candidate_note"] == "  candidate note stays spaced  "
    assert {row["track_note"] for row in track_rows} == {"track-wide observation"}
    assert list(track_rows[0]) == REVIEW_COLUMNS
    assert review_store.session()["progress"]["reviewed_candidates"] == 1


def test_clear_label_concurrent_saves_and_validation(review_store):
    first_case = review_store.session()["cases"][0]
    candidates = first_case["candidates"][:2]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                review_store.submit,
                first_case["stable_track_id"],
                candidate["video_id"],
                label,
            )
            for candidate, label in zip(candidates, ("IDEAL", "WRONG"))
        ]
        [future.result() for future in futures]
    labels = [
        candidate["review"]["label"]
        for candidate in review_store.session()["cases"][0]["candidates"][:2]
    ]
    assert labels == ["IDEAL", "WRONG"]
    review_store.submit(
        first_case["stable_track_id"], candidates[0]["video_id"], "", "note only"
    )
    assert review_store.session()["cases"][0]["candidates"][0]["review"] == {
        "label": "",
        "note": "note only",
    }
    with pytest.raises(Stage5B1AValidationError, match="candidate label"):
        review_store.submit(
            first_case["stable_track_id"], candidates[0]["video_id"], "CORRECT"
        )
    with pytest.raises(Stage5B1AValidationError, match="unknown fresh-challenge candidate"):
        review_store.submit(first_case["stable_track_id"], "not-a-video", "IDEAL")


def test_http_site_loads_autosaves_and_exports(review_server):
    html = request(review_server, "/").read().decode()
    assert "Source safety desk" in html
    assert "Blinded source audit" in html
    assert "Show YouTube description" in html
    assert "Each choice saves immediately" in html
    assert "createElement(\"iframe\")" not in html
    assert json.loads(request(review_server, "/api/ping").read()) == {
        "ok": True,
        "mode": MODE,
    }
    session = json.loads(request(review_server, "/api/session").read())
    first_case = session["cases"][0]
    first = first_case["candidates"][0]
    saved = json.loads(
        request(
            review_server,
            "/api/review",
            "POST",
            {
                "stable_track_id": first_case["stable_track_id"],
                "video_id": first["video_id"],
                "label": "IDEAL",
                "candidate_note": "preferred clean source",
                "track_note": "reviewed against Spotify target",
            },
        ).read()
    )
    assert saved["ok"] is True
    exported = request(review_server, "/api/export")
    assert exported.headers["Content-Disposition"] == (
        f'attachment; filename="{EXPORT_FILENAME}"'
    )
    exported_rows = list(csv.DictReader(exported.read().decode().splitlines()))
    exported_first = next(
        row
        for row in exported_rows
        if row["stable_track_id"] == first_case["stable_track_id"]
        and row["candidate_video_id"] == first["video_id"]
    )
    assert exported_first["candidate_review_label"] == "IDEAL"
    assert exported_first["candidate_note"] == "preferred clean source"
    assert exported_first["track_note"] == "reviewed against Spotify target"


def test_http_rejects_cross_origin_and_unknown_candidates(review_server):
    session = json.loads(request(review_server, "/api/session").read())
    first_case = session["cases"][0]
    first = first_case["candidates"][0]
    payload = json.dumps(
        {
            "stable_track_id": first_case["stable_track_id"],
            "video_id": first["video_id"],
            "label": "IDEAL",
        }
    ).encode()
    value = urllib.request.Request(review_server + "/api/review", data=payload, method="POST")
    value.add_header("Content-Type", "application/json")
    value.add_header("Origin", "https://malicious.example")
    with pytest.raises(urllib.error.HTTPError) as rejected:
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(value)
    assert rejected.value.code == 400
    assert "cross-origin" in json.loads(rejected.value.read())["error"]

    with pytest.raises(urllib.error.HTTPError) as invalid:
        request(
            review_server,
            "/api/review",
            "POST",
            {
                "stable_track_id": first_case["stable_track_id"],
                "video_id": "bad",
                "label": "IDEAL",
            },
        )
    assert invalid.value.code == 400


def test_ui_flushes_note_saves_before_export_and_updates_visual_state(review_server):
    html = request(review_server, "/").read().decode()
    assert "flushPendingNotes();" in html
    assert "await Promise.all([...saveQueues.values()]);" in html
    assert "button.classList.toggle(\"selected\", selected);" in html
    assert "candidate._savedLabel = snapshot.label;\n    updateTrackCount(item);" in html
    assert "session.export_filename" in html
