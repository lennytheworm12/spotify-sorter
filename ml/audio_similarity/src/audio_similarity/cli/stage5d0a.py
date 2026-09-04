"""Prepare and control the resumable Stage 5D.0A Batch 0001 worker."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b1b_artifacts import atomic_json
from audio_similarity.stage5d0a_control import (
    initial_runtime_state,
    persist_runtime_state,
    request_graceful_stop,
    request_resume,
    runtime_status,
)
from audio_similarity.stage5d0a_manifest import (
    ORDERING_SEED,
    REPORT_DIRECTORY,
    freeze_catalog_and_batch_one,
)


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    report = project_root / REPORT_DIRECTORY
    runtime_path = project_root / ".research_audio/stage5d0a/batch_0001_state.json"
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--catalog-input", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("stop")
    subparsers.add_parser("resume")
    args = parser.parse_args()

    try:
        if args.command == "prepare":
            source = Path(args.catalog_input).resolve()
            global_manifest, batch = freeze_catalog_and_batch_one(source, report)
            config = {
                "schema_version": "stage5d0a-global-seed-catalog-config-v1",
                "experiment_id": "STAGE5D0A_COMMERCIAL_SEED_BATCH_0001",
                "catalog_input_name": source.name,
                "catalog_input_sha256": file_sha256(source),
                "catalog_design": global_manifest["catalog_design"],
                "ordering_seed": ORDERING_SEED,
                "batch_size": 500,
                "automatic_next_batch": False,
            }
            config_path = report / "global_seed_catalog_config.json"
            if config_path.is_file() and _json(config_path) != config:
                raise Stage5B1AValidationError(
                    "refusing to replace frozen Stage 5D catalog config"
                )
            if not config_path.is_file():
                atomic_json(config_path, config)
            if runtime_path.is_file():
                state = _json(runtime_path)
                if state.get("batch_manifest_sha256") != file_sha256(
                    report / "batch_0001_manifest.json"
                ):
                    raise Stage5B1AValidationError(
                        "runtime state does not match frozen Batch 0001"
                    )
            else:
                state = initial_runtime_state(batch)
                runtime_path.parent.mkdir(parents=True, exist_ok=True)
                persist_runtime_state(runtime_path, state)
            output = {
                "global_track_count": global_manifest["unique_track_count"],
                "batch_0001_track_count": len(batch["tracks"]),
                "runtime_path": str(runtime_path),
                "batch_0002_started": False,
            }
        else:
            if not runtime_path.is_file():
                raise Stage5B1AValidationError("Stage 5D.0A has not been prepared")
            state = (
                request_graceful_stop(runtime_path)
                if args.command == "stop"
                else request_resume(runtime_path)
                if args.command == "resume"
                else _json(runtime_path)
            )
            output = runtime_status(state)
    except (FileNotFoundError, json.JSONDecodeError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
