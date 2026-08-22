"""Deployment bundle generation tests (no real FMA data required)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from audio_similarity.cli.build_deploy_bundle import build_bundle, referenced_track_ids
from tests.helpers import save_wav, synth_waveform


@pytest.fixture
def mini_env(tmp_path: Path) -> dict:
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    audio_root = tmp_path / "audio"

    rows = []
    for tid in [1, 2, 3]:
        sub = audio_root / f"{tid:03d}"
        sub.mkdir(parents=True)
        save_wav(sub / f"{tid:06d}.wav", synth_waveform(0.2, seed=tid), 24000)
        rows.append(
            {
                "track_id": tid,
                "relative_audio_path": f"{tid:03d}/{tid:06d}.wav",
                "audio_sha256": f"hash{tid}",
                "file_size_bytes": 1000,
                "decode_status": "SUCCESS",
                "duration_sec": 0.2,
                "title": f"t{tid}", "artist": f"a{tid}", "album": "al",
                "top_genre": "g", "fma_split": "test", "subset": "small",
            }
        )
    manifest_path = tmp_path / "manifest.parquet"
    pd.DataFrame(rows).to_parquet(manifest_path, index=False)

    pd.DataFrame(
        [{"cell_id": "1:melody:1", "representation": "m", "neighbor_track_id": 2}]
    ).to_csv(sheets / "key_factor.csv", index=False)
    pd.DataFrame(
        [{"ab_id": "1:melody:1", "a_representation": "m", "b_representation": "g",
          "a_track_id": 2, "b_track_id": 3}]
    ).to_csv(sheets / "key_ab.csv", index=False)

    return {
        "sheets": sheets,
        "manifest": manifest_path,
        "queries": None,
        "audio_root": audio_root,
        "output": tmp_path / "bundle",
    }


def test_referenced_track_ids_union(mini_env):
    ids = referenced_track_ids(mini_env["sheets"], None)
    assert ids == {2, 3}  # neighbor + ab sides; no queries csv provided


def test_bundle_copies_only_referenced_audio(mini_env):
    out = build_bundle(
        sheets_dir=mini_env["sheets"], manifest_path=mini_env["manifest"],
        queries_csv=mini_env["queries"], audio_root=mini_env["audio_root"],
        output_dir=mini_env["output"],
    )
    audio_files = list((out / "data" / "fma").rglob("*.wav"))
    assert len(audio_files) == 2  # tracks 2 and 3 only; track 1 excluded

    assert (out / "Dockerfile").exists()
    assert (out / "fly.toml").exists()

    manifest = pd.read_parquet(out / "data" / "manifests" / "fma_small.parquet")
    assert set(manifest["track_id"]) == {2, 3}

    attrib = pd.read_csv(out / "ATTRIBUTION.csv")
    assert {"track_id", "title", "artist"} <= set(attrib.columns)

    # source + UI + sheets staged for the Dockerfile COPY steps
    assert (out / "src" / "audio_similarity").is_dir()
    assert (out / "evaluation" / "static" / "index.html").exists()
    assert (out / "reports" / "human_eval" / "key_factor.csv").exists()


def test_bundle_regenerates_cleanly(mini_env):
    kw = dict(
        sheets_dir=mini_env["sheets"], manifest_path=mini_env["manifest"],
        queries_csv=mini_env["queries"], audio_root=mini_env["audio_root"],
        output_dir=mini_env["output"],
    )
    out1 = build_bundle(**kw)
    out2 = build_bundle(**kw)
    assert out1 == out2
    assert len(list((out2 / "data" / "fma").rglob("*.wav"))) == 2  # rebuild leaves no duplicates


def test_bundle_handles_missing_audio_gracefully(mini_env, tmp_path):
    # delete track 3's file; bundle must skip it without crashing
    (mini_env["audio_root"] / "003" / "000003.wav").unlink()
    out = build_bundle(
        sheets_dir=mini_env["sheets"], manifest_path=mini_env["manifest"],
        queries_csv=mini_env["queries"], audio_root=mini_env["audio_root"],
        output_dir=mini_env["output"],
    )
    assert len(list((out / "data" / "fma").rglob("*.wav"))) == 1
