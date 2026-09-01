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

from audio_similarity.cli.stage5b1b_review_server import make_review_handler
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b1b_artifacts import REVIEW_COLUMNS
from audio_similarity.stage5b1b_config import load_stage5b1b_config
from audio_similarity.stage5b1b_manifest import load_heldout_manifest
from audio_similarity.stage5b1b_review_store import Stage5B1BReviewStore


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs" / "stage5b1b.json"


def request(base: str, path: str, method: str = "GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    value = urllib.request.Request(base + path, data=body, method=method)
    if payload is not None:
        value.add_header("Content-Type", "application/json")
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(value)


@pytest.fixture
def review_store(tmp_path):
    config = load_stage5b1b_config(CONFIG)
    manifest = load_heldout_manifest(
        config.heldout_manifest_path, expected_sha256=config.heldout_manifest_sha256
    )
    review = tmp_path / "review.csv"
    shutil.copyfile(config.artifacts["heldout_review"], review)
    with review.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["candidate_review_label"] = ""
        row["candidate_note"] = ""
        row["track_note"] = ""
    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return Stage5B1BReviewStore(manifest, review)


@pytest.fixture
def review_server(review_store):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_review_handler(review_store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join()
    server.server_close()


def test_session_groups_248_candidates_under_50_frozen_targets(review_store):
    session = review_store.session()
    assert session["mode"] == "stage5b1b_heldout_candidate_review"
    assert session["manifest_sha256"] == "39557ede8f07bde129ad23d2bc64a0faf0fff755356cd87f2054e14f91d81e5a"
    assert session["progress"] == {
        "reviewed_candidates": 0,
        "remaining_candidates": 248,
        "total_candidates": 248,
        "completed_tracks": 0,
        "total_tracks": 50,
    }
    assert len(session["cases"]) == 50
    first = session["cases"][0]
    assert first["track"]["title"] == "Blinding Lights"
    assert len(first["candidates"]) == 5
    assert first["candidates"][0]["rank"] == 1
    assert first["candidates"][0]["view_count"] is not None
    serialized = json.dumps(session)
    assert '"url"' not in serialized
    assert "title_similarity" not in serialized
    assert "recording_eligible" not in serialized
    assert "version_relationships" not in serialized


def test_targeted_case_filter_limits_session_but_keeps_authoritative_store(tmp_path):
    config = load_stage5b1b_config(CONFIG)
    manifest = load_heldout_manifest(
        config.heldout_manifest_path,
        expected_sha256=config.heldout_manifest_sha256,
    )
    review = tmp_path / "review.csv"
    shutil.copyfile(config.artifacts["heldout_review"], review)
    selected = manifest.stable_track_ids[:2]
    with review.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    first_candidates = tuple(
        row["candidate_video_id"]
        for row in rows
        if row["stable_track_id"] == selected[0]
    )[:2]
    second_candidates = tuple(
        row["candidate_video_id"]
        for row in rows
        if row["stable_track_id"] == selected[1]
    )[:1]
    candidate_filter = {
        selected[0]: first_candidates,
        selected[1]: second_candidates,
    }
    store = Stage5B1BReviewStore(
        manifest,
        review,
        case_filter=selected,
        candidate_filter=candidate_filter,
    )
    session = store.session()
    assert session["mode"] == "stage5b1b_targeted_sol_audit"
    assert [case["stable_track_id"] for case in session["cases"]] == list(selected)
    assert session["progress"]["total_tracks"] == 2
    assert session["progress"]["total_candidates"] == 3

    with pytest.raises(Stage5B1AValidationError, match="case filter"):
        Stage5B1BReviewStore(manifest, review, case_filter=("missing",))


def test_submit_atomically_persists_candidate_label_and_verbatim_notes(review_store):
    first = review_store.session()["cases"][0]["candidates"][0]
    saved = review_store.submit(
        "s5b1b_001",
        first["video_id"],
        "ideal",
        "  candidate note stays spaced  ",
        "track-wide observation",
    )
    assert saved["review"] == {
        "label": "IDEAL",
        "note": "  candidate note stays spaced  ",
    }
    with review_store.review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    track_rows = [row for row in rows if row["stable_track_id"] == "s5b1b_001"]
    assert track_rows[0]["candidate_review_label"] == "IDEAL"
    assert track_rows[0]["candidate_note"] == "  candidate note stays spaced  "
    assert {row["track_note"] for row in track_rows} == {"track-wide observation"}
    assert track_rows[0]["candidate_title"] == first["title"]
    assert list(track_rows[0]) == REVIEW_COLUMNS
    assert review_store.session()["progress"]["reviewed_candidates"] == 1


def test_clear_label_and_note_only_autosave_are_supported(review_store):
    first = review_store.session()["cases"][0]["candidates"][0]
    review_store.submit("s5b1b_001", first["video_id"], "WRONG")
    review_store.submit("s5b1b_001", first["video_id"], "", "note without a label")
    candidate = review_store.session()["cases"][0]["candidates"][0]
    assert candidate["review"] == {"label": "", "note": "note without a label"}


def test_concurrent_candidate_saves_preserve_both_rows(review_store):
    candidates = review_store.session()["cases"][0]["candidates"][:2]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                review_store.submit,
                "s5b1b_001",
                candidate["video_id"],
                label,
            )
            for candidate, label in zip(candidates, ("IDEAL", "ACCEPTABLE"))
        ]
        [future.result() for future in futures]
    labels = [
        candidate["review"]["label"]
        for candidate in review_store.session()["cases"][0]["candidates"][:2]
    ]
    assert labels == ["IDEAL", "ACCEPTABLE"]


