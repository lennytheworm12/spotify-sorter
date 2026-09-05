"""Freeze and explicitly execute one chart-derived research download batch."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from pathlib import Path

from .stage5b1a_models import SpotifyTrack, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5d0a_manifest import document_sha256, _write_immutable_json
from .stage5d0a_network import CircuitOpen, ProviderGovernor
from .stage5d0a_reporting import RUNNER_CONFIG
from .stage5d0a_worker import read_json, run_frozen_batch, worker_status, media_git_audit

REPORT = "reports/chart_download_batches_v1"
RUNTIME = ".research_audio/chart_download_batches_v1"
SEED = "chart-popular-download-order-v1"
DEFAULT_SNAPSHOT = (
    "reports/stage5d_chart_catalog_v1/"
    "matching_16f0ff2b91ea073f73ef099769b6f8b8104c15a4c8225b10d793ee32517c4266.json"
)
SCHEMA = "chart-download-cohort-v1"


def build_cohort(snapshot, snapshot_sha256, *, batch_size=500):
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch size must be 1..500")
    if snapshot.get("metrics", {}).get("catalog_id") != "CHART_ANCHORED_2006_2026_METADATA_V1":
        raise ValueError("not a chart-based matching snapshot")
    matches = {m["song"]["song_key"]: m for m in snapshot["matches"]}
    rows = []
    for recording in snapshot["recordings"]:
        raw = recording["spotify"]
        if not re.fullmatch(r"[A-Za-z0-9]{22}", raw.get("id", "")):
            raise ValueError("invalid Spotify ID")
        for key in recording["song_keys"]:
            match = matches.get(key, {})
            if match.get("status") != "MATCHED_METADATA" or match.get("spotify", {}).get("id") not in recording["spotify_ids"]:
                raise ValueError("recording includes unmatched or ambiguous evidence")
        if not recording["song_keys"] or not recording.get("appearances"):
            raise ValueError("chart popularity provenance missing")
        if not any(raw == matches[key]["spotify"] for key in recording["song_keys"]):
            raise ValueError("recording metadata differs from accepted matching evidence")
        date = (raw.get("album") or {}).get("release_date", "")
        row = {"spotify_track_id": raw["id"], "title": raw["name"],
               "artists": [a["name"] for a in raw["artists"]],
               "album": (raw.get("album") or {}).get("name"),
               "duration_ms": raw["duration_ms"],
               "release_year": int(date[:4]) if re.match(r"^\d{4}", date) else None,
               "isrc": (raw.get("external_ids") or {}).get("isrc"),
               "chart_appearances": recording["appearances"],
               "metadata_match_status": "MATCHED_METADATA_NOT_YOUTUBE_VALIDATED"}
        SpotifyTrack.from_dict({"stable_track_id": raw["id"], **row})
        rows.append(row)
    if not rows or len({r["spotify_track_id"] for r in rows}) != len(rows):
        raise ValueError("cohort is empty or contains duplicate Spotify IDs")
    rows.sort(key=lambda row: (document_sha256({"seed": SEED, "id": row["spotify_track_id"]}), row["spotify_track_id"]))
    for index, row in enumerate(rows):
        # Compatibility field consumed by the shared processor, not a genre-catalog identity.
        row.update(stage5d0a_track_id=f"chart_v1_{index + 1:06d}",
                   batch_number=index // batch_size + 1, batch_position=index % batch_size + 1)
    return {"schema_version": SCHEMA, "source_snapshot_sha256": snapshot_sha256,
            "ordering_seed": SEED, "batch_size": batch_size,
            "batch_count": (len(rows) + batch_size - 1) // batch_size,
            "track_count": len(rows), "tracks": rows, "automatic_next_batch": False,
            "scope": "matched subset only; full chart catalog remains unfinished",
            "unmatched_pending_excluded": snapshot["metrics"].get("matching_outcomes", {}),
            "runner_config": RUNNER_CONFIG}


def batch_document(cohort, number):
    if type(number) is not int or not 1 <= number <= cohort["batch_count"]:
        raise ValueError("batch does not exist")
    tracks = [t for t in cohort["tracks"] if t["batch_number"] == number]
    return {"schema_version": "chart-download-batch-v1", "batch_number": number,
            "cohort_sha256": document_sha256(cohort), "automatic_next_batch": False,
            "requested_track_count": len(tracks), "tracks": tracks}


def freeze(root, source, *, batch_size=500):
    source = Path(source).resolve()
    if not source.is_relative_to(root / "reports/stage5d_chart_catalog_v1"):
        raise ValueError("source must be a versioned chart matching report")
    snapshot = read_json(source)
    cohort = build_cohort(snapshot, file_sha256(source), batch_size=batch_size)
    report = root / REPORT
    reference = {"source_path": str(source.relative_to(root)), "source_sha256": file_sha256(source)}
    _write_immutable_json(report / "source_reference.json", reference)
    _write_immutable_json(report / "cohort.json", cohort)
    for number in range(1, cohort["batch_count"] + 1):
        _write_immutable_json(report / f"batch_{number:04d}.json", batch_document(cohort, number))
    _write_immutable_json(report / "artifact_manifest.json", {
        p.name: file_sha256(p) for p in sorted(report.glob("*.json")) if p.name != "artifact_manifest.json"})
    return {"tracks": cohort["track_count"], "batch_sizes": [len(batch_document(cohort, n)["tracks"]) for n in range(1, cohort["batch_count"] + 1)],
            "downloads_started": False}


def validate_batch(root, number):
    report = root / REPORT
    hashes = read_json(report / "artifact_manifest.json")
    if not {"cohort.json", "source_reference.json", f"batch_{number:04d}.json"} <= hashes.keys():
        raise ValueError("frozen chart cohort hash inventory is incomplete")
    for name, expected in hashes.items():
        if Path(name).name != name or file_sha256(report / name) != expected:
            raise ValueError("frozen chart cohort artifact hash mismatch")
    ref = read_json(report / "source_reference.json")
    source = (root / ref["source_path"]).resolve()
    if not source.is_relative_to(root / "reports/stage5d_chart_catalog_v1") or file_sha256(source) != ref["source_sha256"]:
        raise ValueError("chart matching input changed")
    cohort = read_json(report / "cohort.json")
    if cohort != build_cohort(read_json(source), ref["source_sha256"], batch_size=cohort["batch_size"]):
        raise ValueError("cohort differs from chart snapshot")
    path = report / f"batch_{number:04d}.json"
    batch = batch_document(cohort, number)
    if read_json(path) != batch:
        raise ValueError("batch membership changed")
    return batch, file_sha256(path)


def run(root, number, *, resume=False, **worker_options):
    batch, digest = validate_batch(root, number)
    old_network = root / ".research_audio/stage5d0a/batch_0001/network_state.json"
    if old_network.exists() and read_json(old_network).get("circuit") == "OPEN":
        raise CircuitOpen("original seed worker circuit is open; do not switch catalogs to bypass it")
    directory = root / RUNTIME / f"batch_{number:04d}"
    network = root / RUNTIME / "provider"
    if "governor_factory" not in worker_options:
        def governor_factory(path):
            governor = ProviderGovernor(path)
            if old_network.exists() and read_json(old_network).get("circuit") == "OPEN":
                raise CircuitOpen("original seed worker circuit is open")
            # Carry old provider safety state forward once, without modifying it.
            if not governor.path.exists() and old_network.exists():
                previous = read_json(old_network)
                for key in ("next_job_deadline", "next_request_deadline", "cooldown_deadline",
                            "last_job_start", "last_media_start", "http_429_count",
                            "challenge_tracks", "degraded_tracks"):
                    if key in previous:
                        governor.state[key] = previous[key]
                governor.save()
            return governor
        worker_options["governor_factory"] = governor_factory
    return run_frozen_batch(root, batch, digest, directory, resume=resume,
                            network_directory=network, **worker_options)


def preflight(root, number):
    """Offline readiness checks only; no discovery, downloads, or encoder inference."""
    from .stage5a_contract import load_contract
    from .stage5c1_pipeline import verify_model_files
    batch, digest = validate_batch(root, number)
    audit = media_git_audit(root)
    for command in ("ffmpeg", "ffprobe"):
        if not shutil.which(command):
            raise ValueError(f"{command} is missing")
    contract = load_contract(root / "reports/holistic_stage4a_dual/audio_representation_v1.json")
    verify_model_files(root, contract)
    return {"offline_preflight": "PASS", "batch": f"{number:04d}",
            "tracks": len(batch["tracks"]), "batch_sha256": digest,
            "model_checkpoint_hashes_verified": True,
            "free_disk_gb": round(shutil.disk_usage(root).free / 1e9, 2),
            "network_requests": 0, "encoder_inference": 0, **audit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "preflight", "run", "resume", "status", "stop"])
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=500, help="prepare only; immutable afterward")
    parser.add_argument("--snapshot", type=Path, default=Path(DEFAULT_SNAPSHOT))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.batch < 1:
        parser.error("batch must be positive")
    if args.command != "prepare" and (args.batch_size != 500 or args.snapshot != Path(DEFAULT_SNAPSHOT)):
        parser.error("snapshot and batch-size are prepare-only; existing batches cannot change at run time")
    if args.command == "prepare":
        media_git_audit(root)
        output = freeze(root, root / args.snapshot, batch_size=args.batch_size)
    elif args.command in {"run", "resume"}:
        output = run(root, args.batch, resume=args.command == "resume")
    elif args.command == "preflight":
        output = preflight(root, args.batch)
    else:
        batch, _ = validate_batch(root, args.batch)
        directory = root / RUNTIME / f"batch_{args.batch:04d}"
        network = root / RUNTIME / "provider"
        if args.command == "stop":
            atomic_json(network / "stop.requested", {"requested_at_unix": time.time()})
        output = worker_status(directory, batch_number=args.batch, network_directory=network)
        output["requested"] = len(batch["tracks"])
        if output["status"] == "NOT_STARTED":
            output["states"] = {"PENDING": len(batch["tracks"])}
        output["provider_metrics_scope"] = "all chart batches; circuit and cooldown persist across batches"
        output["automatic_next_batch"] = False
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
