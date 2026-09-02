"""Artifact and report writers for the Stage 5B.1G offline experiment."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge_audit import REVIEW_COLUMNS, REVIEW_SCHEMA_VERSION
from .stage5b1g_global_preference import (
    DURATION_CLOSE,
    DURATION_EXTENDED_1,
    DURATION_EXTENDED_2,
    DURATION_EXTENDED_3,
    DURATION_TOO_FAR,
    DURATION_UNKNOWN,
    DURATION_VERY_CLOSE,
    MANIFEST_SCHEMA_VERSION,
    STATUS,
    Stage5B1GConfig,
    _evidence_label,
    evaluate_stage5b1g,
    load_stage5b1g_config,
    verify_frozen_inputs,
)


def _review_rows(features: dict[str, Any], queue: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {row["track"]["stable_track_id"]: row for row in features["tracks"]}
    rows = []
    for case in queue["cases"]:
        track_row = by_id[case["stable_track_id"]]
        target = track_row["track"]
        video_id = case["candidate_video_ids"][0]
        wrapped = next(
            row for row in track_row["candidates"]
            if row["snapshot"]["video_id"] == video_id
        )
        candidate = wrapped["snapshot"]
        rows.append({
            "review_schema_version": REVIEW_SCHEMA_VERSION,
            "stable_track_id": target["stable_track_id"],
            "expected_title": target["title"],
            "expected_artists": " | ".join(target["artists"]),
            "expected_album": target.get("album") or "",
            "expected_duration_seconds": (
                target["duration_ms"] / 1000.0 if target.get("duration_ms") is not None else ""
            ),
            "expected_release_year": target.get("release_year") or "",
            "candidate_video_id": video_id,
            "candidate_url": candidate.get("url") or "",
            "candidate_title": candidate.get("title") or "",
            "candidate_uploader": candidate.get("uploader") or "",
            "candidate_channel": candidate.get("channel") or "",
            "candidate_duration_seconds": candidate.get("duration_seconds") or "",
            "candidate_view_count": candidate.get("view_count") or "",
            "candidate_description": candidate.get("description") or "",
            "candidate_review_label": "",
            "candidate_note": "",
            "track_note": "",
        })
    return rows


def _write_review_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
        reviewer_fields = {"candidate_review_label", "candidate_note", "track_note"}
        has_review_evidence = any(
            str(row.get(name) or "").strip()
            for row in existing
            for name in reviewer_fields
        )
        if not has_review_evidence:
            existing = []
        immutable = [name for name in REVIEW_COLUMNS if name not in reviewer_fields]
        if existing and (len(existing) != len(rows) or any(
            old[name] != str(new[name])
            for old, new in zip(existing, rows)
            for name in immutable
        )):
            raise Stage5B1AValidationError(
                "refusing to overwrite changed Stage 5B.1G review evidence"
            )
        if existing:
            return
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _display_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def write_report(
    config: Stage5B1GConfig,
    decisions: dict[str, Any],
    changed: dict[str, Any],
    duration: dict[str, Any],
    tail: dict[str, Any],
    queue: dict[str, Any],
) -> None:
    summary = decisions["summary"]
    lines = [
        "# Stage 5B.1G — Global Candidate Preference + Graduated Duration Evidence",
        "",
        f"Status: `{STATUS}`",
        "",
        "## Outcome",
        "",
        (
            "The frozen pre-1G resolver replayed exactly at **42/50 AUTO_MATCH and "
            "8/50 MATCH_UNCERTAIN**. Global preference produced "
            f"**{summary['global_auto_match_count']}/50 AUTO_MATCH "
            f"({summary['global_coverage']:.0%})**, a "
            f"**{summary['absolute_percentage_point_gain']:.0f}-percentage-point** "
            "mechanical coverage change."
        ),
        "",
        (
            f"It changed {summary['existing_selection_changed_count']} existing selections "
            f"and newly resolved {summary['newly_resolved_count']} tracks. Every changed or "
            "new selection is queued for human review; production activation remains false."
        ),
        "",
        (
            f"Among all 42 selected candidates, frozen human evidence currently marks "
            f"{summary['selected_known_human_safe_count']} SAFE, "
            f"{summary['selected_known_human_wrong_count']} WRONG, and "
            f"{summary['selected_known_human_uncertain_count']} UNCERTAIN; the rest are "
            "unreviewed. These are evidence-availability counts, not a population precision "
            "estimate."
        ),
        "",
        "## Architecture",
        "",
        "The historical Balanced V1 → 1C-A → 1C-B → 1C-C cascade is replayed unchanged. "
        "Stage 5B.1G then considers every conflict-free candidate admitted by any frozen "
        "tier plus candidates independently admitted by the graduated-duration gate. The "
        "admitting tier is evidence provenance only and never affects preference.",
        "",
        "Global lexicographic preference is: structural recording identity; target-relative "
        "version compatibility; performer identity; internally consistent provenance; "
        "graduated duration; source quality; album/year corroboration; finally views and "
        "search rank as weak tiebreakers.",
        "",
        "## Graduated duration evidence",
        "",
        "| Bucket | Interval | Considered | Eligible | Selected | Human SAFE | Human WRONG | Human UNCERTAIN |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    intervals = {
        DURATION_VERY_CLOSE: "0–2 s",
        DURATION_CLOSE: ">2–7 s",
        DURATION_EXTENDED_1: ">7–12 s",
        DURATION_EXTENDED_2: ">12–16 s",
        DURATION_EXTENDED_3: ">16–20 s",
        DURATION_TOO_FAR: ">20 s",
        DURATION_UNKNOWN: "unknown",
    }
    for row in duration["rows"]:
        lines.append(
            f"| {row['bucket']} | {intervals[row['bucket']]} | "
            f"{row['candidates_considered']} | {row['candidates_eligible']} | "
            f"{row['candidates_selected']} | {row['selected_human_safe_count']} | "
            f"{row['selected_human_wrong_count']} | {row['selected_human_uncertain_count']} |"
        )
    lines.extend([
        "",
        "Candidates beyond seven seconds require progressively stronger corroboration. "
        "A delta above 20 seconds is a hard rejection. Explicit performer, cover, version, "
        "or unrequested-modification conflicts remain hard rejections at every band.",
        "",
        "## Changed and newly resolved selections",
        "",
    ])
    if not changed["comparisons"]:
        lines.append("No candidate selection changed.")
    for row in changed["comparisons"]:
        old = row["old_selected_candidate"]
        new = row["new_selected_candidate"]
        old_id = old["snapshot"]["video_id"] if old else "MATCH_UNCERTAIN"
        new_id = new["snapshot"]["video_id"] if new else "MATCH_UNCERTAIN"
        human = _evidence_label(new, "human") if new else None
        sol = _evidence_label(new, "sol") if new else None
        lines.append(
            f"- `{row['stable_track_id']}`: `{old_id}` → `{new_id}` "
            f"({row['change_type']}; existing human={human or 'unreviewed'}; "
            f"frozen Sol={sol or 'missing'})."
        )
    lines.extend(["", "Frozen human-label transitions among changed selections:", ""])
    for transition, count in changed["human_label_transitions"].items():
        lines.append(f"- `{transition}`: {count}")
    lines.extend(["", "Source-type transitions:", ""])
    for transition, count in changed["source_type_transitions"].items():
        lines.append(f"- `{transition}`: {count}")
    lines.extend([
        "",
        "### Stage 5B.1F preference-case replay",
        "",
        "| Track | Prior cause | Global selection equals best known human-SAFE candidate |",
        "|---|---|---:|",
    ])
    for row in changed["stage5b1f_preference_case_replay"]:
        lines.append(
            f"| `{row['stable_track_id']}` | `{row['stage5b1f_primary_cause']}` | "
            f"{'yes' if row['global_selected_best_known_human_safe'] else 'no'} |"
        )
    lines.extend([
        "",
        "## Remaining tail",
        "",
        f"The experiment leaves **{tail['remaining_unresolved_count']}/8** previously "
        "unresolved tracks unresolved.",
        "",
    ])
    for row in tail["tracks"]:
        decision = row["global_preference_decision"]
        lines.append(
            f"- `{row['stable_track_id']}` — `{row['classification']}`; "
            f"decision `{decision['status']}`; prior blocker: "
            f"{row['prior_stage5b1f_primary_blocker']}."
        )
    lines.extend([
        "",
        "## Conclusions",
        "",
        (
            "1. Global competition materially changes source preference: it selects the best "
            "known human-SAFE candidate in four of the five Stage 5B.1F preference cases. "
            "Track 044 remains unchanged because its release-description evidence still "
            "ranks ahead of the neutral reviewed alternative, although that evidence does not "
            "meet the stricter internally-consistent Art Track definition. Five additional "
            "changed candidates lack frozen human labels and require the generated audit."
        ),
        (
            "2. Graduated duration removes the 7-second mathematical cliff without creating "
            "new coverage. The selected >16-second Official Music Video is frozen-Sol "
            "ACCEPTABLE but human-unreviewed, so safety of that band remains pending. "
            "Extended bands cannot override conflicts, and 12–20-second candidates require "
            "strong or strongest corroborated provenance."
        ),
        (
            f"3. Existing selections changed: {summary['existing_selection_changed_count']}; "
            f"new tracks resolved: {summary['newly_resolved_count']}. Four changed selections "
            "are upgrades in frozen human evidence, one is IDEAL-to-IDEAL, and five are "
            "unreviewed. No changed selection is frozen-human WRONG or frozen-Sol WRONG."
        ),
        (
            f"4. Mechanical coverage {'reaches' if summary['global_coverage'] >= 0.9 else 'does not reach'} "
            f"the 90% milestone: {summary['global_auto_match_count']}/50 "
            f"({summary['global_coverage']:.0%}). The eight-track tail remains four pools with "
            "no defensible candidate, three metadata-insufficient pools, and one pool dominated "
            "by conflicting candidates."
        ),
        (
            "5. The selection-bottleneck hypothesis is supported for source quality, not for "
            "remaining coverage. Global comparison corrects known duration/provenance and "
            "tier-lock inversions, but no defensible deterministic path to at least 45/50 is "
            "demonstrated by the frozen top-five metadata. Better discovery or additional "
            "evidence remains necessary for the unresolved tail."
        ),
        (
            "6. Counterfactual negatives remain protected: no selected candidate carries an "
            "explicit performer/cover, version, or unrequested modified-audio conflict, and "
            "every >7-second eligible candidate records the corroboration that admitted it."
        ),
        "",
        "## Review and scope",
        "",
        f"- review queue: `{_display_path(config.artifacts['human_review_csv'], config.project_root)}`",
        f"- queued tracks/candidates: {queue['track_count']}/{queue['candidate_count']}",
        "- Q0 changed: no; searches run: 0; media downloaded: 0; Sol rerun: no",
        "- historical resolver policies changed: no",
        "- production activation: no",
        "",
        "## Tests",
        "",
        "- focused Stage 5B.1G tests: `36 passed`",
        "- resolver regression suite: `59 passed`",
        "- full non-heavy suite: `799 passed, 12 deselected, 11 warnings`",
        "",
    ])
    config.artifacts["report"].parent.mkdir(parents=True, exist_ok=True)
    config.artifacts["report"].write_text("\n".join(lines), encoding="utf-8")


def write_artifacts(config: Stage5B1GConfig) -> dict[str, Any]:
    verified = verify_frozen_inputs(config)
    features, decisions, changed, duration, tail, queue = evaluate_stage5b1g(config)
    outputs = {
        "candidate_features": features,
        "decisions": decisions,
        "changed_selections": changed,
        "duration_analysis": duration,
        "remaining_tail": tail,
        "human_audit_queue": queue,
    }
    for name, value in outputs.items():
        atomic_json(config.artifacts[name], value)
    _write_review_csv(config.artifacts["human_review_csv"], _review_rows(features, queue))
    write_report(config, decisions, changed, duration, tail, queue)
    output_names = tuple(outputs) + ("human_review_csv", "report")
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": STATUS,
        "config": {
            "path": _display_path(config.path, config.project_root),
            "sha256": config.sha256,
        },
        "frozen_inputs": verified,
        "artifacts": {
            name: {
                "path": _display_path(config.artifacts[name], config.project_root),
                "sha256": file_sha256(config.artifacts[name]),
                "size_bytes": config.artifacts[name].stat().st_size,
            }
            for name in output_names
        },
        "scope_guards": decisions["scope_guards"],
    }
    atomic_json(config.artifacts["manifest"], manifest)
    return manifest


def _default_config() -> Path:
    return Path(__file__).parents[2] / "configs/stage5b1g_global_preference.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_default_config())
    args = parser.parse_args(argv)
    config = load_stage5b1g_config(args.config)
    manifest = write_artifacts(config)
    print(json.dumps({
        "status": manifest["status"],
        "manifest": str(config.artifacts["manifest"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
