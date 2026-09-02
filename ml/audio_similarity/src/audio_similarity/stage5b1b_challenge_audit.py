"""Sol/policy comparison and blinded targeted human audit for the fresh challenge."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import (
    AUTO_MATCH,
    ChallengeConfig,
    ChallengeManifest,
    DECISIONS_SCHEMA_VERSION,
    POLICY_IDS,
    load_discovery,
)
from .stage5b1b_challenge_sol import ChallengeSolRuntime, mapped_sol_judgments


COMPARISON_SCHEMA_VERSION = "stage5b1b-fresh-challenge-policy-sol-comparison-v1"
QUEUE_SCHEMA_VERSION = "stage5b1b-fresh-challenge-human-audit-queue-v1"
REVIEW_SCHEMA_VERSION = "stage5b1b-fresh-challenge-human-review-v1"
REVIEW_LABELS = {"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"}
REVIEW_COLUMNS = [
    "review_schema_version", "stable_track_id", "expected_title", "expected_artists",
    "expected_album", "expected_duration_seconds", "expected_release_year",
    "candidate_video_id", "candidate_url", "candidate_title", "candidate_uploader",
    "candidate_channel", "candidate_duration_seconds", "candidate_view_count",
    "candidate_description", "candidate_review_label", "candidate_note", "track_note",
]


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _hash_key(seed: str, stable_id: str) -> str:
    return hashlib.sha256(f"{seed}|{stable_id}".encode()).hexdigest()


def _feature_index(config: ChallengeConfig) -> dict[tuple[str, str], dict[str, Any]]:
    dataset = _json_object(config.artifacts["features"])
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for row in dataset["tracks"]:
        stable_id = row["track"]["stable_track_id"]
        for wrapped in row["candidates"]:
            output[(stable_id, wrapped["candidate"]["youtube_video_id"])] = wrapped["features"]
    return output


def _decision_maps(config: ChallengeConfig) -> dict[str, dict[str, dict[str, Any]]]:
    raw = _json_object(config.artifacts["policy_decisions"])
    if raw.get("schema_version") != DECISIONS_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected fresh policy decisions schema")
    return {
        policy_id: {
            row["stable_track_id"]: row["decision"]
            for row in raw["policies"][policy_id]["tracks"]
        }
        for policy_id in POLICY_IDS
    }


def build_comparison_and_queue(
    config: ChallengeConfig, manifest: ChallengeManifest, runtime: ChallengeSolRuntime
) -> tuple[dict[str, Any], dict[str, Any]]:
    discovery = load_discovery(config, manifest)
    decisions = _decision_maps(config)
    features = _feature_index(config)
    sol = mapped_sol_judgments(runtime)
    sol_by_id = {row["stable_track_id"]: row for row in sol["tracks"]}
    track_rows: list[dict[str, Any]] = []
    reasons_by_id: dict[str, set[str]] = {}
    candidate_ids_by_id: dict[str, set[str]] = {}
    confident_agreements: list[str] = []
    conservative_agreements: list[str] = []

    def require(stable_id: str, reason: str, *video_ids: str | None) -> None:
        reasons_by_id.setdefault(stable_id, set()).add(reason)
        candidate_ids_by_id.setdefault(stable_id, set()).update(
            video_id for video_id in video_ids if video_id
        )

    for stable_id in manifest.stable_track_ids:
        conservative = decisions[POLICY_IDS[0]][stable_id]
        balanced = decisions[POLICY_IDS[1]][stable_id]
        sol_row = sol_by_id[stable_id]
        sol_labels = {row["youtube_video_id"]: row["label"] for row in sol_row["candidates"]}
        balanced_id = balanced["selected_video_id"]
        conservative_id = conservative["selected_video_id"]
        sol_selected = sol_row["selected_video_id"]
        balanced_sol_label = sol_labels.get(balanced_id) if balanced_id else None

        if balanced_id and balanced_sol_label in {"WRONG", "UNCERTAIN"}:
            require(stable_id, f"BALANCED_SOL_{balanced_sol_label}", balanced_id)
        if balanced_id and sol_selected and balanced_id != sol_selected:
            require(stable_id, "BALANCED_SOL_PREFERENCE_DISAGREEMENT", balanced_id, sol_selected)
        if conservative_id and balanced_id and conservative_id != balanced_id:
            require(stable_id, "POLICY_SELECTION_DISAGREEMENT", conservative_id, balanced_id)
        if balanced_id:
            feature = features[(stable_id, balanced_id)]
            source_type = feature["source"]["source_type"]
            provenance = feature["source"]["provenance"]
            if source_type in {"LYRIC_VIDEO", "OFFICIAL_MUSIC_VIDEO", "OTHER"}:
                require(stable_id, "SOURCE_FALLBACK_AUDIT", balanced_id)
            if feature["versions"]["version_absent_count"] or feature["versions"]["version_conflict_count"]:
                require(stable_id, "SUSPICIOUS_VERSION_EVIDENCE", balanced_id)
            if (
                source_type != "OFFICIAL_AUDIO"
                and not provenance["topic_channel_signal"]
                and not provenance["provided_to_youtube_by_signal"]
                and not provenance["structured_release_metadata_signal"]
            ):
                require(stable_id, "WEAK_PROVENANCE_AUDIT", balanced_id)
        if (
            balanced_id and sol_selected == balanced_id
            and balanced_sol_label in {"IDEAL", "ACCEPTABLE"}
            and stable_id not in reasons_by_id
        ):
            confident_agreements.append(stable_id)
        if conservative_id and sol_selected == conservative_id and sol_labels.get(conservative_id) in {"IDEAL", "ACCEPTABLE"}:
            conservative_agreements.append(stable_id)

        track_rows.append({
            "stable_track_id": stable_id,
            "conservative": conservative,
            "balanced": balanced,
            "balanced_sol_label": balanced_sol_label,
            "sol_selection_status": sol_row["selection_status"],
            "sol_selected_video_id": sol_selected,
            "sol_selection_rationale": sol_row["selection_rationale"],
            "sol_candidate_labels": sol_labels,
        })

    seed = str(config.audit["random_seed"])
    random_count = math.ceil(len(confident_agreements) * float(config.audit["random_agreement_fraction"]))
    random_ids = sorted(confident_agreements, key=lambda item: _hash_key(seed, item))[:random_count]
    for stable_id in random_ids:
        require(stable_id, "RANDOM_BALANCED_SOL_AGREEMENT_AUDIT", decisions[POLICY_IDS[1]][stable_id]["selected_video_id"])
    conservative_pool = [item for item in conservative_agreements if item not in reasons_by_id]
    conservative_ids = sorted(conservative_pool, key=lambda item: _hash_key(seed + "|conservative", item))[
        : int(config.audit["minimum_conservative_random_tracks"])
    ]
    for stable_id in conservative_ids:
        require(stable_id, "RANDOM_CONSERVATIVE_SOL_AGREEMENT_AUDIT", decisions[POLICY_IDS[0]][stable_id]["selected_video_id"])

    audit_track_ids = [stable_id for stable_id in manifest.stable_track_ids if stable_id in reasons_by_id]
    cases = []
    for stable_id in audit_track_ids:
        ordered = [
            candidate["youtube_video_id"]
            for row in discovery["tracks"] if row["track"]["stable_track_id"] == stable_id
            for candidate in row["candidates"]
        ]
        selected = [video_id for video_id in ordered if video_id in candidate_ids_by_id[stable_id]]
        if not selected:
            raise Stage5B1AValidationError(f"audit case contains no candidates: {stable_id}")
        cases.append({
            "stable_track_id": stable_id,
            "candidate_video_ids": selected,
            "selection_reasons": sorted(reasons_by_id[stable_id]),
        })
    queue = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "status": "AWAITING_TARGETED_HUMAN_AUDIT",
        "manifest_sha256": manifest.sha256,
        "policy_decisions_sha256": file_sha256(config.artifacts["policy_decisions"]),
        "sol_evaluations_sha256": file_sha256(runtime.evaluations_path),
        "random_seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "random_agreement_fraction": config.audit["random_agreement_fraction"],
        "track_count": len(cases),
        "candidate_count": sum(len(row["candidate_video_ids"]) for row in cases),
        "cases": cases,
    }
    source_counts: dict[str, Counter[str]] = {policy_id: Counter() for policy_id in POLICY_IDS}
    for policy_id in POLICY_IDS:
        for stable_id, decision in decisions[policy_id].items():
            selected = decision["selected_video_id"]
            if selected:
                source_counts[policy_id][features[(stable_id, selected)]["source"]["source_type"]] += 1

    def selected_sol_label(stable_id: str, video_id: str) -> str:
        labels = {
            candidate["youtube_video_id"]: candidate["label"]
            for candidate in sol_by_id[stable_id]["candidates"]
        }
        try:
            return labels[video_id]
        except KeyError as exc:
            raise Stage5B1AValidationError(
                f"policy-selected candidate is absent from Sol evidence: {stable_id}"
            ) from exc

    comparison = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "status": "TARGETED_HUMAN_AUDIT_READY",
        "manifest_sha256": manifest.sha256,
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "features_sha256": file_sha256(config.artifacts["features"]),
        "policy_decisions_sha256": file_sha256(config.artifacts["policy_decisions"]),
        "sol_evaluations_sha256": file_sha256(runtime.evaluations_path),
        "audit_queue_sha256": None,
        "policies": {
            policy_id: {
                "auto_match_count": sum(row["status"] == AUTO_MATCH for row in decisions[policy_id].values()),
                "match_uncertain_count": sum(row["status"] != AUTO_MATCH for row in decisions[policy_id].values()),
                "source_type_counts": dict(sorted(source_counts[policy_id].items())),
                "sol_selected_label_counts": dict(sorted(Counter(
                    selected_sol_label(stable_id, decision["selected_video_id"])
                    for stable_id, decision in decisions[policy_id].items()
                    if decision["selected_video_id"]
                ).items())),
            }
            for policy_id in POLICY_IDS
        },
        "balanced_incremental_track_ids": sorted(
            stable_id for stable_id in manifest.stable_track_ids
            if decisions[POLICY_IDS[1]][stable_id]["status"] == AUTO_MATCH
            and decisions[POLICY_IDS[0]][stable_id]["status"] != AUTO_MATCH
        ),
        "targeted_audit": {
            "track_count": len(cases), "candidate_count": queue["candidate_count"],
            "mandatory_or_suspicious_track_count": len(set(audit_track_ids) - set(random_ids) - set(conservative_ids)),
            "random_balanced_agreement_track_ids": random_ids,
            "random_conservative_agreement_track_ids": conservative_ids,
        },
        "tracks": track_rows,
        "limitations": [
            "Sol is independent metadata-only evidence, not human ground truth.",
            "The challenge is an intentionally difficult engineering set, not a population sample.",
            "No final validation verdict is emitted until every targeted human row is labeled.",
        ],
        "production_auto_match_activated": False,
    }
    return comparison, queue


def write_review(config: ChallengeConfig, manifest: ChallengeManifest, queue: dict[str, Any]) -> None:
    discovery = load_discovery(config, manifest)
    track_by_id = {row["track"]["stable_track_id"]: row for row in discovery["tracks"]}
    rows = []
    for case in queue["cases"]:
        source = track_by_id[case["stable_track_id"]]
        track = source["track"]
        by_video = {candidate["youtube_video_id"]: candidate for candidate in source["candidates"]}
        for video_id in case["candidate_video_ids"]:
            candidate = by_video[video_id]
            rows.append({
                "review_schema_version": REVIEW_SCHEMA_VERSION,
                "stable_track_id": track["stable_track_id"],
                "expected_title": track["title"],
                "expected_artists": " | ".join(track["artists"]),
                "expected_album": track.get("album") or "",
                "expected_duration_seconds": track["duration_ms"] / 1000.0,
                "expected_release_year": track.get("release_year") or "",
                "candidate_video_id": video_id,
                "candidate_url": candidate.get("canonical_url") or candidate.get("url") or "",
                "candidate_title": candidate.get("title") or "",
                "candidate_uploader": candidate.get("uploader") or "",
                "candidate_channel": candidate.get("channel") or "",
                "candidate_duration_seconds": candidate.get("duration_seconds") if candidate.get("duration_seconds") is not None else "",
                "candidate_view_count": candidate.get("view_count") if candidate.get("view_count") is not None else "",
                "candidate_description": candidate.get("description") or "",
                "candidate_review_label": "", "candidate_note": "", "track_note": "",
            })
    output = config.artifacts["human_review"]
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        existing = load_review(output)
        if any(row["candidate_review_label"] or row["candidate_note"] or row["track_note"] for row in existing):
            raise Stage5B1AValidationError("refusing to overwrite completed human review data")
    temporary = output.with_suffix(output.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(output)


def load_review(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected fresh human-review columns")
        rows = list(reader)
    identities: set[tuple[str, str]] = set()
    for row in rows:
        label = row["candidate_review_label"].strip().upper()
        if label not in REVIEW_LABELS:
            raise Stage5B1AValidationError(f"invalid fresh review label: {label}")
        row["candidate_review_label"] = label
        identity = (row["stable_track_id"], row["candidate_video_id"])
        if identity in identities:
            raise Stage5B1AValidationError("duplicate fresh review identity")
        identities.add(identity)
    return rows


def evaluate_review(config: ChallengeConfig) -> dict[str, Any]:
    rows = load_review(config.artifacts["human_review"])
    if any(not row["candidate_review_label"] for row in rows):
        return {
            "status": "STAGE5B1B_FRESH_CHALLENGE_AWAITING_HUMAN_AUDIT",
            "required": len(rows),
            "completed": sum(bool(row["candidate_review_label"]) for row in rows),
        }
    labels = {
        (row["stable_track_id"], row["candidate_video_id"]): row["candidate_review_label"]
        for row in rows
    }
    decisions = _decision_maps(config)
    outcomes: dict[str, Counter[str]] = {policy_id: Counter() for policy_id in POLICY_IDS}
    unaudited: dict[str, int] = {policy_id: 0 for policy_id in POLICY_IDS}
    for policy_id in POLICY_IDS:
        for stable_id, decision in decisions[policy_id].items():
            video_id = decision["selected_video_id"]
            if not video_id:
                continue
            label = labels.get((stable_id, video_id))
            if label:
                outcomes[policy_id][label] += 1
            else:
                unaudited[policy_id] += 1
    conservative = outcomes[POLICY_IDS[0]]
    balanced = outcomes[POLICY_IDS[1]]
    if conservative["WRONG"]:
        status = "STAGE5B1B_FRESH_CHALLENGE_FAILED"
    elif balanced["WRONG"] or balanced["UNCERTAIN"]:
        status = "STAGE5B1B_CONSERVATIVE_POLICY_VALIDATED"
    else:
        status = "STAGE5B1B_BALANCED_POLICY_VALIDATED"
    return {
        "status": status,
        "human_review_sha256": file_sha256(config.artifacts["human_review"]),
        "policy_audited_selection_labels": {
            policy_id: dict(sorted(outcomes[policy_id].items())) for policy_id in POLICY_IDS
        },
        "policy_unaudited_selection_counts": unaudited,
        "completed": len(rows), "required": len(rows),
    }


def write_audit_artifacts(
    config: ChallengeConfig, manifest: ChallengeManifest, runtime: ChallengeSolRuntime
) -> dict[str, Any]:
    comparison, queue = build_comparison_and_queue(config, manifest, runtime)
    atomic_json(config.artifacts["audit_queue"], queue)
    comparison["audit_queue_sha256"] = file_sha256(config.artifacts["audit_queue"])
    atomic_json(config.artifacts["comparison"], comparison)
    write_review(config, manifest, queue)
    return evaluate_review(config)
