"""Manifest tests (Phase 1 doc, section 6 dataset contract; section 23)."""

from __future__ import annotations

import pandas as pd
import pytest

from audio_similarity.manifest import (
    MANIFEST_COLUMNS,
    STATUS_DECODE_FAILED,
    build_manifest,
    discover_audio_files,
    load_fma_metadata,
    load_manifest,
)
from tests.helpers import save_wav, synth_waveform


def make_fma_style_metadata(rows: list[dict]) -> pd.DataFrame:
    """Create a tracks.csv-shaped frame with FMA's (attribute, key) columns."""
    columns = pd.MultiIndex.from_tuples(
        [
            ("track", "title"),
            ("artist", "name"),
            ("album", "title"),
            ("track", "genre_top"),
            ("set", "split"),
            ("set", "subset"),
        ]
    )
    frame = pd.DataFrame(
        [
            [r["title"], r["artist"], r["album"], r["top_genre"], r["split"], r["subset"]]
            for r in rows
        ],
        columns=columns,
    )
    frame.index = pd.Index([r["track_id"] for r in rows], name="track_id")
    return frame


@pytest.fixture
def synthetic_tree(tmp_path):
    audio_dir = tmp_path / "audio"
    for fid in (5, 2, 10):  # deliberately out of order on disk
        sub = audio_dir / f"{fid:03d}"
        sub.mkdir(parents=True)
        save_wav(sub / f"{fid:06d}.mp3".replace(".mp3", ".wav"), synth_waveform(1, seed=fid), 24000)
    metadata = make_fma_style_metadata(
        [
            {
                "track_id": 2,
                "title": "Song B",
                "artist": "Artist X",
                "album": "Album 1",
                "top_genre": "Rock",
                "split": "training",
                "subset": "small",
            },
            {
                "track_id": 10,
                "title": "Song C",
                "artist": "Artist Y",
                "album": "Album 2",
                "top_genre": "Electronic",
                "split": "test",
                "subset": "small",
            },
            # track 5 intentionally absent from metadata
        ]
    )
    return audio_dir, metadata, tmp_path


def test_discover_is_sorted_by_track_id_not_traversal(synthetic_tree):
    audio_dir, _, _ = synthetic_tree
    entries = discover_audio_files(audio_dir)
    assert [tid for tid, _ in entries] == [2, 5, 10]


def test_build_manifest_joins_metadata_and_sorts(synthetic_tree):
    audio_dir, metadata, tmp_path = synthetic_tree
    csv_path = tmp_path / "tracks.csv"
    metadata.to_csv(csv_path)

    frame = build_manifest(audio_dir, csv_path, tmp_path / "manifest.parquet", audio_root=audio_dir)

    assert list(frame["track_id"]) == [2, 5, 10]
    row2 = frame[frame["track_id"] == 2].iloc[0]
    assert row2["title"] == "Song B"
    assert row2["artist"] == "Artist X"
    assert row2["top_genre"] == "Rock"
    assert row2["fma_split"] == "training"
    assert row2["relative_audio_path"].startswith("002/")
    assert row2["decode_status"] == "SUCCESS"
    assert row2["duration_sec"] == pytest.approx(1.0, abs=0.05)
    assert len(row2["audio_sha256"]) == 64


def test_missing_metadata_keeps_track_represented(synthetic_tree):
    audio_dir, metadata, tmp_path = synthetic_tree
    csv_path = tmp_path / "tracks.csv"
    metadata.to_csv(csv_path)

    frame = build_manifest(audio_dir, csv_path, tmp_path / "manifest.parquet", audio_root=audio_dir)
    row5 = frame[frame["track_id"] == 5].iloc[0]
    assert row5["decode_status"] == "SUCCESS"  # audio itself is fine
    assert row5["fma_split"] == "missing_metadata"
    assert row5["top_genre"] == ""


def test_corrupt_audio_stays_in_manifest_as_decode_failed(synthetic_tree):
    audio_dir, metadata, tmp_path = synthetic_tree
    bad = audio_dir / "099"
    bad.mkdir()
    (bad / "000099.wav").write_bytes(b"not audio at all")

    rows = [{"track_id": 99}]
    metadata_extra = pd.concat([metadata, make_fma_style_metadata([])])
    csv_path = tmp_path / "tracks.csv"
    metadata_extra.to_csv(csv_path)

    frame = build_manifest(audio_dir, csv_path, tmp_path / "m.parquet", audio_root=audio_dir)
    assert 99 in set(frame["track_id"])
    row = frame[frame["track_id"] == 99].iloc[0]
    assert row["decode_status"] == STATUS_DECODE_FAILED
    assert pd.isna(row["duration_sec"]) or row["duration_sec"] is None


def test_load_manifest_validates_columns(synthetic_tree):
    audio_dir, metadata, tmp_path = synthetic_tree
    csv_path = tmp_path / "tracks.csv"
    metadata.to_csv(csv_path)
    out = tmp_path / "m.parquet"
    build_manifest(audio_dir, csv_path, out, audio_root=audio_dir)

    loaded = load_manifest(out)
    assert list(loaded.columns) == MANIFEST_COLUMNS

    # round-trip determinism: rebuilding yields identical bytes-level content
    rebuilt = build_manifest(audio_dir, csv_path, tmp_path / "m2.parquet", audio_root=audio_dir)
    pd.testing.assert_frame_equal(loaded, rebuilt)


def test_fma_real_metadata_loads(data_fma_available):
    metadata_csv = data_fma_available / "fma_metadata" / "tracks.csv"
    meta = load_fma_metadata(metadata_csv)
    assert len(meta) >= 106574  # full FMA track index
    assert {"title", "artist", "top_genre", "fma_split", "subset"} <= set(meta.columns)


@pytest.fixture(scope="session")
def data_fma_available():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "data" / "fma"
    if not (root / "fma_metadata" / "tracks.csv").exists():
        pytest.skip("FMA data not downloaded")
    return root
