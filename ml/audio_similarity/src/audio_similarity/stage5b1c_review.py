"""Deterministic human-audit artifacts for Stage 5B.1C Tier-2 selections."""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import (
    ChallengeConfig,
    ChallengeManifest,
    load_challenge_config,
    load_challenge_manifest,
    load_discovery,
)
from .stage5b1b_challenge_audit import (
    QUEUE_SCHEMA_VERSION,
    REVIEW_COLUMNS,
    REVIEW_LABELS,
    REVIEW_SCHEMA_VERSION,
)
from .stage5b1b_challenge_review_store import MAX_NOTE_LENGTH


TIER2_REVIEW_QUEUE_STATUS = "AWAITING_TIER2_HUMAN_AUDIT"
TIER2_REVIEW_SCHEMA_VERSION = "stage5b1c-tier2-human-audit-contract-v1"
TIER2_REVIEW_RESULTS_SCHEMA_VERSION = "stage5b1c-tier2-human-audit-results-v1"
FROZEN_CHALLENGE_TRACK_COUNT = 50
FROZEN_BALANCED_AUTO_MATCH_COUNT = 29
FROZEN_TIER2A_DECISIONS_SHA256 = (
    "6b7a987c38294717296f05086186047af6085c2a75a206d0b4595b6100c2304d"
)
FROZEN_SOURCE_NEUTRAL_DECISIONS_SHA256 = (
    "67caf7cd35574bb75271e7950f4b5a105c22425804692073f0c630caf68c5eb3"
)
EXPECTED_SELECTIONS = {
    "s5b1c_015": "ZNEuWldWPD4",
    "s5b1c_016": "WXx5-HGERcg",
    "s5b1c_017": "62TrmUvQGjo",
    "s5b1c_020": "OUkkaqSNduU",
    "s5b1c_022": "oS6wfWu0JvA",
    "s5b1c_025": "9gnyYxEWgi4",
    "s5b1c_026": "sKzoEwQaF7Y",
    "s5b1c_027": "aEi646akxko",
    "s5b1c_028": "k4HWjQNN1K8",
    "s5b1c_043": "zDOILKOOUCo",
    "s5b1c_044": "DQJpFVzeNp8",
}


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _selected_map(path: Path, expected_sha256: str) -> dict[str, str]:
    if file_sha256(path) != expected_sha256:
        raise Stage5B1AValidationError(f"frozen Tier-2 decision artifact changed: {path}")
    value = _json_object(path)
    selected = value.get("selected")
    if not isinstance(selected, list):
        raise Stage5B1AValidationError(f"Tier-2 selections are unavailable: {path}")
    output = {
        str(row["stable_track_id"]): str(row["selected_video_id"])
        for row in selected
    }
    if len(output) != len(selected):
        raise Stage5B1AValidationError(f"duplicate Tier-2 selection identity: {path}")
    return output


def build_tier2_review_queue(
    config: ChallengeConfig,
    manifest: ChallengeManifest,
    *,
    tier2a_decisions_path: Path,
    source_neutral_decisions_path: Path,
) -> dict[str, Any]:
    tier2a = _selected_map(tier2a_decisions_path, FROZEN_TIER2A_DECISIONS_SHA256)
    source_neutral = _selected_map(
        source_neutral_decisions_path, FROZEN_SOURCE_NEUTRAL_DECISIONS_SHA256
    )
    overlap = set(tier2a) & set(source_neutral)
    if overlap:
        raise Stage5B1AValidationError(
            f"candidate selected by both Tier-2 stages: {sorted(overlap)}"
        )
    selected = {**tier2a, **source_neutral}
    if selected != EXPECTED_SELECTIONS:
        raise Stage5B1AValidationError("frozen Tier-2 review selections changed")

    cases = [
        {
            "stable_track_id": stable_id,
            "candidate_video_ids": [selected[stable_id]],
            "selection_reasons": [
                "TIER2A_NORMALIZATION_RECOVERY"
                if stable_id in tier2a
                else "TIER2B_SOURCE_NEUTRAL_RECOVERY"
            ],
        }
        for stable_id in manifest.stable_track_ids
        if stable_id in selected
    ]
    if len(cases) != len(EXPECTED_SELECTIONS):
        raise Stage5B1AValidationError("Tier-2 audit tracks are absent from the manifest")
    return {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "audit_contract_version": TIER2_REVIEW_SCHEMA_VERSION,
        "status": TIER2_REVIEW_QUEUE_STATUS,
        "manifest_sha256": manifest.sha256,
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "tier2a_decisions_sha256": FROZEN_TIER2A_DECISIONS_SHA256,
        "source_neutral_decisions_sha256": FROZEN_SOURCE_NEUTRAL_DECISIONS_SHA256,
        "track_count": len(cases),
        "candidate_count": len(cases),
        "cases": cases,
    }


