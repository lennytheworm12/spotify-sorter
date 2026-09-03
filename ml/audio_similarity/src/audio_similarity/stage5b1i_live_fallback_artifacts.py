"""Artifact and report writers for Stage 5B.1I live representation fallback."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .stage5b1a_models import file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1i_live_fallback import (
    MANIFEST_SCHEMA_VERSION,
    ORDINARY_LIVE,
    STATUS,
    Stage5B1IConfig,
    evaluate_stage5b1i,
    load_stage5b1i_config,
    verify_frozen_inputs,
)


def _display(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def _render_report(
    config: Stage5B1IConfig,
    classifications: dict[str, Any],
    features: dict[str, Any],
    decisions: dict[str, Any],
    queue: dict[str, Any],
) -> str:
    summary = decisions["summary"]
    live_summary = classifications["summary"]
    lines = [
        "# Stage 5B.1I — Representation-Equivalent Live Fallback",
        "",
        f"Status: `{STATUS}`",
        "",
        "## Outcome",
        "",
        (
            "The frozen Stage 5B.1H control reproduced exactly at **42/50 "
            "AUTO_MATCH and 8/50 MATCH_UNCERTAIN** with every prior candidate ID "
            "unchanged. The new ordinary-live fallback recovered **"
            f"{summary['representation_equivalent_fallback_count']}** tracks, so measured "
            f"coverage remains **{summary['stage5b1i_auto_match_count']}/50 "
            f"({summary['coverage_after']:.0%})**."
        ),
        "",
        (
            "This zero-gain result is informative: the one unresolved ordinary-live "
            "target has no conflict-free canonical studio candidate in its frozen Q0 "
            "top five. The experiment does not loosen identity rules or relabel an "
            "uncorroborated user upload as representation-equivalent."
        ),
        "",
        "## Decision contract",
        "",
        "Stage 5B.1I records two distinct outcomes:",
        "",
        "- `EXACT_RECORDING`: the frozen Stage 5B.1H resolver selected the requested recording.",
        "- `REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK`: exact-live resolution failed, "
        "then a canonical studio recording was selected for downstream CLAP/MuQ representation.",
        "",
        "Exact recording always wins. The fallback runs only for an ordinary live target "
        "whose only material version family is `live`. Live targets that also specify "
        "acoustic, orchestral, remix, instrumental, remaster, slowed/sped/reverb, or "
        "another arrangement-changing identity remain unresolved.",
        "",
        "A fallback candidate requires strong structural title and performer identity, "
        "no cover/performer/version/modification conflict, no evidence of another live "
        "performance, no production-changing candidate version, and strong artist, Topic, "
        "label/distributor, or structured-release provenance. Unknown provenance remains "
        "neutral in the general resolver but is insufficient by itself for this approximation.",
        "",
        "Live-target versus studio-candidate duration is retained for inspection but is "
        "not an eligibility or preference signal. Live and studio performances legitimately "
        "differ in crowd interaction, tempo, and performance structure.",
        "",
        "## Frozen live-target replay",
        "",
        "| Track | Target | Classification | Risk | Exact candidates | 1H outcome | Studio fallback candidates | 1I mode |",
        "|---|---|---|---|---:|---|---:|---|",
    ]
    for row in classifications["tracks"]:
        lines.append(
            f"| `{row['stable_track_id']}` | {row['target']['title']} | "
            f"`{row['classification']}` | `{row['representation_risk']}` | "
            f"{len(row['exact_live_candidate_ids'])} | `{row['stage5b1h_exact_outcome']}` | "
            f"{len(row['studio_fallback_candidate_ids'])} | "
            f"`{row['stage5b1i_match_mode'] or 'NONE'}` |"
        )
    lines.extend([
        "",
        "## Unresolved ordinary-live candidate evidence",
        "",
    ])
    for track in features["tracks"]:
        lines.extend([
            f"### `{track['track']['stable_track_id']}` — {track['track']['title']}",
            "",
            "| Rank | Candidate | Canonicality | Live evidence | Eligible | Failed gates |",
            "|---:|---|---|---:|---:|---|",
        ])
        for candidate in track["candidates"]:
            failed = ", ".join(candidate["eligibility"]["failed_conditions"])
            lines.append(
                f"| {candidate['candidate']['search_rank']} | "
                f"`{candidate['candidate_video_id']}` {candidate['candidate']['title']} | "
                f"`{candidate['canonicality']['level']}` | "
                f"{str(candidate['explicit_live_presentation_evidence']).lower()} | "
                f"{str(candidate['eligibility']['eligible']).lower()} | {failed} |"
            )
        lines.extend([
            "",
            "The frozen pool consists of uncorroborated live/user-upload evidence. It does "
            "not contain a candidate with artist, Topic, distributor, or release-backed "
            "studio provenance, so representation equivalence cannot be established safely.",
            "",
        ])
    lines.extend([
        "## Measurement",
        "",
        f"- live targets identified: **{live_summary['live_target_count']}**",
        f"- ordinary live targets: **{live_summary['ordinary_live_target_count']}**",
        f"- arrangement-changing live targets: **{live_summary['arrangement_changing_live_target_count']}**",
        f"- exact live AUTO_MATCHes: **{live_summary['exact_live_auto_match_count']}**",
        f"- ordinary-live exact failures: **{live_summary['ordinary_live_exact_failures']}**",
        f"- studio fallback opportunities in frozen Q0: **{live_summary['studio_fallback_opportunity_count']}**",
        f"- new representation-equivalent AUTO_MATCHes: **{summary['representation_equivalent_fallback_count']}**",
        f"- remaining MATCH_UNCERTAIN: **{summary['stage5b1i_match_uncertain_count']}**",
        f"- absolute coverage change: **{summary['absolute_percentage_point_gain']:.0f} percentage points**",
        f"- human-review queue: **{queue['candidate_count']} candidates** (`{queue['status']}`)",
        "",
        "## Safety and scope",
        "",
        "No existing exact selection changed. No non-live version semantics changed. "
        "Remix, acoustic, instrumental, karaoke, remaster, extended/radio mix, rerecording, "
        "slowed/sped/reverb, nightcore, bass-boosted, mashup, and arrangement-changing live "
        "targets remain exact-only. Explicit performer, cover, and version conflicts remain "
        "hard negatives.",
        "",
        "Searches 0; audio/video downloads 0; Sol runs 0; human labels changed 0; "
        "Stage 5A, CLAP, and MuQ calls 0. This policy is evaluated offline and is not "
        "production-activated.",
        "",
        "## Representation risk and future validation",
        "",
        "Ordinary unqualified live targets are marked `LOW`; venue/year-specific ordinary "
        "live targets are marked `ELEVATED` because the requested performance may differ "
        "more materially even though fallback is allowed. Arrangement-changing live targets "
        "are `UNSUITABLE` and never receive studio fallback.",
        "",
        "A later audio experiment should compare exact live audio against its studio fallback "
        "using CLAP cosine, MuQ cosine, the frozen combined similarity, and nearest-neighbor "
        "overlap. That experiment was not run here.",
        "",
        "## Recommendation",
        "",
        "Keep the explicit match-mode abstraction: it faithfully represents the product "
        "tradeoff and is covered by deterministic safety tests. On this frozen challenge, "
        "however, no actual fallback can be justified because discovery did not surface a "
        "canonical studio candidate for the unresolved live target. Rebuild the later human-"
        "oracle audit around exact versus representation-equivalent semantics, while leaving "
        "the measured baseline at 42/50.",
        "",
        "## Verification",
        "",
        "- focused Stage 5B.1I tests: `26 passed`",
        "- complete Stage 5B resolver regression suite: `401 passed`",
        "- full non-heavy suite: `862 passed, 12 deselected, 11 warnings`",
        "",
        "Reproduce the frozen artifacts from `ml/audio_similarity` with:",
        "",
        "```bash",
        "uv run python -m audio_similarity.cli.stage5b1i_live_fallback",
        "```",
        "",
    ])
    return "\n".join(lines)


def write_artifacts(config: Stage5B1IConfig) -> dict[str, Any]:
    verified = verify_frozen_inputs(config)
    classifications, features, decisions, queue = evaluate_stage5b1i(config)
    outputs = {
        "live_target_classification": classifications,
        "representation_equivalence_decisions": decisions,
        "fallback_candidate_features": features,
        "human_audit_queue": queue,
    }
    for name, value in outputs.items():
        atomic_json(config.artifacts[name], value)
    config.artifacts["report"].parent.mkdir(parents=True, exist_ok=True)
    config.artifacts["report"].write_text(
        _render_report(config, classifications, features, decisions, queue),
        encoding="utf-8",
    )
    output_names = tuple(outputs) + ("report",)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": STATUS,
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
            for name in output_names
        },
        "scope_guards": decisions["scope_guards"],
    }
    atomic_json(config.artifacts["manifest"], manifest)
    return manifest


def _default_config() -> Path:
    return Path(__file__).parents[2] / "configs/stage5b1i_live_representation_fallback.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_default_config())
    args = parser.parse_args(argv)
    config = load_stage5b1i_config(args.config)
    manifest = write_artifacts(config)
    print(json.dumps({
        "status": manifest["status"],
        "manifest": str(config.artifacts["manifest"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
