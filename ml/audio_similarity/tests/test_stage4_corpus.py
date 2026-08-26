from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from audio_similarity.stage4_corpus import CorpusReadinessError, SourceTrack, inspect_medleydb, inspect_musdb_archive, safe_extract_musdb, write_manifest


def make_musdb(path: Path, count=2, unsafe=False):
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("README.md", "official provenance")
        for index in range(count): bundle.writestr(f"train/artist - song{index}.stem.mp4", b"x")
        if unsafe: bundle.writestr("../escape", b"bad")


def test_musdb_count_license_and_hash(tmp_path):
    archive = tmp_path / "musdb.zip"; make_musdb(archive)
    result = inspect_musdb_archive(archive, expected=2)
    assert result["track_count"] == 2 and len(result["archive_sha256"]) == 64
    with pytest.raises(CorpusReadinessError): inspect_musdb_archive(archive, expected=3)


def test_safe_archive_paths(tmp_path):
    archive = tmp_path / "bad.zip"; make_musdb(archive, unsafe=True)
    with pytest.raises(CorpusReadinessError): safe_extract_musdb(archive, tmp_path / "out")
    assert not (tmp_path / "escape").exists()


def test_medley_requires_assets_metadata_and_license(tmp_path):
    with pytest.raises(CorpusReadinessError, match="absent"):
        inspect_medleydb(tmp_path / "missing", 1, 1)
    root = tmp_path / "medley"; root.mkdir(); (root / "LICENSE.txt").write_text("license")
    (root / "full_METADATA.yaml").write_text("version: v2\n")
    (root / "excerpt_METADATA.yaml").write_text("version: v1 excerpt\nis_excerpt: true\n")
    (root / "full_MIX.wav").write_bytes(b"wav")
    (root / "excerpt_MIX.wav").write_bytes(b"wav")
    result = inspect_medleydb(root, expected_full=1, expected_excerpts=1)
    assert result["full_track_count"] == 1 and result["excluded_v1_excerpt_count"] == 1


def test_normalized_manifest_rejects_duplicate_ids(tmp_path):
    item = SourceTrack("musdb18", "musdb18:x", "x", "MUSDB18", "train", "x.mp4", "a", "artist", "title", "", "README")
    with pytest.raises(CorpusReadinessError): write_manifest([item,item], tmp_path / "m.parquet")
    digest = write_manifest([item], tmp_path / "m.parquet")
    assert len(digest) == 64
    assert pd.read_parquet(tmp_path / "m.parquet").track_id.tolist() == ["musdb18:x"]
