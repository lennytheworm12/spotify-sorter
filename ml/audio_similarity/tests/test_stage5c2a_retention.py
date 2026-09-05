from __future__ import annotations

import fcntl
import json
import subprocess
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity import stage5c2a_retention as retention


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    not (ROOT / "reports/stage5b_representative_library_v1/library_snapshot.private.json").is_file(),
    reason="Owner-library provenance audit requires the Git-ignored private export",
)
def test_active_amended_source_reference_is_exactly_100_and_keeps_recoveries() -> None:
    _manifest, _manifest_sha, selected, selected_sha, links = (
        retention.validate_amended_source_set(ROOT)
    )
    assert selected_sha == "b09447af7c28fec5dd9816dd9801da9963c3dbc4c8ae534dc5a67307db175088"
    assert len(selected["tracks"]) == len(links) == 100
    by_id = {row["spotify_track_id"]: row for row in selected["tracks"]}
    assert by_id["5quFr5s5PXYfUX5jV2EBZ1"]["selected_youtube_video_id"] == "v224EdAkZr8"
    assert by_id["5l45vVLs4JKkhzN0tvkWJv"]["selected_youtube_video_id"] == "i4YFngxyJ0k"
    assert selected_sha != file_sha256(
        ROOT / "reports/stage5c2_representative_100/selected_sources.json"
    )


class _FakeLimited:
    def __init__(self) -> None:
        self.calls = []
        self.attempts = []

    def acquire(self, track, output_dir):
        self.calls.append(track["youtube_video_id"])
        path = output_dir / f"{track['spotify_track_id']}.webm"
        path.write_bytes(b"source-audio" * 300)
        return {
            "downloaded_path": str(path),
            "provider_title": "Frozen source",
            "provider_duration_seconds": 180,
            "acquisition_started_at": "2026-09-04T00:00:00+00:00",
            "acquisition_ended_at": "2026-09-04T00:00:01+00:00",
            "acquisition_duration_seconds": 1.0,
            "acquisition_attempts": [{"final_outcome": "SUCCESS"}],
            "warnings": [],
        }


def _configure_one_track(tmp_path: Path, monkeypatch) -> None:
    source_ref = tmp_path / "reports/stage5c2a_persistent_research_audio/amended_100_source_reference.json"
    source_ref.parent.mkdir(parents=True)
    track = {
        "spotify_track_id": "spotify-one",
        "spotify_title": "Song",
        "spotify_artists": ["Artist"],
        "youtube_video_id": "abcdefghijk",
        "selected_youtube_video_id": "abcdefghijk",
        "source_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "selected_rank": 1,
        "discovery_mode": "PRIMARY_MULTI_ARTIST",
        "query_variant_index": 0,
        "successful_query": "Song Artist",
        "selector_decision": {},
        "representation_linkage": {"centered30_v1": {"representation_identity": "frozen"}},
    }
    source_ref.write_text(
        json.dumps(
            {
                "selected_sources_sha256": "frozen-selected-sha",
                "tracks": [track],
            }
        ),
        encoding="utf-8",
    )
    config = {
        "source_reference_path": str(source_ref.relative_to(tmp_path)),
    }
    monkeypatch.setattr(retention, "prepare_retention", lambda _root: config)
    monkeypatch.setattr(
        retention,
        "probe_and_validate",
        lambda _path: {
            "duration_seconds": 180.0,
            "container": "webm",
            "codec": "opus",
            "sample_rate_hz": 48000,
            "channels": 2,
            "content_type": "audio/webm",
            "full_decode_validated": True,
        },
    )


