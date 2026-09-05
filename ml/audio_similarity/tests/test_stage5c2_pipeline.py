from __future__ import annotations

import json
import shutil
from pathlib import Path

import torch
import torchaudio

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5c2_pipeline import run_materialization
from audio_similarity.stage5c2_rate_limit import AcquisitionRetryPolicy, RateLimitedAcquirer


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _Encoder:
    def __init__(self, encoder_id: str) -> None:
        self.encoder_id = encoder_id
        self.embedding_dim = 512
        self.calls = 0

    def encode_segment(self, waveform, _sample_rate):
        self.calls += 1
        value = float(waveform.mean())
        vector = torch.zeros(512, dtype=torch.float32)
        vector[:3] = torch.tensor(
            [1.0, value + (0.2 if self.encoder_id == "muq_mulan_large" else 0), 0.5]
        )
        return vector.numpy()


class _ExactAcquirer:
    def __init__(self, *, fail_id: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_id = fail_id

    def acquire(self, track, output_dir):
        video_id = track["selected_youtube_video_id"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        assert track["selected_youtube_url"] == url
        assert "ytsearch" not in url
        self.calls.append(track["spotify_track_id"])
        prefix = f"{track['stage5c1_track_id']}-{video_id}"
        path = output_dir / f"{prefix}.wav"
        if track["spotify_track_id"] == self.fail_id:
            path.with_suffix(".part").write_bytes(b"partial")
            raise RuntimeError("Video unavailable")
        waveform = torch.full((1, 24_000 * 30), 0.01 * len(self.calls))
        torchaudio.save(str(path), waveform, 24_000)
        return {
            "provider": "fake_exact_url",
            "provider_result": "SUCCESS",
            "video_id": video_id,
            "exact_url": url,
            "temporary_file_path": str(path),
            "elapsed_seconds": 0.01,
            "warnings": [],
            "errors": [],
        }


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def _prepare_root(tmp_path: Path, *, selected_count: int = 3) -> tuple[Path, list[dict]]:
    report = tmp_path / "reports/stage5c2_representative_100"
    report.mkdir(parents=True)
    contract = tmp_path / "reports/holistic_stage4a_dual"
    contract.mkdir(parents=True)
    shutil.copy2(
        PROJECT_ROOT / "reports/holistic_stage4a_dual/audio_representation_v1.json",
        contract / "audio_representation_v1.json",
    )
    tracks = [
        {
            "stage5c2_track_id": f"stage5c2_{index:03d}",
            "manifest_index": index,
            "spotify_track_id": f"{index:022d}",
            "title": f"Song {index}",
            "artists": [f"Artist {index}"],
            "album": f"Album {index}",
            "duration_ms": 180_000,
        }
        for index in range(1, 101)
    ]
    manifest = {
        "schema_version": "stage5c2-representative-100-manifest-v1",
        "experiment_id": "stage5c2_representative_100",
        "sampled_track_count": 100,
        "post_freeze_substitutions": 0,
        "tracks": tracks,
    }
    manifest_path = report / "representative_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_path.with_suffix(".sha256").write_text(file_sha256(manifest_path) + "\n")
    selected_tracks = [
        {
            "stage5c2_track_id": row["stage5c2_track_id"],
            "manifest_index": row["manifest_index"],
            "spotify_track_id": row["spotify_track_id"],
            "title": row["title"],
            "artists": row["artists"],
            "album": row["album"],
            "spotify_duration_ms": row["duration_ms"],
            "selected_youtube_video_id": f"v{row['manifest_index']:07d}001",
            "selected_youtube_url": (
                f"https://www.youtube.com/watch?v=v{row['manifest_index']:07d}001"
            ),
            "selected_candidate_rank": 1,
            "discovery_mode": "PRIMARY_MULTI_ARTIST",
            "query_variant_index": 0,
            "successful_query": f"Song {row['manifest_index']} Artist {row['manifest_index']}",
            "selector_decision": "AUTO_SELECT",
            "selector_reason": "FIRST_NATIVE_RANK_WITHOUT_V1_VETO",
        }
        for row in tracks[:selected_count]
    ]
    selected = {
        "schema_version": "stage5c2-selected-sources-v1",
        "representative_manifest_sha256": file_sha256(manifest_path),
        "automated_selection_count": selected_count,
        "manual_tail_count": 100 - selected_count,
        "post_freeze_substitutions": 0,
        "exact_id_acquisition_only": True,
        "tracks": selected_tracks,
    }
    selected_path = report / "selected_sources.json"
    selected_path.write_text(json.dumps(selected), encoding="utf-8")
    selected_path.with_suffix(".sha256").write_text(file_sha256(selected_path) + "\n")
    return tmp_path, selected_tracks


def _limited(acquirer):
    clock = _Clock()
    return RateLimitedAcquirer(
        acquirer,
        policy=AcquisitionRetryPolicy(jitter_max_seconds=0),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        utc_now=lambda: "test",
    )


def test_exact_id_pipeline_materializes_frozen_k3_and_cache_rerun_skips_work(
    tmp_path: Path,
) -> None:
    root, selected = _prepare_root(tmp_path)
    acquirer = _ExactAcquirer()
    limited = _limited(acquirer)
    clap, muq = _Encoder("laion_clap"), _Encoder("muq_mulan_large")
    encoders = {clap.encoder_id: clap, muq.encoder_id: muq}
    first = run_materialization(
        root,
        run_kind="first",
        rate_limited_acquirer=limited,
        encoders=encoders,
    )
    call_counts = (clap.calls, muq.calls)
    rerun = run_materialization(
        root,
        run_kind="cache_rerun",
        acquirer=acquirer,
        encoders=encoders,
    )
    assert acquirer.calls == [row["spotify_track_id"] for row in selected]
    assert first["full_materialization_successes"] == 3
    assert call_counts == (9, 9)
    assert all(len(row["segments"]) == 6 for row in first["tracks"])
    assert all(
        {segment["center_sec"] for segment in row["segments"]} == {5, 15, 25}
        for row in first["tracks"]
    )
    assert first["frozen_contract"]["clap_weight"] == 0.7172981519
    assert first["frozen_contract"]["muq_weight"] == 0.2827018481
    validation = rerun["cache_rerun_validation"]
    assert validation["network_acquisition_attempts"] == 0
    assert validation["encoder_segments_inferred"] == 0
    assert validation["encoder_rerun"] is False
    assert all(validation["representation_hash_equality"].values())
    assert (clap.calls, muq.calls) == call_counts


def test_cleanup_runs_after_permanent_acquisition_failure(tmp_path: Path) -> None:
    root, selected = _prepare_root(tmp_path, selected_count=2)
    failed_id = selected[0]["spotify_track_id"]
    acquirer = _ExactAcquirer(fail_id=failed_id)
    encoders = {
        "laion_clap": _Encoder("laion_clap"),
        "muq_mulan_large": _Encoder("muq_mulan_large"),
    }
    result = run_materialization(
        root,
        run_kind="first",
        rate_limited_acquirer=_limited(acquirer),
        encoders=encoders,
    )
    cleanup = json.loads(
        (root / "reports/stage5c2_representative_100/cleanup_audit.json").read_text()
    )
    failed = next(row for row in result["tracks"] if row["spotify_track_id"] == failed_id)
    failed_cleanup = next(
        row for row in cleanup["tracks"] if row["spotify_track_id"] == failed_id
    )
    assert failed["failure_category"] == "MEDIA_UNAVAILABLE"
    assert failed_cleanup["cleanup_attempted"] is True
    assert failed_cleanup["temp_files_absent_after_cleanup"] is True
    assert cleanup["temporary_root_absent_after_cleanup"] is True
    assert cleanup["unintended_retained_source_audio_files"] == 0
