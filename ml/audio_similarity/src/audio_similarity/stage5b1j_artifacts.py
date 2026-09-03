"""Frozen artifacts and human-validation gate for Stage 5B.1J Part A."""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from .stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpPythonBackend
from .stage5b1a_models import Stage5B1AValidationError, SpotifyTrack, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import load_challenge_config, load_challenge_manifest
from .stage5b1b_challenge_audit import (
    QUEUE_SCHEMA_VERSION,
    REVIEW_COLUMNS,
    REVIEW_SCHEMA_VERSION,
    load_review,
)
from .stage5b1j_representation_rediscovery import (
    EXACT_RECORDING,
    STATUS_AWAITING_REVIEW,
    STATUS_NO_SELECTIONS,
    STATUS_PART_A_FAILED,
    STATUS_PART_A_PASSED,
    Stage5B1JConfig,
    build_fallback_queries,
    evaluate_fallback_discovery,
    load_stage5b1j_config,
    q0_query_config,
    run_fallback_discovery,
    verify_frozen_inputs,
)


MANIFEST_SCHEMA_VERSION = "stage5b1j-representation-fallback-artifact-manifest-v1"
QUEUE_STATUS = "STAGE5B1J_FALLBACK_AWAITING_HUMAN_REVIEW"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _relative(config: Stage5B1JConfig, path: Path) -> str:
    return str(path.relative_to(config.project_root))


def freeze_queries(config: Stage5B1JConfig) -> dict[str, Any]:
    queries = build_fallback_queries(config)
    path = config.artifacts["queries"]
    if path.exists() and _json(path) != queries:
        raise Stage5B1AValidationError("refusing to replace changed fallback queries")
    atomic_json(path, queries)
    return queries


def discover(config: Stage5B1JConfig) -> dict[str, Any]:
    queries = freeze_queries(config)
    if config.artifacts["discovery"].exists():
        raise Stage5B1AValidationError(
            "fallback discovery is already frozen; refusing to rerun it"
        )
    adapter = YtDlpDiscoveryAdapter(
        config.provider,
        q0_query_config(),
        YtDlpPythonBackend(config.provider),
    )
    result = run_fallback_discovery(config, queries, adapter)
    atomic_json(config.artifacts["discovery"], result)
    return result


def build_review_queue(
    config: Stage5B1JConfig,
    decisions: dict[str, Any],
) -> dict[str, Any]:
    challenge = load_challenge_config(config.challenge_config)
    manifest = load_challenge_manifest(
        challenge.manifest_path, expected_sha256=challenge.manifest_sha256
    )
    by_track = {row["stable_track_id"]: row for row in decisions["tracks"]}
    cases = []
    for selected in decisions["new_selections"]:
        stable_id = selected["stable_track_id"]
        decision = by_track[stable_id]["final_decision"]
        cases.append({
            "stable_track_id": stable_id,
            "candidate_video_ids": [selected["selected_video_id"]],
            "selection_reasons": ["NEW_STAGE5B1J_FALLBACK_DISCOVERY_SELECTION"],
            "fallback": {
                "match_mode": decision["match_mode"],
                "fallback_family": by_track[stable_id]["fallback_family"],
                "reason": decision["selection_reason"],
                "not_exact_recording": decision["match_mode"] != EXACT_RECORDING,
            },
        })
    return {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "status": QUEUE_STATUS if cases else "NO_REVIEW_REQUIRED",
        "manifest_sha256": manifest.sha256,
        "policy_decisions_sha256": file_sha256(config.artifacts["decisions"]),
        "sol_evaluations_sha256": None,
        "random_seed_sha256": None,
        "random_agreement_fraction": 0.0,
        "track_count": len(cases),
        "candidate_count": len(cases),
        "cases": cases,
    }


def _selected_candidate_index(discovery: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (row["stable_track_id"], candidate["youtube_video_id"]): candidate
        for row in discovery["tracks"]
        for candidate in row["outcome"].get("candidates", [])
    }


