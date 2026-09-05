from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5e1_contract import (
    MINIMUM_DURATION_SECONDS,
    active_retention_batches,
    audit_corpus,
    inspect_clap_checkpoint,
)


def _source(root: Path, spotify_id: str, *, duration: float = 180.0) -> None:
    directory = root / ".research_audio" / spotify_id
    directory.mkdir(parents=True)
    source = directory / "source.webm"
    source.write_bytes((spotify_id.encode() + b"-audio") * 200)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (directory / "provenance.json").write_text(
        json.dumps(
            {
                "schema_version": "stage5d0a-retained-source-v1",
                "spotify_track_id": spotify_id,
                "spotify_title": f"Song {spotify_id}",
                "spotify_artists": ["Artist"],
                "album": "Album",
                "release_year": 2020,
                "youtube_video_id": f"{spotify_id:0<11}"[:11],
                "retained_relative_path": f"{spotify_id}/source.webm",
                "source_sha256": digest,
                "file_size_bytes": source.stat().st_size,
                "duration_seconds": duration,
                "full_decode_validated": True,
            }
        ),
        encoding="utf-8",
    )


def _project(tmp_path: Path) -> Path:
    report = tmp_path / "reports/stage5c2_representative_100_amended_v2"
    report.mkdir(parents=True)
    (report / "selected_sources.json").write_text(
        json.dumps({"tracks": [{"spotify_track_id": "one"}]}), encoding="utf-8"
    )
    return tmp_path


def _probe(path: Path, *, minimum_duration_seconds: float) -> dict:
    assert minimum_duration_seconds == 0
    provenance = json.loads((path.parent / "provenance.json").read_text())
    return {
        "duration_seconds": provenance["duration_seconds"],
        "codec": "opus",
        "container": "webm",
        "sample_rate_hz": 48000,
        "channels": 2,
    }


def test_corpus_audit_is_deterministic_and_preserves_eligibility(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _source(root, "two", duration=MINIMUM_DURATION_SECONDS - 0.01)
    _source(root, "one", duration=180)
    first = audit_corpus(root, probe=_probe)
    second = audit_corpus(root, probe=_probe)
    assert first == second
    audit, manifest = first
    assert audit["retained_track_count"] == 2
    assert audit["excluded_track_count"] == 1
    assert manifest["track_count"] == 1
    assert manifest["tracks"][0]["spotify_track_id"] == "one"
    assert manifest["tracks"][0]["historical_stage5c2_review_member"] is True


def test_corpus_audit_rejects_source_integrity_change(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _source(root, "one")
    (root / ".research_audio/one/source.webm").write_bytes(b"changed")
    with pytest.raises(Stage5B1AValidationError, match="integrity"):
        audit_corpus(root, probe=_probe)


def test_checkpoint_gate_requires_both_aff_and_local_projection(tmp_path: Path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "audio_similarity.stage5e1_contract._state_keys",
        lambda _path: ["audio_branch.patch_embed.proj.weight"],
    )
    assert inspect_clap_checkpoint(checkpoint)["trained_aff_available"] is False
    monkeypatch.setattr(
        "audio_similarity.stage5e1_contract._state_keys",
        lambda _path: [
            "audio_branch.patch_embed.mel_conv2d.weight",
            "audio_branch.patch_embed.fusion_model.local_att.0.weight",
        ],
    )
    assert inspect_clap_checkpoint(checkpoint)["trained_aff_available"] is True


def test_checkpoint_gate_rejects_unexpected_file_before_state_load(tmp_path: Path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"wrong")
    monkeypatch.setattr(
        "audio_similarity.stage5e1_contract._state_keys",
        lambda _path: pytest.fail("untrusted checkpoint must not be loaded"),
    )
    result = inspect_clap_checkpoint(
        checkpoint,
        expected_sha256="0" * 64,
        expected_size_bytes=5,
    )
    assert result["trusted_source_identity"] is False
    assert result["trained_aff_available"] is False


def test_active_retention_batch_defers_corpus_freeze(tmp_path: Path) -> None:
    state = tmp_path / ".research_audio/chart_download_batches_v1/batch_0001/state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"status": "RUNNING"}), encoding="utf-8")
    assert active_retention_batches(tmp_path) == [
        ".research_audio/chart_download_batches_v1/batch_0001/state.json"
    ]
    state.write_text(json.dumps({"status": "COMPLETE"}), encoding="utf-8")
    assert active_retention_batches(tmp_path) == []