def tier2_review_rows(
    config: ChallengeConfig,
    manifest: ChallengeManifest,
    queue: dict[str, Any],
) -> list[dict[str, Any]]:
    discovery = load_discovery(config, manifest)
    track_by_id = {
        row["track"]["stable_track_id"]: row for row in discovery["tracks"]
    }
    rows: list[dict[str, Any]] = []
    for case in queue["cases"]:
        source = track_by_id[case["stable_track_id"]]
        track = source["track"]
        by_video = {
            candidate["youtube_video_id"]: candidate
            for candidate in source["candidates"]
        }
        for video_id in case["candidate_video_ids"]:
            try:
                candidate = by_video[video_id]
            except KeyError as exc:
                raise Stage5B1AValidationError(
                    f"Tier-2 review candidate absent from discovery: {video_id}"
                ) from exc
            rows.append(
                {
                    "review_schema_version": REVIEW_SCHEMA_VERSION,
                    "stable_track_id": track["stable_track_id"],
                    "expected_title": track["title"],
                    "expected_artists": " | ".join(track["artists"]),
                    "expected_album": track.get("album") or "",
                    "expected_duration_seconds": track["duration_ms"] / 1000.0,
                    "expected_release_year": track.get("release_year") or "",
                    "candidate_video_id": video_id,
                    "candidate_url": candidate.get("canonical_url")
                    or candidate.get("url")
                    or "",
                    "candidate_title": candidate.get("title") or "",
                    "candidate_uploader": candidate.get("uploader") or "",
                    "candidate_channel": candidate.get("channel") or "",
                    "candidate_duration_seconds": candidate.get("duration_seconds")
                    if candidate.get("duration_seconds") is not None
                    else "",
                    "candidate_view_count": candidate.get("view_count")
                    if candidate.get("view_count") is not None
                    else "",
                    "candidate_description": candidate.get("description") or "",
                    "candidate_review_label": "",
                    "candidate_note": "",
                    "track_note": "",
                }
            )
    return rows


def _atomic_review_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_tier2_review_artifacts(
    *,
    config_path: Path,
    tier2a_decisions_path: Path,
    source_neutral_decisions_path: Path,
    queue_path: Path,
    review_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = load_challenge_config(config_path)
    manifest = load_challenge_manifest(
        config.manifest_path, expected_sha256=config.manifest_sha256
    )
    queue = build_tier2_review_queue(
        config,
        manifest,
        tier2a_decisions_path=tier2a_decisions_path,
        source_neutral_decisions_path=source_neutral_decisions_path,
    )
    rows = tier2_review_rows(config, manifest, queue)
    if review_path.exists():
        with review_path.open(encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))
        if existing != [{name: str(row[name]) for name in REVIEW_COLUMNS} for row in rows]:
            raise Stage5B1AValidationError(
                "refusing to overwrite existing Tier-2 human-review data"
            )
    else:
        _atomic_review_csv(review_path, rows)
    atomic_json(queue_path, queue)
    return queue, rows


