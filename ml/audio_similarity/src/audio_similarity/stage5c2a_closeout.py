"""Non-media closeout report for Stage 5C.2A persistent retention."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .stage5b1a_models import file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c2a_retention import (
    EXPERIMENT_ID,
    MEDIA_ROOT,
    REPORT_DIRECTORY,
    closeout_retention,
    validate_local_playback,
)
from .stage5c2_discovery import _json


def write_stage5c2a_closeout(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = root / REPORT_DIRECTORY
    metrics = closeout_retention(root)
    playback_path = report / "playback_validation.json"
    playback = (
        _json(playback_path)
        if playback_path.is_file()
        else validate_local_playback(root)
    )
    report_text = f"""# Stage 5C.2A — Persistent Research Audio

## Verdict

`{metrics['verdict']}`

The active input is the versioned amended Stage 5C.2 V2 corpus, not the historical 98-source execution. All acquisition consumes exact frozen YouTube IDs; discovery and selection call counts are zero.

## Corpus retention

- Expected / retained: 100 / {metrics['retained_successful']}
- Local retained bytes: {metrics['total_bytes']}
- Last-run retention cache hits: {metrics['retention_cache_hits_last_run']}
- Last-run acquisition failures: {metrics['acquisition_failures_last_run']}
- Scratch artifacts after audit: {len(metrics['scratch_artifacts'])}
- Retained media tracked by Git: {metrics['media_files_tracked_by_git']}

Full compressed source audio and per-source provenance remain under the Git-ignored `.research_audio/` cache. Temporary downloads, partials, and decode products are not retained.

## Acquisition behavior

- Live attempts: {metrics['total_live_attempts']}
- Retry attempts: {metrics['retry_attempts']}
- Minimum start spacing: {metrics['acquisition_start_spacing_seconds']['minimum']} seconds
- Required minimum: 20 seconds
- Spacing audit: {'PASS' if metrics['acquisition_start_spacing_seconds']['all_compliant'] else 'FAIL'}
- HTTP 429 / 5xx: {metrics['http_429_events']} / {metrics['http_5xx_events']}

## Representation reuse

Existing centered30_v1 CLAP and MuQ identities are linked in each provenance record. CLAP reruns: {metrics['clap_reruns']}; MuQ reruns: {metrics['muq_reruns']}.

## Local review playback

The unchanged amended queue contains {playback['review_query_count']} queries, {playback['review_directional_relationship_count']} directional relationships, and {playback['review_unique_pair_count']} unique unordered pairs. The reviewer resolves Spotify IDs through the local index and supports ordinary responses plus HTTP 206 beginning, middle, near-end, and repeated seeks. Browser validation status: `{playback['browser_validation']}`.

From `ml/audio_similarity`, run:

```bash
.venv/bin/python -m audio_similarity.cli.stage5c2_review_server
```

The default is local retained-audio playback. `--playback-source youtube` remains an explicit compatibility mode.

## Historical integrity

The original 98-track Stage 5C.2 report and amended V2 evidence are hash-guarded and were not rewritten. Existing human labels are preserved by the canonical unordered pair identifier.
"""
    (report / "stage5c2a_report.md").write_text(report_text, encoding="utf-8")
    artifact_names = (
        "retention_config.json",
        "amended_100_source_reference.json",
        "retention_results.json",
        "retention_metrics.json",
        "playback_validation.json",
        "stage5c2a_report.md",
    )
    artifact_manifest = {
        "schema_version": "stage5c2a-artifact-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "artifacts": [
            {
                "path": name,
                "sha256": file_sha256(report / name),
                "size_bytes": (report / name).stat().st_size,
                "contains_media": False,
            }
            for name in artifact_names
        ],
        "local_media_root": str(MEDIA_ROOT),
        "local_media_committed": False,
    }
    atomic_json(report / "artifact_manifest.json", artifact_manifest)
    return {
        "metrics": metrics,
        "playback": playback,
        "artifact_manifest": artifact_manifest,
    }
