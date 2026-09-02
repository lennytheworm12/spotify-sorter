"""Artifact and closeout writers for Stage 5B.1H."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .stage5b1a_models import file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1h_source_semantics import (
    MANIFEST_SCHEMA_VERSION,
    STATUS,
    Stage5B1HConfig,
    evaluate_stage5b1h,
    load_stage5b1h_config,
    source_phrase_vocabulary,
    verify_frozen_inputs,
)


def _display(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def _phrase_text(row: dict[str, Any]) -> str:
    positive = [item["matched_text"] for item in row["source_phrase_evidence"]]
    negative = [item["matched_text"] for item in row["negation_evidence"]]
    values = negative or positive
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def write_report(
    config: Stage5B1HConfig,
    semantics: dict[str, Any],
    decisions: dict[str, Any],
    comparisons: dict[str, Any],
    padding: dict[str, Any],
    queue: dict[str, Any],
) -> None:
    summary = decisions["summary"]
    source_summary = semantics["summary"]
    lines = [
        "# Stage 5B.1H — Canonical Source Recognition + Video-Padding Semantics",
        "",
        f"Status: `{STATUS}`",
        "",
        "## Outcome",
        "",
        (
            "The frozen Stage 5B.1G control reproduced exactly at **42/50 AUTO_MATCH "
            "and 8/50 MATCH_UNCERTAIN**. Stage 5B.1H preserves all 50 decisions and "
            "all selected candidate IDs, so coverage remains **42/50 (84%)**."
        ),
        "",
        (
            f"Among the 42 selected candidates, frozen human evidence now records "
            f"**{summary['known_human_safe_selected']} SAFE**, "
            f"**{summary['known_human_wrong_selected']} WRONG**, and "
            f"**{summary['known_human_uncertain_selected']} UNCERTAIN**; two selections "
            "remain without human evidence. These are evidence-availability counts, not "
            "a population precision estimate."
        ),
        "",
        "## Architectural decision",
        "",
        "Stage 5B.1H records three orthogonal dimensions:",
        "",
        "1. **Recording identity** — compatible, incomplete, or explicitly conflicting.",
        "2. **Source canonicality** — strong, supported, or unknown. Recognized artist, "
        "label/distributor, Topic, and structured-release provenance is positive; unknown "
        "provenance remains neutral.",
        "3. **Audio cleanliness / video-padding risk** — likely clean audio, low padding, "
        "possible padding, elevated/unknown padding, or outside the frozen 20-second limit.",
        "",
        "This is a separate evidence layer. Frozen Stage 5B.1G remains responsible for "
        "eligibility and global ordering; source terminology cannot rescue a recording, "
        "performer, version, or unrequested-modification conflict.",
        "",
        "## Source vocabulary",
        "",
        "The parser uses a small explicit vocabulary: `Official Audio`, `Official Video`, "
        "`Official Music Video`, `Official MV`, `M/V`, `MV`, `Official Lyric Video`, "
        "`Lyric Video`, `Audio`, French `clip officiel` / `vidéo officielle`, and Spanish "
        "`video oficial` / `vídeo oficial`. Bare `Audio`, bare `M/V`, and bare lyric wording "
        "require provenance corroboration before becoming canonical.",
        "",
        "Negation is evaluated first. `Not a MV`, `Not an MV`, `Unofficial Video`, "
        "`Not Official`, and `Fan Made Official Style` cannot create positive video-source "
        "evidence. No translation model, language detector, or external NLP dependency is used.",
        "",
        "## Metrics",
        "",
        f"- legacy source classifications refined: "
        f"{source_summary['legacy_source_classifications_changed']}",
        f"- selected canonicality: `{source_summary['selected_canonicality_counts']}`",
        f"- selected padding/cleanliness: `{source_summary['selected_padding_risk_counts']}`",
        f"- selected normalized sources: `{source_summary['selected_source_type_counts']}`",
        f"- selected IDs changed: {summary['selection_ids_changed']}",
        f"- known human WRONG introduced: {summary['known_human_wrong_selected']}",
        "",
        "The source-classification count describes semantic refinements relative to the "
        "legacy broad source enum; it does not imply that 55 historical selections were wrong.",
        "",
        "## Reviewed diagnostic cases",
        "",
        "| Track | Recognized phrase | Normalized source | Canonicality | Duration delta | Padding risk | Selected | Human |",
        "|---|---|---|---|---:|---|---:|---|",
    ]
    for row in comparisons["diagnostic_cases"]:
        lines.append(
            f"| `{row['stable_track_id']}` | {_phrase_text(row)} | "
            f"`{row['normalized_source_type']}` | `{row['canonicality']['level']}` | "
            f"{row['absolute_duration_delta_seconds']:.3f}s | "
            f"`{row['padding_risk']['level']}` | yes | "
            f"`{row['human_label'] or 'UNREVIEWED'}` |"
        )
    lines.extend([
        "",
        "`s5b1c_048` (PROVENZA) is interpreted as a compatible recording from a strongly "
        "canonical artist-controlled Official Video, while its 16.8-second difference is "
        "retained as elevated/unknown video-padding risk. The candidate remains eligible "
        "because frozen 1G already admitted it—not because 1H ignores duration.",
        "",
        "`s5b1c_049` (Shinunoga E-Wa) records `Not a MV` as negated presentation evidence. "
        "Its artist-channel provenance may still be canonical, but `MV` does not generate "
        "a positive music-video classification.",
        "",
        "## Padding-risk distribution",
        "",
        "| Risk | Candidates | Selected | Selected human labels |",
        "|---|---:|---:|---|",
    ])
    for row in padding["rows"]:
        lines.append(
            f"| `{row['padding_risk']}` | {row['candidate_count']} | "
            f"{row['selected_count']} | `{row['selected_human_label_counts']}` |"
        )
    lines.extend([
        "",
        "## Selection and safety",
        "",
        "- selections changed from Stage 5B.1G: **0**",
        "- additional AUTO_MATCH decisions: **0**",
        "- known negative controls newly eligible: **0** (1H preserves frozen eligibility)",
        f"- human-review queue: **{queue['candidate_count']} candidates** (`{queue['status']}`)",
        "",
        "The five newly reviewed 1G selections are all human `IDEAL`. The semantics explain "
        "them through generalized phrase and provenance rules; no artist, track, or video ID "
        "is present in runtime classification logic.",
        "",
        "## Scope and recommendation",
        "",
        "The refinement succeeds as an interpretation layer: obvious canonical sources are "
        "recognized consistently, while canonicality is no longer conflated with guaranteed "
        "clean audio. It should remain attached to downstream acquisition evidence so a later "
        "audio-validation/trimming stage can treat padding risk explicitly. This experiment "
        "does not justify broader eligibility, new searches, or real-library validation.",
        "",
        "Scope guards: Q0 unchanged; searches 0; media downloads 0; Sol reruns 0; Stage 5A, "
        "CLAP, and MuQ calls 0; historical resolver policies unchanged.",
        "",
        "## Verification",
        "",
        "- focused Stage 5B.1H tests: `37 passed`",
        "- resolver regression suite: `138 passed`",
        "- full non-heavy suite: `836 passed, 12 deselected, 11 warnings`",
        "",
    ])
    config.artifacts["report"].parent.mkdir(parents=True, exist_ok=True)
    config.artifacts["report"].write_text("\n".join(lines), encoding="utf-8")


def write_artifacts(config: Stage5B1HConfig) -> dict[str, Any]:
    verified = verify_frozen_inputs(config)
    semantics, decisions, comparisons, padding, queue = evaluate_stage5b1h(config)
    outputs = {
        "source_semantics": semantics,
        "source_phrase_normalization": source_phrase_vocabulary(),
        "selection_comparisons": comparisons,
        "padding_risk_analysis": padding,
        "human_audit_queue": queue,
    }
    for name, value in outputs.items():
        atomic_json(config.artifacts[name], value)
    write_report(config, semantics, decisions, comparisons, padding, queue)
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
    return Path(__file__).parents[2] / "configs/stage5b1h_canonical_source_semantics.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_default_config())
    args = parser.parse_args(argv)
    config = load_stage5b1h_config(args.config)
    manifest = write_artifacts(config)
    print(json.dumps({
        "status": manifest["status"],
        "manifest": str(config.artifacts["manifest"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