@pytest.mark.parametrize("label", ["CORRECT", "NOT_IN_TOP_5", "1"])
def test_submit_rejects_old_or_unknown_label_schemas(review_store, label):
    first = review_store.session()["cases"][0]["candidates"][0]
    with pytest.raises(Stage5B1AValidationError, match="candidate label"):
        review_store.submit("s5b1b_001", first["video_id"], label)


def test_submit_rejects_unknown_identity_and_oversized_notes(review_store):
    first = review_store.session()["cases"][0]["candidates"][0]
    with pytest.raises(Stage5B1AValidationError, match="unknown candidate"):
        review_store.submit("s5b1b_001", "not-a-video", "IDEAL")
    with pytest.raises(Stage5B1AValidationError, match="must not exceed"):
        review_store.submit("s5b1b_001", first["video_id"], "IDEAL", "x" * 2001)


def test_http_site_loads_autosaves_and_exports(review_server):
    html = request(review_server, "/").read().decode()
    assert "Recording cue sheet" in html
    assert "Label every candidate" in html
    assert "Each choice saves immediately" in html
    assert "Open YouTube" in html
    assert "createElement(\"iframe\")" not in html
    assert json.loads(request(review_server, "/api/ping").read()) == {
        "ok": True,
        "mode": "stage5b1b_heldout_candidate_review",
    }
    session = json.loads(request(review_server, "/api/session").read())
    first = session["cases"][0]["candidates"][0]
    saved = json.loads(
        request(
            review_server,
            "/api/review",
            "POST",
            {
                "stable_track_id": "s5b1b_001",
                "video_id": first["video_id"],
                "label": "ACCEPTABLE",
                "candidate_note": "safe source",
                "track_note": "multiple candidates may be usable",
            },
        ).read()
    )
    assert saved["ok"] is True
    exported = request(review_server, "/api/export")
    assert exported.headers["Content-Disposition"] == (
        'attachment; filename="stage5b1b-heldout-review.csv"'
    )
    exported_rows = list(csv.DictReader(exported.read().decode().splitlines()))
    exported_first = next(
        row
        for row in exported_rows
        if row["stable_track_id"] == "s5b1b_001"
        and row["candidate_video_id"] == first["video_id"]
    )
    assert exported_first["candidate_review_label"] == "ACCEPTABLE"
    assert exported_first["candidate_note"] == "safe source"
    assert exported_first["track_note"] == "multiple candidates may be usable"


def test_export_ui_flushes_debounced_notes_before_download(review_server):
    html = request(review_server, "/").read().decode()
    assert 'id="export"' in html
    assert "async function exportReview(event)" in html
    assert "flushPendingNotes();" in html
    assert "await Promise.all([...saveQueues.values()]);" in html
    assert "Export blocked" in html


def test_per_track_saved_counter_updates_after_autosave(review_server):
    html = request(review_server, "/").read().decode()
    assert 'trackCount.id = "track-count"' in html
    assert "function updateTrackCount(item)" in html
    assert "candidate._savedLabel = snapshot.label;\n    updateTrackCount(item);" in html


def test_http_errors_are_bounded_json(review_server):
    with pytest.raises(urllib.error.HTTPError) as missing:
        request(review_server, "/missing")
    assert missing.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as invalid:
        request(
            review_server,
            "/api/review",
            "POST",
            {"stable_track_id": "s5b1b_001", "video_id": "bad", "label": "IDEAL"},
        )
    assert invalid.value.code == 400
    assert "unknown candidate" in json.loads(invalid.value.read())["error"]


def test_http_rejects_cross_origin_autosave(review_server):
    session = json.loads(request(review_server, "/api/session").read())
    first = session["cases"][0]["candidates"][0]
    payload = json.dumps(
        {
            "stable_track_id": "s5b1b_001",
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
