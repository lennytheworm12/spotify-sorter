"""Frozen-evidence GLAP Stage 2B materialization and resumable cache."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from .glap_encoder import GLAP_DIMENSION, GlapAudioEncoder, sha256_file
from .stage2b_audio import canonical_pcm, float32_le_bytes
from .stage2b_contract import ContractError


CACHE_SCHEMA_VERSION = "glap-stage2b-cache-sqlite-v1"
RESAMPLING_VERSION = "torchaudio_functional_resample_2.6.0_v1"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"


class GlapCacheError(ContractError):
    """The challenger cache contains incompatible or corrupted state."""


def load_glap_contract(path: str | Path, root: str | Path, *, validate_evidence: bool = True) -> dict[str, Any]:
    path, root = Path(path), Path(root)
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("experiment_id") != "glap_stage2b_challenger_v1":
        raise ContractError("unexpected GLAP challenger experiment ID")
    if contract.get("contract_status") != "FROZEN_PRE_OUTCOME":
        raise ContractError("GLAP challenger contract is not frozen pre-outcome")
    challenger = contract.get("challenger", {})
    if challenger.get("representation_namespace") != "glap_stage2b_challenger_v1":
        raise ContractError("GLAP representation namespace changed")
    if int(challenger.get("embedding_dimensions", 0)) != GLAP_DIMENSION:
        raise ContractError("GLAP embedding dimension changed")
    audio = contract.get("audio_evidence", {})
    if (audio.get("excerpt_start_sample_at_24000_hz"), audio.get("excerpt_end_sample_at_24000_hz")) != (
        300000,
        420000,
    ):
        raise ContractError("historical center5_v1 interval changed")
    if validate_evidence:
        for name, spec in contract["historical_evidence"].items():
            if not isinstance(spec, dict) or "path" not in spec or "sha256" not in spec:
                continue
            actual = sha256_file(root / spec["path"])
            if actual != spec["sha256"]:
                raise ContractError(f"frozen historical artifact hash mismatch for {name}: {actual}")
    return contract


def analysis_identity(contract: dict[str, Any], *, source_sha256: str, center5_pcm_sha256: str) -> str:
    challenger, audio = contract["challenger"], contract["audio_evidence"]
    payload = {
        "representation_namespace": challenger["representation_namespace"],
        "model_identifier": challenger["model_identifier"],
        "model_revision": challenger["model_revision"],
        "model_file_sha256": challenger["model_file_sha256"],
        "source_sha256": str(source_sha256),
        "center5_v1_pcm_sha256": str(center5_pcm_sha256),
        "canonical_preprocessing": audio["canonical_preprocessing"],
        "historical_excerpt": audio["historical_excerpt"],
        "resampling_version": RESAMPLING_VERSION,
        "embedding_dtype": challenger["stored_dtype"],
        "embedding_dimensions": int(challenger["embedding_dimensions"]),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _vector_payload(vector: np.ndarray) -> tuple[bytes, str]:
    array = np.asarray(vector, dtype="<f4")
    if array.shape != (GLAP_DIMENSION,) or not np.isfinite(array).all():
        raise GlapCacheError("invalid GLAP vector shape or values")
    norm = float(np.linalg.norm(array.astype(np.float64)))
    if norm <= 0 or abs(norm - 1.0) > 1e-3:
        raise GlapCacheError(f"invalid GLAP vector norm: {norm}")
    raw = array.tobytes(order="C")
    return raw, hashlib.sha256(raw).hexdigest()


CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
  track_id INTEGER NOT NULL,
  analysis_key TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  center5_pcm_sha256 TEXT NOT NULL,
  representation_version TEXT NOT NULL,
  model_identifier TEXT NOT NULL,
  model_revision TEXT NOT NULL,
  model_sha256 TEXT NOT NULL,
  preprocessing_version TEXT NOT NULL,
  sampling_version TEXT NOT NULL,
  resampling_version TEXT NOT NULL,
  embedding_dtype TEXT NOT NULL,
  embedding_dimension INTEGER NOT NULL,
  embedding BLOB,
  embedding_sha256 TEXT NOT NULL,
  status TEXT NOT NULL,
  failure_code TEXT NOT NULL,
  error_message TEXT NOT NULL,
  encode_ms REAL NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (track_id, analysis_key)
)
"""