def test_retention_keeps_validated_source_cleans_scratch_and_resumes(
    tmp_path: Path, monkeypatch
) -> None:
    _configure_one_track(tmp_path, monkeypatch)
    first = _FakeLimited()
    retention.run_retention(tmp_path, rate_limited_acquirer=first)
    retained = tmp_path / ".research_audio/spotify-one/source.webm"
    assert first.calls == ["abcdefghijk"]
    assert retained.is_file()
    assert file_sha256(retained) == json.loads(
        (retained.parent / "provenance.json").read_text()
    )["source_sha256"]
    assert not list((tmp_path / ".research_audio").glob(".scratch-*"))
    second = _FakeLimited()
    rerun = retention.run_retention(tmp_path, rate_limited_acquirer=second)
    assert second.calls == []
    assert rerun["tracks"][0]["retention_mode"] == "RETENTION_CACHE_HIT"
    assert rerun["clap_inference_calls"] == rerun["muq_inference_calls"] == 0


def test_failed_partial_download_is_removed(tmp_path: Path, monkeypatch) -> None:
    _configure_one_track(tmp_path, monkeypatch)

    class FailedLimited:
        attempts = []

        def acquire(self, _track, output_dir):
            (output_dir / "incomplete.webm.part").write_bytes(b"partial")
            raise RuntimeError("permanent acquisition failure")

    result = retention.run_retention(
        tmp_path, rate_limited_acquirer=FailedLimited()
    )
    assert result["tracks"][0]["status"] == "FAILED"
    assert not list((tmp_path / ".research_audio").glob(".scratch-*"))
    assert not list((tmp_path / ".research_audio").rglob("*.part"))


def test_cleanup_failure_is_structured(tmp_path: Path, monkeypatch) -> None:
    _configure_one_track(tmp_path, monkeypatch)
    limited = _FakeLimited()

    def fail_cleanup(_path, *, ignore_errors):
        assert ignore_errors is False
        raise OSError("scratch directory busy")

    monkeypatch.setattr(retention.shutil, "rmtree", fail_cleanup)
    result = retention.run_retention(
        tmp_path, rate_limited_acquirer=limited
    )
    assert result["tracks"][0]["status"] == "FAILED"
    assert result["tracks"][0]["failure_category"] == "CLEANUP_FAILED"


def test_concurrent_retention_process_is_rejected(tmp_path: Path) -> None:
    media_root = tmp_path / ".research_audio"
    media_root.mkdir()
    with (media_root / ".retention.lock").open("w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(
            retention.Stage5B1AValidationError, match="another retained-media"
        ):
            retention.run_retention(tmp_path)


def test_retention_implementation_has_no_discovery_or_selector_execution() -> None:
    source = Path(retention.__file__).read_text(encoding="utf-8")
    assert "ytsearch" not in source
    assert "playwright" not in source.casefold()
    assert "search.list" not in source
    assert "clap_model" not in source
    assert "muq_model" not in source


def test_persistent_media_root_is_ignored_and_no_media_is_tracked() -> None:
    probe = ".research_audio/ignored-probe.webm"
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", probe], cwd=ROOT, check=False
    )
    assert ignored.returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "--", ".research_audio"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert tracked.stdout == ""


def test_audio_only_webm_is_served_with_an_audio_media_type() -> None:
    assert retention._audio_content_type(".webm") == "audio/webm"


def test_spacing_audit_uses_the_enforcing_monotonic_delta() -> None:
    attempts = [
        {
            "request_start_timestamp": "2026-09-04T00:00:00+00:00",
            "previous_request_start_delta_seconds": None,
        },
        {
            "request_start_timestamp": "2026-09-04T00:00:19.999900+00:00",
            "previous_request_start_delta_seconds": 20.0002,
        },
    ]
    assert retention._attempt_spacings(attempts) == [20.0002]


def test_amended_review_queue_and_original_98_evidence_are_untouched() -> None:
    assert file_sha256(
        ROOT / "reports/stage5c2_representative_100_amended_v2/review_queue.json"
    ) == "e0b36ed25206970d5dad9b8122f3e74d176da9a3827dfb239d45f9fc848cbba0"
    assert file_sha256(
        ROOT / "reports/stage5c2_representative_100/selected_sources.json"
    ) == "dc9c868d603f456782867eee76aea6a8a9784b3b43ace3777636b77b97bf12b9"