def write_review_csv(
    config: Stage5B1JConfig,
    queue: dict[str, Any],
    discovery: dict[str, Any],
) -> None:
    if not queue["cases"]:
        return
    challenge = load_challenge_config(config.challenge_config)
    manifest = load_challenge_manifest(
        challenge.manifest_path, expected_sha256=challenge.manifest_sha256
    )
    tracks = {item.track.stable_track_id: item.track for item in manifest.tracks}
    candidates = _selected_candidate_index(discovery)
    rows = []
    for case in queue["cases"]:
        stable_id = case["stable_track_id"]
        track = tracks[stable_id]
        for video_id in case["candidate_video_ids"]:
            candidate = candidates[(stable_id, video_id)]
            rows.append({
                "review_schema_version": REVIEW_SCHEMA_VERSION,
                "stable_track_id": stable_id,
                "expected_title": track.title,
                "expected_artists": " | ".join(track.artists),
                "expected_album": track.album or "",
                "expected_duration_seconds": track.duration_ms / 1000.0,
                "expected_release_year": track.release_year or "",
                "candidate_video_id": video_id,
                "candidate_url": candidate.get("canonical_url") or candidate.get("url") or "",
                "candidate_title": candidate.get("title") or "",
                "candidate_uploader": candidate.get("uploader") or "",
                "candidate_channel": candidate.get("channel") or "",
                "candidate_duration_seconds": candidate.get("duration_seconds")
                if candidate.get("duration_seconds") is not None else "",
                "candidate_view_count": candidate.get("view_count")
                if candidate.get("view_count") is not None else "",
                "candidate_description": candidate.get("description") or "",
                "candidate_review_label": "",
                "candidate_note": "",
                "track_note": "",
            })
    path = config.artifacts["human_review"]
    if path.exists():
        existing = load_review(path)
        if [
            (row["stable_track_id"], row["candidate_video_id"])
            for row in existing
        ] != [
            (row["stable_track_id"], row["candidate_video_id"])
            for row in rows
        ]:
            raise Stage5B1AValidationError("existing fallback review identity changed")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def review_gate(config: Stage5B1JConfig, decisions: dict[str, Any]) -> dict[str, Any]:
    required = len(decisions["new_selections"])
    if required == 0:
        return {
            "status": STATUS_NO_SELECTIONS,
            "required": 0,
            "completed": 0,
            "label_counts": {},
            "all_new_selections_human_safe": False,
            "part_b_authorized": False,
        }
    rows = load_review(config.artifacts["human_review"])
    labels = [row["candidate_review_label"] for row in rows]
    counts = Counter(label for label in labels if label)
    complete = len(labels) == required and all(labels)
    safe = complete and not (counts["WRONG"] or counts["UNCERTAIN"])
    status = (
        STATUS_PART_A_PASSED if safe
        else STATUS_PART_A_FAILED if complete
        else STATUS_AWAITING_REVIEW
    )
    return {
        "status": status,
        "required": required,
        "completed": sum(bool(label) for label in labels),
        "label_counts": dict(sorted(counts.items())),
        "human_review_sha256": file_sha256(config.artifacts["human_review"]),
        "all_new_selections_human_safe": safe,
        "part_b_authorized": safe,
    }


def _render_report(
    config: Stage5B1JConfig,
    discovery: dict[str, Any],
    features: dict[str, Any],
    decisions: dict[str, Any],
    queue: dict[str, Any],
    gate: dict[str, Any],
) -> str:
    summary = decisions["summary"]
    lines = [
        "# Stage 5B.1J — Representation-Equivalent Rediscovery",
        "",
        f"Status: `{gate['status']}`",
        "",
        "## Frozen control",
        "",
        "The pre-1J Stage 5B.1H/1I stack reproduced exactly at **42/50 "
        "AUTO_MATCH and 8/50 MATCH_UNCERTAIN**, with every historical selection unchanged.",
        "",
        "## Rediscovery contract",
        "",
        "Fallback discovery is restricted to unresolved ordinary-live and true-remaster "
        "targets. It uses metadata-only `ytsearch5` with the frozen Q0 form "
        "`\"{primary_artist}\" \"{base_title}\" official`. The original Q0 pools are "
        "referenced but never replaced. Each new pool is first judged against the exact "
        "Spotify target; only an exact failure permits evaluation against the base "
        "representation target.",
        "",
        "- ordinary live → `REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK`",
        "- true remaster → `REPRESENTATION_EQUIVALENT_MASTER_FALLBACK`",
        "- exact recording always wins",
        "- remix, alternate mix, rerecording, acoustic, instrumental, karaoke, "
        "slowed/sped/reverb, nightcore, bass-boosted, radio/extended edits, and "
        "arrangement-changing live targets remain exact-only",
        "",
        "## Discovery",
        "",
        f"- searches run: **{discovery['summary']['tracks_attempted']}**",
        f"- tracks with candidates: **{discovery['summary']['tracks_with_candidates']}**",
        f"- failures: **{discovery['summary']['search_failures']}**",
        f"- warnings: **{discovery['summary']['warning_count']}**",
        f"- unique candidates: **{discovery['summary']['total_deduplicated_candidates']}**",
        f"- yt-dlp versions: `{', '.join(discovery['provider']['versions'])}`",
        "",
        "## Decisions",
        "",
        f"- new exact selections from fallback pools: **{summary['new_exact_recording_count']}**",
        f"- new studio fallbacks: **{summary['new_studio_fallback_count']}**",
        f"- new master fallbacks: **{summary['new_master_fallback_count']}**",
        f"- coverage: **42/50 (84%) → {summary['combined_auto_match_count']}/50 "
        f"({summary['coverage_after']:.0%})**",
        f"- absolute gain: **{summary['absolute_percentage_point_gain']:.0f} percentage points**",
        "",
        "| Track | Family | Query | Decision | Match mode | Candidate |",
        "|---|---|---|---|---|---|",
    ]
    for row in decisions["tracks"]:
        final = row["final_decision"]
        feature = next(
            item for item in features["tracks"]
            if item["stable_track_id"] == row["stable_track_id"]
        )
        lines.append(
            f"| `{row['stable_track_id']}` | `{row['fallback_family']}` | "
            f"`{feature['fallback_query']}` | `{final['status']}` | "
            f"`{final['match_mode'] or 'NONE'}` | "
            f"`{final['selected_video_id'] or 'NONE'}` |"
        )
    lines.extend([
        "",
        "## Human validation gate",
        "",
        f"- selections requiring review: **{gate['required']}**",
        f"- completed: **{gate['completed']}**",
        f"- labels: `{json.dumps(gate['label_counts'], sort_keys=True)}`",
        f"- Part B authorized: **{str(gate['part_b_authorized']).lower()}**",
        "",
        "Part B may run only after every new selection is human `IDEAL` or `ACCEPTABLE`. "
        "Any `WRONG` or `UNCERTAIN` result stops the phase. Zero selections do not "
        "authorize automatic continuation.",
        "",
        "## Scope guards",
        "",
        "Audio downloads 0; video downloads 0; Stage 5A calls 0; CLAP calls 0; "
        "MuQ calls 0; Sol runs 0. The experiment is not production activated.",
        "",
    ])
    return "\n".join(lines)