class GlapEmbeddingCache:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute(CACHE_SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def valid_embedding(self, track_id: int, analysis_key: str) -> np.ndarray | None:
        row = self.db.execute(
            "SELECT embedding, embedding_sha256, embedding_dimension, embedding_dtype, status "
            "FROM embeddings WHERE track_id=? AND analysis_key=?",
            (int(track_id), str(analysis_key)),
        ).fetchone()
        if row is None or row[4] != STATUS_SUCCESS:
            return None
        raw, expected_hash, dimension, dtype, _ = row
        if raw is None or int(dimension) != GLAP_DIMENSION or dtype != "float32":
            raise GlapCacheError(f"corrupt GLAP cache metadata for track {track_id}")
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != expected_hash:
            raise GlapCacheError(f"corrupt GLAP cache payload for track {track_id}")
        vector = np.frombuffer(raw, dtype="<f4").copy()
        _vector_payload(vector)
        return vector

    def put_success(
        self,
        *,
        track_id: int,
        analysis_key: str,
        source_sha256: str,
        center5_pcm_sha256: str,
        contract: dict[str, Any],
        vector: np.ndarray,
        encode_ms: float,
    ) -> None:
        raw, digest = _vector_payload(vector)
        self._put(
            track_id=track_id,
            analysis_key=analysis_key,
            source_sha256=source_sha256,
            center5_pcm_sha256=center5_pcm_sha256,
            contract=contract,
            embedding=raw,
            embedding_sha256=digest,
            status=STATUS_SUCCESS,
            failure_code="",
            error_message="",
            encode_ms=encode_ms,
        )

    def put_failure(
        self,
        *,
        track_id: int,
        analysis_key: str,
        source_sha256: str,
        center5_pcm_sha256: str,
        contract: dict[str, Any],
        exc: Exception,
        encode_ms: float,
    ) -> None:
        self._put(
            track_id=track_id,
            analysis_key=analysis_key,
            source_sha256=source_sha256,
            center5_pcm_sha256=center5_pcm_sha256,
            contract=contract,
            embedding=None,
            embedding_sha256="",
            status=STATUS_FAILED,
            failure_code=type(exc).__name__[:80],
            error_message=str(exc)[:1000],
            encode_ms=encode_ms,
        )

    def _put(self, **values: Any) -> None:
        contract = values.pop("contract")
        challenger, audio = contract["challenger"], contract["audio_evidence"]
        row = values | {
            "representation_version": challenger["representation_namespace"],
            "model_identifier": challenger["model_identifier"],
            "model_revision": challenger["model_revision"],
            "model_sha256": challenger["model_file_sha256"],
            "preprocessing_version": audio["canonical_preprocessing"],
            "sampling_version": audio["historical_excerpt"],
            "resampling_version": RESAMPLING_VERSION,
            "embedding_dtype": challenger["stored_dtype"],
            "embedding_dimension": int(challenger["embedding_dimensions"]),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        names = [item[1] for item in self.db.execute("PRAGMA table_info(embeddings)")]
        placeholders = ",".join("?" for _ in names)
        self.db.execute(
            f"INSERT OR REPLACE INTO embeddings ({','.join(names)}) VALUES ({placeholders})",
            [row[name] for name in names],
        )
        self.db.commit()

    def all_success_embeddings(self) -> dict[int, np.ndarray]:
        output: dict[int, np.ndarray] = {}
        for track_id, key in self.db.execute(
            "SELECT track_id, analysis_key FROM embeddings WHERE status=? ORDER BY track_id",
            (STATUS_SUCCESS,),
        ):
            vector = self.valid_embedding(int(track_id), str(key))
            if vector is not None:
                output[int(track_id)] = vector
        return output

    def summary(self) -> dict[str, Any]:
        total, succeeded, failed, tracks = self.db.execute(
            "SELECT count(*), sum(status='SUCCESS'), sum(status='FAILED'), count(DISTINCT track_id) FROM embeddings"
        ).fetchone()
        timings = [float(row[0]) for row in self.db.execute(
            "SELECT encode_ms FROM embeddings WHERE status='SUCCESS' ORDER BY encode_ms"
        )]
        return {
            "schema_version": CACHE_SCHEMA_VERSION,
            "path": str(self.path),
            "row_count": int(total or 0),
            "success_count": int(succeeded or 0),
            "failure_count": int(failed or 0),
            "track_count": int(tracks or 0),
            "p50_inference_ms": float(np.percentile(timings, 50)) if timings else None,
            "p95_inference_ms": float(np.percentile(timings, 95)) if timings else None,
        }


@dataclass(frozen=True)
class EvidenceTrack:
    track_id: int
    relative_audio_path: str
    source_sha256: str
    center5_pcm_sha256: str


def load_evidence_tracks(contract: dict[str, Any], root: str | Path) -> list[EvidenceTrack]:
    root = Path(root)
    keys_path = root / contract["historical_evidence"]["trial_manifest"]["path"]
    trials = json.loads(keys_path.read_text(encoding="utf-8"))["trials"]
    identities: dict[int, dict[str, Any]] = {}
    for trial in trials.values():
        for id_key, identity_key in (
            ("query_id", "query_identity"),
            ("candidate_a", "candidate_a_identity"),
            ("candidate_b", "candidate_b_identity"),
        ):
            track_id = int(trial[id_key])
            identity = trial[identity_key]
            if track_id in identities and identities[track_id] != identity:
                raise ContractError(f"contradictory frozen PCM identity for track {track_id}")
            identities[track_id] = identity
    stage2b_config_path = root / contract["historical_evidence"]["stage2b_config"]["path"]
    import yaml

    stage2b_config = yaml.safe_load(stage2b_config_path.read_text(encoding="utf-8"))
    manifest = pd.read_parquet(root / stage2b_config["inputs"]["manifest"]["path"]).set_index("track_id")
    output = []
    for track_id in sorted(identities):
        if track_id not in manifest.index:
            raise ContractError(f"frozen evidence track {track_id} missing from source manifest")
        row, identity = manifest.loc[track_id], identities[track_id]
        source_hash = str(row["audio_sha256"])
        if source_hash != identity["source_sha256"]:
            raise ContractError(f"source identity mismatch for track {track_id}")
        output.append(
            EvidenceTrack(
                track_id=track_id,
                relative_audio_path=str(row["relative_audio_path"]),
                source_sha256=source_hash,
                center5_pcm_sha256=str(identity["center5_v1_pcm_sha256"]),
            )
        )
    if len(output) != int(contract["historical_evidence"]["trial_manifest"]["unique_audio_track_count"]):
        raise ContractError("frozen evidence track count changed")
    return output


def _prepare_excerpt(track: EvidenceTrack, audio_root: Path) -> np.ndarray:
    path = audio_root / track.relative_audio_path
    if not path.is_file():
        raise FileNotFoundError(path)
    if sha256_file(path) != track.source_sha256:
        raise ContractError(f"source SHA-256 mismatch for track {track.track_id}")
    _, excerpt, start, end = canonical_pcm(path)
    if (start, end) != (300000, 420000):
        raise ContractError(f"center5_v1 bounds changed for track {track.track_id}")
    digest = hashlib.sha256(float32_le_bytes(excerpt)).hexdigest()
    if digest != track.center5_pcm_sha256:
        raise ContractError(f"center5_v1 PCM hash mismatch for track {track.track_id}")
    return np.asarray(excerpt, dtype=np.float32)


def encode_historical_evidence(
    *,
    contract_path: str | Path,
    root: str | Path,
    model_dir: str | Path,
    cache_path: str | Path,
    device: str,
    batch_size: int = 1,
    limit: int | None = None,
    track_ids: Sequence[int] | None = None,
    encoder_factory: Callable[..., Any] = GlapAudioEncoder,
) -> dict[str, Any]:
    """Encode exact Stage 2B evidence, reusing only identity-valid successes."""

    root = Path(root)
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    contract = load_glap_contract(contract_path, root)
    challenger = contract["challenger"]
    tracks = load_evidence_tracks(contract, root)
    if track_ids is not None:
        selected = {int(value) for value in track_ids}
        unknown = selected - {track.track_id for track in tracks}
        if unknown:
            raise ContractError(f"requested non-evidence track IDs: {sorted(unknown)}")
        tracks = [track for track in tracks if track.track_id in selected]
    if limit is not None:
        tracks = tracks[: int(limit)]

    cache = GlapEmbeddingCache(cache_path)
    invalidated, skipped, prepared, failed = 0, 0, [], 0
    audio_root = root / "data/fma/fma_small"
    for track in tracks:
        key = analysis_identity(
            contract,
            source_sha256=track.source_sha256,
            center5_pcm_sha256=track.center5_pcm_sha256,
        )
        try:
            cached = cache.valid_embedding(track.track_id, key)
        except GlapCacheError:
            cached, invalidated = None, invalidated + 1
        if cached is not None:
            skipped += 1
            continue
        started = time.perf_counter()
        try:
            excerpt = _prepare_excerpt(track, audio_root)
            prepared.append((track, key, excerpt))
        except Exception as exc:
            cache.put_failure(
                track_id=track.track_id,
                analysis_key=key,
                source_sha256=track.source_sha256,
                center5_pcm_sha256=track.center5_pcm_sha256,
                contract=contract,
                exc=exc,
                encode_ms=(time.perf_counter() - started) * 1000,
            )
            failed += 1

    encoder = None
    succeeded = 0
    inference_attempted = 0
    wall_started = time.perf_counter()
    if prepared:
        encoder = encoder_factory(
            model_dir,
            model_revision=challenger["model_revision"],
            model_sha256=challenger["model_file_sha256"],
            device=device,
        )
        for offset in range(0, len(prepared), batch_size):
            batch = prepared[offset : offset + batch_size]
            batch_started = time.perf_counter()
            inference_attempted += len(batch)
            try:
                outputs = encoder.encode_batch([row[2] for row in batch], 24000)
                if len(outputs) != len(batch):
                    raise ContractError("GLAP encoder returned wrong batch size")
                elapsed_each = (time.perf_counter() - batch_started) * 1000 / len(batch)
                for (track, key, _), output in zip(batch, outputs):
                    cache.put_success(
                        track_id=track.track_id,
                        analysis_key=key,
                        source_sha256=track.source_sha256,
                        center5_pcm_sha256=track.center5_pcm_sha256,
                        contract=contract,
                        vector=output.embedding,
                        encode_ms=elapsed_each,
                    )
                    succeeded += 1
            except Exception as batch_exc:
                # Isolate a model failure to individual tracks.  Batch size one
                # is already isolated and is not recomputed.
                if len(batch) == 1:
                    isolated = [(batch[0], batch_exc, (time.perf_counter() - batch_started) * 1000)]
                else:
                    isolated = []
                    for item in batch:
                        item_started = time.perf_counter()
                        try:
                            output = encoder.encode_batch([item[2]], 24000)[0]
                            cache.put_success(
                                track_id=item[0].track_id,
                                analysis_key=item[1],
                                source_sha256=item[0].source_sha256,
                                center5_pcm_sha256=item[0].center5_pcm_sha256,
                                contract=contract,
                                vector=output.embedding,
                                encode_ms=(time.perf_counter() - item_started) * 1000,
                            )
                            succeeded += 1
                        except Exception as exc:
                            isolated.append((item, exc, (time.perf_counter() - item_started) * 1000))
                for (track, key, _), exc, elapsed in isolated:
                    cache.put_failure(
                        track_id=track.track_id,
                        analysis_key=key,
                        source_sha256=track.source_sha256,
                        center5_pcm_sha256=track.center5_pcm_sha256,
                        contract=contract,
                        exc=exc,
                        encode_ms=elapsed,
                    )
                    failed += 1

    summary = cache.summary() | {
        "experiment_id": contract["experiment_id"],
        "selected_track_count": len(tracks),
        "skipped_valid_success": skipped,
        "cache_invalidated": invalidated,
        "inference_attempted": inference_attempted,
        "succeeded_this_run": succeeded,
        "failed_this_run": failed,
        "wall_seconds": time.perf_counter() - wall_started,
        "model_load_seconds": getattr(encoder, "load_seconds", None),
        "peak_vram_bytes": encoder.peak_vram_bytes() if encoder is not None else None,
        "full_historical_run": len(tracks) == 246,
    }
    cache.close()
    return summary
