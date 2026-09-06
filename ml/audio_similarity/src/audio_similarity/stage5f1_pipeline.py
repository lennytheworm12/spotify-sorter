"""Stage 5F.1 prepare, materialize, compare, analyze, and closeout pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing as mp
import platform
import queue
import resource
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import pandas as pd
import scipy
import torch
import torchaudio
from scipy.stats import spearmanr

from .energy_motion_audio import _failure_track, algorithm_spec_sha256, extract_track, extraction_config_sha256, file_sha256
from .energy_motion_config import Stage5F1Config, canonical_json, canonical_sha256, load_config
from .energy_motion_similarity import compare_tracks, derived_track_features, fit_reference_scaler
from .stage5b1b_artifacts import atomic_json
from .stage5f1_analysis import analyze_rated_pairs
from .stage5f1_cache import FeatureCache, feature_key
from .stage5f1_gain_audit import run_gain_audit
from .stage5f1_inputs import frozen_matrices, frozen_tracks, input_hashes, snapshot_compatible_labels
from .stage5f1_validation import validate_golden, validate_synthetic


REPORT_ROOT = Path("reports/stage5f1_energy_motion")
CACHE_PATH = Path(".research_audio/stage5f1_energy_motion/feature_cache.sqlite")
DESIGN_PATH = Path("docs/designs/stage5f1_energy_motion.md")
CONFIG_PATH = Path("configs/stage5f1_energy_motion_v1.json")


def _run(root: Path, run_id: str) -> Path:
    if not run_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in run_id):
        raise ValueError("run ID must contain only letters, numbers, underscore, or hyphen")
    return root / REPORT_ROOT / run_id


def _implementation_sha(root: Path) -> str:
    names = (
        "energy_motion_config.py", "energy_motion_schema.py", "energy_motion_loudness.py",
        "energy_motion_features.py", "energy_motion_rhythm.py", "energy_motion_audio.py",
    )
    paths = [root / "src/audio_similarity" / name for name in names]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _environment() -> dict[str, Any]:
    ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    document = {
        "python": sys.version.split()[0], "platform": platform.platform(),
        "numpy": np.__version__, "scipy": scipy.__version__, "librosa": librosa.__version__,
        "torch": torch.__version__, "torchaudio": torchaudio.__version__, "pandas": pd.__version__,
        "ffmpeg": ffmpeg,
    }
    document["environment_sha256"] = canonical_sha256(document)
    return document


def _extract_worker(output: Any, arguments: tuple[Any, ...], memory_limit_gib: int) -> None:
    try:
        limit = memory_limit_gib * 1024 ** 3
        _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        resource.setrlimit(resource.RLIMIT_AS, (min(limit, hard) if hard >= 0 else limit, hard))
        output.put({"kind": "result", "payload": extract_track(*arguments).as_dict()})
    except BaseException as exc:
        output.put({"kind": "error", "code": "RESOURCE_LIMIT" if isinstance(exc, MemoryError) else "WORKER_FAILURE",
                    "message": f"{type(exc).__name__}: {exc}"[:500]})


def _bounded_extract(path: Path, source_sha: str, config: Stage5F1Config,
                     environment_sha: str, implementation_sha: str) -> dict[str, Any]:
    context = mp.get_context("spawn")
    output = context.Queue(maxsize=1)
    arguments = (path, source_sha, config.extraction, environment_sha, implementation_sha,
                 config.execution.loudness_timeout_seconds)
    process = context.Process(target=_extract_worker, args=(output, arguments, config.execution.worker_memory_limit_gib))
    process.start()
    process.join(config.execution.per_track_timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(10)
        code, message = "TIMEOUT", f"full-track extraction exceeded {config.execution.per_track_timeout_seconds} seconds"
    else:
        try:
            message_record = output.get(timeout=2)
        except queue.Empty:
            message_record = {"kind": "error", "code": "WORKER_EXIT", "message": f"worker exited {process.exitcode} without a result"}
        if message_record["kind"] == "result":
            return message_record["payload"]
        code, message = message_record["code"], message_record["message"]
    return _failure_track(source_sha256=source_sha, environment_sha256=environment_sha,
                          implementation_sha256=implementation_sha, config=config.extraction,
                          code=code, message=message).as_dict()


def _config(root: Path) -> Stage5F1Config:
    return load_config(root / CONFIG_PATH)


def _safe_correlation(rows: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    pairs = [(row.get(left), row.get(right)) for row in rows]
    pairs = [(float(a), float(b)) for a, b in pairs if a is not None and b is not None
             and math.isfinite(float(a)) and math.isfinite(float(b))]
    if len(pairs) < 3 or len({a for a, _ in pairs}) < 2 or len({b for _, b in pairs}) < 2:
        return {"rho": None, "count": len(pairs), "reason": "INSUFFICIENT_OR_CONSTANT_INPUT"}
    statistic = spearmanr([a for a, _ in pairs], [b for _, b in pairs]).statistic
    return {"rho": float(statistic), "count": len(pairs)}


def prepare(root: Path, run_id: str) -> dict[str, Any]:
    report = _run(root, run_id)
    report.mkdir(parents=True, exist_ok=True)
    config = _config(root)
    tracks = frozen_tracks(root, "original100")
    environment = _environment()
    design_target = report / "design.md"
    shutil.copyfile(root / DESIGN_PATH, design_target)
    atomic_json(report / "experiment_config.json", config.as_dict())
    atomic_json(report / "environment.json", environment)
    atomic_json(report / "algorithm_spec.json", {
        "algorithm_spec_sha256": algorithm_spec_sha256(),
        "implementation_sha256": _implementation_sha(root),
        "design_sha256": file_sha256(root / DESIGN_PATH),
        "config_sha256": config.sha256,
    })
    atomic_json(report / "source_manifest.json", {
        "schema_version": "stage5f1-source-manifest-v1", "corpus": "original100",
        "track_count": len(tracks), "tracks": tracks,
    })
    labels = snapshot_compatible_labels(root, tracks)
    atomic_json(report / "label_evidence.json", {"evidence": labels["evidence"]})
    atomic_json(report / "resolved_labels.json", {
        key: labels[key] for key in ("resolved_labels", "pair_members", "conflicts", "unsure_pairs", "counts")
    })
    atomic_json(report / "label_search_audit.json", {
        "strategy": "compatible_existing_stage5e_ratings_only", "new_review_queue_created": False,
        "evidence_rows": len(labels["evidence"]), "resolved_pairs": len(labels["resolved_labels"]),
        "conflicts": len(labels["conflicts"]), "unsure_pairs": len(labels["unsure_pairs"]),
    })
    inputs = input_hashes(root)
    atomic_json(report / "input_reference.json", {
        "schema_version": "stage5f1-input-reference-v1", "input_hashes": inputs,
        "network_downloads": 0, "encoder_calls": 0, "production_activation": False,
    })
    atomic_json(report / "preparation_status.json", {
        "status": "READY", "run_id": run_id, "config_sha256": config.sha256,
        "source_count": len(tracks), "rating_counts": labels["counts"],
    })
    atomic_json(report / "schema_registry.json", {
        "track": "stage5f1-energy-motion-track-v1", "pair": "stage5f1-energy-motion-pair-v1",
        "scaler": "stage5f1-energy-motion-scaler-v1", "null_policy": "finite-or-explicit-null-with-status",
    })
    atomic_json(report / "validation_config.json", {
        "config_sha256": config.sha256, "evaluation": asdict(config.evaluation),
        "frozen_before_historical_analysis": True,
    })
    return {"status": "READY", "report": str(report), "source_count": len(tracks), "config_sha256": config.sha256}


def synthetic(root: Path, run_id: str) -> dict[str, Any]:
    report = _run(root, run_id)
    config = _config(root)
    environment = json.loads((report / "environment.json").read_text())
    result = validate_synthetic(config, environment["environment_sha256"], _implementation_sha(root))
    atomic_json(report / "synthetic_validation.json", result)
    return result


def materialize(root: Path, run_id: str, corpus: str = "original100") -> dict[str, Any]:
    report = _run(root, run_id)
    config = _config(root)
    environment = json.loads((report / "environment.json").read_text())
    implementation = _implementation_sha(root)
    tracks = frozen_tracks(root, corpus)
    cache = FeatureCache(root / CACHE_PATH)
    started = time.monotonic()
    hits = misses = 0
    feature_by_sha: dict[str, dict[str, Any]] = {}
    try:
        for index, membership in enumerate(tracks, 1):
            source_sha = membership["source_sha256"]
            source_path = Path(membership["retained_source_path"])
            source_available = source_path.is_file()
            if source_available and file_sha256(source_path) != source_sha:
                raise ValueError(f"frozen source hash mismatch for {membership['spotify_track_id']}")
            key = feature_key(
                source_sha, config.extractor_id, algorithm_spec_sha256(), implementation,
                extraction_config_sha256(config.extraction), environment["environment_sha256"],
            )
            cached = cache.get(key) if source_available else None
            if cached is not None:
                hits += 1
                feature_by_sha[source_sha] = cached
                continue
            misses += 1
            result = _bounded_extract(source_path, source_sha, config, environment["environment_sha256"], implementation)
            if source_available:
                cache.put(key, source_sha, result)
            feature_by_sha[source_sha] = result
            if index % 10 == 0:
                print(json.dumps({"processed": index, "total": len(tracks), "cache_hits": hits, "computed": misses}), flush=True)
    finally:
        cache.close()
    joined = [membership | {"features": feature_by_sha[membership["source_sha256"]]} for membership in tracks]
    rows = [{
        "spotify_track_id": row["spotify_track_id"], "source_sha256": row["source_sha256"],
        "status": row["features"]["status"],
        "payload_json": canonical_json(row["features"]).decode("utf-8"),
    } for row in joined]
    output = report / ("tempo_motion_features.parquet" if corpus == "original100" else "reference741_features.parquet")
    pd.DataFrame(rows).sort_values("spotify_track_id", kind="stable").to_parquet(output, index=False)
    profiles = []
    for row in joined:
        for profile in row["features"].get("temporal_profiles", []):
            profiles.append({"spotify_track_id": row["spotify_track_id"], "source_sha256": row["source_sha256"], **profile})
    if corpus == "original100":
        pd.DataFrame(profiles).sort_values(["spotify_track_id", "start_seconds"], kind="stable").to_parquet(report / "temporal_profiles.parquet", index=False)
    counts = Counter(row["features"]["status"] for row in joined)
    ledger = {
        "schema_version": "stage5f1-materialization-ledger-v1", "corpus": corpus,
        "source_count": len(tracks), "cache_hits": hits, "computed": misses,
        "status_counts": dict(sorted(counts.items())), "elapsed_seconds": time.monotonic() - started,
        "output_sha256": file_sha256(output), "network_downloads": 0, "encoder_calls": 0,
    }
    ledgers = report / "ledgers"
    ledgers.mkdir(exist_ok=True)
    first = ledgers / f"first_run_{corpus}.json"
    if first.exists():
        sequence = 1
        while (ledgers / f"rerun_{corpus}_{sequence:04d}.json").exists():
            sequence += 1
        atomic_json(ledgers / f"rerun_{corpus}_{sequence:04d}.json", ledger)
    else:
        atomic_json(first, ledger)
    atomic_json(report / "extraction_diagnostics.json", {
        "corpus": corpus, "status_counts": ledger["status_counts"],
        "family_status_counts": {
            family: dict(sorted(Counter(row["features"][family]["status"] for row in joined).items()))
            for family in ("source_level", "dynamics", "activity", "percussion", "pulse", "beat")
        },
    })
    return ledger


def _load_track_rows(report: Path, corpus: str = "original100") -> list[dict[str, Any]]:
    name = "tempo_motion_features.parquet" if corpus == "original100" else "reference741_features.parquet"
    frame = pd.read_parquet(report / name).sort_values("spotify_track_id", kind="stable")
    return [{"spotify_track_id": row.spotify_track_id, **json.loads(row.payload_json)} for row in frame.itertuples(index=False)]


def golden(root: Path, run_id: str) -> dict[str, Any]:
    report = _run(root, run_id)
    tracks = _load_track_rows(report)
    manifest = json.loads((report / "source_manifest.json").read_text())["tracks"]
    result = validate_golden(tracks, manifest)
    atomic_json(report / "golden_validation.json", result)
    atomic_json(report / "golden_manifest.json", {"tracks": [row["spotify_track_id"] for row in result["checks"]]})
    return result


def fit_scaler(root: Path, run_id: str, reference_corpus: str | None = None) -> dict[str, Any]:
    report = _run(root, run_id)
    config = _config(root)
    corpus = reference_corpus or config.comparison.reference_corpus
    tracks = _load_track_rows(report, corpus)
    manifest_sha = file_sha256(report / ("source_manifest.json" if corpus == "original100" else "reference741_features.parquet"))
    scaler = fit_reference_scaler(tracks, config.comparison, manifest_sha)
    atomic_json(report / "scaler.json", scaler)
    derived = [derived_track_features(row, scaler) | {"spotify_track_id": row["spotify_track_id"]} for row in tracks]
    pd.DataFrame({
        "spotify_track_id": [row["spotify_track_id"] for row in derived],
        "source_sha256": [row["source_sha256"] for row in derived],
        "payload_json": [canonical_json(row).decode("utf-8") for row in derived],
    }).sort_values("spotify_track_id", kind="stable").to_parquet(report / "derived_features.parquet", index=False)
    return {"status": "COMPLETE", "scaler_sha256": scaler["scaler_sha256"], "source_count": len(tracks)}


def audit_gain(root: Path, run_id: str) -> dict[str, Any]:
    report = _run(root, run_id)
    config = _config(root)
    tracks = frozen_tracks(root, "original100")
    references = {row["spotify_track_id"]: row for row in _load_track_rows(report)}
    scaler = json.loads((report / "scaler.json").read_text())
    environment = json.loads((report / "environment.json").read_text())
    result = run_gain_audit(root, report, tracks, references, scaler, config, environment["environment_sha256"])
    atomic_json(report / "distribution_gain_audit.json", result)
    return {key: result[key] for key in ("eligible_track_count", "eligible_variant_count", "pass_fraction", "gate_passed")}


def compare_and_analyze(root: Path, run_id: str) -> dict[str, Any]:
    report = _run(root, run_id)
    config = _config(root)
    synthetic_doc = json.loads((report / "synthetic_validation.json").read_text())
    golden_doc = json.loads((report / "golden_validation.json").read_text())
    if synthetic_doc["status"] != "PASSED" or golden_doc["status"] != "PASSED":
        raise ValueError("validation must pass before historical-rating analysis")
    gain_audit = json.loads((report / "distribution_gain_audit.json").read_text())
    if not gain_audit["gate_passed"]:
        raise ValueError("gain audit must pass before historical-rating analysis")
    track_rows = _load_track_rows(report)
    membership = {row["spotify_track_id"]: row for row in json.loads((report / "source_manifest.json").read_text())["tracks"]}
    track_rows = [row | {
        "artist_credit": membership[row["spotify_track_id"]].get("primary_artist_id")
        or membership[row["spotify_track_id"]].get("artist_credit"),
        "source_format": membership[row["spotify_track_id"]].get("source_format"),
        "manifest_sample_rate_hz": membership[row["spotify_track_id"]].get("sample_rate_hz"),
        "manifest_channels": membership[row["spotify_track_id"]].get("channels"),
        "youtube_video_id": membership[row["spotify_track_id"]].get("youtube_video_id"),
    } for row in track_rows]
    by_id = {row["spotify_track_id"]: row for row in track_rows}
    ids = sorted(by_id)
    scaler = json.loads((report / "scaler.json").read_text())
    labels = json.loads((report / "resolved_labels.json").read_text())
    resolved = labels["resolved_labels"]
    pair_members = labels["pair_members"]
    label_by_members = {tuple(sorted(members)): resolved[pair] for pair, members in pair_members.items() if pair in resolved}
    matrices = frozen_matrices(root, ids)
    rows = []
    full_payload = []
    for left_index, left_id in enumerate(ids):
        for right_index in range(left_index + 1, len(ids)):
            right_id = ids[right_index]
            if (by_id[left_id]["source_sha256"] == by_id[right_id]["source_sha256"]
                    or by_id[left_id].get("youtube_video_id") == by_id[right_id].get("youtube_video_id")):
                continue
            pair = {"schema_version": "stage5f1-energy-motion-pair-v1", **compare_tracks(
                left_id, right_id, by_id[left_id], by_id[right_id], scaler, config.comparison
            ).as_dict()}
            activity = pair["components"]["activity"]
            left_lufs = by_id[left_id].get("source_level", {}).get("values", {}).get("integrated_loudness_lufs")
            right_lufs = by_id[right_id].get("source_level", {}).get("values", {}).get("integrated_loudness_lufs")
            row = {
                "pair_id": pair["pair_id"], "left_spotify_id": left_id, "right_spotify_id": right_id,
                "a_clap": float(matrices["a_clap"][left_index, right_index]),
                "muq": float(matrices["muq"][left_index, right_index]),
                "base_combined": float(matrices["a_combined"][left_index, right_index]),
                "activity_similarity": activity["similarity"],
                "human_rating": label_by_members.get((left_id, right_id)),
                "normalization_warning": bool({"POSSIBLE_CLIPPING", "EXTREME_NORMALIZATION_GAIN"}
                                              & (set(by_id[left_id].get("warnings", [])) | set(by_id[right_id].get("warnings", [])))),
                "source_lufs_mean": (left_lufs + right_lufs) / 2 if left_lufs is not None and right_lufs is not None else None,
                "source_lufs_abs_difference": abs(left_lufs - right_lufs) if left_lufs is not None and right_lufs is not None else None,
            }
            row.update({f"{name}_similarity": component.get("similarity")
                        for name, component in pair["components"].items()})
            rows.append(row)
            full_payload.append(pair | row)
    pd.DataFrame({
        **{key: [row.get(key) for row in rows] for key in rows[0]},
        "payload_json": [canonical_json(row).decode("utf-8") for row in full_payload],
    }).sort_values("pair_id", kind="stable").to_parquet(report / "rated_pair_features.parquet", index=False)
    analysis = analyze_rated_pairs(rows, track_rows, config.evaluation, bool(gain_audit["gate_passed"]))
    atomic_json(report / "rated_pair_analysis.json", analysis)
    atomic_json(report / "error_slice_analysis.json", analysis["primary_effect"] | analysis["pair_counts"])
    atomic_json(report / "counterexample_analysis.json", analysis["counterexamples"])
    atomic_json(report / "redundancy_analysis.json", analysis["correlations"])
    feature_names = sorted({name for row in track_rows for family in ("source_level", "normalization", "activity", "percussion", "dynamics", "pulse", "beat")
                            for name, value in row.get(family, {}).get("values", {}).items() if isinstance(value, (int, float))})
    distributions = {}
    for name in feature_names:
        values = [float(value) for row in track_rows for family in ("source_level", "normalization", "activity", "percussion", "dynamics", "pulse", "beat")
                  if isinstance((value := row.get(family, {}).get("values", {}).get(name)), (int, float)) and math.isfinite(float(value))]
        if values:
            distributions[name] = {"count": len(values), "min": min(values), "q25": float(np.quantile(values, .25)),
                                   "median": float(np.quantile(values, .5)), "q75": float(np.quantile(values, .75)), "max": max(values)}
    atomic_json(report / "feature_distribution_analysis.json", distributions)
    atomic_json(report / "residual_analysis.json", {
        "definition": "predeclared high-base/low-rated error slice; no cosine-minus-rating arithmetic",
        "primary_effect": analysis["primary_effect"], "pair_counts": analysis["pair_counts"],
    })
    atomic_json(report / "reliability_analysis.json", {
        "pulse_thresholds_predeclared": [0.45, 0.55, 0.65],
        "valid_counts": {str(threshold): sum((row.get("pulse", {}).get("values", {}).get("pulse_reliability") or 0) >= threshold for row in track_rows)
                         for threshold in (0.45, 0.55, 0.65)},
        "primary_activity_is_pulse_independent": True,
    })
    atomic_json(report / "normalization_confound_analysis.json", {
        "source_lufs_mean_vs_activity_similarity": _safe_correlation(rows, "source_lufs_mean", "activity_similarity"),
        "source_lufs_difference_vs_activity_similarity": _safe_correlation(rows, "source_lufs_abs_difference", "activity_similarity"),
        "warning_exclusion_sensitivity": analysis["normalization_sensitivity"],
        "raw_loudness_used_in_primary_similarity": False,
    })
    family_names = ("source_level", "normalization", "activity", "percussion", "dynamics", "pulse", "beat")
    atomic_json(report / "coverage_analysis.json", {
        "tracks": [{"spotify_track_id": row["spotify_track_id"], "artist_group": row["artist_credit"],
                    "source_format": row["source_format"], "sample_rate_hz": row["manifest_sample_rate_hz"],
                    "channels": row["manifest_channels"],
                    "family_status": {family: row.get(family, {}).get("status") for family in family_names}}
                   for row in sorted(track_rows, key=lambda item: item["spotify_track_id"])],
    })
    evidence = json.loads((report / "label_evidence.json").read_text())["evidence"]
    directed = pd.DataFrame([{**item, "direction_status": "UNAVAILABLE_IN_SOURCE_ARTIFACT"} for item in evidence])
    directed.sort_values(["pair_id", "source", "source_sha256"], kind="stable").to_parquet(report / "directed_pair_appearances.parquet", index=False)
    atomic_json(report / "conditional_reranking.json", {
        "executed": False, "production_activation": False,
        "reason": analysis["reranking_reason"],
    })
    return analysis


def cache_rerun(root: Path, run_id: str) -> dict[str, Any]:
    report = _run(root, run_id)
    first = report / "ledgers/first_run_original100.json"
    first_hash = file_sha256(first)
    output = report / "tempo_motion_features.parquet"
    output_hash = file_sha256(output)
    ledger = materialize(root, run_id, "original100")
    result = {
        "status": "PASSED" if ledger["computed"] == 0 and file_sha256(first) == first_hash and file_sha256(output) == output_hash else "FAILED",
        "computed": ledger["computed"], "cache_hits": ledger["cache_hits"],
        "first_run_ledger_preserved": file_sha256(first) == first_hash,
        "output_preserved": file_sha256(output) == output_hash,
    }
    atomic_json(report / "cache_rerun_results.json", result)
    return result


def finalize(root: Path, run_id: str) -> dict[str, Any]:
    report = _run(root, run_id)
    required = [
        "design.md", "experiment_config.json", "environment.json", "algorithm_spec.json",
        "source_manifest.json", "synthetic_validation.json", "golden_validation.json",
        "tempo_motion_features.parquet", "temporal_profiles.parquet", "scaler.json",
        "derived_features.parquet", "rated_pair_features.parquet", "rated_pair_analysis.json",
        "cache_rerun_results.json", "input_reference.json",
        "schema_registry.json", "validation_config.json", "distribution_gain_audit.json",
        "feature_distribution_analysis.json", "residual_analysis.json", "reliability_analysis.json",
        "directed_pair_appearances.parquet",
    ]
    missing = [name for name in required if not (report / name).is_file()]
    if missing:
        raise ValueError(f"closeout missing artifacts: {missing}")
    analysis = json.loads((report / "rated_pair_analysis.json").read_text())
    cache = json.loads((report / "cache_rerun_results.json").read_text())
    synthetic_doc = json.loads((report / "synthetic_validation.json").read_text())
    golden_doc = json.loads((report / "golden_validation.json").read_text())
    gain_doc = json.loads((report / "distribution_gain_audit.json").read_text())
    inputs = json.loads((report / "input_reference.json").read_text())["input_hashes"]
    current = input_hashes(root)
    unchanged = inputs == current
    engineering_passed = all((cache["status"] == "PASSED", unchanged,
                              synthetic_doc["status"] == "PASSED", golden_doc["status"] == "PASSED",
                              gain_doc["gate_passed"], analysis["coverage"]["core_valid_count"] >= 95))
    verdict = analysis["verdict"] if engineering_passed else "REVISE"
    closeout = {
        "schema_version": "stage5f1-closeout-v1", "verdict": verdict,
        "production_activation": False, "network_downloads": 0, "new_review_queue_created": False,
        "stage5e_inputs_unchanged": unchanged, "cache_rerun_status": cache["status"],
        "engineering_gates_passed": engineering_passed, "gain_audit_gate_passed": gain_doc["gate_passed"],
        "reference741_status": "NOT_REQUIRED_OR_RUN_ORIGINAL100_IS_FROZEN_SCALER_REFERENCE",
        "limitations": analysis["limitations"],
    }
    atomic_json(report / "closeout.json", closeout)
    report_text = f"""# Stage 5F.1 Energy and Motion closeout

