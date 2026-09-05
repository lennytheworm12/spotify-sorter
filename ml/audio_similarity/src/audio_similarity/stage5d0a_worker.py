"""Single-batch durable execution. Only the worker writes queue state."""
from __future__ import annotations

import fcntl
import json
import signal
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path

from .stage5b1a_models import file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5d0a_manifest import REPORT_DIRECTORY, build_batch_manifest, _write_immutable_json
from .stage5d0a_network import ProviderGovernor, WorkerStopped, CircuitOpen

TERMINAL = {"COMPLETE", "MANUAL_TAIL", "ACQUISITION_FAILED", "MATERIALIZATION_FAILED"}
ACTIVE = {"PENDING", "DISCOVERING", "RESOLVED", "ACQUIRING", "SOURCE_RETAINED", "MATERIALIZING"}


def read_json(path):
    return json.loads(path.read_text())


def validate_freeze(root):
    report = root / REPORT_DIRECTORY
    for name in ("global_seed_catalog_manifest", "batch_0001_manifest"):
        if file_sha256(report / f"{name}.json") != (report / f"{name}.sha256").read_text().strip():
            raise ValueError(f"frozen {name} hash mismatch")
    catalog = read_json(report / "global_seed_catalog_manifest.json")
    batch = read_json(report / "batch_0001_manifest.json")
    if batch != build_batch_manifest(catalog, 1):
        raise ValueError("Batch 0001 does not match the frozen global catalog")
    if catalog["catalog_design"]["design_id"] != "POPULAR_COMMERCIAL_2000_2026_SPOTIFY_SEARCH_V1":
        raise ValueError("wrong Spotify catalog recipe")
    if not 1 <= len(batch["tracks"]) <= 500:
        raise ValueError("Batch 0001 must contain 1..500 tracks")
    return batch, file_sha256(report / "batch_0001_manifest.json")


def media_git_audit(root):
    repo = root.parents[1]
    media = root / ".research_audio"
    if media.is_symlink() or media.resolve().parent != root.resolve():
        raise ValueError("research media root must remain project-local")
    fake = root / ".research_audio/git-ignore-audit.mp3"
    subprocess.run(["git", "check-ignore", "--no-index", "--quiet", str(fake)], cwd=repo, check=True)
    tracked = subprocess.check_output(["git", "ls-files", "--", "ml/audio_similarity/.research_audio"], cwd=repo, text=True)
    if tracked.strip():
        raise ValueError("research media is tracked or staged in Git")
    return {"media_root_ignored": True, "tracked_research_files": 0}


def worker_status(directory, *, batch_number=1, network_directory=None):
    network_directory = network_directory or directory
    path = directory / "state.json"
    if not path.exists():
        return {"status": "NOT_STARTED", "batch": f"{batch_number:04d}"}
    state = read_json(path)
    network = read_json(network_directory / "network_state.json") if (network_directory / "network_state.json").exists() else {}
    results = [row.get("result", {}) for row in state["tracks"].values()]
    requests = network.get("requests", [])
    return {"batch": f"{batch_number:04d}", "status": state["status"],
            "states": dict(Counter(row["state"] for row in state["tracks"].values())),
            "requested": len(state["tracks"]), "circuit": network.get("circuit", "CLOSED"),
            "circuit_reason": network.get("circuit_reason"),
            "http_429_count": network.get("http_429_count", 0),
            "http_5xx_count": sum(500 <= (row.get("http_status") or 0) <= 599 for row in requests),
            "retries": sum(row["attempt"] > 1 for row in requests),
            "provider_warning_count": sum(len(row.get("warnings", [])) for row in requests),
            "retained_source_gb": sum(row.get("retained_bytes", 0) for row in results) / 1e9,
            "representations_complete": sum(row.get("representation_complete", False) for row in results),
            "network_jobs": len(network.get("jobs", [])),
            "last_job_start": network.get("last_job_start"),
            "next_job_earliest": max(network.get("next_job_deadline", 0), network.get("cooldown_deadline", 0)),
            "stop_requested": (network_directory / "stop.requested").exists(),
            "updated_at_unix": state["updated_at_unix"]}


def run_worker(root, *, processor_factory=None, governor_factory=ProviderGovernor, resume=False):
    """Never dispatch another batch; terminal failures require a separate future experiment."""
    from .stage5d0a_reporting import RUNNER_CONFIG
    root = Path(root).resolve()
    batch, digest = validate_freeze(root)
    _write_immutable_json(root / REPORT_DIRECTORY / "runner_config.json", RUNNER_CONFIG)
    return run_frozen_batch(root, batch, digest, root / ".research_audio/stage5d0a/batch_0001",
                            processor_factory=processor_factory, governor_factory=governor_factory, resume=resume)


