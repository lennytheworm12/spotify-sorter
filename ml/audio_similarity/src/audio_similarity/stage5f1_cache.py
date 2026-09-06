"""Versioned, integrity-checked SQLite cache for Stage 5F.1."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .energy_motion_config import canonical_json, canonical_sha256


SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_cache (
    feature_key TEXT PRIMARY KEY,
    source_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quarantine (
    feature_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload_sha256 TEXT,
    quarantined_at_utc TEXT NOT NULL
);
"""


def feature_key(
    source_sha256: str, extractor_id: str, algorithm_spec_sha256: str,
    implementation_sha256: str, extraction_config_sha256: str,
    environment_sha256: str,
) -> str:
    return canonical_sha256([
        source_sha256, extractor_id, algorithm_spec_sha256,
        implementation_sha256, extraction_config_sha256, environment_sha256,
    ])


class FeatureCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def get(self, key: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT payload, payload_sha256 FROM feature_cache WHERE feature_key=?", (key,)
        ).fetchone()
        if row is None:
            return None
        payload, expected = row
        observed = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if observed != expected:
            self.db.execute(
                "INSERT INTO quarantine VALUES (?, ?, ?, datetime('now'))",
                (key, "PAYLOAD_HASH_MISMATCH", expected),
            )
            self.db.execute("DELETE FROM feature_cache WHERE feature_key=?", (key,))
            self.db.commit()
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            self.db.execute(
                "INSERT INTO quarantine VALUES (?, ?, ?, datetime('now'))",
                (key, "INVALID_JSON", expected),
            )
            self.db.execute("DELETE FROM feature_cache WHERE feature_key=?", (key,))
            self.db.commit()
            return None

    def put(self, key: str, source_sha256: str, payload: dict[str, Any]) -> None:
        encoded = canonical_json(payload).decode("utf-8")
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        self.db.execute(
            "INSERT OR REPLACE INTO feature_cache VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (key, source_sha256, payload["status"], encoded, digest),
        )
        self.db.commit()