def evaluate_and_write(config: Stage5B1JConfig) -> dict[str, Any]:
    discovery = _json(config.artifacts["discovery"])
    features, decisions = evaluate_fallback_discovery(config, discovery)
    atomic_json(config.artifacts["features"], features)
    atomic_json(config.artifacts["decisions"], decisions)
    queue = build_review_queue(config, decisions)
    atomic_json(config.artifacts["audit_queue"], queue)
    write_review_csv(config, queue, discovery)
    gate = review_gate(config, decisions)
    decisions["status"] = gate["status"]
    decisions["human_validation_gate"] = gate
    label_by_identity = {}
    if config.artifacts["human_review"].exists():
        label_by_identity = {
            (row["stable_track_id"], row["candidate_video_id"]): row[
                "candidate_review_label"
            ]
            for row in load_review(config.artifacts["human_review"])
        }
    for row in decisions["new_selections"]:
        row["human_label"] = label_by_identity.get(
            (row["stable_track_id"], row["selected_video_id"]), ""
        )
    atomic_json(config.artifacts["decisions"], decisions)
    config.artifacts["report"].parent.mkdir(parents=True, exist_ok=True)
    config.artifacts["report"].write_text(
        _render_report(config, discovery, features, decisions, queue, gate),
        encoding="utf-8",
    )
    artifacts = {
        name: {
            "path": _relative(config, config.artifacts[name]),
            "sha256": file_sha256(config.artifacts[name]),
            "size_bytes": config.artifacts[name].stat().st_size,
        }
        for name in (
            "queries", "discovery", "features", "decisions", "audit_queue",
            "report",
        )
    }
    if config.artifacts["human_review"].exists():
        artifacts["human_review"] = {
            "path": _relative(config, config.artifacts["human_review"]),
            "sha256": file_sha256(config.artifacts["human_review"]),
            "size_bytes": config.artifacts["human_review"].stat().st_size,
            "reviewer_owned_fields_mutable_until_gate": not gate[
                "part_b_authorized"
            ],
        }
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": gate["status"],
        "config": {
            "path": _relative(config, config.path),
            "sha256": config.sha256,
        },
        "frozen_inputs": verify_frozen_inputs(config),
        "artifacts": artifacts,
        "summary": decisions["summary"],
        "human_validation_gate": gate,
        "part_b_authorized": gate["part_b_authorized"],
        "scope_guards": decisions["scope_guards"],
    }
    atomic_json(config.artifacts["manifest"], manifest)
    return manifest


def load_config(path: str | Path) -> Stage5B1JConfig:
    return load_stage5b1j_config(path)
