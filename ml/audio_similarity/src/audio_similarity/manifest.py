"""Deterministic FMA manifest construction (Phase 1 doc, section 6).

Identity is the FMA track id parsed from the filename — never filesystem
traversal order. Genre/split/subset metadata is evaluation-only and joined
for diagnostics; it never feeds the encoder or retrieval.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import torchaudio

MANIFEST_COLUMNS = [
    "track_id",
    "relative_audio_path",
    "audio_sha256",
    "file_size_bytes",
    "decode_status",
    "duration_sec",
    "title",
    "artist",
    "album",
    "top_genre",
    "fma_split",
    "subset",
]

STATUS_OK = "SUCCESS"
STATUS_DECODE_FAILED = "DECODE_FAILED"
STATUS_MISSING_METADATA = "SUCCESS"  # audio ok; metadata absence recorded via empty fields


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_duration(path: Path) -> tuple[str, float | None]:
    try:
        info = torchaudio.info(str(path))
        if info.num_frames <= 0:
            return STATUS_DECODE_FAILED, None
        return STATUS_OK, info.num_frames / info.sample_rate
    except Exception:
        return STATUS_DECODE_FAILED, None


def load_fma_metadata(metadata_csv: str | Path) -> pd.DataFrame:
    """Load tracks.csv and reduce it to per-track evaluation metadata."""
    tracks = pd.read_csv(metadata_csv, index_col=0, header=[0, 1])
    frame = pd.DataFrame(
        {
            "title": tracks[("track", "title")],
            "artist": tracks[("artist", "name")],
            "album": tracks[("album", "title")],
            "top_genre": tracks[("track", "genre_top")],
            "fma_split": tracks[("set", "split")],
            "subset": tracks[("set", "subset")],
        }
    )
    frame.index.name = "track_id"
    return frame


def discover_audio_files(audio_dir: str | Path, suffixes: tuple[str, ...] = (".mp3", ".wav")) -> list[tuple[int, Path]]:
    """Return (track_id, path) sorted by track_id; ids parsed from stems."""
    entries: list[tuple[int, Path]] = []
    for path in sorted(Path(audio_dir).rglob("*")):
        if path.suffix.lower() not in suffixes or not path.is_file():
            continue
        try:
            track_id = int(path.stem)
        except ValueError:
            continue
        entries.append((track_id, path))
    entries.sort(key=lambda item: item[0])
    return entries


def build_manifest(
    audio_dir: str | Path,
    metadata_csv: str | Path,
    output_path: str | Path,
    audio_root: str | Path | None = None,
) -> pd.DataFrame:
    """Build the frozen experiment manifest and write it as Parquet."""
    audio_root = Path(audio_root) if audio_root else Path(audio_dir)
    metadata = load_fma_metadata(metadata_csv)

    rows: list[dict] = []
    for track_id, path in discover_audio_files(audio_dir):
        decode_status, duration = _probe_duration(path)
        if track_id in metadata.index:
            meta = metadata.loc[track_id]
            meta_values = {
                "title": "" if pd.isna(meta["title"]) else str(meta["title"]),
                "artist": "" if pd.isna(meta["artist"]) else str(meta["artist"]),
                "album": "" if pd.isna(meta["album"]) else str(meta["album"]),
                "top_genre": "" if pd.isna(meta["top_genre"]) else str(meta["top_genre"]),
                "fma_split": "" if pd.isna(meta["fma_split"]) else str(meta["fma_split"]),
                "subset": "" if pd.isna(meta["subset"]) else str(meta["subset"]),
            }
        else:
            meta_values = {key: "" for key in ("title", "artist", "album", "top_genre", "fma_split", "subset")}
            meta_values["fma_split"] = "missing_metadata"

        rows.append(
            {
                "track_id": track_id,
                "relative_audio_path": str(path.relative_to(audio_root)),
                "audio_sha256": _sha256_file(path),
                "file_size_bytes": path.stat().st_size,
                "decode_status": decode_status,
                "duration_sec": duration,
                **meta_values,
            }
        )

    frame = pd.DataFrame(rows, columns=MANIFEST_COLUMNS).sort_values("track_id").reset_index(drop=True)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    return frame


def load_manifest(path: str | Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    frame = frame.sort_values("track_id").reset_index(drop=True)
    missing = set(MANIFEST_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"manifest {path} missing columns: {sorted(missing)}")
    return frame
