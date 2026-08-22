"""End-to-end HTTP tests for the evaluator server (no heavy models)."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from audio_similarity.cli.eval_server import make_handler
from audio_similarity.eval_store import SheetStore
from tests.helpers import save_wav, synth_waveform
import pandas as pd


@pytest.fixture
def server(tmp_path: Path):
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    audio_root = tmp_path / "audio"
    sub = audio_root / "001"
    sub.mkdir(parents=True)
    wav_path = save_wav(sub / "000001.wav", synth_waveform(0.5), 24000)

    manifest = pd.DataFrame(
        [
            {"track_id": 1, "relative_audio_path": "001/000001.wav", "title": "q",
             "artist": "qa", "top_genre": "g", "decode_status": "SUCCESS"}
        ]
    )
    manifest_path = tmp_path / "manifest.parquet"
    manifest.to_parquet(manifest_path, index=False)

    factor = pd.DataFrame(
        [{"cell_id": "1:melody:1", "query_track_id": 1, "target_factor": "melody",
          "neighbor_rank": 1, "rating": "", "neighbor_title": "n", "neighbor_artist": "na"}]
    )
    factor.to_csv(sheets / "judgments_factor.csv", index=False)
    pd.DataFrame(
        [{"cell_id": "1:melody:1", "representation": "merit_melody", "neighbor_track_id": 1}]
    ).to_csv(sheets / "key_factor.csv", index=False)
    ab = pd.DataFrame(
        [{"ab_id": "1:melody:1", "question": "q", "a_title": "a", "a_artist": "x",
          "b_title": "b", "b_artist": "y", "choice": ""}]
    )
    ab.to_csv(sheets / "judgments_ab.csv", index=False)
    pd.DataFrame(
        [{"ab_id": "1:melody:1", "a_representation": "m", "b_representation": "g",
          "a_track_id": 1, "b_track_id": 1}]
    ).to_csv(sheets / "key_ab.csv", index=False)

    store = SheetStore(sheets, manifest_path, audio_root)
    from http.server import ThreadingHTTPServer

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, wav_path
    httpd.shutdown()


def get(base: str, path: str, headers: dict | None = None):
    request = urllib.request.Request(base + path, headers=headers or {})
    return urllib.request.urlopen(request)


def post(base: str, path: str, payload: dict):
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        base + path, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    return urllib.request.urlopen(request)


def test_index_served(server):
    base, _ = server
    response = get(base, "/")
    assert response.status == 200
    assert b"Listening Test" in response.read()


def test_session_endpoint(server):
    base, _ = server
    payload = json.loads(get(base, "/api/session").read())
    assert len(payload["factor_cells"]) == 1
    assert payload["progress"]["factor_total"] == 1


def test_rating_via_http_persists(server):
    base, _ = server
    response = post(base, "/api/rate", {"cell_id": "1:melody:1", "rating": "3"})
    assert response.status == 200
    session = json.loads(get(base, "/api/session").read())
    assert session["progress"]["factor_rated"] == 1


def test_invalid_rating_rejected(server):
    base, _ = server
    try:
        post(base, "/api/rate", {"cell_id": "1:melody:1", "rating": "7"})
        raised = False
    except urllib.error.HTTPError as exc:
        raised = exc.code == 400
    assert raised


def test_audio_streaming_with_range(server):
    base, wav_path = server
    size = wav_path.stat().st_size

    full = get(base, "/audio/track/1")
    assert full.status == 200
    assert int(full.headers["Content-Length"]) == size
    assert full.headers["Accept-Ranges"] == "bytes"

    partial = get(base, "/audio/track/1", {"Range": f"bytes=10-{min(99, size - 1)}"})
    assert partial.status == 206
    data = partial.read()
    assert len(data) == min(100, size) - 10
    with open(wav_path, "rb") as fh:
        fh.seek(10)
        assert data == fh.read(len(data))


def test_unknown_audio_404(server):
    base, _ = server
    try:
        get(base, "/audio/track/999")
        raised = False
    except urllib.error.HTTPError as exc:
        raised = exc.code == 404
    assert raised


def post_raw(base: str, path: str, payload: dict, headers: dict | None = None):
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        base + path, data=body,
        headers={"Content-Type": "application/json", **(headers or {})}, method="POST",
    )
    return urllib.request.urlopen(request)


def test_ping_and_cors_headers(server):
    base, _ = server
    response = get(base, "/api/ping")
    assert json.loads(response.read())["mode"] == "server"
    assert response.headers["Access-Control-Allow-Origin"] == "*"

    # preflight from a cross-origin Pages UI
    req = urllib.request.Request(base + "/api/rate", method="OPTIONS")
    pre = urllib.request.urlopen(req)
    assert pre.status == 204
    assert "POST" in pre.headers["Access-Control-Allow-Methods"]


def test_note_via_http(server):
    base, _ = server
    response = post_raw(base, "/api/note", {"kind": "factor", "id": "1:melody:1", "note": "ambiguous clip"})
    assert response.status == 200
    session = json.loads(get(base, "/api/session").read())
    assert session["factor_cells"][0]["note"] == "ambiguous clip"


def test_rating_with_reviewer_attribution(server):
    base, _ = server
    post_raw(base, "/api/rate", {"cell_id": "1:melody:1", "rating": "2", "rated_by": "carol"})
    session = json.loads(get(base, "/api/session").read())
    cell = session["factor_cells"][0]
    assert cell["rating"] == "2"
    assert cell["rated_by"] == "carol"


def test_import_via_http(server):
    base, _ = server
    payload = {
        "factor_cells": [{"cell_id": "1:melody:1", "rating": "3", "note": "from phone", "rated_by": "dave"}],
        "ab_trials": [{"ab_id": "1:melody:1", "choice": "Tie"}],
    }
    result = json.loads(post_raw(base, "/api/import", payload).read())
    assert result["ok"] is True
    session = json.loads(get(base, "/api/session").read())
    assert session["factor_cells"][0]["rating"] == "3"
    assert session["factor_cells"][0]["note"] == "from phone"
    assert session["ab_trials"][0]["choice"] == "Tie"