def evaluate_tier2_review(
    *,
    config_path: Path,
    tier2a_decisions_path: Path,
    source_neutral_decisions_path: Path,
    queue_path: Path,
    review_path: Path,
) -> dict[str, Any]:
    """Validate reviewer-owned fields and summarize Tier-2 selection safety."""

    config = load_challenge_config(config_path)
    manifest = load_challenge_manifest(
        config.manifest_path, expected_sha256=config.manifest_sha256
    )
    expected_queue = build_tier2_review_queue(
        config,
        manifest,
        tier2a_decisions_path=tier2a_decisions_path,
        source_neutral_decisions_path=source_neutral_decisions_path,
    )
    queue = _json_object(queue_path)
    if queue != expected_queue:
        raise Stage5B1AValidationError("Tier-2 human-audit queue changed")
    expected_rows = tier2_review_rows(config, manifest, queue)
    with review_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Tier-2 human-review CSV columns")
        rows = list(reader)
    if len(rows) != len(expected_rows):
        raise Stage5B1AValidationError("Tier-2 human-review row count changed")

    reviewer_fields = {"candidate_review_label", "candidate_note", "track_note"}
    stage_by_id = {
        case["stable_track_id"]: (
            "STAGE5B1C_A_NORMALIZATION"
            if case["selection_reasons"] == ["TIER2A_NORMALIZATION_RECOVERY"]
            else "STAGE5B1C_B_SOURCE_NEUTRAL"
        )
        for case in queue["cases"]
    }
    judgments: list[dict[str, Any]] = []
    for row, expected in zip(rows, expected_rows):
        for name in REVIEW_COLUMNS:
            if name not in reviewer_fields and row[name] != str(expected[name]):
                raise Stage5B1AValidationError(
                    f"Tier-2 review metadata changed for {row.get('stable_track_id')}:{name}"
                )
        label = row["candidate_review_label"].strip().upper()
        if label not in REVIEW_LABELS:
            raise Stage5B1AValidationError(f"invalid Tier-2 human-review label: {label}")
        if (
            len(row["candidate_note"]) > MAX_NOTE_LENGTH
            or len(row["track_note"]) > MAX_NOTE_LENGTH
        ):
            raise Stage5B1AValidationError("Tier-2 human-review note exceeds maximum length")
        judgments.append(
            {
                "stable_track_id": row["stable_track_id"],
                "candidate_video_id": row["candidate_video_id"],
                "tier2_stage": stage_by_id[row["stable_track_id"]],
                "human_label": label,
                "safety_class": (
                    "SAFE"
                    if label in {"IDEAL", "ACCEPTABLE"}
                    else "UNSAFE"
                    if label == "WRONG"
                    else "UNRESOLVED"
                ),
                "candidate_note_verbatim": row["candidate_note"],
                "track_note_verbatim": row["track_note"],
            }
        )

    label_counts = Counter(row["human_label"] or "BLANK" for row in judgments)
    reviewed = sum(row["human_label"] != "" for row in judgments)
    safe = sum(row["safety_class"] == "SAFE" for row in judgments)
    wrong = label_counts["WRONG"]
    uncertain = label_counts["UNCERTAIN"]
    complete = reviewed == len(judgments)
    if not complete:
        status = "STAGE5B1C_TIER2_HUMAN_AUDIT_INCOMPLETE"
        recommendation = "COMPLETE_REMAINING_HUMAN_REVIEW"
    elif wrong or uncertain:
        status = "STAGE5B1C_TIER2_HUMAN_AUDIT_REQUIRES_RESOLVER_REVIEW"
        recommendation = "DO_NOT_ADVANCE_UNREVIEWED_TIER2_POLICY"
    else:
        status = "STAGE5B1C_TIER2_HUMAN_AUDIT_SAFETY_HOLDS"
        recommendation = "PROCEED_TO_STAGE5B1C_C_DIAGNOSTIC"

    stage_counts: dict[str, Counter[str]] = {}
    for stage in ("STAGE5B1C_A_NORMALIZATION", "STAGE5B1C_B_SOURCE_NEUTRAL"):
        stage_counts[stage] = Counter(
            row["human_label"] or "BLANK"
            for row in judgments
            if row["tier2_stage"] == stage
        )
    combined_auto_match_count = FROZEN_BALANCED_AUTO_MATCH_COUNT + len(judgments)
    return {
        "schema_version": TIER2_REVIEW_RESULTS_SCHEMA_VERSION,
        "status": status,
        "recommendation": recommendation,
        "review_sha256": file_sha256(review_path),
        "queue_sha256": file_sha256(queue_path),
        "summary": {
            "required_judgments": len(judgments),
            "reviewed_judgments": reviewed,
            "remaining_judgments": len(judgments) - reviewed,
            "ideal_count": label_counts["IDEAL"],
            "acceptable_count": label_counts["ACCEPTABLE"],
            "wrong_count": wrong,
            "uncertain_count": uncertain,
            "safe_count": safe,
            "safe_rate_among_reviewed": safe / reviewed if reviewed else None,
            "tier1_plus_tier2_auto_match_count": combined_auto_match_count,
            "tier1_plus_tier2_coverage": (
                combined_auto_match_count / FROZEN_CHALLENGE_TRACK_COUNT
            ),
        },
        "stage_label_counts": {
            stage: dict(sorted(counts.items())) for stage, counts in stage_counts.items()
        },
        "judgments": judgments,
        "scope": {
            "human_validates_only_the_11_incremental_tier2_selections": True,
            "does_not_establish_population_precision": True,
            "production_auto_match_activated": False,
        },
    }


def write_tier2_review_results(
    *,
    output_path: Path,
    **evaluation_paths: Path,
) -> dict[str, Any]:
    results = evaluate_tier2_review(**evaluation_paths)
    atomic_json(output_path, results)
    return results