**Verdict:** `{verdict}`

The deterministic full-track energy/motion layer was evaluated beside the frozen A CLAP + MuQ representation. Production activation is prohibited and no ranking was changed.

- Original100 extraction coverage: {analysis['coverage']['core_valid_count']}/{analysis['coverage']['track_count']} core-valid tracks.
- Pulse-valid coverage: {analysis['coverage']['pulse_valid_count']}/{analysis['coverage']['track_count']} tracks.
- Compatible rated pairs: {analysis['pair_counts']['rated']}.
- Primary high-base slice: {analysis['pair_counts']['primary_low']} low-rated and {analysis['pair_counts']['primary_high']} high-rated pairs.
- Primary median activity-mismatch difference: {analysis['primary_effect']['median_mismatch_difference']}.
- Cache rerun: `{cache['status']}` with {cache['computed']} recomputations.
- Frozen Stage 5E inputs unchanged: `{unchanged}`.

The historical evidence is selected by earlier models and is not a prospective retrieval holdout. Arousal and danceability values remain transparent diagnostic proxies. Reranking requires a separate Stage 5F.2 design even when this stage is supported.
"""
    (report / "experiment_report.md").write_text(report_text)
    files = []
    for path in sorted(report.rglob("*")):
        if path.is_file() and path.name != "artifact_manifest.json":
            files.append({"path": str(path.relative_to(report)), "size_bytes": path.stat().st_size, "sha256": file_sha256(path)})
    atomic_json(report / "artifact_manifest.json", {
        "schema_version": "stage5f1-artifact-manifest-v1", "run_id": run_id,
        "files": files,
    })
    return closeout
