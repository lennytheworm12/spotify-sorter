from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from audio_similarity.cli.stage2b_eval_server import make_stage2b_handler
from tests.test_stage2b_store import stage2b_store  # noqa: F401 - shared fixture


def request(base: str, path: str, method: str = "GET", payload=None, headers=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(request)


@pytest.fixture
def stage2b_server(stage2b_store):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_stage2b_handler(stage2b_store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join()


def test_index_ping_session_and_payload_blinding(stage2b_server):
    assert b"Overall song similarity" in request(stage2b_server, "/").read()
    assert json.loads(request(stage2b_server, "/api/ping").read()) == {"ok": True, "mode": "stage2b"}
    payload = json.loads(request(stage2b_server, "/api/session?rater_id=Alice").read())
    blob = json.dumps(payload)
    assert payload["rater_id"] == "alice"
    assert "laion_clap" not in blob and "TRAIN" not in blob and "query_id" not in blob


def test_empty_rater_and_unknown_audio_errors(stage2b_server):
    with pytest.raises(urllib.error.HTTPError) as empty:
        request(stage2b_server, "/api/session?rater_id=%20")
    assert empty.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as missing:
        request(stage2b_server, "/trial/nope/query")
    assert missing.value.code == 404


def test_exact_pcm_headers_range_and_invalid_range(stage2b_server):
    full = request(stage2b_server, "/trial/opaque_train/query")
    body = full.read()
    assert full.status == 200 and len(body) == 120000 * 4
    assert full.headers["X-Audio-Sample-Rate"] == "24000"
    assert full.headers["X-Audio-Sample-Format"] == "float32le"
    assert full.headers["X-Audio-Sample-Count"] == "120000"
    partial = request(stage2b_server, "/trial/opaque_train/query", headers={"Range": "bytes=4-19"})
    assert partial.status == 206 and partial.read() == body[4:20]
    with pytest.raises(urllib.error.HTTPError) as invalid:
        request(stage2b_server, "/trial/opaque_train/query", headers={"Range": "bytes=999999-1000000"})
    assert invalid.value.code == 416


def test_rating_autosave_resume_and_exports(stage2b_server):
    saved = json.loads(request(stage2b_server, "/api/rate", "POST", {
        "trial_id": "opaque_train", "rater_id": "Alice", "choice": "A", "note": "blinded note",
    }).read())
    assert saved["ok"] is True
    session = json.loads(request(stage2b_server, "/api/session?rater_id=alice").read())
    trial = next(row for row in session["trials"] if row["trial_id"] == "opaque_train")
    assert trial["current_reviewer"] == {"choice": "A", "note": "blinded note"}
    assert trial["needs_rating_by_current_reviewer"] is False
    export = request(stage2b_server, "/api/export/train-validation")
    assert b"opaque_train" in export.read()


def test_import_route_and_old_stage1_routes_absent(stage2b_server):
    payload = {"ratings": [{
        "trial_id": "opaque_validation", "rater_id": "bob", "choice": "Tie", "submitted_at": 1,
    }]}
    imported = json.loads(request(stage2b_server, "/api/import", "POST", payload).read())
    assert imported == {"ok": True, "applied": 1}
    with pytest.raises(urllib.error.HTTPError) as old:
        request(stage2b_server, "/audio/track/1")
    assert old.value.code == 404
