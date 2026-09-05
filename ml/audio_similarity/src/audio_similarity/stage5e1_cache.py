"""Resumable local vector cache for Stage 5E.1 experimental arms."""
from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Any

import numpy as np

from .stage5a_cache import validate_vector, vector_blob


VECTOR_SCHEMA = """CREATE TABLE IF NOT EXISTS vectors (
 representation_identity TEXT PRIMARY KEY,
 spotify_track_id TEXT NOT NULL, arm TEXT NOT NULL, source_sha256 TEXT NOT NULL,
 config_sha256 TEXT NOT NULL, sampling_plan_sha256 TEXT NOT NULL,
 checkpoint_sha256 TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('SUCCESS','FAILED')),
 embedding BLOB, embedding_sha256 TEXT NOT NULL, embedding_dimension INTEGER NOT NULL,
 view_count INTEGER NOT NULL, inference_seconds REAL NOT NULL,
 failure_category TEXT NOT NULL, failure_detail TEXT NOT NULL, updated_at INTEGER NOT NULL,
 UNIQUE(spotify_track_id, arm, source_sha256, config_sha256, sampling_plan_sha256)
)"""
VIEW_SCHEMA = """CREATE TABLE IF NOT EXISTS views (
 representation_identity TEXT NOT NULL, view_index INTEGER NOT NULL,
 view_kind TEXT NOT NULL, start_unit INTEGER NOT NULL, end_unit INTEGER NOT NULL,
 embedding BLOB NOT NULL, embedding_sha256 TEXT NOT NULL,
 embedding_dimension INTEGER NOT NULL, inference_seconds REAL NOT NULL,
 PRIMARY KEY(representation_identity, view_index)
)"""
METADATA_SCHEMA = """CREATE TABLE IF NOT EXISTS metadata (
 key TEXT PRIMARY KEY, value TEXT NOT NULL
)"""


def representation_identity(
    *,
    spotify_track_id: str,
    arm: str,
    source_sha256: str,
    config_sha256: str,
    sampling_plan_sha256: str,
    checkpoint_sha256: str,
) -> str:
    fields = (
        spotify_track_id,
        arm,
        source_sha256,
        config_sha256,
        sampling_plan_sha256,
        checkpoint_sha256,
    )
    if any(not value for value in fields):
        raise ValueError("complete Stage 5E.1 vector identity is required")
    return hashlib.sha256("\0".join(fields).encode()).hexdigest()


class Stage5E1Cache:
    schema_version = "stage5e1-vector-cache-v1"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(VECTOR_SCHEMA)
        self.db.execute(VIEW_SCHEMA)
        self.db.execute(METADATA_SCHEMA)
        row = self.db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
        if row and row[0] != self.schema_version:
            self.db.close()
            raise ValueError("incompatible Stage 5E.1 cache schema")
        self.db.execute(
            "INSERT OR IGNORE INTO metadata VALUES ('schema_version', ?)",
            (self.schema_version,),
        )
        self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.db.close()

    def vector(self, identity: str) -> np.ndarray | None:
        row = self.db.execute(
            "SELECT embedding,embedding_dimension,embedding_sha256 FROM vectors "
            "WHERE representation_identity=? AND status='SUCCESS'",
            (identity,),
        ).fetchone()
        if row is None:
            return None
        blob = bytes(row["embedding"])
        if hashlib.sha256(blob).hexdigest() != row["embedding_sha256"]:
            raise ValueError("Stage 5E.1 cached vector hash differs")
        return validate_vector(
            np.frombuffer(blob, dtype="<f4").copy(), int(row["embedding_dimension"])
        )

    def views(self, identity: str) -> dict[int, np.ndarray]:
        output = {}
        for row in self.db.execute(
            "SELECT * FROM views WHERE representation_identity=? ORDER BY view_index",
            (identity,),
        ):
            blob = bytes(row["embedding"])
            if hashlib.sha256(blob).hexdigest() != row["embedding_sha256"]:
                raise ValueError("Stage 5E.1 cached view hash differs")
            output[int(row["view_index"])] = validate_vector(
                np.frombuffer(blob, dtype="<f4").copy(), int(row["embedding_dimension"])
            )
        return output

    def record_view(
        self,
        identity: str,
        *,
        view_index: int,
        view_kind: str,
        start_unit: int,
        end_unit: int,
        embedding: np.ndarray,
        inference_seconds: float,
    ) -> None:
        blob, digest = vector_blob(embedding, 512)
        self.db.execute(
            "INSERT OR REPLACE INTO views VALUES (?,?,?,?,?,?,?,?,?)",
            (
                identity,
                view_index,
                view_kind,
                start_unit,
                end_unit,
                blob,
                digest,
                512,
                float(inference_seconds),
            ),
        )
        self.db.commit()

    def record_vector(
        self,
        identity: str,
        identity_fields: dict[str, str],
        *,
        status: str,
        embedding: np.ndarray | None = None,
        view_count: int = 0,
        inference_seconds: float = 0.0,
        failure_category: str = "",
        failure_detail: str = "",
    ) -> None:
        if status == "SUCCESS":
            if embedding is None:
                raise ValueError("successful Stage 5E.1 vector requires an embedding")
            blob, digest = vector_blob(embedding, 512)
            failure_category = failure_detail = ""
        elif status == "FAILED":
            blob, digest = None, ""
        else:
            raise ValueError("invalid Stage 5E.1 vector status")
        row: dict[str, Any] = {
            "representation_identity": identity,
            **identity_fields,
            "status": status,
            "embedding": blob,
            "embedding_sha256": digest,
            "embedding_dimension": 512,
            "view_count": int(view_count),
            "inference_seconds": float(inference_seconds),
            "failure_category": failure_category,
            "failure_detail": str(failure_detail)[:2000],
            "updated_at": int(time.time()),
        }
        names = list(row)
        self.db.execute(
            f"INSERT OR REPLACE INTO vectors ({','.join(names)}) "
            f"VALUES ({','.join('?' for _ in names)})",
            [row[name] for name in names],
        )
        self.db.commit()

    def summary(self) -> dict[str, Any]:
        statuses = {
            f"{row['arm']}:{row['status']}": int(row["count"])
            for row in self.db.execute(
                "SELECT arm,status,count(*) AS count FROM vectors GROUP BY arm,status"
            )
        }
        return {
            "schema_version": self.schema_version,
            "vector_status_counts": statuses,
            "view_vector_count": self.db.execute("SELECT count(*) FROM views").fetchone()[0],
        }
