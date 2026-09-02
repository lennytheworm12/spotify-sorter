"""Stage 5B.1E natural-query discovery, frozen resolver replay, and audit analysis."""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpPythonBackend, YtDlpSearchError
from .stage5b1a_config import QueryConfig
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import load_challenge_config, load_challenge_manifest, load_frozen_policies
from .stage5b1c_tier2 import _mapped_sol
from .stage5b1d_rediscovery import evaluate_resolver_cascade, verify_frozen_resolver_stack
from .stage5b1d_queries import load_stage5b1d_config
from .stage5b1e_queries import (
    EXPERIMENT_ID,
    STRATEGY_IDS,
    Stage5B1EConfig,
    build_query_strategy_artifact,
    load_stage5b1e_config,
    verify_frozen_inputs,
)


DISCOVERY_SCHEMA_VERSION = "stage5b1e-query-discovery-v1"
REPLAY_SCHEMA_VERSION = "stage5b1e-resolver-replays-v1"
COMPARISON_SCHEMA_VERSION = "stage5b1e-candidate-pool-comparison-v1"
AUDIT_SCHEMA_VERSION = "stage5b1e-human-audit-queue-v1"
MANIFEST_SCHEMA_VERSION = "stage5b1e-artifact-manifest-v1"
SAFE_LABELS = {"IDEAL", "ACCEPTABLE"}
REVIEW_LABELS = {"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"}
REVIEW_COLUMNS = [
    "review_schema_version", "stable_track_id", "expected_title", "expected_artists",
    "expected_album", "expected_duration_seconds", "expected_release_year",
    "candidate_video_id", "candidate_url", "candidate_title", "candidate_uploader",
    "candidate_channel", "candidate_duration_seconds", "candidate_view_count",
    "candidate_description", "strategy_ids", "audit_reasons", "candidate_review_label",
    "candidate_note", "track_note",
]
DECISION_BY_STRATEGY = {
    "Q0_CURRENT_CONTROL": "KEEP_CURRENT_QUERY",
    "Q1_NATURAL_SPOTIFY_TITLE": "ADOPT_NATURAL_TITLE",
    "Q2_NATURAL_TITLE_PLUS_ARTIST": "ADOPT_NATURAL_TITLE_PLUS_ARTIST",
    "Q3_CORE_TITLE_ARTIST_VERSION": "ADOPT_CORE_TITLE_ARTIST_VERSION",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _challenge(config: Stage5B1EConfig):
    challenge = load_challenge_config(config.challenge_config_path)
    manifest = load_challenge_manifest(
        challenge.manifest_path, expected_sha256=challenge.manifest_sha256
    )
    return challenge, manifest


def expected_strategy_artifact(config: Stage5B1EConfig) -> dict[str, Any]:
    _, manifest = _challenge(config)
    return build_query_strategy_artifact(config, [row.track for row in manifest.tracks])


def verify_strategy_artifact(config: Stage5B1EConfig, artifact: dict[str, Any]) -> None:
    if artifact != expected_strategy_artifact(config):
        raise Stage5B1AValidationError("frozen Stage 5B.1E strategy artifact changed")


def _discovery_summary(tracks: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = [outcome for track in tracks for outcome in track["strategies"]]
    return {
        "tracks_recorded": len(tracks),
        "strategy_outcomes_recorded": len(outcomes),
        "successful_queries": sum(outcome.get("error") is None for outcome in outcomes),
        "failed_queries": sum(outcome.get("error") is not None for outcome in outcomes),
        "zero_candidate_queries": sum(
            outcome.get("error") is None and not outcome.get("candidates") for outcome in outcomes
        ),
        "unique_candidate_video_ids": len({
            candidate["youtube_video_id"]
            for outcome in outcomes for candidate in outcome.get("candidates", [])
        }),
        "warning_count": sum(len(outcome.get("warnings") or []) for outcome in outcomes),
        "yt_dlp_versions": sorted({
            str(outcome.get("provider", {}).get("version"))
            for outcome in outcomes if outcome.get("provider", {}).get("version")
        }),
    }


def _discovery_document(
    config: Stage5B1EConfig,
    strategy_artifact: dict[str, Any],
    tracks: list[dict[str, Any]],
    *,
    started_at: str,
    completed_at: str | None = None,
) -> dict[str, Any]:
    count = len(strategy_artifact["tracks"]) * len(STRATEGY_IDS)
    summary = _discovery_summary(tracks)
    complete = summary["strategy_outcomes_recorded"] == count
    return {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "config_sha256": config.sha256,
        "strategies_sha256": file_sha256(config.artifacts["strategies"]),
        "status": "DISCOVERY_COMPLETE" if complete else "DISCOVERY_IN_PROGRESS",
        "started_at_utc": started_at,
        "completed_at_utc": completed_at if complete else None,
        "provider_mode": {
            "search_prefix": "ytsearch5:", "candidate_limit": 5,
            "metadata_only": True, "sequential": True,
        },
        "summary": summary,
        "tracks": tracks,
        "media_activity": {
            "audio_downloads": 0, "video_downloads": 0, "stage5a_calls": 0,
            "clap_calls": 0, "muq_calls": 0,
        },
    }


def run_discovery(
    config: Stage5B1EConfig,
    strategy_artifact: dict[str, Any],
    adapter: YtDlpDiscoveryAdapter,
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] = _utc_now,
    checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run 4×50 searches sequentially and checkpoint after every query."""

    verify_strategy_artifact(config, strategy_artifact)
    existing: dict[str, Any] | None = None
    if config.artifacts["discovery"].exists():
        existing = _json(config.artifacts["discovery"])
        if (
            existing.get("schema_version") != DISCOVERY_SCHEMA_VERSION
            or existing.get("config_sha256") != config.sha256
            or existing.get("strategies_sha256") != file_sha256(config.artifacts["strategies"])
        ):
            raise Stage5B1AValidationError("existing Stage 5B.1E checkpoint identity changed")
    started_at = existing.get("started_at_utc") if existing else now()
    completed: dict[tuple[str, str], dict[str, Any]] = {}
    if existing:
        for row in existing.get("tracks", []):
            for outcome in row.get("strategies", []):
                completed[(row["track"]["stable_track_id"], outcome["strategy_id"])] = outcome
    output_by_id: dict[str, dict[str, Any]] = {}
    for track_index, row in enumerate(strategy_artifact["tracks"]):
        track = SpotifyTrack.from_dict(row["target"])
        output = {"track": track.to_dict(), "strategies": []}
        output_by_id[track.stable_track_id] = output
        ran_query = False
        for query_index, query_row in enumerate(row["queries"]):
            key = (track.stable_track_id, query_row["strategy_id"])
            if key in completed:
                output["strategies"].append(completed[key])
                continue
            requested_at = now()
            ran_query = True
            try:
                result = adapter.discover_query(track, query_row["query"], limit=5).to_dict()
                outcome = {
                    "strategy_id": query_row["strategy_id"],
                    "query": query_row["query"],
                    "requested_at_utc": requested_at,
                    "completed_at_utc": now(),
                    "request": result["request"],
                    "provider": result["provider"],
                    "candidates": result["candidates"],
                    "candidate_video_ids": result["candidate_video_ids"],
                    "warnings": result["warnings"],
                    "error": None,
                }
            except YtDlpSearchError as exc:
                outcome = {
                    "strategy_id": query_row["strategy_id"],
                    "query": query_row["query"],
                    "requested_at_utc": requested_at,
                    "completed_at_utc": now(),
                    "request": {"search_expression": config.provider.search_expression(query_row["query"]), "download": False},
                    "provider": {"name": "yt_dlp", "version": getattr(adapter.backend, "version", "unknown")},
                    "candidates": [], "candidate_video_ids": [],
                    "warnings": list(exc.warnings), "error": exc.to_dict(),
                }
            output["strategies"].append(outcome)
            document = _discovery_document(
                config, strategy_artifact, list(output_by_id.values()), started_at=started_at
            )
            (checkpoint or (lambda value: atomic_json(config.artifacts["discovery"], value)))(document)
            if query_index + 1 < len(row["queries"]):
                sleep(config.sleep_between_queries_seconds)
        if ran_query and track_index + 1 < len(strategy_artifact["tracks"]):
            sleep(config.provider.sleep_between_tracks_seconds)
    document = _discovery_document(
        config, strategy_artifact, list(output_by_id.values()),
        started_at=started_at, completed_at=now(),
    )
    (checkpoint or (lambda value: atomic_json(config.artifacts["discovery"], value)))(document)
    return document


def _human_evidence(config: Stage5B1EConfig) -> dict[tuple[str, str], str]:
    evidence: dict[tuple[str, str], str] = {}

    def add(stable_id: str, video_id: str, label: str) -> None:
        label = label.strip().upper()
        if not label:
            return
        key = (stable_id, video_id)
        if key in evidence and evidence[key] != label:
            raise Stage5B1AValidationError(f"conflicting human labels for {key}")
        evidence[key] = label

    human_path = config.project_root / config.frozen_inputs["challenge_human_review"]["path"]
    with human_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            add(row["stable_track_id"], row["candidate_video_id"], row["candidate_review_label"])
    for input_name in ("tier2_human_audit", "strong_metadata_human_audit"):
        payload = _json(config.project_root / config.frozen_inputs[input_name]["path"])
        for row in payload.get("judgments", []):
            add(row["stable_track_id"], row["candidate_video_id"], row["human_label"])
    if config.artifacts["human_review"].exists():
        with config.artifacts["human_review"].open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                add(row["stable_track_id"], row["candidate_video_id"], row["candidate_review_label"])
    return evidence


def _sol_evidence(config: Stage5B1EConfig) -> dict[tuple[str, str], str]:
    report_dir = config.project_root / "reports/stage5b1b_fresh_challenge"
    return {key: value["label"] for key, value in _mapped_sol(report_dir).items()}


def _metric(ids: list[str], safe_ids: set[str], k: int) -> bool:
    return bool(set(ids[:k]) & safe_ids)


def _selected_source(replay: dict[str, Any]) -> str | None:
    selected_id = replay["final_decision"].get("selected_video_id")
    if not selected_id:
        return None
    for row in replay["feature_layers"]["stage5b1b"]["candidates"]:
        if row["candidate"]["youtube_video_id"] == selected_id:
            return row["features"]["source"]["source_type"]
    raise Stage5B1AValidationError("resolver selected candidate missing from feature layer")


def _canonical_strong_source_present(replay: dict[str, Any]) -> bool:
    return any(
        row["features"]["recording_eligible"]
        and row["features"]["source"]["source_type"]
        in {"ART_TRACK_TOPIC", "OFFICIAL_AUDIO"}
        for row in replay["feature_layers"]["stage5b1b"]["candidates"]
    )


def _candidate_source_types(replay: dict[str, Any]) -> dict[str, str]:
    return {
        row["candidate"]["youtube_video_id"]: row["features"]["source"]["source_type"]
        for row in replay["feature_layers"]["stage5b1b"]["candidates"]
    }


def _replay_candidate_pool(
    track: SpotifyTrack,
    candidates: list[dict[str, Any]],
    *,
    policy: Any,
    boundaries: Any,
) -> dict[str, Any]:
    """Treat a provider-empty pool as uncertainty before entering frozen layers."""

    if candidates:
        return evaluate_resolver_cascade(
            track, candidates, policy=policy, boundaries=boundaries
        )
    return {
        "selected_stage": "MATCH_UNCERTAIN",
        "final_decision": {
            "status": "MATCH_UNCERTAIN",
            "selected_video_id": None,
            "selected_candidate_rank": None,
            "uncertainty_reason": "NO_CANDIDATES",
            "ranked_plausible_candidates": [],
            "evidence_summary": {"candidate_count": 0},
        },
        "layer_decisions": {},
        "feature_layers": {"stage5b1b": {"candidates": []}},
    }


def evaluate(config: Stage5B1EConfig, discovery: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    verify_frozen_inputs(config)
    frozen_regression = verify_frozen_resolver_stack(
        load_stage5b1d_config(
            config.project_root / "configs/stage5b1d_targeted_rediscovery.json"
        )
    )
    if discovery.get("schema_version") != DISCOVERY_SCHEMA_VERSION or discovery.get("status") != "DISCOVERY_COMPLETE":
        raise Stage5B1AValidationError("Stage 5B.1E discovery is not complete")
    if discovery.get("media_activity") != {
        "audio_downloads": 0, "video_downloads": 0, "stage5a_calls": 0,
        "clap_calls": 0, "muq_calls": 0,
    }:
        raise Stage5B1AValidationError("Stage 5B.1E media guard changed")
    challenge, manifest = _challenge(config)
    boundaries, policies = load_frozen_policies(challenge)
    track_by_id = {row.track.stable_track_id: row.track for row in manifest.tracks}
    replays: list[dict[str, Any]] = []
    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in discovery["tracks"]:
        stable_id = row["track"]["stable_track_id"]
        if stable_id not in track_by_id:
            raise Stage5B1AValidationError(f"discovery track outside frozen manifest: {stable_id}")
        observed = tuple(item["strategy_id"] for item in row["strategies"])
        if observed != STRATEGY_IDS:
            raise Stage5B1AValidationError(f"query strategy order changed for {stable_id}")
        for outcome in row["strategies"]:
            replay = _replay_candidate_pool(
                track_by_id[stable_id], outcome["candidates"],
                policy=policies["POLICY_BALANCED_V1"], boundaries=boundaries,
            )
            compact = {
                "stable_track_id": stable_id,
                "strategy_id": outcome["strategy_id"],
                "query": outcome["query"],
                "candidate_video_ids": outcome["candidate_video_ids"],
                "candidate_count": len(outcome["candidates"]),
                "request_error": outcome["error"],
                "warnings": outcome["warnings"],
                "selected_stage": replay["selected_stage"],
                "final_decision": replay["final_decision"],
                "selected_source_type": _selected_source(replay),
                "canonical_strong_source_present": _canonical_strong_source_present(replay),
                "candidate_source_types": _candidate_source_types(replay),
                "candidates": outcome["candidates"],
            }
            replays.append(compact)
            by_strategy[outcome["strategy_id"]].append(compact)
    human = _human_evidence(config)
    sol = _sol_evidence(config)
    human_safe_by_track: dict[str, set[str]] = defaultdict(set)
    sol_safe_by_track: dict[str, set[str]] = defaultdict(set)
    for (stable_id, video_id), label in human.items():
        if label in SAFE_LABELS:
            human_safe_by_track[stable_id].add(video_id)
    for (stable_id, video_id), label in sol.items():
        if label in SAFE_LABELS:
            sol_safe_by_track[stable_id].add(video_id)
    control = {row["stable_track_id"]: row for row in by_strategy["Q0_CURRENT_CONTROL"]}
    summaries = {}
    per_track = []
    for strategy_id in STRATEGY_IDS:
        rows = by_strategy[strategy_id]
        source_counts = Counter(row["selected_source_type"] or "MATCH_UNCERTAIN" for row in rows)
        selected_human = Counter()
        selected_sol = Counter()
        overlap_values = []
        new_count = 0
        human_hits = {1: 0, 3: 0, 5: 0}
        sol_hits = {1: 0, 3: 0, 5: 0}
        for row in rows:
            stable_id = row["stable_track_id"]
            ids = row["candidate_video_ids"]
            control_ids = control[stable_id]["candidate_video_ids"]
            overlap_values.append(len(set(ids) & set(control_ids)))
            new_count += len(set(ids) - set(control_ids))
            for k in (1, 3, 5):
                human_hits[k] += _metric(ids, human_safe_by_track[stable_id], k)
                sol_hits[k] += _metric(ids, sol_safe_by_track[stable_id], k)
            selected_id = row["final_decision"].get("selected_video_id")
            if selected_id:
                selected_human[human.get((stable_id, selected_id), "UNREVIEWED")] += 1
                selected_sol[sol.get((stable_id, selected_id), "UNREVIEWED")] += 1
        human_denominator = sum(bool(human_safe_by_track[row["stable_track_id"]]) for row in rows)
        sol_denominator = sum(bool(sol_safe_by_track[row["stable_track_id"]]) for row in rows)
        auto_count = sum(row["final_decision"]["status"] == "AUTO_MATCH" for row in rows)
        summaries[strategy_id] = {
            "track_count": len(rows),
            "successful_query_count": sum(row["request_error"] is None for row in rows),
            "request_failure_count": sum(row["request_error"] is not None for row in rows),
            "zero_candidate_query_count": sum(not row["candidate_video_ids"] for row in rows),
            "unique_candidate_count": len({candidate for row in rows for candidate in row["candidate_video_ids"]}),
            "candidate_overlap_with_control_total": sum(overlap_values),
            "mean_candidate_overlap_with_control": sum(overlap_values) / len(overlap_values),
            "new_candidate_occurrences_vs_control": new_count,
            "known_human_safe_recall": {
                f"recall_at_{k}": human_hits[k] / human_denominator if human_denominator else None
                for k in (1, 3, 5)
            } | {"evaluable_tracks": human_denominator},
            "diagnostic_sol_safe_recall": {
                f"recall_at_{k}": sol_hits[k] / sol_denominator if sol_denominator else None
                for k in (1, 3, 5)
            } | {"evaluable_tracks": sol_denominator},
            "known_human_safe_candidate_absent_count": human_denominator - human_hits[5],
            "candidate_set_failure_count": human_denominator - human_hits[5],
            "candidate_set_failure_rate_among_human_evaluable_tracks": (
                (human_denominator - human_hits[5]) / human_denominator
                if human_denominator else None
            ),
            "diagnostic_sol_safe_candidate_absent_count": sol_denominator - sol_hits[5],
            "canonical_strong_source_present_count": sum(
                row["canonical_strong_source_present"] for row in rows
            ),
            "resolver_auto_match_count": auto_count,
            "resolver_coverage": auto_count / len(rows),
            "resolver_match_uncertain_count": len(rows) - auto_count,
            "selected_source_composition": dict(sorted(source_counts.items())),
            "selected_human_label_counts": dict(sorted(selected_human.items())),
            "selected_sol_label_counts": dict(sorted(selected_sol.items())),
        }
    for stable_id in track_by_id:
        rows = {strategy: next(row for row in by_strategy[strategy] if row["stable_track_id"] == stable_id) for strategy in STRATEGY_IDS}
        selected = {strategy: row["final_decision"].get("selected_video_id") for strategy, row in rows.items()}
        per_track.append({
            "stable_track_id": stable_id,
            "selected_video_ids": selected,
            "material_selection_disagreement": len({value for value in selected.values() if value}) > 1,
            "strategies": {
                strategy: {
                    "query": row["query"], "candidate_video_ids": row["candidate_video_ids"],
                    "selected_video_id": row["final_decision"].get("selected_video_id"),
                    "status": row["final_decision"]["status"],
                    "selected_source_type": row["selected_source_type"],
                    "canonical_strong_source_present": row["canonical_strong_source_present"],
                    "candidates": [
                        {
                            "rank": candidate["rank"],
                            "youtube_video_id": candidate["youtube_video_id"],
                            "title": candidate.get("title"),
                            "channel": candidate.get("channel") or candidate.get("uploader"),
                            "duration_seconds": candidate.get("duration_seconds"),
                            "view_count": candidate.get("view_count"),
                            "source_type": row["candidate_source_types"].get(
                                candidate["youtube_video_id"]
                            ),
                        }
                        for candidate in row["candidates"]
                    ],
                }
                for strategy, row in rows.items()
            },
        })
    replay_artifact = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "frozen_original_pool_regression": frozen_regression,
        "resolver_layers_unchanged": True,
        "track_strategy_replay_count": len(replays),
        "replays": replays,
    }
    comparison = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "dataset_role": "ADVERSARIAL_QUERY_STRATEGY_EVALUATION",
        "evidence_semantics": {
            "human_safe_recall": "Recall of previously human-confirmed SAFE video IDs; new unlabeled videos cannot count until reviewed.",
            "sol_safe_recall": "Diagnostic only; Sol is not ground truth.",
            "candidate_set_failure_count": "Known-safe-ID absence is not proof that every new unlabeled candidate is unsafe.",
        },
        "strategies": summaries,
        "tracks": per_track,
        "taki_taki": next(row for row in per_track if row["stable_track_id"] == "s5b1c_012"),
        "selection_status": "NO_CLEAR_WINNER_PENDING_TARGETED_HUMAN_REVIEW",
        "production_query_activated": False,
    }
    return replay_artifact, comparison


def _review_rows(
    config: Stage5B1EConfig, replays: dict[str, Any], comparison: dict[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    challenge, manifest = _challenge(config)
    del challenge
    tracks = {row.track.stable_track_id: row.track for row in manifest.tracks}
    human = _human_evidence(config)
    replay_by_key = {
        (row["stable_track_id"], row["strategy_id"]): row for row in replays["replays"]
    }
    candidate_cases: dict[tuple[str, str], dict[str, Any]] = {}
    prior_failures = {"s5b1c_021", "s5b1c_029", "s5b1c_032", "s5b1c_040"}
    for track_row in comparison["tracks"]:
        stable_id = track_row["stable_track_id"]
        control_selected = track_row["selected_video_ids"]["Q0_CURRENT_CONTROL"]
        selections = {
            strategy: value for strategy, value in track_row["selected_video_ids"].items() if value
        }
        material = len(set(selections.values())) > 1
        for strategy_id, video_id in selections.items():
            label = human.get((stable_id, video_id))
            if label is not None:
                # Previously completed human evidence remains authoritative;
                # disagreement context is retained in comparison.json without
                # asking the reviewer to label the same video again.
                continue
            reasons = []
            if material:
                reasons.append("MATERIAL_STRATEGY_SELECTION_DISAGREEMENT")
            if (
                strategy_id != "Q0_CURRENT_CONTROL"
                and video_id != control_selected
                and label not in SAFE_LABELS
            ):
                reasons.append("NATURAL_QUERY_NEW_SELECTION_WITHOUT_HUMAN_SAFE_EVIDENCE")
            if (
                stable_id in prior_failures
                and strategy_id != "Q0_CURRENT_CONTROL"
                and control_selected is None
            ):
                reasons.append("PRIOR_CANDIDATE_SET_FAILURE_NOW_AUTO_MATCHED")
            if not reasons:
                continue
            key = (stable_id, video_id)
            case = candidate_cases.setdefault(key, {"strategy_ids": set(), "reasons": set()})
            case["strategy_ids"].add(strategy_id)
            case["reasons"].update(reasons)
    rows = []
    queue_cases = []
    for (stable_id, video_id), case in sorted(candidate_cases.items()):
        strategy_ids = sorted(case["strategy_ids"])
        source = replay_by_key[(stable_id, strategy_ids[0])]
        candidate = next(row for row in source["candidates"] if row["youtube_video_id"] == video_id)
        target = tracks[stable_id]
        row = {
            "review_schema_version": AUDIT_SCHEMA_VERSION,
            "stable_track_id": stable_id,
            "expected_title": target.title,
            "expected_artists": " | ".join(target.artists),
            "expected_album": target.album or "",
            "expected_duration_seconds": str(target.duration_ms / 1000.0),
            "expected_release_year": str(target.release_year or ""),
            "candidate_video_id": video_id,
            "candidate_url": candidate.get("canonical_url") or candidate.get("url") or "",
            "candidate_title": candidate.get("title") or "",
            "candidate_uploader": candidate.get("uploader") or "",
            "candidate_channel": candidate.get("channel") or "",
            "candidate_duration_seconds": str(candidate.get("duration_seconds") or ""),
            "candidate_view_count": str(candidate.get("view_count") or ""),
            "candidate_description": candidate.get("description") or "",
            "strategy_ids": " | ".join(strategy_ids),
            "audit_reasons": " | ".join(sorted(case["reasons"])),
            "candidate_review_label": "",
            "candidate_note": "",
            "track_note": "",
        }
        rows.append(row)
        queue_cases.append({
            "stable_track_id": stable_id, "candidate_video_id": video_id,
            "strategy_ids": strategy_ids, "audit_reasons": sorted(case["reasons"]),
        })
    return rows, queue_cases


def _write_review(path: Path, rows: list[dict[str, str]]) -> None:
    reviewer = {"candidate_review_label", "candidate_note", "track_note"}
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
        if len(existing) != len(rows):
            raise Stage5B1AValidationError("Stage 5B.1E review queue size changed")
        for old, new in zip(existing, rows):
            if any(old[name] != new[name] for name in REVIEW_COLUMNS if name not in reviewer):
                raise Stage5B1AValidationError("Stage 5B.1E review metadata changed")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def select_query_strategy(
    comparison: dict[str, Any], *, human_audit_complete: bool
) -> str:
    """Apply the predeclared evidence priority only after targeted review."""

    if not human_audit_complete:
        return "NO_CLEAR_WINNER_PENDING_TARGETED_HUMAN_REVIEW"
    eligible = [
        strategy_id for strategy_id in STRATEGY_IDS
        if comparison["strategies"][strategy_id]["selected_human_label_counts"].get(
            "WRONG", 0
        ) == 0
    ]
    if not eligible:
        return "NO_CLEAR_WINNER"
    # Human-safe Recall@5 and resolver coverage are the governing metrics.
    # Human uncertainty and known candidate-set failures break later ties;
    # the last component prefers the simpler natural forms only when all
    # stronger evidence is identical.
    simplicity = {
        "Q1_NATURAL_SPOTIFY_TITLE": 4,
        "Q2_NATURAL_TITLE_PLUS_ARTIST": 3,
        "Q0_CURRENT_CONTROL": 2,
        "Q3_CORE_TITLE_ARTIST_VERSION": 1,
    }

    def key(strategy_id: str) -> tuple[float, float, int, int, int]:
        row = comparison["strategies"][strategy_id]
        return (
            row["known_human_safe_recall"]["recall_at_5"] or 0.0,
            row["resolver_coverage"],
            -row["selected_human_label_counts"].get("UNCERTAIN", 0),
            -row["candidate_set_failure_count"],
            simplicity[strategy_id],
        )

    winner = max(eligible, key=key)
    return DECISION_BY_STRATEGY[winner]


def write_evaluation(config: Stage5B1EConfig, discovery: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    replays, comparison = evaluate(config, discovery)
    rows, cases = _review_rows(config, replays, comparison)
    _write_review(config.artifacts["human_review"], rows)
    completed = 0
    labels = Counter()
    with config.artifacts["human_review"].open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row["candidate_review_label"].strip().upper()
            if label not in REVIEW_LABELS:
                raise Stage5B1AValidationError(f"invalid Stage 5B.1E review label: {label}")
            if label:
                completed += 1
                labels[label] += 1
    audit_complete = completed == len(cases)
    comparison["selection_status"] = select_query_strategy(
        comparison, human_audit_complete=audit_complete
    )
    atomic_json(config.artifacts["replays"], replays)
    comparison["resolver_replays_sha256"] = file_sha256(config.artifacts["replays"])
    atomic_json(config.artifacts["comparison"], comparison)
    queue = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "status": "COMPLETE" if audit_complete else "AWAITING_HUMAN_REVIEW",
        "comparison_sha256": file_sha256(config.artifacts["comparison"]),
        "required_judgments": len(cases), "completed_judgments": completed,
        "remaining_judgments": len(cases) - completed,
        "label_counts": dict(sorted(labels.items())), "cases": cases,
    }
    atomic_json(config.artifacts["audit_queue"], queue)
    return replays, comparison, queue


def write_report(config: Stage5B1EConfig, comparison: dict[str, Any], queue: dict[str, Any]) -> None:
    discovery = _json(config.artifacts["discovery"])
    discovery_summary = discovery["summary"]
    lines = [
        "# Stage 5B.1E Natural YouTube Discovery Query Evaluation", "",
        "## Status", "",
        ("`STAGE5B1E_DISCOVERY_COMPLETE_AWAITING_HUMAN_REVIEW`" if queue["remaining_judgments"] else "`STAGE5B1E_QUERY_EVALUATION_COMPLETE`"),
        "", "No production query was activated. All resolver policies remained unchanged.", "",
        "## Frozen resolver regression", "",
        "The original candidate pools replay exactly at 42/50 AUTO_MATCH and 8/50 MATCH_UNCERTAIN.", "",
        "## Discovery execution", "",
        f"- yt-dlp version(s): `{', '.join(discovery_summary['yt_dlp_versions'])}`",
        f"- successful queries: {discovery_summary['successful_queries']}/200",
        f"- request failures: {discovery_summary['failed_queries']}",
        f"- zero-candidate query outcomes: {discovery_summary['zero_candidate_queries']}",
        f"- provider warnings: {discovery_summary['warning_count']}",
        f"- unique candidate video IDs: {discovery_summary['unique_candidate_video_ids']}",
        "- media downloads: 0", "",
        "## Strategy comparison", "",
        "| Strategy | Human-safe R@1 | R@3 | R@5 | Resolver AUTO_MATCH | Coverage | Candidate-set failures* | Canonical/strong source |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for strategy_id in STRATEGY_IDS:
        row = comparison["strategies"][strategy_id]
        recall = row["known_human_safe_recall"]
        values = [recall[f"recall_at_{k}"] for k in (1, 3, 5)]
        rendered = ["n/a" if value is None else f"{value:.1%}" for value in values]
        lines.append(
            f"| {strategy_id} | {rendered[0]} | {rendered[1]} | {rendered[2]} | "
            f"{row['resolver_auto_match_count']}/50 | {row['resolver_coverage']:.1%} | "
            f"{row['candidate_set_failure_count']} | "
            f"{row['canonical_strong_source_present_count']}/50 |"
        )
    lines += [
        "", "*Candidate-set failure here means no previously human-confirmed SAFE video ID appeared in the top five for a human-evaluable track. New unlabeled candidates can reduce this count only after review.",
    ]
    taki = comparison["taki_taki"]
    lines += ["", "## Taki Taki diagnostic", ""]
    for strategy_id in STRATEGY_IDS:
        row = taki["strategies"][strategy_id]
        lines += [
            f"### {strategy_id}", "", f"Query: `{row['query']}`", "",
            *[
                f"{candidate['rank']}. `{candidate['youtube_video_id']}` — {candidate['title']} "
                f"(`{candidate['source_type']}`)"
                for candidate in row["candidates"]
            ], "",
            f"Resolver: `{row['status']}`; selected `{row['selected_video_id']}`; source `{row['selected_source_type']}`.", "",
        ]
    lines += [
        "## Evidence limitations", "",
        "Human-safe recall only recognizes previously human-confirmed video IDs. A new candidate may be correct but remains unvalidated until reviewed.", "",
        "Frozen Sol labels are reported diagnostically and are not ground truth. Candidate availability alone is not treated as useful discovery.", "",
        "## Human review", "",
        f"Targeted judgments required: {queue['required_judgments']}", "",
        f"Completed: {queue['completed_judgments']}; remaining: {queue['remaining_judgments']}", "",
        "Review artifact: `human_review.csv`.", "",
        "## Decision", "",
        f"`{comparison['selection_status']}`", "",
        "A final KEEP/ADOPT decision is deferred until materially changed selections have human evidence.", "",
        "## Scope guards", "",
        "- audio/video downloads: 0", "- Stage 5A calls: 0", "- CLAP/MuQ calls: 0",
        "- Sol reruns: 0", "- resolver changes: 0", "- production activation: false", "",
    ]
    config.artifacts["report"].write_text("\n".join(lines), encoding="utf-8")


def write_manifest(config: Stage5B1EConfig) -> dict[str, Any]:
    names = ("strategies", "discovery", "comparison", "replays", "audit_queue", "human_review", "report")
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "config_sha256": config.sha256,
        "frozen_inputs": verify_frozen_inputs(config),
        "artifacts": {
            name: {"path": str(config.artifacts[name].relative_to(config.project_root)), "sha256": file_sha256(config.artifacts[name]), "size_bytes": config.artifacts[name].stat().st_size}
            for name in names if config.artifacts[name].exists()
        },
        "scope": {
            "production_query_activated": False, "resolver_changed": False,
            "audio_downloads": 0, "video_downloads": 0, "stage5a_calls": 0,
            "clap_calls": 0, "muq_calls": 0, "sol_runs": 0,
        },
    }
    atomic_json(config.artifacts["manifest"], manifest)
    return manifest


def _default_config() -> Path:
    return Path(__file__).parents[2] / "configs/stage5b1e_natural_query_evaluation.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "discover", "evaluate", "manifest"))
    parser.add_argument("--config", type=Path, default=_default_config())
    args = parser.parse_args(argv)
    config = load_stage5b1e_config(args.config)
    if args.command == "prepare":
        atomic_json(config.artifacts["strategies"], expected_strategy_artifact(config))
        print(json.dumps({"track_count": 50, "strategy_count": 4}))
        return 0
    strategies = _json(config.artifacts["strategies"])
    if args.command == "discover":
        adapter = YtDlpDiscoveryAdapter(
            config.provider,
            QueryConfig(variant_id="unused-explicit-query", template="{normalized_title}", normalize_featured_artist_noise=False),
            YtDlpPythonBackend(config.provider),
        )
        result = run_discovery(config, strategies, adapter)
        print(json.dumps(result["summary"], sort_keys=True))
        return 0
    discovery = _json(config.artifacts["discovery"])
    if args.command == "evaluate":
        _, comparison, queue = write_evaluation(config, discovery)
        write_report(config, comparison, queue)
        print(json.dumps({"strategies": comparison["strategies"], "audit": queue}, sort_keys=True))
        return 0
    manifest = write_manifest(config)
    print(json.dumps({"artifact_count": len(manifest["artifacts"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
