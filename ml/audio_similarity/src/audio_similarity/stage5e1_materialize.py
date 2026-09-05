"""Resumable local-only materialization of the Stage 5E.1 representations."""
from __future__ import annotations

import gc
import hashlib
import json
import resource
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .stage4a_sampling import cache_windows
from .stage5a_cache import validate_vector
from .stage5a_contract import load_contract
from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c1_pipeline import load_frozen_encoders, verify_model_files
from .stage5e1_cache import Stage5E1Cache, representation_identity
from .stage5e1_contract import (
    BASELINE_CHECKPOINT,
    EXPERIMENT_ID,
    FUSION_CHECKPOINT,
    FUSION_EXPECTED_SHA256,
    REPORT_DIRECTORY,
    inspect_aff_feasibility,
)
from .stage5e1_encoders import (
    NativeFusionClapEncoder,
    decode_mono,
    encode_segments,
    native_view_spans,
)
from .stage5e1_sampling import normalized_mean


ARTIFACT_DIRECTORY = Path("artifacts/stage5e1_four_arm_retrieval")
ARM_KEYS = ("A", "B", "C", "D", "MUQ")


def _load_frozen_inputs(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    report = root / REPORT_DIRECTORY
    paths = [
        report / "corpus_manifest.json",
        report / "experiment_config.json",
        report / "sampling_plans.json",
    ]
    if any(not path.is_file() for path in paths):
        raise Stage5B1AValidationError("Stage 5E.1 corpus/config/sampling freeze is incomplete")
    manifest, config, plans = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if config.get("experiment_id") != EXPERIMENT_ID or manifest.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("Stage 5E.1 frozen identity differs")
    track_ids = [row["spotify_track_id"] for row in manifest["tracks"]]
    plan_ids = [row["spotify_track_id"] for row in plans["tracks"]]
    if track_ids != plan_ids or len(track_ids) != len(set(track_ids)):
        raise Stage5B1AValidationError("Stage 5E.1 sampling plans do not match corpus order")
    return manifest, config, plans


def _identity_fields(
    track: dict[str, Any], arm: str, config_sha: str, plan_sha: str, checkpoint_sha: str
) -> tuple[str, dict[str, str]]:
    fields = {
        "spotify_track_id": track["spotify_track_id"],
        "arm": arm,
        "source_sha256": track["source_sha256"],
        "config_sha256": config_sha,
        "sampling_plan_sha256": plan_sha,
        "checkpoint_sha256": checkpoint_sha,
    }
    return representation_identity(**fields), fields


def _historical_stage5a_vectors(
    root: Path, manifest: dict[str, Any], vector_contract_sha: str
) -> dict[tuple[str, str], tuple[np.ndarray, str]]:
    wanted = {(row["spotify_track_id"], row["source_sha256"]) for row in manifest["tracks"]}
    found: dict[tuple[str, str, str], list[tuple[np.ndarray, str, str]]] = {}
    for path in sorted((root / "artifacts").rglob("representations.sqlite")):
        if "stage5e1_four_arm_retrieval" in path.parts:
            continue
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "pooled" not in tables:
                continue
            for row in connection.execute(
                "SELECT stable_track_id,source_audio_sha256,encoder_id,embedding,"
                "embedding_dimension,embedding_sha256 FROM pooled "
                "WHERE status='SUCCESS' AND vector_contract_sha256=?",
                (vector_contract_sha,),
            ):
                key2 = (str(row["stable_track_id"]), str(row["source_audio_sha256"]))
                if key2 not in wanted or row["encoder_id"] not in {"laion_clap", "muq_mulan_large"}:
                    continue
                blob = bytes(row["embedding"])
                if hashlib.sha256(blob).hexdigest() != row["embedding_sha256"]:
                    raise Stage5B1AValidationError(f"historical vector hash failed in {path}")
                vector = validate_vector(np.frombuffer(blob, dtype="<f4").copy(), int(row["embedding_dimension"]))
                found.setdefault((*key2, str(row["encoder_id"])), []).append(
                    (vector, hashlib.sha256(vector.astype("<f4").tobytes()).hexdigest(), str(path.relative_to(root)))
                )
        finally:
            connection.close()
    output: dict[tuple[str, str], tuple[np.ndarray, str]] = {}
    for (spotify_id, _source_sha, encoder_id), rows in found.items():
        hashes = {row[1] for row in rows}
        if len(hashes) != 1:
            raise Stage5B1AValidationError(f"conflicting exact-source historical vectors: {spotify_id}/{encoder_id}")
        output[(spotify_id, encoder_id)] = (rows[0][0], rows[0][2])
    return output


def _record_progress(path: Path, rows: list[dict[str, Any]], started: float) -> None:
    counts = Counter(row["status"] for row in rows)
    atomic_json(
        path,
        {
            "schema_version": "stage5e1-materialization-progress-v1",
            "experiment_id": EXPERIMENT_ID,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - started,
            "result_count": len(rows),
            "status_counts": dict(sorted(counts.items())),
            "results": rows,
        },
    )


def _view_cache_pool(
    cache: Stage5E1Cache,
    identity: str,
    fields: dict[str, str],
    *,
    spans: list[tuple[str, int, int]],
    encoder: Any,
    waveform: np.ndarray,
    sample_rate: int,
) -> tuple[np.ndarray, int, float]:
    existing = cache.views(identity)
    inferred = 0
    total_seconds = 0.0
    for index, (kind, start, end) in enumerate(spans):
        if index in existing:
            continue
        vectors, elapsed = encode_segments(encoder, waveform, sample_rate, [(start, end)])
        cache.record_view(
            identity,
            view_index=index,
            view_kind=kind,
            start_unit=start,
            end_unit=end,
            embedding=vectors[0],
            inference_seconds=elapsed,
        )
        existing[index] = vectors[0]
        inferred += 1
        total_seconds += elapsed
    ordered = [existing[index] for index in range(len(spans))]
    pooled = normalized_mean(ordered)
    cache.record_vector(
        identity,
        fields,
        status="SUCCESS",
        embedding=pooled,
        view_count=len(spans),
        inference_seconds=total_seconds,
    )
    return pooled, inferred, total_seconds


def run_materialization(
    root: str | Path,
    *,
    arms: tuple[str, ...] = ARM_KEYS,
    baseline_encoders: dict[str, Any] | None = None,
    fusion_encoder: Any | None = None,
) -> dict[str, Any]:
    """Run requested arms from local retained audio; this function performs no network I/O."""
    project = Path(root).resolve()
    requested = tuple(dict.fromkeys(value.upper() for value in arms))
    if not requested or any(value not in ARM_KEYS for value in requested):
        raise ValueError(f"arms must be drawn from {ARM_KEYS}")
    manifest, config, plans = _load_frozen_inputs(project)
    report = project / REPORT_DIRECTORY
    artifacts = project / ARTIFACT_DIRECTORY
    artifacts.mkdir(parents=True, exist_ok=True)
    config_sha = file_sha256(report / "experiment_config.json")
    contract = load_contract(project / "reports/holistic_stage4a_dual/audio_representation_v1.json")
    plan_by_id = {row["spotify_track_id"]: row["plan"] for row in plans["tracks"]}
    historical = _historical_stage5a_vectors(project, manifest, contract.vector_contract_sha256)
    started = time.perf_counter()
    result_rows: list[dict[str, Any]] = []
    progress_path = artifacts / "materialization_progress.json"

    with Stage5E1Cache(artifacts / "representations.sqlite") as cache:
        # Import exact-source A/MuQ vectors before loading any model.
        for track in manifest["tracks"]:
            plan_sha = plan_by_id[track["spotify_track_id"]]["sampling_plan_sha256"]
            for arm, encoder_id, checkpoint_sha in (
                ("A", "laion_clap", config["arms"]["A"]["checkpoint_sha256"]),
                ("MUQ", "muq_mulan_large", contract.encoder("muq_mulan_large").provenance_sha256),
            ):
                if arm not in requested:
                    continue
                identity, fields = _identity_fields(track, arm, config_sha, plan_sha, checkpoint_sha)
                if cache.vector(identity) is not None:
                    result_rows.append({"spotify_track_id": track["spotify_track_id"], "arm": arm, "status": "CACHE_HIT", "representation_identity": identity, "inferred_views": 0})
                    continue
                prior = historical.get((track["spotify_track_id"], encoder_id))
                if prior:
                    cache.record_vector(identity, fields, status="SUCCESS", embedding=prior[0], view_count=3, inference_seconds=0)
                    result_rows.append({"spotify_track_id": track["spotify_track_id"], "arm": arm, "status": "HISTORICAL_EXACT_SOURCE_REUSE", "representation_identity": identity, "source_cache": prior[1], "inferred_views": 0})
            if result_rows:
                _record_progress(progress_path, result_rows, started)

        baseline_needed = any(value in requested for value in ("A", "C", "MUQ"))
        if baseline_needed:
            if baseline_encoders is None:
                verify_model_files(project, contract)
                baseline_encoders = load_frozen_encoders(project, contract)
            clap = baseline_encoders["laion_clap"]
            muq = baseline_encoders["muq_mulan_large"]
            for track in manifest["tracks"]:
                spotify_id = track["spotify_track_id"]
                plan = plan_by_id[spotify_id]
                plan_sha = plan["sampling_plan_sha256"]
                source = project / track["retained_source_path"]
                waveform24: np.ndarray | None = None
                waveform48: np.ndarray | None = None
                for arm, encoder, checkpoint_sha in (
                    ("A", clap, config["arms"]["A"]["checkpoint_sha256"]),
                    ("MUQ", muq, contract.encoder("muq_mulan_large").provenance_sha256),
                    ("C", clap, config["arms"]["C"]["checkpoint_sha256"]),
                ):
                    if arm not in requested:
                        continue
                    identity, fields = _identity_fields(track, arm, config_sha, plan_sha, checkpoint_sha)
                    if cache.vector(identity) is not None:
                        if not any(row["representation_identity"] == identity for row in result_rows):
                            result_rows.append({"spotify_track_id": spotify_id, "arm": arm, "status": "CACHE_HIT", "representation_identity": identity, "inferred_views": 0})
                        continue
                    began = time.perf_counter()
                    try:
                        if arm in {"A", "MUQ"}:
                            waveform24 = waveform24 if waveform24 is not None else decode_mono(source, 24_000)
                            windows = [window for window in cache_windows(len(waveform24)) if window.center_sec in (5, 15, 25)]
                            spans = [("CENTERED30_SEGMENT", row.start_sample, row.end_sample) for row in windows]
                            _, inferred, inference_seconds = _view_cache_pool(cache, identity, fields, spans=spans, encoder=encoder, waveform=waveform24, sample_rate=24_000)
                        else:
                            waveform48 = waveform48 if waveform48 is not None else decode_mono(source, 48_000)
                            if len(waveform48) != plan["native_fusion"]["sample_count_48khz"]:
                                raise ValueError("decoded waveform differs from frozen sampling plan")
                            spans = [("FULL_SONG_CHUNK", int(row["start_sample"]), int(row["end_sample"])) for row in plan["full_song_chunks"]]
                            _, inferred, inference_seconds = _view_cache_pool(cache, identity, fields, spans=spans, encoder=encoder, waveform=waveform48, sample_rate=48_000)
                        result_rows.append({"spotify_track_id": spotify_id, "arm": arm, "status": "SUCCESS", "representation_identity": identity, "inferred_views": inferred, "inference_seconds": inference_seconds})
                    except Exception as exc:
                        cache.record_vector(identity, fields, status="FAILED", failure_category=f"{arm}_INFERENCE_FAILED", failure_detail=str(exc), inference_seconds=time.perf_counter() - began)
                        result_rows.append({"spotify_track_id": spotify_id, "arm": arm, "status": "FAILED", "representation_identity": identity, "failure_category": f"{arm}_INFERENCE_FAILED", "failure_detail": str(exc)})
                    _record_progress(progress_path, result_rows, started)
            if baseline_encoders is not None:
                del baseline_encoders
                gc.collect()
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass

        if any(value in requested for value in ("B", "D")):
            feasibility = inspect_aff_feasibility(project)
            if feasibility["status"] != "AFF_READY":
                raise Stage5B1AValidationError("B/D require the verified trained native AFF checkpoint")
            fusion_encoder = fusion_encoder or NativeFusionClapEncoder(project / FUSION_CHECKPOINT)
            for track in manifest["tracks"]:
                spotify_id = track["spotify_track_id"]
                plan = plan_by_id[spotify_id]
                plan_sha = plan["sampling_plan_sha256"]
                needed = {}
                for arm in ("B", "D"):
                    if arm not in requested:
                        continue
                    identity, fields = _identity_fields(track, arm, config_sha, plan_sha, FUSION_EXPECTED_SHA256)
                    if cache.vector(identity) is not None:
                        result_rows.append({"spotify_track_id": spotify_id, "arm": arm, "status": "CACHE_HIT", "representation_identity": identity, "inferred_views": 0})
                    else:
                        needed[arm] = (identity, fields)
                if not needed:
                    continue
                waveform = decode_mono(project / track["retained_source_path"], 48_000)
                if len(waveform) != plan["native_fusion"]["sample_count_48khz"]:
                    raise Stage5B1AValidationError("decoded waveform differs from frozen sampling plan")
                views = None
                if "B" in needed:
                    identity, fields = needed["B"]
                    began = time.perf_counter()
                    try:
                        vector, views, elapsed = fusion_encoder.encode_aff(waveform, plan["native_fusion"])
                        cache.record_vector(identity, fields, status="SUCCESS", embedding=vector, view_count=4, inference_seconds=elapsed)
                        result_rows.append({"spotify_track_id": spotify_id, "arm": "B", "status": "SUCCESS", "representation_identity": identity, "inferred_views": 1, "inference_seconds": elapsed})
                    except Exception as exc:
                        cache.record_vector(identity, fields, status="FAILED", failure_category="B_AFF_INFERENCE_FAILED", failure_detail=str(exc), inference_seconds=time.perf_counter() - began)
                        result_rows.append({"spotify_track_id": spotify_id, "arm": "B", "status": "FAILED", "representation_identity": identity, "failure_category": "B_AFF_INFERENCE_FAILED", "failure_detail": str(exc)})
                if "D" in needed:
                    identity, fields = needed["D"]
                    began = time.perf_counter()
                    try:
                        vectors, pooled, elapsed = fusion_encoder.encode_independent_views(waveform, plan["native_fusion"], views=views)
                        for index, ((kind, start, end), vector) in enumerate(zip(native_view_spans(plan["native_fusion"]), vectors, strict=True)):
                            cache.record_view(identity, view_index=index, view_kind=kind, start_unit=start, end_unit=end, embedding=vector, inference_seconds=elapsed / 4)
                        cache.record_vector(identity, fields, status="SUCCESS", embedding=pooled, view_count=4, inference_seconds=elapsed)
                        result_rows.append({"spotify_track_id": spotify_id, "arm": "D", "status": "SUCCESS", "representation_identity": identity, "inferred_views": 4, "inference_seconds": elapsed})
                    except Exception as exc:
                        cache.record_vector(identity, fields, status="FAILED", failure_category="D_VIEW_INFERENCE_FAILED", failure_detail=str(exc), inference_seconds=time.perf_counter() - began)
                        result_rows.append({"spotify_track_id": spotify_id, "arm": "D", "status": "FAILED", "representation_identity": identity, "failure_category": "D_VIEW_INFERENCE_FAILED", "failure_detail": str(exc)})
                _record_progress(progress_path, result_rows, started)

        summary = cache.summary()
    output = {
        "schema_version": "stage5e1-materialization-results-v1",
        "experiment_id": EXPERIMENT_ID,
        "network_downloads": 0,
        "requested_arms": list(requested),
        "corpus_track_count": manifest["track_count"],
        "elapsed_seconds": time.perf_counter() - started,
        "peak_process_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "cache_summary": summary,
        "results": result_rows,
    }
    atomic_json(report / "materialization_results.json", output)
    return output


def cache_rerun(root: str | Path) -> dict[str, Any]:
    result = run_materialization(root)
    unexpected = [row for row in result["results"] if row.get("inferred_views", 0)]
    payload = {
        "schema_version": "stage5e1-cache-rerun-results-v1",
        "experiment_id": EXPERIMENT_ID,
        "track_count": result["corpus_track_count"],
        "network_downloads": 0,
        "unexpected_inference_count": len(unexpected),
        "representation_identity_equality": not unexpected,
        "status": "PASSED" if not unexpected else "FAILED",
    }
    atomic_json(Path(root).resolve() / REPORT_DIRECTORY / "cache_rerun_results.json", payload)
    return payload
