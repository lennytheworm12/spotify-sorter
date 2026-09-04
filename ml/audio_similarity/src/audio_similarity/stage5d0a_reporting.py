"""Non-media snapshots and conservative health verdicts for the first seed batch."""
from __future__ import annotations

import json
import statistics
from collections import Counter

from .stage5b1a_models import file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5d0a_manifest import REPORT_DIRECTORY
from .stage5d0a_worker import read_json, media_git_audit, validate_freeze

RUNNER_CONFIG = {
    "schema_version": "stage5d0a-live-runner-config-v1",
    "batch_number": 1, "maximum_tracks": 500, "automatic_next_batch": False,
    "serial_network_jobs": True, "ordinary_start_delay_seconds": [30, 60],
    "random_generator": "SystemRandom; actual draws persisted",
    "minimum_media_attempt_spacing_seconds": 30, "extraction_request_sleep_seconds": 1.5,
    "search_wall_timeout_seconds": 120, "media_wall_timeout_seconds": 900,
    "maximum_attempts": 4, "retry_after_honored": True,
    "first_youtube_429_minimum_cooldown_seconds": 900,
    "second_youtube_429": "OPEN_CIRCUIT",
    "consecutive_unrelated_challenge_tracks": 2,
    "consecutive_exhausted_transient_tracks": 3,
    "consecutive_http_403_tracks": 3, "explicit_anti_abuse": "OPEN_CIRCUIT",
    "personal_cookies": False, "proxies": False, "bandwidth_throttle": False,
    "resolver": "NATURAL_TITLE_FIRST3_THEN_SINGLE_ARTIST_THEN_TITLE_ONLY_ON_UNSELECTABLE_V2",
    "selector": "frozen Stage 5B.3 minimal YouTube-prior selector",
    "representation": "centered30_v1", "centers_sec": [5, 15, 25], "segment_seconds": 5,
    "weights": {"clap": 0.7172981519, "muq": 0.2827018481},
    "source_retention": "full compressed source + provenance; local Git-ignored only",
}


