"""Stage 5B.3 native-rank selector with two deliberately narrow vetoes.

This experiment does not invoke or emulate the historical proof-heavy resolver.
It trusts native YouTube rank unless the raw title explicitly presents an
unrequested live/performance source or the duration differs by more than 20s.
"""
from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b2_youtube_prior import (
    BENCHMARK_ID as PRIOR_BENCHMARK_ID,
    SAMPLE_SIZE,
    load_youtube_prior_config,
    load_youtube_prior_manifest,
)
from .stage5b2_youtube_prior_review import LABELS, SAFE_LABELS, validate_complete_human_review


EXPERIMENT_ID = "STAGE5B3_MINIMAL_YOUTUBE_SELECTOR_V1"
DECISION_SCHEMA_VERSION = "stage5b3-minimal-selector-decisions-v1"
CHANGED_SCHEMA_VERSION = "stage5b3-minimal-selector-changed-selections-v1"
REVIEW_SCHEMA_VERSION = "stage5b3-minimal-selector-human-review-v1"
ARTIFACT_SCHEMA_VERSION = "stage5b3-minimal-selector-artifact-manifest-v1"
STATUS_PENDING = "STAGE5B3_MINIMAL_SELECTOR_AWAITING_HUMAN_REVIEW"
STATUS_COMPLETE = "STAGE5B3_MINIMAL_SELECTOR_EVALUATED"
AUTO_SELECT = "AUTO_SELECT"
MATCH_UNCERTAIN = "MATCH_UNCERTAIN"
DURATION_ANOMALY_SECONDS = 20.0
EXPECTED_PRIOR_HASHES = {
    "benchmark_manifest.json": "3a967360ece50d3792f48c3bf857f5270965d09610d2601b517bd2a0e1c23396",
    "youtube_top3_discovery.json": "3a90301a008824a3001b464aae0e348bc56649f508ccca6f11d88c171f31b9b8",
    "human_review.csv": "e0a39ed88fe840982b4e3ece77102e667baaed83cebff49f7fee0f3f0ecdcef7",
}
_LIVE_PRESENTATION = re.compile(r"\b(?:live|concert|performance|stage)\b", re.IGNORECASE)
REVIEW_COLUMNS = (
    "review_schema_version", "experiment_id", "benchmark_id", "spotify_track_id",
    "expected_title", "expected_artists", "expected_album", "expected_duration_seconds",
    "selected_rank", "candidate_video_id", "candidate_url", "candidate_title",
    "candidate_uploader", "candidate_channel", "candidate_duration_seconds",
    "candidate_view_count", "candidate_description", "candidate_review_label",
    "candidate_note", "track_note",
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def target_requests_live(target: dict[str, Any]) -> bool:
    """Return whether Spotify explicitly presents the target as live."""

    return bool(_LIVE_PRESENTATION.search(str(target.get("title") or "")))


def duration_delta_seconds(
    target: dict[str, Any], candidate: dict[str, Any]
) -> float | None:
    duration_ms = target.get("duration_ms")
    candidate_seconds = candidate.get("duration_seconds")
    if duration_ms is None or candidate_seconds is None:
        return None
    return abs(float(candidate_seconds) - float(duration_ms) / 1000.0)


def veto_reasons(target: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    """Apply only the two frozen V1 veto families."""

    reasons = []
    if not target_requests_live(target) and _LIVE_PRESENTATION.search(
        str(candidate.get("title") or "")
    ):
        reasons.append("UNREQUESTED_LIVE_OR_PERFORMANCE")
    delta = duration_delta_seconds(target, candidate)
    if delta is not None and delta > DURATION_ANOMALY_SECONDS:
        reasons.append("DURATION_ANOMALY_GT_20_SECONDS")
    return reasons


def select_native_rank(
    target: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    ranks = [candidate.get("rank") for candidate in candidates]
    if ranks != list(range(1, len(candidates) + 1)) or len(candidates) > 3:
        raise Stage5B1AValidationError("Stage 5B.3 requires preserved native ranks 1–3")
    evaluations = []
    selected = None
    for candidate in candidates:
        reasons = veto_reasons(target, candidate)
        evaluation = {
            "native_rank": candidate["rank"],
            "video_id": candidate["youtube_video_id"],
            "title": candidate.get("title"),
            "duration_seconds": candidate.get("duration_seconds"),
            "absolute_duration_delta_seconds": duration_delta_seconds(target, candidate),
            "vetoed": bool(reasons),
            "veto_reasons": reasons,
        }
        evaluations.append(evaluation)
        if not reasons:
            selected = candidate
            break
    if selected is None:
        return {
            "decision": MATCH_UNCERTAIN,
            "selected_rank": None,
            "selected_video_id": None,
            "selection_reason": "ALL_TOP3_CANDIDATES_VETOED",
            "candidate_evaluations": evaluations,
        }
    return {
        "decision": AUTO_SELECT,
        "selected_rank": selected["rank"],
        "selected_video_id": selected["youtube_video_id"],
        "selection_reason": "FIRST_NATIVE_RANK_WITHOUT_V1_VETO",
        "selected_candidate": selected,
        "candidate_evaluations": evaluations,
    }


def _verify_prior(prior_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    for name, expected in EXPECTED_PRIOR_HASHES.items():
        path = prior_dir / name
        if file_sha256(path) != expected:
            raise Stage5B1AValidationError(f"frozen Stage 5B.2 artifact changed: {name}")
    config = load_youtube_prior_config(prior_dir / "benchmark_config.json")
    manifest = load_youtube_prior_manifest(config)
    discovery = _json(prior_dir / "youtube_top3_discovery.json")
    if (
        discovery.get("summary", {}).get("tracks_completed") != SAMPLE_SIZE
        or discovery.get("summary", {}).get("candidate_count") != SAMPLE_SIZE * 3
        or discovery.get("summary", {}).get("search_failures") != 0
    ):
        raise Stage5B1AValidationError("frozen Stage 5B.2 discovery is incomplete")
    return manifest, discovery


def _prior_human_labels(prior_dir: Path) -> dict[tuple[str, int], dict[str, str]]:
    grouped = validate_complete_human_review(prior_dir / "human_review.csv")
    return {
        (benchmark_id, int(row["youtube_rank"])): row
        for benchmark_id, rows in grouped.items()
        for row in rows
    }


def _write_review_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        with path.open(encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))
        expected = [(row["benchmark_id"], str(row["selected_rank"]), row["candidate_video_id"]) for row in rows]
        actual = [(row["benchmark_id"], row["selected_rank"], row["candidate_video_id"]) for row in existing]
        if actual != expected:
            raise Stage5B1AValidationError("existing Stage 5B.3 human-review identities changed")
        return
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _queue_review_rows(
    decisions: list[dict[str, Any]],
    prior_labels: dict[tuple[str, int], dict[str, str]],
) -> list[dict[str, Any]]:
    rows = []
    for row in decisions:
        if row["decision"] != AUTO_SELECT:
            continue
        prior = prior_labels.get((row["benchmark_id"], row["selected_rank"]))
        if prior and prior["candidate_review_label"]:
            continue
        target = row["spotify_target"]
        candidate = row["selected_candidate"]
        rows.append({
            "review_schema_version": REVIEW_SCHEMA_VERSION,
            "experiment_id": EXPERIMENT_ID,
            "benchmark_id": row["benchmark_id"],
            "spotify_track_id": target["spotify_track_id"],
            "expected_title": target["title"],
            "expected_artists": " | ".join(target["artists"]),
            "expected_album": target.get("album") or "",
            "expected_duration_seconds": target["duration_ms"] / 1000,
            "selected_rank": row["selected_rank"],
            "candidate_video_id": candidate["youtube_video_id"],
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
    return rows


def _load_new_human_labels(path: Path) -> dict[tuple[str, int], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Stage 5B.3 review columns")
        rows = list(reader)
    output = {}
    for row in rows:
        label = row["candidate_review_label"].strip().upper()
        if label and label not in LABELS:
            raise Stage5B1AValidationError("invalid Stage 5B.3 human label")
        key = (row["benchmark_id"], int(row["selected_rank"]))
        if key in output:
            raise Stage5B1AValidationError("duplicate Stage 5B.3 review identity")
        output[key] = row | {
            "candidate_review_label": label
        }
    return output


def _report(
    output_dir: Path,
    summary: dict[str, Any],
    changed: list[dict[str, Any]],
) -> None:
    lines = [
        "# Stage 5B.3 — YouTube-Prior Minimal Selector",
        "",
        "## Contract",
        "",
        "Native YouTube rank is trusted unless the raw candidate title explicitly presents an unrequested live/performance source or its duration delta is greater than 20 seconds. Missing positive identity, performer, provenance, source, album, year, or version evidence is not a veto.",
        "",
        "- frozen input: Stage 5B.2 100-track native Top-3 dataset",
        "- searches run: **0**",
        "- existing resolver invocations: **0**",
        "- additional veto families: **0**",
        "",
        "## Results",
        "",
        f"- AUTO_SELECT: **{summary['auto_select_count']}/100 ({summary['coverage'] * 100:.1f}%)**",
        f"- MATCH_UNCERTAIN: **{summary['match_uncertain_count']}/100**",
        f"- selected ranks: `{summary['selected_rank_distribution']}`",
        f"- existing human SAFE: **{summary['human_safe_count']}**",
        f"- existing human WRONG: **{summary['human_wrong_count']}**",
        f"- existing human UNCERTAIN: **{summary['human_uncertain_count']}**",
        f"- selections awaiting review: **{summary['human_unreviewed_count']}**",
        f"- human SAFE precision: **{summary['safe_precision'] * 100:.1f}%**" if summary["safe_precision"] is not None else "- human SAFE precision: **pending review**",
        "",
        "## Critical checks",
        "",
        f"1. `We got so much` live veto corrected rank 1: **{summary['critical_checks']['we_got_so_much_fixed']}**",
        f"2. `A Little Bit Colder` duration veto corrected rank 1: **{summary['critical_checks']['a_little_bit_colder_fixed']}**",
        f"3. `Goddess of the Hollow` duration veto corrected rank 1: **{summary['critical_checks']['goddess_of_the_hollow_fixed']}**",
        f"4. Original SAFE rank-1 candidates vetoed: **{summary['safe_rank1_vetoed_count']}**",
        f"5. Known WRONG selections: **{summary['human_wrong_count']}**",
        f"6. Rank 2 selections: **{summary['selected_rank_distribution']['rank_2']}**",
        f"7. Rank 3 selections: **{summary['selected_rank_distribution']['rank_3']}**",
        "",
        "## Changed selections",
        "",
        *(
            [
                f"- `{row['benchmark_id']}`: rank 1 vetoed by `{row['rank1_veto_reasons']}`; selected rank {row['selected_rank']} `{row['selected_video_id']}` ({row['human_label'] or 'UNREVIEWED'})."
                for row in changed
            ] or ["- none"]
        ),
        "",
        "## Decision",
        "",
        summary["architecture_decision"],
        "",
        "This is calibration on frozen Stage 5B.2 evidence. It is not production-activated and Representative Library V3 was not run.",
    ]
    (output_dir / "minimal_selector_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_minimal_selector(prior_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    prior_dir = Path(prior_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest, discovery = _verify_prior(prior_dir)
    targets = {row["benchmark_id"]: row for row in manifest["tracks"]}
    prior_labels = _prior_human_labels(prior_dir)
    new_labels = _load_new_human_labels(output_dir / "human_review.csv")
    decisions = []
    for track_row in discovery["tracks"]:
        benchmark_id = track_row["benchmark_id"]
        target = targets[benchmark_id]
        decision = select_native_rank(target, track_row["outcome"]["candidates"])
        selected_rank = decision["selected_rank"]
        label_row = prior_labels.get((benchmark_id, selected_rank)) if selected_rank else None
        if selected_rank and (not label_row or not label_row["candidate_review_label"]):
            label_row = new_labels.get((benchmark_id, selected_rank))
        human_label = label_row["candidate_review_label"] if label_row else ""
        decisions.append({
            "benchmark_id": benchmark_id,
            "spotify_target": target,
            **decision,
            "human_label": human_label,
            "human_label_source": "STAGE5B2_FROZEN_REVIEW" if prior_labels.get((benchmark_id, selected_rank or 0), {}).get("candidate_review_label") else "STAGE5B3_TARGETED_REVIEW" if human_label else None,
        })
    if len(decisions) != SAMPLE_SIZE:
        raise Stage5B1AValidationError("Stage 5B.3 decision denominator changed")
    review_rows = _queue_review_rows(decisions, prior_labels)
    _write_review_csv(output_dir / "human_review.csv", review_rows)
    # Reload after creating the queue so a later rerun consumes reviewer-owned labels.
    new_labels = _load_new_human_labels(output_dir / "human_review.csv")
    for row in decisions:
        if row["decision"] == AUTO_SELECT and not row["human_label"]:
            label = new_labels.get((row["benchmark_id"], row["selected_rank"]))
            if label:
                row["human_label"] = label["candidate_review_label"]
                row["human_label_source"] = "STAGE5B3_TARGETED_REVIEW" if row["human_label"] else None
    auto = [row for row in decisions if row["decision"] == AUTO_SELECT]
    labels = Counter(row["human_label"] for row in auto)
    rank_counts = Counter(row["selected_rank"] for row in auto)
    changed = []
    for row in auto:
        if row["selected_rank"] == 1:
            continue
        first = row["candidate_evaluations"][0]
        changed.append({
            "benchmark_id": row["benchmark_id"],
            "target_title": row["spotify_target"]["title"],
            "rank1_video_id": first["video_id"],
            "rank1_veto_reasons": first["veto_reasons"],
            "selected_rank": row["selected_rank"],
            "selected_video_id": row["selected_video_id"],
            "human_label": row["human_label"],
        })
    safe_rank1_vetoed = []
    for row in decisions:
        first = row["candidate_evaluations"][0]
        rank1_label = prior_labels[(row["benchmark_id"], 1)]["candidate_review_label"]
        if first["vetoed"] and rank1_label in SAFE_LABELS:
            safe_rank1_vetoed.append({
                "benchmark_id": row["benchmark_id"],
                "target_title": row["spotify_target"]["title"],
                "rank1_video_id": first["video_id"],
                "rank1_veto_reasons": first["veto_reasons"],
                "rank1_human_label": rank1_label,
                "selector_decision": row["decision"],
                "selected_rank": row["selected_rank"],
                "selected_video_id": row["selected_video_id"],
                "selected_human_label": row["human_label"],
            })
    reviewed_count = sum(bool(row["human_label"]) for row in auto)
    safe_count = sum(row["human_label"] in SAFE_LABELS for row in auto)
    pending = len(auto) - reviewed_count
    precision = safe_count / reviewed_count if reviewed_count else None
    by_title = {row["spotify_target"]["title"]: row for row in decisions}
    checks = {
        "we_got_so_much_fixed": by_title["We got so much"]["selected_rank"] == 2,
        "a_little_bit_colder_fixed": by_title["A Little Bit Colder"]["selected_rank"] == 2,
        "goddess_of_the_hollow_fixed": by_title["Goddess of the Hollow"]["selected_rank"] == 2,
    }
    coverage = len(auto) / SAMPLE_SIZE
    gate_passed = (
        not pending and coverage >= 0.90 and precision is not None and precision >= 0.95
    )
    if pending:
        architecture = "**AWAITING TARGETED HUMAN REVIEW.** No architecture decision is frozen yet."
    elif gate_passed:
        architecture = "**PASS.** Test this unchanged minimal selector on a fresh Representative Library V3 benchmark; do not production-activate from calibration."
    else:
        architecture = "**FAIL.** Preserve the minimal design and identify only the smallest additional veto family justified by observed human errors."
    summary = {
        "auto_select_count": len(auto),
        "match_uncertain_count": SAMPLE_SIZE - len(auto),
        "coverage": coverage,
        "selected_rank_distribution": {
            "rank_1": rank_counts[1], "rank_2": rank_counts[2],
            "rank_3": rank_counts[3], "none": SAMPLE_SIZE - len(auto),
        },
        "human_safe_count": safe_count,
        "human_wrong_count": labels["WRONG"],
        "human_uncertain_count": labels["UNCERTAIN"],
        "human_unreviewed_count": pending,
        "safe_precision": precision if not pending else None,
        "safe_rank1_vetoed_count": len(safe_rank1_vetoed),
        "safe_rank1_vetoed": safe_rank1_vetoed,
        "critical_checks": checks,
        "success_gate_passed": gate_passed,
        "architecture_decision": architecture,
    }
    decision_doc = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "source_benchmark_id": PRIOR_BENCHMARK_ID,
        "source_artifact_hashes": EXPECTED_PRIOR_HASHES,
        "policy": {
            "native_rank_is_primary": True,
            "vetoes": ["UNREQUESTED_LIVE_OR_PERFORMANCE", "DURATION_ANOMALY_GT_20_SECONDS"],
            "duration_boundary_seconds": DURATION_ANOMALY_SECONDS,
            "positive_proof_requirements": [],
            "existing_resolver_invocations": 0,
        },
        "status": STATUS_PENDING if pending else STATUS_COMPLETE,
        "summary": summary,
        "tracks": decisions,
    }
    changed_doc = {
        "schema_version": CHANGED_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "changed_selection_count": len(changed),
        "changed_selections": changed,
    }
    atomic_json(output_dir / "minimal_selector_decisions.json", decision_doc)
    atomic_json(output_dir / "changed_selections.json", changed_doc)
    _report(output_dir, summary, changed)
    artifacts = (
        "minimal_selector_decisions.json", "changed_selections.json",
        "human_review.csv", "minimal_selector_report.md",
    )
    atomic_json(output_dir / "artifact_manifest.json", {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "status": decision_doc["status"],
        "source_artifact_hashes": EXPECTED_PRIOR_HASHES,
        "artifacts": {
            name: {"sha256": file_sha256(output_dir / name), "size_bytes": (output_dir / name).stat().st_size}
            for name in artifacts
        },
        "scope_guards": {
            "youtube_searches": 0, "sol_runs": 0, "existing_resolver_invocations": 0,
            "audio_downloads": 0, "video_downloads": 0,
            "representative_library_v3_runs": 0, "production_activation": False,
        },
    })
    return decision_doc
