"""Collect/freeze the Spotify recipe and explicitly run only seed Batch 0001."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1b_artifacts import atomic_json
from audio_similarity.stage5d0a_catalog import allocate_catalog
from audio_similarity.stage5d0a_manifest import REPORT_DIRECTORY, freeze_catalog_and_batch_one, _write_immutable_json
from audio_similarity.stage5d0a_spotify import RECIPE, collect_catalog
from audio_similarity.stage5d0a_worker import read_json, run_worker, worker_status


def freeze_spotify_catalog(root):
    """Consume only complete checkpointed official-search metadata; no external input."""
    runtime = root / ".research_audio/stage5d0a/spotify_catalog"
    collected = read_json(runtime / "collected_cells.json")
    expected = {(year, bucket) for year in RECIPE["years"] for bucket in RECIPE["aliases"]}
    cells = collected["cells"]
    if collected["recipe"] != RECIPE or len(cells) != 216 or {(c["year"], c["bucket"]) for c in cells} != expected:
        raise ValueError("all 216 Spotify recipe cells must complete before freeze")
    page_hashes = {}
    for cell in cells:
        folder = runtime / f"{cell['year']}_{cell['bucket']}"
        if cell != read_json(folder / "cell.json"):
            raise ValueError("collected cell differs from immutable checkpoint")
        for name in cell["pages"]:
            page = folder / name
            if page.parent != folder or not page.is_file():
                raise ValueError("invalid Spotify page provenance")
            page_hashes[str(page.relative_to(runtime))] = file_sha256(page)
    report = root / REPORT_DIRECTORY
    catalog = allocate_catalog(cells)
    source = report / "spotify_catalog_allocation.json"
    _write_immutable_json(source, catalog)
    _write_immutable_json(report / "spotify_search_page_hashes.json", page_hashes)
    global_manifest, batch = freeze_catalog_and_batch_one(source, report)
    _write_immutable_json(report / "global_seed_catalog_config.json", {
        "recipe": catalog["catalog_design"], "ordering": global_manifest["ordering"],
        "spotify_search_page_count": len(page_hashes),
        "raw_selected_target": 5400, "actual_catalog_size": len(global_manifest["tracks"]),
        "global_dedupe_before_youtube": True, "automatic_next_batch": False,
        "collected_cells_sha256": file_sha256(runtime / "collected_cells.json")})
    return {"global_tracks": len(global_manifest["tracks"]), "batch_0001_tracks": len(batch["tracks"]),
            "batch_0002_started": False}


def main():
    root = Path(__file__).resolve().parents[3]
    directory = root / ".research_audio/stage5d0a/batch_0001"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["collect", "prepare", "run", "status", "stop", "resume", "report"])
    args = parser.parse_args()
    if args.command == "collect":
        cells = collect_catalog(root)
        output = {"completed_cells": len(cells), "youtube_started": False}
    elif args.command == "prepare":
        output = freeze_spotify_catalog(root)
    elif args.command in {"run", "resume"}:
        output = run_worker(root, resume=args.command == "resume")
    elif args.command == "report":
        from audio_similarity.stage5d0a_reporting import write_report
        output = write_report(root)
    elif args.command == "stop":
        atomic_json(directory / "stop.requested", {"requested_at_unix": time.time()})
        output = worker_status(directory)
    else:
        output = worker_status(directory)
        catalog = root / ".research_audio/stage5d0a/spotify_catalog"
        output["spotify_catalog_cells_completed"] = len(list(catalog.glob("*/cell.json")))
        output["spotify_catalog_cells_expected"] = 216
        output["catalog_frozen"] = (root / REPORT_DIRECTORY / "global_seed_catalog_manifest.sha256").exists()
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