def summarize(state, network):
    tracks = list(state["tracks"].values())
    counts = Counter(row["state"] for row in tracks)
    requests = network.get("requests", [])
    jobs = network.get("jobs", [])
    deltas = [row["previous_start_delta_seconds"] for row in jobs if row["previous_start_delta_seconds"] is not None]
    spacing_ok = all(right["start_unix"] + 1e-6 >= left["start_unix"] + left["next_spacing_seconds"] for left, right in zip(jobs, jobs[1:]))
    failures = [row for row in requests if row["status"] == "FAILED"]
    warnings = sum(len(row.get("warnings", [])) for row in requests)
    attempted_sources = sum(bool(row.get("selected_video_id")) for row in tracks)
    reliability = counts["COMPLETE"] / attempted_sources if attempted_sources else None
    runtime = max(0, state["updated_at_unix"] - state["started_at_unix"])
    if network.get("circuit") == "OPEN":
        verdict = "BATCH_500_CIRCUIT_BREAKER_STOPPED"
    elif state["status"] != "FINISHED":
        verdict = "BATCH_500_PIPELINE_FAILED" if state["status"] == "PIPELINE_STOPPED" else "BATCH_500_INCOMPLETE"
    elif not spacing_ok or reliability is None or reliability < .95:
        verdict = "BATCH_500_PIPELINE_FAILED"
    elif warnings or failures:
        verdict = "BATCH_500_COMPLETED_WITH_PROVIDER_WARNINGS"
    else:
        verdict = "BATCH_500_HEALTHY"
    return {
        "verdict": verdict, "requested_batch_size": len(tracks), "state_counts": dict(counts),
        "tracks_network_attempted": len({row["spotify_track_id"] for row in jobs}),
        "complete_tracks": counts["COMPLETE"], "manual_tail": counts["MANUAL_TAIL"],
        "automated_selected_tracks": attempted_sources,
        "end_to_end_materialization_fraction": counts["COMPLETE"] / len(tracks) if tracks else None,
        "source_retained_count": sum(row.get("result", {}).get("source_retained", False) for row in tracks),
        "representation_complete_count": sum(row.get("result", {}).get("representation_complete", False) for row in tracks),
        "cache_skips": sum(all(row.get("initial_cache_state", {}).get(key) for key in ("source", "representation")) for row in tracks),
        "resolver_failures": sum(row.get("failure_category") == "RESOLVER_PROVIDER_ERROR" for row in tracks),
        "acquisition_failures": sum(row["state"] == "ACQUISITION_FAILED" and bool(row.get("selected_video_id")) for row in tracks),
        "materialization_failures": counts["MATERIALIZATION_FAILED"],
        "clap_inferred_segments": sum(row.get("result", {}).get("clap_inferred_segments", 0) for row in tracks),
        "muq_inferred_segments": sum(row.get("result", {}).get("muq_inferred_segments", 0) for row in tracks),
        "network_track_jobs": len(jobs), "search_calls": sum(row["kind"] == "SEARCH" for row in requests),
        "media_extraction_calls": sum(row["kind"] == "MEDIA" for row in requests),
        "internal_http_calls": "not exposed by yt-dlp; counts above are extraction boundaries",
        "total_downloaded_bytes": sum(row.get("downloaded_bytes", 0) for row in requests),
        "download_bytes_scope": "completed extraction outputs; partial/interrupted transfer bytes unavailable",
        "inference_count_scope": "completed materializer calls; process loss may interrupt accounting",
        "minimum_track_start_spacing": min(deltas) if deltas else None,
        "mean_track_start_spacing": statistics.mean(deltas) if deltas else None,
        "median_track_start_spacing": statistics.median(deltas) if deltas else None,
        "maximum_track_start_spacing": max(deltas) if deltas else None,
        "spacing_compliant": spacing_ok, "retries": sum(row["attempt"] > 1 for row in requests),
        "http_429_count": sum(row.get("http_status") == 429 for row in failures),
        "http_5xx_count": sum(500 <= (row.get("http_status") or 0) <= 599 for row in failures),
        "timeout_count": sum(any(term in row.get("error", "").lower() for term in ("timeout", "timed out")) for row in failures),
        "retry_after_count": sum(row.get("retry_after_seconds") is not None for row in failures),
        "challenge_count": sum(row.get("challenge", False) for row in failures),
        "provider_warning_count": warnings, "circuit_open": network.get("circuit") == "OPEN",
        "circuit_reason": network.get("circuit_reason"), "runtime_seconds": runtime,
        "completed_tracks_per_hour": 3600 * counts["COMPLETE"] / runtime if runtime else None,
        "selected_source_materialization_fraction": reliability,
        "batch_0002_started": False,
    }


def audit_completed(root, state):
    """Read-only retention/representation checks; never acquire or infer on audit."""
    from .stage5d0a_processor import SeedProcessor
    class NoNetwork:
        def call(self, *args, **kwargs):
            raise RuntimeError("network is forbidden during final cache audit")
    directory = root / ".research_audio/stage5d0a/batch_0001"
    if not (directory / "frozen_upstream_contracts.json").is_file():
        return {"tracks": [], "failures": 1, "error": "frozen upstream snapshot is missing",
                "network_calls": 0, "encoder_calls": 0}
    processor = SeedProcessor(root, directory, NoNetwork())
    batch, _ = validate_freeze(root)
    tracks = {row["spotify_track_id"]: row for row in batch["tracks"]}
    results = []
    for spotify_id, row in state["tracks"].items():
        if row["state"] != "COMPLETE":
            continue
        try:
            if not processor.selection_path(spotify_id).is_file():
                raise ValueError("completed track is missing frozen source selection")
            inspected = processor.inspect(tracks[spotify_id])
            if inspected["source"] is None or inspected["representation"] is None:
                raise ValueError("completed track is missing retained source or representation")
            if inspected["provenance"]["source_sha256"] != row["result"]["source_sha256"]:
                raise ValueError("retained source bytes differ from completed checkpoint")
            if inspected["representation"] != row["result"]["representation"]:
                raise ValueError("representation identity differs from completed checkpoint")
            results.append({"spotify_track_id": spotify_id, "status": "PASS"})
        except Exception as exc:
            results.append({"spotify_track_id": spotify_id, "status": "FAILED",
                            "error": str(exc).replace(str(root), "<PROJECT_ROOT>")})
    return {"tracks": results, "failures": sum(row["status"] == "FAILED" for row in results),
            "network_calls": 0, "encoder_calls": 0}


