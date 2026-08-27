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


def _mix_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and "_MIX" in path.stem and path.suffix.lower() in {".wav", ".flac", ".mp3", ".aiff", ".aif"})


def _read_tracklist(metadata_root: Path, name: str) -> list[str]:
    path = metadata_root / "medleydb" / "resources" / name
    if not path.is_file():
        raise CorpusReadinessError(f"official MedleyDB tracklist absent: {path}")
    values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(values) != len(set(values)):
        raise CorpusReadinessError(f"duplicate IDs in official {name}")
    return values


def _load_metadata(metadata_root: Path, track_id: str) -> tuple[Path, dict]:
    path = metadata_root / "medleydb" / "data" / "Metadata" / f"{track_id}_METADATA.yaml"
    if not path.is_file():
        raise CorpusReadinessError(f"official metadata absent for {track_id}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise CorpusReadinessError(f"invalid metadata YAML {path}: {exc}") from exc
    if not isinstance(payload, dict) or not payload.get("mix_filename"):
        raise CorpusReadinessError(f"metadata lacks mix_filename: {path}")
    return path, payload


def _git_revision(root: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CorpusReadinessError(f"MedleyDB metadata must retain its official git revision: {exc}") from exc


def inspect_medleydb(audio_root: str | Path, metadata_root: str | Path, expected_full: int = EXPECTED_MEDLEYDB2_FULL, expected_excerpts: int = EXPECTED_MEDLEYDB1_EXCERPTS, expected_revision: str | None = None) -> dict:
    """Validate the frozen V1+V2 release policy using official tracklists.

    The approved denominator is 122 V1 + 74 V2 - 17 V1 excerpts = 179.
    Six V2 rows marked ``excerpt: yes`` remain included by that explicit policy;
    this fact is surfaced in provenance instead of silently changing the count.
    """
    audio_root, metadata_root = Path(audio_root), Path(metadata_root)
    if not audio_root.is_dir():
        raise CorpusReadinessError(f"official MedleyDB 2.0 assets absent: {audio_root}")
    if not metadata_root.is_dir():
        raise CorpusReadinessError(f"official MedleyDB metadata absent: {metadata_root}")
    revision = _git_revision(metadata_root)
    if expected_revision and revision != expected_revision:
        raise CorpusReadinessError(f"MedleyDB metadata revision mismatch: expected {expected_revision}, found {revision}")
    licenses = sorted(path for path in metadata_root.iterdir() if path.is_file() and any(token in path.name.casefold() for token in ("license", "readme", "provenance")))
    if not licenses:
        raise CorpusReadinessError("MedleyDB license/provenance files absent")
    v1, v2 = _read_tracklist(metadata_root, "tracklist_v1.txt"), _read_tracklist(metadata_root, "tracklist_v2.txt")
    metadata: dict[str, tuple[Path, dict]] = {track_id: _load_metadata(metadata_root, track_id) for track_id in v1 + v2}
    v1_excerpts = [track_id for track_id in v1 if str(metadata[track_id][1].get("excerpt", "")).casefold() == "yes"]
    v2_excerpts = [track_id for track_id in v2 if str(metadata[track_id][1].get("excerpt", "")).casefold() == "yes"]
    if len(v1_excerpts) != expected_excerpts:
        raise CorpusReadinessError(f"MedleyDB expected {expected_excerpts} marked v1 excerpts, found {len(v1_excerpts)}")
    eligible = [track_id for track_id in v1 + v2 if track_id not in set(v1_excerpts)]
    if len(eligible) != expected_full:
        raise CorpusReadinessError(f"MedleyDB expected {expected_full} tracks after frozen v1-excerpt policy, found {len(eligible)}")
    mix_index: dict[str, list[Path]] = {}
    for path in _mix_files(audio_root):
        mix_index.setdefault(path.name, []).append(path)
    missing, ambiguous = [], []
    for track_id in eligible:
        filename = str(metadata[track_id][1]["mix_filename"])
        matches = mix_index.get(filename, [])
        if not matches:
            missing.append(track_id)
        elif len(matches) != 1:
            ambiguous.append(track_id)
    if missing or ambiguous:
        raise CorpusReadinessError(f"MedleyDB mixture set invalid: missing={len(missing)}, ambiguous={len(ambiguous)}; examples={(missing + ambiguous)[:5]}")
    metadata_hash = hashlib.sha256()
    source_files = [metadata_root / "medleydb" / "resources" / "tracklist_v1.txt", metadata_root / "medleydb" / "resources" / "tracklist_v2.txt", *[metadata[t][0] for t in v1 + v2], *licenses]
    for path in sorted(source_files):
        metadata_hash.update(str(path.relative_to(metadata_root)).encode() + b"\0" + bytes.fromhex(sha256_file(path)))
    return {"release": "MedleyDB_2.0", "audio_root": str(audio_root), "metadata_root": str(metadata_root), "metadata_git_revision": revision, "metadata_bundle_sha256": metadata_hash.hexdigest(), "tracklist_v1_count": len(v1), "tracklist_v2_count": len(v2), "eligible_track_count": len(eligible), "excluded_v1_excerpt_count": len(v1_excerpts), "included_v2_excerpt_count": len(v2_excerpts), "license_files": [str(p.relative_to(metadata_root)) for p in licenses]}


def readiness(musdb_archive: str | Path, medley_root: str | Path, medley_metadata_root: str | Path, medley_metadata_revision: str | None = None) -> dict:
    """Stop-gate validation; never downloads copyrighted assets."""
    return {"musdb18": inspect_musdb_archive(musdb_archive), "medleydb": inspect_medleydb(medley_root, medley_metadata_root, expected_revision=medley_metadata_revision)}


def write_manifest(rows: Iterable[SourceTrack], path: str | Path) -> str:
    frame = pd.DataFrame([asdict(row) for row in rows]).sort_values(["corpus", "track_id"])
    if frame["track_id"].duplicated().any():
        raise CorpusReadinessError("duplicate normalized track IDs")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return sha256_file(path)