def run_frozen_batch(root, batch, digest, directory, *, processor_factory=None,
                     governor_factory=ProviderGovernor, resume=False, network_directory=None):
    """Execute one already-validated frozen batch; never select another batch."""
    from .stage5d0a_processor import SeedProcessor
    root, directory = Path(root).resolve(), Path(directory).resolve()
    if not directory.is_relative_to(root / ".research_audio"):
        raise ValueError("worker state must remain under the local research root")
    ids = [row["spotify_track_id"] for row in batch["tracks"]]
    if not 1 <= len(ids) <= 500 or len(set(ids)) != len(ids):
        raise ValueError("batch must contain 1..500 distinct Spotify tracks")
    media_git_audit(root)
    media = root / ".research_audio"
    directory.mkdir(parents=True, exist_ok=True)
    network_directory = Path(network_directory or directory).resolve()
    if not network_directory.is_relative_to(media):
        raise ValueError("provider state must remain under the local research root")
    network_directory.mkdir(parents=True, exist_ok=True)
    def status():
        return worker_status(directory, batch_number=batch["batch_number"], network_directory=network_directory)
    with (media / ".retention.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another retained-media worker is active") from exc
        governor = governor_factory(network_directory)
        if resume and governor.state["circuit"] != "OPEN":
            governor.stop_path.unlink(missing_ok=True)
        governor.check()
        # Only abandoned Stage 5D scratch is disposable; never retained source folders.
        for scratch in media.glob(".stage5d-scratch-*"):
            if scratch.is_dir() and not scratch.is_symlink():
                shutil.rmtree(scratch)
        state_path = directory / "state.json"
        state = read_json(state_path) if state_path.exists() else {
            "schema_version": "stage5d0a-live-worker-v1", "batch_manifest_sha256": digest,
            "started_at_unix": time.time(), "tracks": {
                row["spotify_track_id"]: {"state": "PENDING"} for row in batch["tracks"]}}
        if state.get("batch_manifest_sha256") != digest or set(state["tracks"]) != {row["spotify_track_id"] for row in batch["tracks"]}:
            raise ValueError("runtime queue differs from frozen batch")
        if state.get("schema_version") != "stage5d0a-live-worker-v1" or any(row.get("state") not in TERMINAL | ACTIVE for row in state["tracks"].values()):
            raise ValueError("invalid persistent queue state")

        def save():
            state["updated_at_unix"] = time.time()
            atomic_json(state_path, state)

        def stop_signal(_signum, _frame):
            atomic_json(governor.stop_path, {"requested_at_unix": time.time()})

        old_handlers = {sig: signal.signal(sig, stop_signal) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            state["status"] = "RUNNING"
            save()
            processor = (processor_factory or SeedProcessor)(root, directory, governor)
            for track in batch["tracks"]:
                governor.check()
                spotify_id = track["spotify_track_id"]
                row = state["tracks"][spotify_id]
                if row["state"] in TERMINAL and row["state"] != "COMPLETE":
                    continue
                inspected = processor.inspect(track)
                if row.get("selected_video_id") and (inspected.get("selection") or {}).get("youtube_video_id") != row["selected_video_id"]:
                    raise ValueError("resumed source differs from durable selection checkpoint")
                if row["state"] == "COMPLETE":
                    if inspected["source"] is not None and inspected["representation"] is not None:
                        continue
                    # A completed queue marker is not a substitute for actual cache integrity.
                    row["state"] = "RESOLVED"
                    save()
                cache_state = {
                    "source": inspected["source"] is not None,
                    "representation": inspected["representation"] is not None}
                if "initial_cache_state" in row:
                    row["resume_cache_state"] = cache_state
                else:
                    row["initial_cache_state"] = cache_state
                save()
                if inspected["network_required"]:
                    governor.start_job(spotify_id)

                def checkpoint(stage, **details):
                    row.update(state=stage, **details)
                    save()

                outcome = processor.process(track, inspected, checkpoint)
                if outcome["state"] not in TERMINAL:
                    raise ValueError("processor returned non-terminal outcome")
                row.update(outcome)
                save()
                governor.finish_job(success=outcome["state"] == "COMPLETE")
                print(json.dumps(status(), sort_keys=True), flush=True)
            state["status"] = "FINISHED"
        except CircuitOpen as exc:
            state.update(status="CIRCUIT_STOPPED", stop_reason=str(exc))
        except WorkerStopped as exc:
            state.update(status="STOPPED", stop_reason=str(exc))
        except Exception as exc:
            state.update(status="PIPELINE_STOPPED", stop_reason=f"{type(exc).__name__}: {exc}"[:2000])
            raise
        finally:
            save()
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
            media_git_audit(root)
    return status()
