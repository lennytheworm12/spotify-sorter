from __future__ import annotations

import csv
import json
import shutil
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from audio_similarity.cli.stage5b1a2_review_server import make_review_handler
from audio_similarity.stage5b1a2_config import load_ytdlp_config
from audio_similarity.stage5b1a2_experiment import load_ytdlp_results
from audio_similarity.stage5b1a2_review import REVIEW_COLUMNS
from audio_similarity.stage5b1a2_review_store import Stage5B1A2ReviewStore
from audio_similarity.stage5b1a_models import Stage5B1AValidationError, load_frozen_manifest


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs" / "stage5b1a2_ytdlp.json"


def request(base: str, path: str, method: str = "GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    value = urllib.request.Request(base + path, data=body, method=method)
    if payload is not None:
        value.add_header("Content-Type", "application/json")
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(value)


@pytest.fixture
def review_store(tmp_path):
    config = load_ytdlp_config(CONFIG)
    manifest = load_frozen_manifest(config.manifest_path, expected_sha256=config.manifest_sha256)
    results = load_ytdlp_results(config.artifacts["discovery_results"], manifest, config)
    review = tmp_path / "review.csv"
    shutil.copyfile(config.artifacts["review"], review)
    with review.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["review_label"] = ""
        row["optional_note"] = ""
    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return Stage5B1A2ReviewStore(manifest, results, review)


@pytest.fixture
def review_server(review_store):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_review_handler(review_store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join()
    server.server_close()


def test_session_exposes_frozen_cases_and_only_review_safe_candidate_metadata(review_store):
    session = review_store.session()
    assert session["mode"] == "stage5b1a2_ytdlp_human_review"
    assert session["manifest_sha256"] == "f3592bb8c8dea689959a22da222d8b7ce4911c1804392acb501cffe768700c57"
    assert session["progress"] == {"reviewed": 0, "remaining": 25, "total": 25}
    assert len(session["cases"]) == 25
    first = session["cases"][0]
    assert first["track"]["title"] == "Hello"
    assert first["candidates"][0]["youtube_video_id"] == "YQHsXMglC9A"
    assert first["candidates"][0]["duration_seconds"] == 367.0
    assert "raw_source" not in json.dumps(session)


def test_submit_atomically_persists_only_label_and_note(review_store):
    before = review_store.review_path.read_text(encoding="utf-8")
    saved = review_store.submit("s5b1a_001", "1", "Official upload matches the expected recording.")
    assert saved["review"] == {
        "label": "1",
        "note": "Official upload matches the expected recording.",
    }
    with review_store.review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["review_label"] == "1"
    assert rows[0]["optional_note"] == "Official upload matches the expected recording."
    assert rows[0]["candidate_1_title"] == "Adele - Hello (Official Music Video)"
    assert list(rows[0]) == REVIEW_COLUMNS
    assert before.splitlines()[0] == review_store.review_path.read_text(encoding="utf-8").splitlines()[0]
    assert review_store.session()["progress"] == {"reviewed": 1, "remaining": 24, "total": 25}


@pytest.mark.parametrize("label", ["", "6", "CORRECT", "NOT_IN_TOP_K"])
def test_submit_rejects_non_ui_labels(review_store, label):
    with pytest.raises(Stage5B1AValidationError, match="review label"):
        review_store.submit("s5b1a_001", label)


def test_submit_rejects_unknown_track_and_long_note(review_store):
    with pytest.raises(Stage5B1AValidationError, match="unknown"):
        review_store.submit("not-a-track", "1")
    with pytest.raises(Stage5B1AValidationError, match="exceeds"):
        review_store.submit("s5b1a_001", "UNCERTAIN", "x" * 2001)


def test_http_site_ping_session_save_and_export(review_server):
    html = request(review_server, "/").read().decode()
    assert "Recording match review" in html
    assert "Watch on YouTube" in html
    assert "youtube.com/watch?v=" in html
    assert 'createElement("iframe")' not in html
    assert "does not download media" in html
    assert json.loads(request(review_server, "/api/ping").read()) == {
        "ok": True,
        "mode": "stage5b1a2_ytdlp_human_review",
    }
    session = json.loads(request(review_server, "/api/session").read())
    assert session["progress"]["total"] == 25
    saved = json.loads(
        request(
            review_server,
            "/api/review",
            "POST",
            {"stable_track_id": "s5b1a_025", "label": "NOT_IN_TOP_5", "note": "No match"},
        ).read()
    )
    assert saved["ok"] is True
    exported = request(review_server, "/api/export")
    assert exported.headers["Content-Disposition"] == 'attachment; filename="stage5b1a2-ytdlp-review.csv"'
    assert b"NOT_IN_TOP_5" in exported.read()


def test_http_errors_are_bounded_and_json(review_server):
    with pytest.raises(urllib.error.HTTPError) as missing:
        request(review_server, "/missing")
    assert missing.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as invalid:
        request(review_server, "/api/review", "POST", {"stable_track_id": "s5b1a_001", "label": "6"})
    assert invalid.value.code == 400
    assert "review label" in json.loads(invalid.value.read())["error"]
