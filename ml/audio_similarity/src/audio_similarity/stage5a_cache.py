"""Provenance-bound SQLite work state for Stage 5A materialization."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

import numpy as np

SEGMENT_SCHEMA = """CREATE TABLE IF NOT EXISTS segments (
 encoder_analysis_identity TEXT NOT NULL,
 corpus TEXT NOT NULL, corpus_version TEXT NOT NULL, stable_track_id TEXT NOT NULL,
 source_audio_sha256 TEXT NOT NULL, canonical_pcm_sha256 TEXT NOT NULL,
 vector_contract_sha256 TEXT NOT NULL, representation_version TEXT NOT NULL,
 preprocessing_version TEXT NOT NULL, sampling_version TEXT NOT NULL,
 centers_json TEXT NOT NULL, aggregation_version TEXT NOT NULL,
 encoder_id TEXT NOT NULL, encoder_provenance_json TEXT NOT NULL,
 encoder_provenance_sha256 TEXT NOT NULL, embedding_dtype TEXT NOT NULL,
 embedding_dimension INTEGER NOT NULL, center_sec INTEGER NOT NULL,
 start_sample INTEGER NOT NULL, end_sample INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('SUCCESS','FAILED')),
 embedding BLOB, embedding_sha256 TEXT NOT NULL,
 failure_category TEXT NOT NULL, failure_detail TEXT NOT NULL,
 retryable INTEGER NOT NULL, attempt_count INTEGER NOT NULL,
 encode_ms REAL NOT NULL, updated_at INTEGER NOT NULL,
 PRIMARY KEY(encoder_analysis_identity, center_sec)
)"""

POOLED_SCHEMA = """CREATE TABLE IF NOT EXISTS pooled (
 encoder_analysis_identity TEXT PRIMARY KEY,
 corpus TEXT NOT NULL, corpus_version TEXT NOT NULL, stable_track_id TEXT NOT NULL,
 source_audio_sha256 TEXT NOT NULL, canonical_pcm_sha256 TEXT NOT NULL,
 vector_contract_sha256 TEXT NOT NULL, representation_version TEXT NOT NULL,
 preprocessing_version TEXT NOT NULL, sampling_version TEXT NOT NULL,
 centers_json TEXT NOT NULL, aggregation_version TEXT NOT NULL,
 encoder_id TEXT NOT NULL, encoder_provenance_json TEXT NOT NULL,
 encoder_provenance_sha256 TEXT NOT NULL, embedding_dtype TEXT NOT NULL,
 embedding_dimension INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('SUCCESS','FAILED')),
 embedding BLOB, embedding_sha256 TEXT NOT NULL,
 failure_category TEXT NOT NULL, failure_detail TEXT NOT NULL,
 aggregate_ms REAL NOT NULL, updated_at INTEGER NOT NULL
)"""

TRACK_SCHEMA = """CREATE TABLE IF NOT EXISTS tracks (
 representation_identity TEXT PRIMARY KEY,
 corpus TEXT NOT NULL, corpus_version TEXT NOT NULL, stable_track_id TEXT NOT NULL,
 source_audio_sha256 TEXT NOT NULL, canonical_pcm_sha256 TEXT NOT NULL,
 vector_contract_sha256 TEXT NOT NULL, representation_version TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('SUCCESS','FAILED')),
 failure_category TEXT NOT NULL, failure_detail TEXT NOT NULL,
 retryable INTEGER NOT NULL, materialized_at INTEGER, updated_at INTEGER NOT NULL,
 UNIQUE(corpus, corpus_version, stable_track_id, source_audio_sha256, vector_contract_sha256)
)"""
METADATA_SCHEMA = """CREATE TABLE IF NOT EXISTS cache_metadata (
 key TEXT PRIMARY KEY, value TEXT NOT NULL
)"""


class Stage5ACacheError(ValueError):
    """Raised when cached state violates the Stage 5A vector contract."""


def validate_vector(vector, dimension: int) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32)
    if array.shape != (dimension,):
        raise Stage5ACacheError(
            f"expected {dimension}-D embedding, got shape {array.shape}"
        )
    if not np.isfinite(array).all():
        raise Stage5ACacheError("embedding contains non-finite values")
    norm = float(np.linalg.norm(array.astype(np.float64)))
    if norm <= 0:
        raise Stage5ACacheError("embedding has zero norm")
    return (array / norm).astype("<f4")


def vector_blob(vector, dimension: int) -> tuple[bytes, str]:
    array = validate_vector(vector, dimension)
    blob = array.tobytes()
    return blob, hashlib.sha256(blob).hexdigest()


class Stage5ACache:
    schema_version = "stage5a-work-cache-sqlite-v1"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(SEGMENT_SCHEMA)
        self.db.execute(POOLED_SCHEMA)
        self.db.execute(TRACK_SCHEMA)
        self.db.execute(METADATA_SCHEMA)
        saved = self.db.execute(
            "SELECT value FROM cache_metadata WHERE key='schema_version'"
        ).fetchone()
        if saved is not None and saved[0] != self.schema_version:
            self.db.close()
            raise Stage5ACacheError(
                f"cache schema is {saved[0]!r}, expected {self.schema_version!r}"
            )
        self.db.execute(
            "INSERT OR IGNORE INTO cache_metadata VALUES ('schema_version', ?)",
            (self.schema_version,),
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def successful_track(
        self,
        *,
        corpus: str,
        corpus_version: str,
        stable_track_id: str,
        source_audio_sha256: str,
        vector_contract_sha256: str,
    ) -> sqlite3.Row | None:
        return self.db.execute(
            """SELECT * FROM tracks WHERE corpus=? AND corpus_version=?
               AND stable_track_id=? AND source_audio_sha256=?
               AND vector_contract_sha256=? AND status='SUCCESS'""",
            (
                corpus,
                corpus_version,
                stable_track_id,
                source_audio_sha256,
                vector_contract_sha256,
            ),
        ).fetchone()

    def successful_segments(self, encoder_analysis_identity: str) -> dict[int, np.ndarray]:
        rows = self.db.execute(
            """SELECT center_sec, embedding, embedding_dimension FROM segments
               WHERE encoder_analysis_identity=? AND status='SUCCESS'""",
            (encoder_analysis_identity,),
        )
        return {
            int(row["center_sec"]): validate_vector(
                np.frombuffer(row["embedding"], dtype="<f4").copy(),
                int(row["embedding_dimension"]),
            )
            for row in rows
        }

    def pooled_vector(self, encoder_analysis_identity: str) -> np.ndarray | None:
        row = self.db.execute(
            """SELECT embedding, embedding_dimension FROM pooled
               WHERE encoder_analysis_identity=? AND status='SUCCESS'""",
            (encoder_analysis_identity,),
        ).fetchone()
        if row is None:
            return None
        return validate_vector(
            np.frombuffer(row["embedding"], dtype="<f4").copy(),
            int(row["embedding_dimension"]),
        )

    def _identity_fields(self, identity: dict) -> dict:
        required = (
            "encoder_analysis_identity",
            "corpus",
            "corpus_version",
            "stable_track_id",
            "source_audio_sha256",
            "canonical_pcm_sha256",
            "vector_contract_sha256",
            "representation_version",
            "preprocessing_version",
            "sampling_version",
            "centers_json",
            "aggregation_version",
            "encoder_id",
            "encoder_provenance_json",
            "encoder_provenance_sha256",
            "embedding_dtype",
            "embedding_dimension",
        )
        missing = [name for name in required if name not in identity]
        if missing:
            raise Stage5ACacheError(f"missing cache identity fields: {missing}")
        return {name: identity[name] for name in required}

    def record_segment(
        self,
        identity: dict,
        *,
        center_sec: int,
        start_sample: int,
        end_sample: int,
        status: str,
        embedding=None,
        failure_category: str = "",
        failure_detail: str = "",
        retryable: bool = True,
        encode_ms: float = 0.0,
    ) -> None:
        fields = self._identity_fields(identity)
        existing = self.db.execute(
            """SELECT attempt_count FROM segments
               WHERE encoder_analysis_identity=? AND center_sec=?""",
            (fields["encoder_analysis_identity"], center_sec),
        ).fetchone()
        attempts = int(existing[0]) + 1 if existing else 1
        blob, digest = (None, "")
        if status == "SUCCESS":
            blob, digest = vector_blob(embedding, int(fields["embedding_dimension"]))
            failure_category = failure_detail = ""
        elif status != "FAILED":
            raise Stage5ACacheError(f"invalid segment status {status}")
        row = fields | {
            "center_sec": int(center_sec),
            "start_sample": int(start_sample),
            "end_sample": int(end_sample),
            "status": status,
            "embedding": blob,
            "embedding_sha256": digest,
            "failure_category": failure_category,
            "failure_detail": str(failure_detail)[:1000],
            "retryable": int(bool(retryable)),
            "attempt_count": attempts,
            "encode_ms": float(encode_ms),
            "updated_at": int(time.time()),
        }
        names = list(row)
        self.db.execute(
            f"INSERT OR REPLACE INTO segments ({','.join(names)}) "
            f"VALUES ({','.join('?' for _ in names)})",
            [row[name] for name in names],
        )
        self.db.commit()

    def record_pooled(
        self,
        identity: dict,
        *,
        status: str,
        embedding=None,
        failure_category: str = "",
        failure_detail: str = "",
        aggregate_ms: float = 0.0,
    ) -> None:
        fields = self._identity_fields(identity)
        blob, digest = (None, "")
        if status == "SUCCESS":
            blob, digest = vector_blob(embedding, int(fields["embedding_dimension"]))
            failure_category = failure_detail = ""
        elif status != "FAILED":
            raise Stage5ACacheError(f"invalid pooled status {status}")
        row = fields | {
            "status": status,
            "embedding": blob,
            "embedding_sha256": digest,
            "failure_category": failure_category,
            "failure_detail": str(failure_detail)[:1000],
            "aggregate_ms": float(aggregate_ms),
            "updated_at": int(time.time()),
        }
        names = list(row)
        self.db.execute(
            f"INSERT OR REPLACE INTO pooled ({','.join(names)}) "
            f"VALUES ({','.join('?' for _ in names)})",
            [row[name] for name in names],
        )
        self.db.commit()

    def record_track(
        self,
        *,
        representation_identity: str,
        corpus: str,
        corpus_version: str,
        stable_track_id: str,
        source_audio_sha256: str,
        canonical_pcm_sha256: str,
        vector_contract_sha256: str,
        representation_version: str,
        status: str,
        failure_category: str = "",
        failure_detail: str = "",
        retryable: bool = True,
    ) -> None:
        if status not in ("SUCCESS", "FAILED"):
            raise Stage5ACacheError(f"invalid track status {status}")
        now = int(time.time())
        previous = self.db.execute(
            "SELECT materialized_at FROM tracks WHERE representation_identity=?",
            (representation_identity,),
        ).fetchone()
        materialized_at = (
            (int(previous[0]) if previous and previous[0] is not None else now)
            if status == "SUCCESS"
            else None
        )
        self.db.execute(
            """INSERT OR REPLACE INTO tracks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                representation_identity,
                corpus,
                corpus_version,
                stable_track_id,
                source_audio_sha256,
                canonical_pcm_sha256,
                vector_contract_sha256,
                representation_version,
                status,
                "" if status == "SUCCESS" else failure_category,
                "" if status == "SUCCESS" else str(failure_detail)[:1000],
                int(bool(retryable)),
                materialized_at,
                now,
            ),
        )
        self.db.commit()

    def segment_attempts(self, encoder_analysis_identity: str, center_sec: int) -> int:
        row = self.db.execute(
            """SELECT attempt_count FROM segments
               WHERE encoder_analysis_identity=? AND center_sec=?""",
            (encoder_analysis_identity, center_sec),
        ).fetchone()
        return int(row[0]) if row else 0

    def failure_counts(self) -> dict[str, int]:
        rows = self.db.execute(
            """SELECT failure_category, count(*) FROM tracks
               WHERE status='FAILED' GROUP BY failure_category ORDER BY failure_category"""
        )
        return {str(category): int(count) for category, count in rows}

    def manifest(self) -> dict:
        counts = {}
        for table in ("segments", "pooled", "tracks"):
            total = self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            success = self.db.execute(
                f"SELECT count(*) FROM {table} WHERE status='SUCCESS'"
            ).fetchone()[0]
            counts[table] = {"rows": int(total), "success": int(success)}
        self.db.execute("PRAGMA wal_checkpoint(FULL)")
        return {
            "schema_version": self.schema_version,
            "path": str(self.path),
            "tables": counts,
            "failure_categories": self.failure_counts(),
            "sqlite_sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
        }
