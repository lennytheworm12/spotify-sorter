"""Audio Representation v1 materialization using frozen Stage 4 machinery."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Protocol

import numpy as np

from .stage4a_dual_scoring import normalized_mean
from .stage4a_sampling import MINIMUM_SAMPLES, Stage4AError, cache_windows, decode, pcm_sha256
from .stage5a_cache import Stage5ACache, Stage5ACacheError, validate_vector
from .stage5a_contract import RepresentationContract
from .stage5a_dataset import write_dataset


class SegmentEncoder(Protocol):
    encoder_id: str
    embedding_dim: int

    def encode_segment(self, waveform: np.ndarray, sample_rate: int): ...


@dataclass(frozen=True)
class TrackInput:
    stable_track_id: str
    audio_path: Path
    source_audio_sha256: str


@dataclass
class EncoderRunStats:
    inferred_segments: int = 0
    reused_segments: int = 0
    reused_pooled: int = 0
    inference_seconds: float = 0.0


@dataclass
class MaterializationStats:
    input_tracks: int = 0
    successful_tracks: int = 0
    failed_tracks: int = 0
    reused_complete_tracks: int = 0
    clap: EncoderRunStats = field(default_factory=EncoderRunStats)
    muq: EncoderRunStats = field(default_factory=EncoderRunStats)
    elapsed_seconds: float = 0.0
    failure_categories: dict[str, int] = field(default_factory=dict)
    dataset_manifest: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        def encoder(values: EncoderRunStats) -> dict:
            throughput = (
                values.inferred_segments / values.inference_seconds
                if values.inference_seconds > 0
                else None
            )
            return vars(values) | {"inferred_segments_per_second": throughput}

        return {
            "input_tracks": self.input_tracks,
            "successful_tracks": self.successful_tracks,
            "failed_tracks": self.failed_tracks,
            "reused_complete_tracks": self.reused_complete_tracks,
            "elapsed_seconds": self.elapsed_seconds,
            "successful_tracks_per_second": (
                self.successful_tracks / self.elapsed_seconds
                if self.elapsed_seconds > 0
                else None
            ),
            "failure_categories": self.failure_categories,
            "clap": encoder(self.clap),
            "muq": encoder(self.muq),
            "dataset_manifest": self.dataset_manifest,
        }


def source_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _extract_embedding(encoded) -> np.ndarray:
    return np.asarray(getattr(encoded, "embedding", encoded), dtype=np.float32)


def _embedding_sha256(vector: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(vector, dtype="<f4").tobytes()).hexdigest()


def _identity_fields(
    contract: RepresentationContract,
    encoder_id: str,
    *,
    corpus: str,
    corpus_version: str,
    track: TrackInput,
    canonical_hash: str,
) -> dict:
    encoder = contract.encoder(encoder_id)
    return {
        "encoder_analysis_identity": contract.encoder_analysis_identity(
            corpus=corpus,
            corpus_version=corpus_version,
            stable_track_id=track.stable_track_id,
            source_audio_sha256=track.source_audio_sha256,
            canonical_pcm_sha256=canonical_hash,
            encoder_id=encoder_id,
        ),
        "corpus": corpus,
        "corpus_version": corpus_version,
        "stable_track_id": track.stable_track_id,
        "source_audio_sha256": track.source_audio_sha256,
        "canonical_pcm_sha256": canonical_hash,
        "vector_contract_sha256": contract.vector_contract_sha256,
        "representation_version": contract.representation_version,
        "preprocessing_version": contract.preprocessing_version,
        "sampling_version": contract.sampling_version,
        "centers_json": json.dumps(list(contract.centers_sec), separators=(",", ":")),
        "aggregation_version": contract.aggregation_version,
        "encoder_id": encoder.encoder_id,
        "encoder_provenance_json": encoder.provenance_json,
        "encoder_provenance_sha256": encoder.provenance_sha256,
        "embedding_dtype": contract.embedding_dtype,
        "embedding_dimension": encoder.dimension,
    }


def _record_track_failure(
    cache: Stage5ACache,
    contract: RepresentationContract,
    *,
    corpus: str,
    corpus_version: str,
    track: TrackInput,
    canonical_hash: str,
    category: str,
    detail: str,
) -> None:
    cache.record_track(
        representation_identity=contract.representation_identity(
            corpus=corpus,
            corpus_version=corpus_version,
            stable_track_id=track.stable_track_id,
            source_audio_sha256=track.source_audio_sha256,
            canonical_pcm_sha256=canonical_hash,
        ),
        corpus=corpus,
        corpus_version=corpus_version,
        stable_track_id=track.stable_track_id,
        source_audio_sha256=track.source_audio_sha256,
        canonical_pcm_sha256=canonical_hash,
        vector_contract_sha256=contract.vector_contract_sha256,
        representation_version=contract.representation_version,
        status="FAILED",
        failure_category=category,
        failure_detail=detail,
        retryable=True,
    )


def _encode_one(
    *,
    cache: Stage5ACache,
    contract: RepresentationContract,
    identity: dict,
    encoder: SegmentEncoder,
    windows,
    waveform,
    stats: EncoderRunStats,
    on_segment_saved: Callable[[str, str, int], None] | None,
) -> tuple[np.ndarray | None, tuple[str, str] | None]:
    analysis_identity = identity["encoder_analysis_identity"]
    pooled = cache.pooled_vector(analysis_identity)
    if pooled is not None:
        stats.reused_pooled += 1
        return pooled, None

    segments = cache.successful_segments(analysis_identity)
    stats.reused_segments += len(segments)
    for window in windows:
        if window.center_sec in segments:
            continue
        started = time.perf_counter()
        try:
            excerpt = np.asarray(
                waveform[window.start_sample : window.end_sample].cpu(), dtype=np.float32
            )
            encoded = encoder.encode_segment(excerpt, contract.sample_rate)
            vector = validate_vector(_extract_embedding(encoded), int(identity["embedding_dimension"]))
        except Stage5ACacheError as exc:
            elapsed = time.perf_counter() - started
            cache.record_segment(
                identity,
                center_sec=window.center_sec,
                start_sample=window.start_sample,
                end_sample=window.end_sample,
                status="FAILED",
                failure_category="INVALID_EMBEDDING",
                failure_detail=str(exc),
                encode_ms=elapsed * 1000,
            )
            stats.inference_seconds += elapsed
            stats.inferred_segments += 1
            return None, ("INVALID_EMBEDDING", str(exc))
        except Exception as exc:
            elapsed = time.perf_counter() - started
            category = (
                "CLAP_INFERENCE_FAILURE"
                if identity["encoder_id"] == "laion_clap"
                else "MUQ_INFERENCE_FAILURE"
            )
            cache.record_segment(
                identity,
                center_sec=window.center_sec,
                start_sample=window.start_sample,
                end_sample=window.end_sample,
                status="FAILED",
                failure_category=category,
                failure_detail=str(exc),
                encode_ms=elapsed * 1000,
            )
            stats.inference_seconds += elapsed
            stats.inferred_segments += 1
            return None, (category, str(exc))
        elapsed = time.perf_counter() - started
        cache.record_segment(
            identity,
            center_sec=window.center_sec,
            start_sample=window.start_sample,
            end_sample=window.end_sample,
            status="SUCCESS",
            embedding=vector,
            encode_ms=elapsed * 1000,
        )
        stats.inference_seconds += elapsed
        stats.inferred_segments += 1
        segments[window.center_sec] = vector
        if on_segment_saved:
            on_segment_saved(identity["encoder_id"], identity["stable_track_id"], window.center_sec)

    aggregate_started = time.perf_counter()
    try:
        pooled = normalized_mean(np.stack([segments[center] for center in contract.centers_sec]))
        pooled = validate_vector(pooled, int(identity["embedding_dimension"]))
    except Exception as exc:
        cache.record_pooled(
            identity,
            status="FAILED",
            failure_category="INVALID_EMBEDDING",
            failure_detail=f"aggregation failed: {exc}",
            aggregate_ms=(time.perf_counter() - aggregate_started) * 1000,
        )
        return None, ("INVALID_EMBEDDING", str(exc))
    cache.record_pooled(
        identity,
        status="SUCCESS",
        embedding=pooled,
        aggregate_ms=(time.perf_counter() - aggregate_started) * 1000,
    )
    return pooled, None


def _record_from_cache(
    cache: Stage5ACache,
    contract: RepresentationContract,
    track_row,
    *,
    corpus: str,
    corpus_version: str,
) -> dict:
    vectors: dict[str, np.ndarray] = {}
    analysis_identities: dict[str, str] = {}
    for encoder in contract.encoders:
        analysis_identity = contract.encoder_analysis_identity(
            corpus=corpus,
            corpus_version=corpus_version,
            stable_track_id=str(track_row["stable_track_id"]),
            source_audio_sha256=str(track_row["source_audio_sha256"]),
            canonical_pcm_sha256=str(track_row["canonical_pcm_sha256"]),
            encoder_id=encoder.encoder_id,
        )
        vector = cache.pooled_vector(analysis_identity)
        if vector is None:
            raise Stage5ACacheError("successful track is missing a pooled encoder vector")
        vectors[encoder.encoder_id] = vector
        analysis_identities[encoder.encoder_id] = analysis_identity
    clap = contract.encoder("laion_clap")
    muq = contract.encoder("muq_mulan_large")
    return {
        "corpus": corpus,
        "corpus_version": corpus_version,
        "stable_track_id": str(track_row["stable_track_id"]),
        "source_audio_sha256": str(track_row["source_audio_sha256"]),
        "canonical_pcm_sha256": str(track_row["canonical_pcm_sha256"]),
        "representation_version": contract.representation_version,
        "contract_artifact_sha256": contract.artifact_sha256,
        "vector_contract_sha256": contract.vector_contract_sha256,
        "preprocessing_version": contract.preprocessing_version,
        "sampling_version": contract.sampling_version,
        "segment_centers_sec": list(contract.centers_sec),
        "aggregation_version": contract.aggregation_version,
        "clap_similarity_weight": contract.clap_weight,
        "clap_encoder_id": clap.encoder_id,
        "clap_analysis_identity": analysis_identities[clap.encoder_id],
        "clap_provenance_json": clap.provenance_json,
        "clap_embedding": vectors[clap.encoder_id],
        "clap_embedding_sha256": _embedding_sha256(vectors[clap.encoder_id]),
        "clap_embedding_dtype": contract.embedding_dtype,
        "clap_embedding_dimension": clap.dimension,
        "muq_similarity_weight": contract.muq_weight,
        "muq_encoder_id": muq.encoder_id,
        "muq_analysis_identity": analysis_identities[muq.encoder_id],
        "muq_provenance_json": muq.provenance_json,
        "muq_embedding": vectors[muq.encoder_id],
        "muq_embedding_sha256": _embedding_sha256(vectors[muq.encoder_id]),
        "muq_embedding_dtype": contract.embedding_dtype,
        "muq_embedding_dimension": muq.dimension,
        "status": "SUCCESS",
        "representation_identity": str(track_row["representation_identity"]),
        "materialized_at_unix": int(track_row["materialized_at"]),
    }


def materialize(
    tracks: Iterable[TrackInput],
    *,
    corpus: str,
    corpus_version: str,
    contract: RepresentationContract,
    cache: Stage5ACache,
    encoders: dict[str, SegmentEncoder],
    output_dir: str | Path,
    rows_per_shard: int = 10_000,
    verify_source_hash: bool = True,
    on_segment_saved: Callable[[str, str, int], None] | None = None,
) -> MaterializationStats:
    """Materialize valid tracks, continuing after deterministic per-track failures."""
    started = time.perf_counter()
    ordered = sorted(tracks, key=lambda item: item.stable_track_id)
    if len({item.stable_track_id for item in ordered}) != len(ordered):
        raise ValueError("duplicate stable track IDs in input manifest")
    for required in contract.encoders:
        adapter = encoders.get(required.encoder_id)
        if adapter is None:
            raise ValueError(f"missing encoder adapter {required.encoder_id}")
        if adapter.encoder_id != required.encoder_id or adapter.embedding_dim != required.dimension:
            raise ValueError(f"encoder adapter contract mismatch for {required.encoder_id}")

    stats = MaterializationStats(input_tracks=len(ordered))
    records: list[dict] = []
    for track in ordered:
        complete = cache.successful_track(
            corpus=corpus,
            corpus_version=corpus_version,
            stable_track_id=track.stable_track_id,
            source_audio_sha256=track.source_audio_sha256,
            vector_contract_sha256=contract.vector_contract_sha256,
        )
        if complete is not None:
            records.append(_record_from_cache(cache, contract, complete, corpus=corpus, corpus_version=corpus_version))
            stats.successful_tracks += 1
            stats.reused_complete_tracks += 1
            continue

        canonical_hash = "UNAVAILABLE"
        try:
            if verify_source_hash and source_sha256(track.audio_path) != track.source_audio_sha256:
                raise ValueError("source audio SHA-256 does not match the manifest")
            waveform = decode(track.audio_path)
            if len(waveform) < MINIMUM_SAMPLES:
                raise Stage4AError(f"requires at least {MINIMUM_SAMPLES} samples")
            windows = [
                window for window in cache_windows(len(waveform))
                if window.center_sec in contract.centers_sec
            ]
            if tuple(window.center_sec for window in windows) != contract.centers_sec:
                raise Stage4AError("frozen K=3 window selection mismatch")
            canonical_hash = pcm_sha256(waveform)
        except FileNotFoundError as exc:
            category = "DECODE_FAILURE"
            _record_track_failure(cache, contract, corpus=corpus, corpus_version=corpus_version, track=track, canonical_hash=canonical_hash, category=category, detail=str(exc))
            stats.failed_tracks += 1
            continue
        except Stage4AError as exc:
            category = "DECODE_FAILURE" if "decode failed" in str(exc) else "INVALID_OR_TOO_SHORT_AUDIO"
            _record_track_failure(cache, contract, corpus=corpus, corpus_version=corpus_version, track=track, canonical_hash=canonical_hash, category=category, detail=str(exc))
            stats.failed_tracks += 1
            continue
        except Exception as exc:
            category = "SOURCE_IDENTITY_FAILURE"
            _record_track_failure(cache, contract, corpus=corpus, corpus_version=corpus_version, track=track, canonical_hash=canonical_hash, category=category, detail=str(exc))
            stats.failed_tracks += 1
            continue

        pooled: dict[str, np.ndarray] = {}
        failures: list[tuple[str, str]] = []
        for encoder_contract in contract.encoders:
            identity = _identity_fields(contract, encoder_contract.encoder_id, corpus=corpus, corpus_version=corpus_version, track=track, canonical_hash=canonical_hash)
            encoder_stats = stats.clap if encoder_contract.encoder_id == "laion_clap" else stats.muq
            vector, failure = _encode_one(cache=cache, contract=contract, identity=identity, encoder=encoders[encoder_contract.encoder_id], windows=windows, waveform=waveform, stats=encoder_stats, on_segment_saved=on_segment_saved)
            if vector is not None:
                pooled[encoder_contract.encoder_id] = vector
            if failure is not None:
                failures.append(failure)
        representation_identity = contract.representation_identity(corpus=corpus, corpus_version=corpus_version, stable_track_id=track.stable_track_id, source_audio_sha256=track.source_audio_sha256, canonical_pcm_sha256=canonical_hash)
        if failures:
            category, detail = failures[0]
            cache.record_track(representation_identity=representation_identity, corpus=corpus, corpus_version=corpus_version, stable_track_id=track.stable_track_id, source_audio_sha256=track.source_audio_sha256, canonical_pcm_sha256=canonical_hash, vector_contract_sha256=contract.vector_contract_sha256, representation_version=contract.representation_version, status="FAILED", failure_category=category, failure_detail=detail)
            stats.failed_tracks += 1
            continue
        cache.record_track(representation_identity=representation_identity, corpus=corpus, corpus_version=corpus_version, stable_track_id=track.stable_track_id, source_audio_sha256=track.source_audio_sha256, canonical_pcm_sha256=canonical_hash, vector_contract_sha256=contract.vector_contract_sha256, representation_version=contract.representation_version, status="SUCCESS")
        row = cache.successful_track(corpus=corpus, corpus_version=corpus_version, stable_track_id=track.stable_track_id, source_audio_sha256=track.source_audio_sha256, vector_contract_sha256=contract.vector_contract_sha256)
        records.append(_record_from_cache(cache, contract, row, corpus=corpus, corpus_version=corpus_version))
        stats.successful_tracks += 1

    stats.failure_categories = cache.failure_counts()
    try:
        stats.dataset_manifest = write_dataset(
            records,
            output_dir,
            clap_dimension=contract.encoder("laion_clap").dimension,
            muq_dimension=contract.encoder("muq_mulan_large").dimension,
            rows_per_shard=rows_per_shard,
        )
    except Exception as exc:
        raise RuntimeError(f"PERSISTENCE_MATERIALIZATION_FAILURE: {exc}") from exc
    stats.elapsed_seconds = time.perf_counter() - started
    return stats
