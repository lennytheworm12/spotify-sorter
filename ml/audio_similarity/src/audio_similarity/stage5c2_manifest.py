"""Deterministic fresh representative manifest for Stage 5C.2."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .stage5a_contract import load_contract
from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b3_minimal_selector import EXPERIMENT_ID as SELECTOR_ID
from .stage5b4c_artist_decomposition import QUERY_CONTRACT_ID
from .stage5b5_representative_v4 import historical_json_paths
from .stage5b_representative_library import (
    build_benchmark_manifest,
    historical_exclusion_identities,
    load_library_snapshot,
    track_identities,
)


EXPERIMENT_ID = "stage5c2_representative_100"
MANIFEST_SCHEMA_VERSION = "stage5c2-representative-100-manifest-v1"
SAMPLE_SIZE = 100
SAMPLE_SEED = "stage5c2-representative-100-seed-2026-09-04"
REPORT_DIRECTORY = "reports/stage5c2_representative_100"


def _source(path: Path, root: Path) -> dict[str, Any]:
    if not path.is_file():
        raise Stage5B1AValidationError(f"missing frozen input: {path}")
    return {
        "path": str(path.resolve().relative_to(root.resolve())),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def stage5c2_exclusion_paths(project_root: str | Path) -> tuple[Path, ...]:
    root = Path(project_root).resolve()
    return (
        *historical_json_paths(root),
        root / "reports/stage5b5_representative_v4/benchmark_manifest.json",
        root / "reports/stage5c1_curated_25_materialization/curated_manifest.json",
    )


def _validate_contracts(root: Path) -> dict[str, Any]:
    v4_config = root / "reports/stage5b5_representative_v4/benchmark_config.json"
    c1_manifest = root / "reports/stage5c1_curated_25_materialization/curated_manifest.json"
    c1_digest = c1_manifest.with_suffix(".sha256")
    selector = root / "src/audio_similarity/stage5b3_minimal_selector.py"
    query = root / "src/audio_similarity/stage5b4a_query_contract_repair.py"
    decomposition = root / "src/audio_similarity/stage5b4c_artist_decomposition.py"
    representation = root / "reports/holistic_stage4a_dual/audio_representation_v1.json"
    required = (
        v4_config,
        c1_manifest,
        c1_digest,
        selector,
        query,
        decomposition,
        representation,
    )
    if not all(path.is_file() for path in required):
        raise Stage5B1AValidationError("Stage 5C.2 frozen-history guard is incomplete")
    v4 = json.loads(v4_config.read_text(encoding="utf-8"))
    if v4.get("scope_guards", {}).get("production_activation") is not False:
        raise Stage5B1AValidationError("Stage 5B production activation guard changed")
    if (
        v4.get("contracts", {}).get("discovery", {}).get("contract_id")
        != QUERY_CONTRACT_ID
    ):
        raise Stage5B1AValidationError("Stage 5B discovery contract changed")
    if v4.get("contracts", {}).get("selection", {}).get("selector_id") != SELECTOR_ID:
        raise Stage5B1AValidationError("Stage 5B selector contract changed")
    expected_c1 = c1_digest.read_text(encoding="utf-8").split()[0]
    if file_sha256(c1_manifest) != expected_c1:
        raise Stage5B1AValidationError("Stage 5C.1 manifest identity changed")
    contract = load_contract(representation)
    return {
        "discovery_contract_id": QUERY_CONTRACT_ID,
        "selector_id": SELECTOR_ID,
        "discovery_query_source": _source(query, root),
        "decomposition_source": _source(decomposition, root),
        "selector_source": _source(selector, root),
        "representation_artifact": _source(representation, root),
        "representation_artifact_sha256": contract.artifact_sha256,
        "vector_contract_sha256": contract.vector_contract_sha256,
        "stage5b5_config": _source(v4_config, root),
        "stage5c1_manifest": _source(c1_manifest, root),
        "production_activation": False,
    }


def validate_manifest(value: dict[str, Any]) -> None:
    tracks = value.get("tracks")
    if (
        value.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or value.get("experiment_id") != EXPERIMENT_ID
        or value.get("sampled_track_count") != SAMPLE_SIZE
        or not isinstance(tracks, list)
        or len(tracks) != SAMPLE_SIZE
        or value.get("post_freeze_substitutions") != 0
    ):
        raise Stage5B1AValidationError("invalid Stage 5C.2 representative manifest")
    ids = [row.get("spotify_track_id") for row in tracks]
    if any(not isinstance(track_id, str) or not track_id for track_id in ids):
        raise Stage5B1AValidationError("Stage 5C.2 tracks require Spotify IDs")
    if len(set(ids)) != SAMPLE_SIZE:
        raise Stage5B1AValidationError("Stage 5C.2 manifest contains duplicate Spotify IDs")
    if [row.get("stage5c2_track_id") for row in tracks] != [
        f"stage5c2_{index:03d}" for index in range(1, SAMPLE_SIZE + 1)
    ]:
        raise Stage5B1AValidationError("Stage 5C.2 manifest order identity changed")


def freeze_representative_manifest(
    project_root: str | Path,
    snapshot_path: str | Path | None = None,
    report_dir: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    root = Path(project_root).resolve()
    snapshot = Path(snapshot_path).resolve() if snapshot_path else (
        root / "reports/stage5b_representative_library_v1/library_snapshot.private.json"
    )
    report = Path(report_dir).resolve() if report_dir else root / REPORT_DIRECTORY
    contracts = _validate_contracts(root)
    exclusions = stage5c2_exclusion_paths(root)
    if not snapshot.is_file() or not all(path.is_file() for path in exclusions):
        raise Stage5B1AValidationError("Stage 5C.2 source/exclusion evidence is incomplete")
    library = load_library_snapshot(snapshot)
    excluded, provenance = historical_exclusion_identities(exclusions)
    generated = build_benchmark_manifest(
        library,
        excluded,
        sample_size=SAMPLE_SIZE,
        seed=SAMPLE_SEED,
        snapshot_sha256=file_sha256(snapshot),
        exclusion_provenance=provenance,
    )
    if generated["sampled_track_count"] != SAMPLE_SIZE:
        raise Stage5B1AValidationError(
            f"Stage 5C.2 requires 100 fresh tracks; {generated['sampled_track_count']} available"
        )
    tracks = [
        row | {
            "stage5c2_track_id": f"stage5c2_{index:03d}",
            "manifest_index": index,
        }
        for index, row in enumerate(generated["tracks"], start=1)
    ]
    tracks_by_spotify_id = {item.track.spotify_track_id: item.track for item in library}
    selected_identities = {
        identity
        for row in tracks
        for identity in track_identities(tracks_by_spotify_id[row["spotify_track_id"]])
    }
    if selected_identities & excluded:
        raise Stage5B1AValidationError("Stage 5C.2 selection overlaps historical evidence")
    manifest = generated | {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "benchmark_id": "STAGE5C2_REPRESENTATIVE_100",
        "sample_seed": SAMPLE_SEED,
        "freshness_scope": "EXCLUDES_STAGE5B_HISTORY_V4_AND_STAGE5C1",
        "frozen_contracts": contracts,
        "source_artifacts": [
            _source(snapshot, root),
            *[_source(path, root) for path in exclusions],
        ],
        "tracks": tracks,
    }
    validate_manifest(manifest)
    report.mkdir(parents=True, exist_ok=True)
    path = report / "representative_manifest.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != manifest:
        raise Stage5B1AValidationError("refusing to replace frozen Stage 5C.2 manifest")
    if not path.exists():
        atomic_json(path, manifest)
    digest = file_sha256(path)
    digest_path = report / "representative_manifest.sha256"
    if digest_path.exists() and digest_path.read_text(encoding="utf-8").strip() != digest:
        raise Stage5B1AValidationError("Stage 5C.2 manifest digest lock changed")
    if not digest_path.exists():
        digest_path.write_text(digest + "\n", encoding="utf-8")
    return manifest, digest


def verify_frozen_manifest(path: str | Path) -> tuple[dict[str, Any], str]:
    manifest_path = Path(path).resolve()
    digest_path = manifest_path.with_suffix(".sha256")
    expected = digest_path.read_text(encoding="utf-8").strip()
    actual = file_sha256(manifest_path)
    if actual != expected:
        raise Stage5B1AValidationError("Stage 5C.2 representative manifest changed")
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(value)
    return value, actual
