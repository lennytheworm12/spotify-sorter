"""Official MUSDB18 + MedleyDB 2.0 readiness and normalized manifest boundary."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

import pandas as pd
import yaml

EXPECTED_MUSDB18 = 150
EXPECTED_MEDLEYDB2_FULL = 179
EXPECTED_MEDLEYDB1_EXCERPTS = 17


class CorpusReadinessError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceTrack:
    corpus: str
    track_id: str
    official_id: str
    dataset_version: str
    split: str
    relative_source_path: str
    source_sha256: str
    artist: str
    title: str
    genre: str
    license_provenance: str
    decode_status: str = "pending"
    canonical_pcm_sha256: str = ""
    sample_count: int = 0
    duration_sec: float = 0.0


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and not re.match(r"^[A-Za-z]:", name)


def safe_extract_musdb(archive: str | Path, destination: str | Path) -> list[Path]:
    archive, destination = Path(archive), Path(destination)
    with zipfile.ZipFile(archive) as bundle:
        unsafe = [item.filename for item in bundle.infolist() if not _safe_member(item.filename)]
        if unsafe:
            raise CorpusReadinessError(f"unsafe archive paths: {unsafe[:3]}")
        destination.mkdir(parents=True, exist_ok=True)
        bundle.extractall(destination)
    return sorted(destination.rglob("*.stem.mp4"))


def inspect_musdb_archive(archive: str | Path, expected: int = EXPECTED_MUSDB18) -> dict:
    path = Path(archive)
    if not path.is_file():
        raise CorpusReadinessError(f"official MUSDB18 archive absent: {path}")
    with zipfile.ZipFile(path) as bundle:
        names = [item.filename for item in bundle.infolist()]
        if any(not _safe_member(name) for name in names):
            raise CorpusReadinessError("MUSDB18 archive contains unsafe paths")
        tracks = sorted(name for name in names if name.endswith(".stem.mp4"))
        license_files = sorted(name for name in names if Path(name).name.lower() in {"readme.md", "license", "license.txt", "licenses.md"})
    if len(tracks) != expected:
        raise CorpusReadinessError(f"MUSDB18 expected {expected} mixtures, found {len(tracks)}")
    if not license_files:
        raise CorpusReadinessError("MUSDB18 archive has no license/provenance file")
    return {"release": "MUSDB18", "archive": str(path), "archive_sha256": sha256_file(path), "track_count": len(tracks), "license_files": license_files, "mixture_stream": 0}


def verify_mixture_stream(path: str | Path) -> dict:
    """Require stream 0 to be audio; additional stem streams are never decoded."""
    command = ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CorpusReadinessError(f"ffprobe failed for {path}: {exc}") from exc
    streams = json.loads(result.stdout).get("streams", [])
    if not streams or streams[0].get("codec_type") != "audio":
        raise CorpusReadinessError(f"ambiguous MUSDB mixture stream 0 for {path}")
    return {"stream_index": 0, "codec": streams[0].get("codec_name"), "channels": streams[0].get("channels"), "sample_rate": streams[0].get("sample_rate")}


def _metadata_files(root: Path) -> list[Path]:
    return sorted([*root.rglob("*.yaml"), *root.rglob("*.yml")])


def _mix_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and "_MIX" in path.stem and path.suffix.lower() in {".wav", ".flac", ".mp3", ".aiff", ".aif"})


def _is_v1_excerpt(meta: dict, path: Path) -> bool:
    text = " ".join(str(meta.get(key, "")) for key in ("version", "dataset", "excerpt", "track_type", "origin")).casefold()
    return bool(meta.get("is_excerpt") is True or ("v1" in text and "excerpt" in text) or "excerpt" in path.as_posix().casefold())


def inspect_medleydb(root: str | Path, expected_full: int = EXPECTED_MEDLEYDB2_FULL, expected_excerpts: int = EXPECTED_MEDLEYDB1_EXCERPTS) -> dict:
    root = Path(root)
    if not root.is_dir():
        raise CorpusReadinessError(f"official MedleyDB 2.0 assets absent: {root}")
    licenses = sorted(path for path in root.rglob("*") if path.is_file() and any(token in path.name.casefold() for token in ("license", "readme", "provenance")))
    if not licenses:
        raise CorpusReadinessError("MedleyDB 2.0 license/provenance files absent")
    mixes = _mix_files(root)
    metadata = _metadata_files(root)
    if not mixes or not metadata:
        raise CorpusReadinessError("MedleyDB requires official metadata YAML and *_MIX audio")
    excerpt_ids = set()
    for path in metadata:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise CorpusReadinessError(f"invalid metadata YAML {path}: {exc}") from exc
        if isinstance(payload, dict) and _is_v1_excerpt(payload, path):
            excerpt_ids.add(path.stem.replace("_METADATA", ""))
    full = [path for path in mixes if not any(alias in path.stem for alias in excerpt_ids)]
    if len(full) != expected_full:
        raise CorpusReadinessError(f"MedleyDB 2.0 expected {expected_full} full tracks after 17 v1 excerpts, found {len(full)}")
    if len(excerpt_ids) != expected_excerpts:
        raise CorpusReadinessError(f"MedleyDB expected {expected_excerpts} marked v1 excerpts, found {len(excerpt_ids)}")
    return {"release": "MedleyDB_2.0", "root": str(root), "full_track_count": len(full), "excluded_v1_excerpt_count": len(excerpt_ids), "license_files": [str(p.relative_to(root)) for p in licenses], "metadata_count": len(metadata)}


def readiness(musdb_archive: str | Path, medley_root: str | Path) -> dict:
    """Stop-gate validation; never downloads copyrighted assets."""
    return {"musdb18": inspect_musdb_archive(musdb_archive), "medleydb": inspect_medleydb(medley_root)}


def write_manifest(rows: Iterable[SourceTrack], path: str | Path) -> str:
    frame = pd.DataFrame([asdict(row) for row in rows]).sort_values(["corpus", "track_id"])
    if frame["track_id"].duplicated().any():
        raise CorpusReadinessError("duplicate normalized track IDs")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return sha256_file(path)
