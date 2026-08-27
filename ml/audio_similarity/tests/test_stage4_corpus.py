from __future__ import annotations

import zipfile
from pathlib import Path
import subprocess

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


def test_medley_requires_assets_metadata_license_and_official_tracklists(tmp_path):
    with pytest.raises(CorpusReadinessError, match="assets absent"):
        inspect_medleydb(tmp_path / "missing", tmp_path / "metadata", 2, 1)
    audio = tmp_path / "audio"; audio.mkdir()
    root = tmp_path / "metadata"; (root / "medleydb/resources").mkdir(parents=True); (root / "medleydb/data/Metadata").mkdir(parents=True)
    (root / "LICENSE").write_text("license")
    (root / "medleydb/resources/tracklist_v1.txt").write_text("fullv1\nexcerptv1\n")
    (root / "medleydb/resources/tracklist_v2.txt").write_text("excerptv2\n")
    for track_id, excerpt in (("fullv1", "no"), ("excerptv1", "yes"), ("excerptv2", "yes")):
        (root / f"medleydb/data/Metadata/{track_id}_METADATA.yaml").write_text(f"excerpt: '{excerpt}'\nmix_filename: {track_id}_MIX.wav\n")
    (audio / "fullv1_MIX.wav").write_bytes(b"wav")
    (audio / "excerptv2_MIX.wav").write_bytes(b"wav")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-qm", "metadata"], check=True)
    revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    result = inspect_medleydb(audio, root, expected_full=2, expected_excerpts=1, expected_revision=revision)
    assert result["eligible_track_count"] == 2
    assert result["excluded_v1_excerpt_count"] == 1
    assert result["included_v2_excerpt_count"] == 1
    assert len(result["metadata_bundle_sha256"]) == 64


def test_normalized_manifest_rejects_duplicate_ids(tmp_path):
    item = SourceTrack("musdb18", "musdb18:x", "x", "MUSDB18", "train", "x.mp4", "a", "artist", "title", "", "README")
    with pytest.raises(CorpusReadinessError): write_manifest([item,item], tmp_path / "m.parquet")
    digest = write_manifest([item], tmp_path / "m.parquet")
    assert len(digest) == 64
    assert pd.read_parquet(tmp_path / "m.parquet").track_id.tolist() == ["musdb18:x"]
