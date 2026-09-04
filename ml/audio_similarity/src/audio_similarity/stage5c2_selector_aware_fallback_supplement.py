"""Targeted post-benchmark validation of selector-aware query fallback."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b_selector_aware_fallback import (
    FALLBACK_SELECTED,
    QUERY_CONTRACT_ID,
    discover_and_select_with_fallback,
)
from .stage5c2_discovery import default_provider


EXPERIMENT_ID = "STAGE5C2_SELECTOR_AWARE_FALLBACK_SUPPLEMENT"
REPORT_DIRECTORY = "reports/stage5c2_selector_aware_fallback_supplement"
FROZEN_STAGE5C2_DIRECTORY = "reports/stage5c2_representative_100"
TARGETS = {
    "stage5c2_008": {
        "owner_video_id": "v224EdAkZr8",
        "owner_url": "https://www.youtube.com/watch?v=v224EdAkZr8",
    },
    "stage5c2_019": {
        "owner_video_id": "i4YFngxyJ0k",
        "owner_url": "https://www.youtube.com/watch?v=i4YFngxyJ0k",
    },
}
FROZEN_INPUT_NAMES = (
    "representative_manifest.json",
    "discovery_results.json",
    "automated_selector_decisions.json",
    "selected_sources.json",
    "stage5c2_metrics.json",
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _hashes(directory: Path) -> dict[str, str]:
    return {name: file_sha256(directory / name) for name in FROZEN_INPUT_NAMES}


def _spotify_track(row: dict[str, Any]) -> SpotifyTrack:
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": row["stage5c2_track_id"],
            "spotify_track_id": row["spotify_track_id"],
            "title": row["title"],
            "artists": row["artists"],
            "album": row.get("album"),
            "duration_ms": row.get("duration_ms"),
            "release_year": row.get("release_year"),
            "isrc": row.get("isrc"),
        }
    )


def run_targeted_supplement(
    project_root: str | Path,
    provider: Any | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    frozen = root / FROZEN_STAGE5C2_DIRECTORY
    output = root / REPORT_DIRECTORY
    output.mkdir(parents=True, exist_ok=True)
    before = _hashes(frozen)
    manifest = _json(frozen / "representative_manifest.json")
    decisions = _json(frozen / "automated_selector_decisions.json")
    manifest_by_id = {row["stage5c2_track_id"]: row for row in manifest["tracks"]}
    decisions_by_id = {row["stage5c2_track_id"]: row for row in decisions["tracks"]}
    for track_id in TARGETS:
        if decisions_by_id[track_id]["decision"] != "MATCH_UNCERTAIN":
            raise Stage5B1AValidationError(
                f"historical manual-tail evidence changed: {track_id}"
            )

    active_provider = provider or default_provider()
    rows = []
    for track_id, reference in TARGETS.items():
        target = manifest_by_id[track_id]
        result = discover_and_select_with_fallback(
            _spotify_track(target), active_provider
        )
        rows.append(
            {
                "stage5c2_track_id": track_id,
                "spotify_track_id": target["spotify_track_id"],
                "title": target["title"],
                "artists": target["artists"],
                "spotify_duration_seconds": target["duration_ms"] / 1000,
                "historical_stage5c2": {
                    "decision": decisions_by_id[track_id]["decision"],
                    "reason": decisions_by_id[track_id]["selection_reason"],
                    "successful_query": decisions_by_id[track_id]["successful_query"],
                    "candidate_video_ids": [
                        item["video_id"]
                        for item in decisions_by_id[track_id]["candidate_evaluations"]
                    ],
                },
                "owner_supplied_reference": reference,
                "selector_aware_result": result,
                "owner_reference_recovered": (
                    result["selected_video_id"] == reference["owner_video_id"]
                ),
            }
        )

    after = _hashes(frozen)
    if before != after:
        raise Stage5B1AValidationError("frozen Stage 5C.2 inputs changed")
    love = next(row for row in rows if row["stage5c2_track_id"] == "stage5c2_019")
    validated = all(row["owner_reference_recovered"] for row in rows) and (
        love["selector_aware_result"]["outcome"] == FALLBACK_SELECTED
        and love["selector_aware_result"]["query_variant_index"] == 4
    )
    document = {
        "schema_version": "stage5c2-selector-aware-fallback-supplement-v1",
        "experiment_id": EXPERIMENT_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": (
            "SELECTOR_AWARE_FALLBACK_TARGETED_VALIDATED"
            if validated
            else "SELECTOR_AWARE_FALLBACK_TARGETED_INCONCLUSIVE"
        ),
        "query_contract_id": QUERY_CONTRACT_ID,
        "tracks": rows,
        "frozen_stage5c2_input_sha256": before,
        "scope_guards": {
            "historical_stage5c2_rewritten": False,
            "stage5b3_selector_modified": False,
            "media_downloads": 0,
            "candidate_pool_merges": 0,
            "production_activation": False,
            "broad_corpus_search": False,
        },
    }
    config = {
        "schema_version": "stage5c2-selector-aware-fallback-config-v1",
        "experiment_id": EXPERIMENT_ID,
        "query_contract_id": QUERY_CONTRACT_ID,
        "trigger": "NO_SELECTABLE_CANDIDATE_FROM_FROZEN_SELECTOR",
        "variant_order": [
            "TITLE_FIRST3_ARTISTS",
            "TITLE_ARTIST_1",
            "TITLE_ARTIST_2",
            "TITLE_ARTIST_3",
            "TITLE_ONLY",
        ],
        "stop_condition": "FIRST_QUERY_POOL_WITH_AUTO_SELECT",
        "candidate_limit_per_query": 3,
        "candidate_pool_merging": False,
        "selector": "STAGE5B3_MINIMAL_YOUTUBE_SELECTOR_V1_UNCHANGED",
        "targets": TARGETS,
    }
    atomic_json(output / "fallback_config.json", config)
    atomic_json(output / "targeted_discovery.json", document)
    _write_report(output / "selector_aware_fallback_report.md", document)
    _write_artifact_manifest(output)
    return document


def _write_report(path: Path, document: dict[str, Any]) -> None:
    lines = [
        "# Stage 5C.2 Selector-Aware Query Fallback Supplement",
        "",
        f"Verdict: `{document['verdict']}`",
        "",
        "This post-benchmark supplement leaves the frozen Stage 5C.2 manifest, discovery, selector decisions, selected sources, and metrics unchanged.",
        "",
        "## Decision",
        "",
        "A discovery query is successful only when the unchanged Stage 5B.3 selector accepts a candidate. A non-empty but fully vetoed Top-3 therefore advances to the next single-artist query and finally one sanitized title-only query. Query pools remain separate and native rank remains authoritative within each pool.",
        "",
        "## Targeted evidence",
        "",
    ]
    for row in document["tracks"]:
        result = row["selector_aware_result"]
        lines.extend(
            [
                f"### {row['title']}",
                "",
                f"- Historical result: `{row['historical_stage5c2']['decision']}`.",
                f"- Current result: `{result['outcome']}` via `{result['successful_query']}`.",
                f"- Selected video: `{result['selected_video_id']}` at native rank {result['selected_rank']}.",
                f"- Owner-supplied reference recovered: `{row['owner_reference_recovered']}`.",
                f"- Provider requests: {result['total_provider_requests']}.",
                "",
            ]
        )
    lines.extend(
        [
            "## Boundary",
            "",
            "This validates the repair on the two observed manual-tail cases only. It does not retroactively change Stage 5C.2 and does not establish representative title-only precision. The contract requires a fresh held-out benchmark before production activation.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_artifact_manifest(output: Path) -> None:
    paths = [
        output / "fallback_config.json",
        output / "targeted_discovery.json",
        output / "selector_aware_fallback_report.md",
    ]
    atomic_json(
        output / "artifact_manifest.json",
        {
            "schema_version": "stage5c2-selector-aware-artifact-manifest-v1",
            "experiment_id": EXPERIMENT_ID,
            "artifacts": {
                path.name: {
                    "path": str(path.relative_to(output.parents[1])),
                    "sha256": file_sha256(path),
                    "size_bytes": path.stat().st_size,
                }
                for path in paths
            },
        },
    )
