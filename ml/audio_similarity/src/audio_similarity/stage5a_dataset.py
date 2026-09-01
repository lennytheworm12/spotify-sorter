"""Deterministic portable representation dataset for Stage 5A."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .stage5a_cache import validate_vector


SCHEMA_VERSION = "audio-representation-dataset-v1"
DEFAULT_ROWS_PER_SHARD = 10_000


class Stage5ADatasetError(ValueError):
    """Raised when final records are incomplete, invalid, or duplicated."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema(clap_dimension: int, muq_dimension: int) -> pa.Schema:
    metadata = {
        b"schema_version": SCHEMA_VERSION.encode(),
        b"shard_policy": b"sorted-stable-track-id-fixed-rows-v1",
    }
    return pa.schema(
        [
            pa.field("corpus", pa.string(), nullable=False),
            pa.field("corpus_version", pa.string(), nullable=False),
            pa.field("stable_track_id", pa.string(), nullable=False),
            pa.field("source_audio_sha256", pa.string(), nullable=False),
            pa.field("canonical_pcm_sha256", pa.string(), nullable=False),
            pa.field("representation_version", pa.string(), nullable=False),
            pa.field("contract_artifact_sha256", pa.string(), nullable=False),
            pa.field("vector_contract_sha256", pa.string(), nullable=False),
            pa.field("preprocessing_version", pa.string(), nullable=False),
            pa.field("sampling_version", pa.string(), nullable=False),
            pa.field("segment_centers_sec", pa.list_(pa.int16(), 3), nullable=False),
            pa.field("aggregation_version", pa.string(), nullable=False),
            pa.field("clap_encoder_id", pa.string(), nullable=False),
            pa.field("clap_provenance_json", pa.string(), nullable=False),
            pa.field("clap_embedding", pa.list_(pa.float32(), clap_dimension), nullable=False),
            pa.field("clap_embedding_dtype", pa.string(), nullable=False),
            pa.field("clap_embedding_dimension", pa.int32(), nullable=False),
            pa.field("muq_encoder_id", pa.string(), nullable=False),
            pa.field("muq_provenance_json", pa.string(), nullable=False),
            pa.field("muq_embedding", pa.list_(pa.float32(), muq_dimension), nullable=False),
            pa.field("muq_embedding_dtype", pa.string(), nullable=False),
            pa.field("muq_embedding_dimension", pa.int32(), nullable=False),
            pa.field("status", pa.string(), nullable=False),
            pa.field("representation_identity", pa.string(), nullable=False),
            pa.field("materialized_at_unix", pa.int64(), nullable=False),
        ],
        metadata=metadata,
    )


def _validated(records: list[dict], clap_dimension: int, muq_dimension: int) -> list[dict]:
    ordered = sorted(
        records,
        key=lambda row: (
            str(row["corpus"]),
            str(row["corpus_version"]),
            str(row["stable_track_id"]),
            str(row["representation_identity"]),
        ),
    )
    identities: set[str] = set()
    track_keys: set[tuple[str, str, str]] = set()
    for row in ordered:
        identity = str(row["representation_identity"])
        track_key = (str(row["corpus"]), str(row["corpus_version"]), str(row["stable_track_id"]))
        if identity in identities or track_key in track_keys:
            raise Stage5ADatasetError(f"duplicate representation record for {track_key}")
        identities.add(identity)
        track_keys.add(track_key)
        if row.get("status") != "SUCCESS":
            raise Stage5ADatasetError("the final dataset may only contain SUCCESS records")
        centers = [int(value) for value in row["segment_centers_sec"]]
        if centers != [5, 15, 25]:
            raise Stage5ADatasetError(f"invalid Audio Representation v1 centers: {centers}")
        row["segment_centers_sec"] = centers
        row["clap_embedding"] = validate_vector(row["clap_embedding"], clap_dimension).tolist()
        row["muq_embedding"] = validate_vector(row["muq_embedding"], muq_dimension).tolist()
    return ordered


def write_dataset(
    records: list[dict],
    output_dir: str | Path,
    *,
    clap_dimension: int,
    muq_dimension: int,
    rows_per_shard: int = DEFAULT_ROWS_PER_SHARD,
) -> dict:
    """Atomically replace ``output_dir`` with deterministic sorted shards."""
    if rows_per_shard < 1:
        raise Stage5ADatasetError("rows_per_shard must be positive")
    output = Path(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    backup = output.with_name(f".{output.name}.previous-{os.getpid()}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    schema = _schema(clap_dimension, muq_dimension)
    ordered = _validated(records, clap_dimension, muq_dimension)
    shards: list[dict] = []
    try:
        for index, offset in enumerate(range(0, len(ordered), rows_per_shard)):
            rows = ordered[offset : offset + rows_per_shard]
            name = f"part-{index:05d}.parquet"
            path = temporary / name
            table = pa.Table.from_pylist(rows, schema=schema)
            pq.write_table(
                table,
                path,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                data_page_version="1.0",
            )
            shards.append(
                {
                    "path": name,
                    "rows": len(rows),
                    "first_track_id": str(rows[0]["stable_track_id"]),
                    "last_track_id": str(rows[-1]["stable_track_id"]),
                    "sha256": _sha256(path),
                }
            )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "shard_policy": "sort by corpus/corpus_version/stable_track_id/representation_identity; fixed rows per shard",
            "rows_per_shard": rows_per_shard,
            "record_count": len(ordered),
            "clap_dimension": clap_dimension,
            "muq_dimension": muq_dimension,
            "shards": shards,
        }
        manifest_path = temporary / "dataset_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        manifest["dataset_manifest_sha256"] = _sha256(manifest_path)
        if output.exists():
            output.rename(backup)
        temporary.rename(output)
        if backup.exists():
            shutil.rmtree(backup)
        return manifest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        if backup.exists() and not output.exists():
            backup.rename(output)
        raise


def read_dataset(output_dir: str | Path) -> list[dict]:
    output = Path(output_dir)
    manifest = json.loads((output / "dataset_manifest.json").read_text())
    rows: list[dict] = []
    for shard in manifest["shards"]:
        rows.extend(pq.read_table(output / shard["path"]).to_pylist())
    return rows
