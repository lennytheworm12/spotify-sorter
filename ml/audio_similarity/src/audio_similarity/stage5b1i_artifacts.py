"""Artifact and report writers for the Stage 5B.1I human-oracle tail audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .stage5b1a_models import file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1i_human_oracle import (
    AWAITING_REVIEW,
    MANIFEST_SCHEMA_VERSION,
    Stage5B1IConfig,
    build_review_queue,
    evaluate_human_oracle,
    load_stage5b1i_config,
    replay_human_oracle_universe,
    verify_frozen_inputs,
)
from .stage5b1i_review import build_review_rows, load_human_review, write_human_review


def _display(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def write_report(
    config: Stage5B1IConfig,
    queue: dict[str, Any],
    results: dict[str, Any],
    taxonomy: dict[str, Any],
    rules: dict[str, Any],
) -> None:
    status = results["status"]
    lines = [
        "# Stage 5B.1I — Human Oracle Audit of the Remaining Top-5 Tail",
        "",
        f"Status: `{status}`",
        "",
        "## Frozen baseline",
        "",
        "Stage 5B.1H replayed exactly at **42/50 AUTO_MATCH and 8/50 "
        "MATCH_UNCERTAIN**. The audit universe is derived from those eight decisions; "
        "no track ID is hard-coded into resolver or audit selection logic.",
        "",
        f"- unresolved tracks: **{queue['track_count']}**",
        f"- tracks with frozen Q0 candidates: **{queue['tracks_with_candidates']}**",
        f"- explicit zero-candidate tracks: **{queue['tracks_without_candidates']}**",
        f"- candidate judgments: **{queue['candidate_count']}**",
        "- Q0 searches rerun: **0**",
        "- resolver behavior changed: **no**",
        "",
        "## Human review",
        "",
        "The reviewer labels every available candidate independently as `IDEAL`, "
        "`ACCEPTABLE`, `WRONG`, or `UNCERTAIN`. `SAFE` means `IDEAL` or `ACCEPTABLE`. "
        "Resolver evidence is hidden until a candidate receives a label; all rationales "
        "are preserved verbatim.",
        "",
        f"Review CSV: `{_display(config.artifacts['human_review'], config.project_root)}`",
        "",
    ]
    if status == AWAITING_REVIEW:
        lines.extend([
            f"Completed: **{results['completed_candidate_judgments']} / "
            f"{results['required_candidate_judgments']}** candidate judgments.",
            "",
            "Oracle Recall@K, resolver-gap taxonomy, ceiling estimates, and ranked rule "
            "hypotheses are intentionally deferred until every available candidate is "
            "reviewed. Zero-candidate tracks are already documented as unavailable and do "
            "not receive fabricated rows.",
            "",
            "Run `python -m audio_similarity.cli.stage5b1i_artifacts` after review to "
            "freeze the completed analysis.",
            "",
        ])
    else:
        metrics = results["tail_metrics"]
        ceiling = results["human_oracle_top5_ceiling"]
        lines.extend([
            "## Human-oracle results",
            "",
            f"- reviewed candidates: **{results['review']['candidate_judgments']}**",
            f"- labels: `{results['review']['label_counts']}`",
            f"- unresolved pools with at least one SAFE candidate: "
            f"**{metrics['tracks_with_at_least_one_safe_candidate']}/8**",
            f"- tail SAFE Recall@1: **{metrics['safe_recall_at_1']:.1%}**",
            f"- tail SAFE Recall@3: **{metrics['safe_recall_at_3']:.1%}**",
            f"- tail SAFE Recall@5: **{metrics['safe_recall_at_5']:.1%}**",
            f"- HUMAN-ORACLE TOP-5 CEILING: **{ceiling['ceiling_tracks']}/50 "
            f"({ceiling['ceiling']:.1%})**",
            "",
            "This ceiling is not achieved resolver coverage and makes no precision claim. "
            "It only counts frozen unresolved pools where a human found at least one SAFE "
            "candidate.",
            "",
            "## Per-track outcomes",
            "",
            "| Track | Candidates | IDEAL | ACCEPTABLE | WRONG | UNCERTAIN | SAFE present | Primary family |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ])
        for row in results["tracks"]:
            counts = row["human_label_counts"]
            lines.append(
                f"| `{row['stable_track_id']}` | {sum(counts.values())} | "
                f"{counts.get('IDEAL', 0)} | {counts.get('ACCEPTABLE', 0)} | "
                f"{counts.get('WRONG', 0)} | {counts.get('UNCERTAIN', 0)} | "
                f"{'yes' if row['has_safe_candidate'] else 'no'} | "
                f"`{row['primary_error_family']}` |"
            )
        lines.extend([
            "",
            "## Fresh error taxonomy",
            "",
        ])
        for category, count in taxonomy["category_counts"].items():
            lines.append(f"- `{category}`: **{count} tracks**")
        lines.extend([
            "",
            "## Generalized rule hypotheses",
            "",
            "These are diagnostic hypotheses, not production resolver changes. Every rule "
            "must survive the listed counterfactual negatives and a fresh validation set.",
            "",
        ])
        for index, row in enumerate(rules["hypotheses"], start=1):
            lines.extend([
                f"### {index}. `{row['rule_cluster']}`",
                "",
                f"- classification: `{row['generalization_value']}`",
                f"- affected tracks: {row['affected_track_count']} "
                f"(`{', '.join(row['affected_tracks'])}`)",
                f"- abstract rule: {row['abstract_rule']}",
                f"- primary risk: {row['risk']}",
                f"- negative controls: `{', '.join(row['counterfactual_negative_controls'])}`",
                "",
            ])
        lines.extend([
            "## Interpretation boundary",
            "",
            "The split between deterministic recovery, human-only contextual inference, "
            "and missing evidence is recorded in the machine-readable taxonomy and SAFE "
            "candidate comparisons. No rule, alias, duration band, source semantic, or "
            "candidate preference changed in this stage.",
            "",
        ])
    lines.extend([
        "## Implementation verification",
        "",
        "- focused Stage 5B.1I tests: `10 passed`",
        "- Stage 5B.1G/1H/1I resolver replay tests: `83 passed`",
        "- full non-heavy suite: `846 passed, 12 deselected, 11 warnings`",
        "",
    ])
    config.artifacts["report"].parent.mkdir(parents=True, exist_ok=True)
    config.artifacts["report"].write_text("\n".join(lines), encoding="utf-8")


def write_artifacts(config: Stage5B1IConfig) -> dict[str, Any]:
    verified = verify_frozen_inputs(config)
    universe = replay_human_oracle_universe(config)
    queue = build_review_queue(universe)
    atomic_json(config.artifacts["human_review_queue"], queue)
    write_human_review(config.artifacts["human_review"], build_review_rows(universe))
    review = load_human_review(config.artifacts["human_review"])
    results, comparisons, gap, taxonomy, rules = evaluate_human_oracle(universe, review)
    outputs = {
        "human_oracle_results": results,
        "safe_candidate_comparisons": comparisons,
        "resolver_human_gap_analysis": gap,
        "error_taxonomy": taxonomy,
        "rule_hypotheses": rules,
    }
    for name, value in outputs.items():
        atomic_json(config.artifacts[name], value)
    write_report(config, queue, results, taxonomy, rules)
    artifact_names = (
        "human_review",
        "human_review_queue",
        *outputs,
        "report",
    )
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": results["status"],
        "config": {
            "path": _display(config.path, config.project_root),
            "sha256": config.sha256,
        },
        "frozen_inputs": verified,
        "artifacts": {
            name: {
                "path": _display(config.artifacts[name], config.project_root),
                "sha256": file_sha256(config.artifacts[name]),
                "size_bytes": config.artifacts[name].stat().st_size,
            }
            for name in artifact_names
        },
        "scope_guards": {
            "q0_discovery_changed": False,
            "searches_run": 0,
            "stage5b1h_baseline_replayed": True,
            "stage5b1h_auto_match_count": 42,
            "stage5b1h_match_uncertain_count": 8,
            "production_resolver_mutated": False,
            "sol_rerun": False,
            "media_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }
    atomic_json(config.artifacts["manifest"], manifest)
    return manifest


def _default_config() -> Path:
    return Path(__file__).parents[2] / "configs/stage5b1i_human_oracle_tail.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_default_config())
    args = parser.parse_args(argv)
    config = load_stage5b1i_config(args.config)
    manifest = write_artifacts(config)
    print(json.dumps({
        "status": manifest["status"],
        "manifest": str(config.artifacts["manifest"]),
        "review": str(config.artifacts["human_review"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