def write_report(root):
    validate_freeze(root)
    directory = root / ".research_audio/stage5d0a/batch_0001"
    state = read_json(directory / "state.json")
    if state["status"] == "RUNNING":
        raise ValueError("stop or finish the worker before final report generation")
    network = read_json(directory / "network_state.json")
    metrics = summarize(state, network)
    metrics["git_audit"] = media_git_audit(root)
    metrics["scratch_directory_count"] = len(list((root / ".research_audio").glob(".stage5d-scratch-*")))
    try:
        cache_audit = audit_completed(root, state)
    except Exception as exc:
        cache_audit = {"tracks": [], "failures": 1,
                      "error": str(exc).replace(str(root), "<PROJECT_ROOT>"),
                      "network_calls": 0, "encoder_calls": 0}
    metrics["cache_audit_failures"] = cache_audit["failures"]
    if cache_audit["failures"]:
        metrics["verdict"] = "BATCH_500_PIPELINE_FAILED"
    if metrics["scratch_directory_count"] and state["status"] == "FINISHED":
        metrics["verdict"] = "BATCH_500_PIPELINE_FAILED"
    report = root / REPORT_DIRECTORY
    atomic_json(report / "runner_config.json", RUNNER_CONFIG)
    frozen_path = directory / "frozen_upstream_contracts.json"
    atomic_json(report / "frozen_upstream_contracts.json", read_json(frozen_path) if frozen_path.exists() else {"status": "UNAVAILABLE"})
    atomic_json(report / "batch_0001_cache_audit.json", cache_audit)
    atomic_json(report / "batch_0001_metrics.json", metrics)
    def portable(value):
        if isinstance(value, dict):
            return {key: portable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [portable(item) for item in value]
        return value.replace(str(root), "<PROJECT_ROOT>") if isinstance(value, str) else value
    atomic_json(report / "batch_0001_failures.json", portable({key: value for key, value in state["tracks"].items() if value["state"] != "COMPLETE"}))
    atomic_json(report / "batch_0001_network_events.json", portable(network))
    selected = []
    for path in sorted((directory / "selected").glob("*.json")):
        frozen = read_json(path)
        source = frozen["selection"]
        resolver = source.get("resolver", {})
        selected.append({"spotify_track_id": path.stem,
                         "youtube_video_id": source["youtube_video_id"],
                         "source_url": source["source_url"], "selected_rank": source.get("selected_rank"),
                         "query": resolver.get("successful_query"),
                         "query_variant_index": resolver.get("query_variant_index"),
                         "selection_sha256": frozen["selection_sha256"],
                         "freeze_scope": "individual source frozen before its acquisition"})
    atomic_json(report / "batch_0001_selected_sources.json", {"tracks": selected})
    content = "# Stage 5D.0A — Batch 0001\n\n" + metrics["verdict"] + "\n\n"
    content += "Only Batch 0001 was authorized; Batch 0002 remains unstarted. Frozen metadata came solely from Spotify search. Full validated compressed sources stay local and Git-ignored. No selector or representation tuning.\n\n"
    content += "## Observed metrics\n\n```json\n" + json.dumps(metrics, indent=2, sort_keys=True) + "\n```\n\n"
    content += "## Decision\n\nStop after this batch or circuit interruption. Any Batch 0002 run requires a separate owner decision. This is corpus construction and provider-safety evidence, not a retrieval-quality benchmark.\n"
    (report / "batch_0001_report.md").write_text(content)
    atomic_json(report / "artifact_manifest.json", {"files": {path.name: file_sha256(path) for path in sorted(report.iterdir()) if path.is_file() and path.name != "artifact_manifest.json"}})
    return metrics
