"""FMA Large source accounting for Stage 5A."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from .manifest import _probe_duration, _sha256_file, discover_audio_files, load_fma_metadata
from .stage4a_sampling import MINIMUM_SAMPLES, SAMPLE_RATE
from .stage5a_materialize import TrackInput


MANIFEST_SCHEMA_VERSION = "stage5a-fma-large-manifest-v1"
MANIFEST_COLUMNS = [
    "track_id",
    "relative_audio_path",
    "source_audio_sha256",
    "file_size_bytes",
    "duration_sec",
    "metadata_subset",
    "status",
    "detail",
]
ELIGIBLE = "ELIGIBLE"


def _logical_hash(frame: pd.DataFrame, corpus_version: str) -> str:
    records = []
    for row in frame.to_dict(orient="records"):
        records.append(
            {
                key: (None if pd.isna(value) else value)
                for key, value in row.items()
            }
        )
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "corpus": "fma_large",
        "corpus_version": corpus_version,
        "records": records,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_fma_large_manifest(
    audio_dir: str | Path,
    metadata_csv: str | Path,
    output_path: str | Path,
    *,
    corpus_version: str,
) -> tuple[pd.DataFrame, dict]:
    """Account for the union of official FMA Large IDs and discovered files."""
    audio_root = Path(audio_dir)
    metadata = load_fma_metadata(metadata_csv)
    # FMA's subset value records the smallest nested tier containing a track.
    # The Large download contains small + medium + large, so every official
    # metadata identity is expected rather than only rows literally labelled
    # ``large``.
    expected = metadata
    discovered: dict[int, list[Path]] = {}
    for track_id, path in discover_audio_files(audio_root):
        discovered.setdefault(track_id, []).append(path)

    rows: list[dict] = []
    for track_id in sorted(set(int(value) for value in expected.index) | set(discovered)):
        paths = discovered.get(track_id, [])
        subset = str(metadata.loc[track_id, "subset"]) if track_id in metadata.index else ""
        base = {
            "track_id": track_id,
            "relative_audio_path": "",
            "source_audio_sha256": "",
            "file_size_bytes": 0,
            "duration_sec": None,
            "metadata_subset": subset,
            "status": "",
            "detail": "",
        }
        if not paths:
            row = base | {"status": "MISSING_AUDIO", "detail": "official FMA Large metadata row has no discovered source file"}
        elif len(paths) > 1:
            row = base | {
                "status": "DUPLICATE_SOURCE_ID",
                "detail": json.dumps([str(path.relative_to(audio_root)) for path in paths]),
            }
        else:
            path = paths[0]
            relative = str(path.relative_to(audio_root))
            digest = _sha256_file(path)
            decode_status, duration = _probe_duration(path)
            common = base | {
                "relative_audio_path": relative,
                "source_audio_sha256": digest,
                "file_size_bytes": int(path.stat().st_size),
                "duration_sec": duration,
            }
            if track_id not in metadata.index:
                row = common | {"status": "MISSING_METADATA", "detail": "source track is absent from official metadata"}
            elif decode_status != "SUCCESS":
                row = common | {"status": "DECODE_FAILED", "detail": "audio header probe failed"}
            elif duration is None or duration * SAMPLE_RATE < MINIMUM_SAMPLES:
                row = common | {"status": "TOO_SHORT", "detail": f"duration {duration!r} cannot support frozen sampling"}
            else:
                row = common | {"status": ELIGIBLE, "detail": ""}
        rows.append(row)

    frame = pd.DataFrame(rows, columns=MANIFEST_COLUMNS).sort_values("track_id").reset_index(drop=True)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    status_counts = {
        str(status): int(count)
        for status, count in frame.groupby("status", dropna=False).size().sort_index().items()
    }
    summary = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "corpus": "fma_large",
        "corpus_version": corpus_version,
        "official_fma_large_metadata_tracks": int(len(expected)),
        "discovered_source_tracks": int(len(discovered)),
        "accounted_track_identities": int(len(frame)),
        "eligible_tracks": int((frame.status == ELIGIBLE).sum()),
        "status_counts": status_counts,
        "manifest_logical_sha256": _logical_hash(frame, corpus_version),
        "parquet_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "path": str(output),
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return frame, summary


def eligible_tracks(frame: pd.DataFrame, audio_root: str | Path) -> list[TrackInput]:
    eligible = frame[frame.status == ELIGIBLE].sort_values("track_id")
    return [
        TrackInput(
            stable_track_id=str(int(row.track_id)),
            audio_path=Path(audio_root) / row.relative_audio_path,
            source_audio_sha256=str(row.source_audio_sha256),
        )
        for row in eligible.itertuples(index=False)
    ]


def load_fma_large_manifest(path: str | Path) -> tuple[pd.DataFrame, dict]:
    path = Path(path)
    frame = pd.read_parquet(path).sort_values("track_id").reset_index(drop=True)
    missing = set(MANIFEST_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"manifest is missing columns: {sorted(missing)}")
    summary_path = path.with_suffix(path.suffix + ".json")
    summary = json.loads(summary_path.read_text())
    actual = _logical_hash(frame[MANIFEST_COLUMNS], summary["corpus_version"])
    if actual != summary["manifest_logical_sha256"]:
        raise ValueError("FMA Large manifest logical hash mismatch")
    return frame[MANIFEST_COLUMNS], summary


def deterministic_smoke_tracks(
    frame: pd.DataFrame,
    audio_root: str | Path,
    *,
    manifest_sha256: str,
    count: int = 100,
) -> list[TrackInput]:
    if count < 1 or count > 500:
        raise ValueError("smoke count must be between 1 and 500")
    tracks = eligible_tracks(frame, audio_root)
    ranked = sorted(
        tracks,
        key=lambda track: hashlib.sha256(
            f"{manifest_sha256}|{track.stable_track_id}".encode()
        ).hexdigest(),
    )[:count]
    return sorted(ranked, key=lambda track: track.stable_track_id)
