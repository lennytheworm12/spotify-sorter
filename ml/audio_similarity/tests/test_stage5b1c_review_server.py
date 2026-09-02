from __future__ import annotations

import csv
import json
import shutil
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from audio_similarity.cli import stage5b1c_review_server
from audio_similarity.cli.stage5b1c_review_server import (
    EXPORT_FILENAME,
    MODE,
    SHUFFLE_SALT,
    handler_for,
)
from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b1b_challenge import (
    load_challenge_config,
    load_challenge_manifest,
)
from audio_similarity.stage5b1b_challenge_audit import REVIEW_COLUMNS
from audio_similarity.stage5b1b_challenge_review_store import (
    Stage5B1BChallengeReviewStore,
)
from audio_similarity.stage5b1c_review import (
    EXPECTED_SELECTIONS,
    write_tier2_review_artifacts,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1b_fresh_challenge.json"
REPORT = ROOT / "reports/stage5b1c_b"
QUEUE = REPORT / "tier2_human_audit_queue.json"
REVIEW = REPORT / "tier2_human_review.csv"
TIER2A = ROOT / "reports/stage5b1c_a/tier2_decisions.json"
SOURCE_NEUTRAL = REPORT / "source_neutral_decisions.json"
STATIC = ROOT / "evaluation/static/stage5b1b_review.html"


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
        config.manifest_path, expected_sha256=config.manifest_sha256
    )
    review = tmp_path / "review.csv"
    shutil.copyfile(REVIEW, review)
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
    return Stage5B1BChallengeReviewStore(
        manifest,
        QUEUE,
        review,
        session_mode=MODE,
        export_filename=EXPORT_FILENAME,
        shuffle_salt=SHUFFLE_SALT,
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


def test_committed_queue_contains_exactly_the_eleven_tier2_selections():
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    assert queue["track_count"] == 11
    assert queue["candidate_count"] == 11
    assert {
        row["stable_track_id"]: row["candidate_video_ids"][0]
        for row in queue["cases"]
    } == EXPECTED_SELECTIONS
    with REVIEW.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 11
    assert all(
        row["candidate_review_label"]
        in {"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"}
        for row in rows
    )


def test_artifact_builder_is_deterministic_and_refuses_to_replace_review_data(tmp_path):
    queue_path = tmp_path / "queue.json"
    review_path = tmp_path / "review.csv"
    kwargs = {
        "config_path": CONFIG,
        "tier2a_decisions_path": TIER2A,
        "source_neutral_decisions_path": SOURCE_NEUTRAL,
        "queue_path": queue_path,
        "review_path": review_path,
    }
    queue, rows = write_tier2_review_artifacts(**kwargs)
    first_hashes = file_sha256(queue_path), file_sha256(review_path)
    repeated_queue, repeated_rows = write_tier2_review_artifacts(**kwargs)
    assert repeated_queue == queue
    assert repeated_rows == rows
    assert (file_sha256(queue_path), file_sha256(review_path)) == first_hashes

    with review_path.open(encoding="utf-8", newline="") as handle:
        changed = list(csv.DictReader(handle))
    changed[0]["candidate_note"] = "do not overwrite this"
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(changed)
    with pytest.raises(Stage5B1AValidationError, match="refusing to overwrite"):
        write_tier2_review_artifacts(**kwargs)


def test_session_is_blinded_and_starts_at_zero_of_eleven(review_store):
    session = review_store.session()
    assert session["mode"] == MODE
    assert session["export_filename"] == EXPORT_FILENAME
    assert session["progress"] == {
        "reviewed_candidates": 0,
        "remaining_candidates": 11,
        "total_candidates": 11,
        "completed_tracks": 0,
        "total_tracks": 11,
    }
    assert len(session["cases"]) == 11
    assert all(len(case["candidates"]) == 1 for case in session["cases"])
    serialized = json.dumps(session).lower()
    for forbidden in (
        "selection_reasons",
        "sol_label",
        "source_type",
        "policy_rule",
        "source_neutral",
        "recovery_evidence",
    ):
        assert forbidden not in serialized


def test_label_and_note_autosave_then_export(review_server):
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
                "label": "ACCEPTABLE",
                "candidate_note": "Correct recording; source is safe enough.",
                "track_note": "Checked metadata and YouTube.",
            },
        ).read()
    )
    assert saved["review"] == {
        "label": "ACCEPTABLE",
        "note": "Correct recording; source is safe enough.",
    }
    updated = json.loads(request(review_server, "/api/session").read())
    assert updated["progress"]["reviewed_candidates"] == 1
    assert updated["cases"][0]["candidates"][0]["review"]["label"] == "ACCEPTABLE"

    exported = request(review_server, "/api/export")
    assert exported.headers["Content-Disposition"] == (
        f'attachment; filename="{EXPORT_FILENAME}"'
    )
    rows = list(csv.DictReader(exported.read().decode().splitlines()))
    assert rows[0]["candidate_review_label"] == "ACCEPTABLE"
    assert rows[0]["candidate_note"] == "Correct recording; source is safe enough."
    assert rows[0]["track_note"] == "Checked metadata and YouTube."


def test_shared_frontend_has_tier2_mode_copy_and_save_guards(review_server):
    html = request(review_server, "/").read().decode()
    assert 'session.mode === "stage5b1c_tier2_human_audit"' in html
    assert "Recovered source review" in html
    assert "Blinded Tier-2 safety audit" in html
    assert "flushPendingNotes();" in html
    assert "await Promise.all([...saveQueues.values()]);" in html
    assert "button.classList.toggle(\"selected\", selected);" in html
    assert json.loads(request(review_server, "/api/ping").read()) == {
        "ok": True,
        "mode": MODE,
    }


def test_main_wires_tier2_paths_mode_and_export(monkeypatch):
    captured = {}

    def fake_serve(store, host, port, **options):
        captured.update(store=store, host=host, port=port, options=options)

    monkeypatch.setattr(stage5b1c_review_server, "serve", fake_serve)
    monkeypatch.setattr(sys, "argv", ["stage5b1c_review_server", "--no-browser"])
    stage5b1c_review_server.main()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8770
    assert captured["options"] == {
        "open_browser": False,
        "mode": MODE,
        "export_filename": EXPORT_FILENAME,
        "server_name": "Stage 5B.1C Tier-2 reviewer",
    }
    session = captured["store"].session()
    assert session["mode"] == MODE
    assert session["progress"]["total_candidates"] == 11


def test_static_frontend_remains_single_shared_review_site():
    html = STATIC.read_text(encoding="utf-8")
    assert html.count("stage5b1c_tier2_human_audit") == 2
    assert "createElement(\"iframe\")" not in html
