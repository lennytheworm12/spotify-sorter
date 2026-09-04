"""Deterministic curated-manifest freeze for Stage 5C.1."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b4c_artist_decomposition import (
    PRIMARY_MULTI_ARTIST,
    QUERY_CONTRACT_ID,
    build_artist_decomposition_plan,
)
from .stage5a_contract import load_contract


MANIFEST_SCHEMA_VERSION = "stage5c1-curated-manifest-v1"
EXPERIMENT_ID = "stage5c1_curated_25_materialization"
GROUPS = tuple("ABCDE")
SAFE_LABELS = frozenset({"IDEAL", "ACCEPTABLE"})


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _source(path: Path, root: Path) -> dict[str, Any]:
    if not path.is_file():
        raise Stage5B1AValidationError(f"missing frozen input: {path}")
    return {
        "path": _relative(path, root),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _v4_labels(review_path: Path) -> dict[tuple[str, str], dict[str, str]]:
    labels: dict[tuple[str, str], dict[str, str]] = {}
    with review_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row.get("candidate_review_label", "")
            if label:
                labels[(row["spotify_track_id"], row["candidate_video_id"])] = {
                    "label": label,
                    "note": row.get("candidate_note", ""),
                }
    return labels


def _historical_evidence(project_root: Path) -> dict[str, dict[str, Any]]:
    v2_path = project_root / "reports/stage5b3_minimal_selector/minimal_selector_decisions.json"
    v4_path = project_root / "reports/stage5b5_representative_v4/automated_selector_decisions.json"
    review_path = project_root / "reports/stage5b5_representative_v4/human_review.csv"
    labels = _v4_labels(review_path)
    evidence: dict[str, dict[str, Any]] = {}

    for source_stage, decision_path in (("STAGE5B3", v2_path), ("STAGE5B5_V4", v4_path)):
        payload = _json(decision_path)
        tracks = payload.get("tracks")
        if not isinstance(tracks, list):
            raise Stage5B1AValidationError(f"invalid selector decisions: {decision_path}")
        for decision in tracks:
            target = decision.get("spotify_target") or {}
            spotify_id = target.get("spotify_track_id")
            video_id = decision.get("selected_video_id")
            if not spotify_id or not video_id:
                continue
            if source_stage == "STAGE5B3":
                label = decision.get("human_label", "")
                note = "Frozen Stage 5B.2 human review carried through Stage 5B.3."
                review_source = "reports/stage5b2_youtube_prior/human_review.csv"
            else:
                review = labels.get((spotify_id, video_id), {})
                label = review.get("label", "")
                note = review.get("note", "")
                review_source = "reports/stage5b5_representative_v4/human_review.csv"
            evidence[spotify_id] = {
                "source_stage": source_stage,
                "decision_source": _relative(decision_path, project_root),
                "review_source": review_source,
                "human_label": label,
                "human_note": note,
                "decision": decision,
            }
    return evidence


def _track_from_target(target: dict[str, Any]) -> SpotifyTrack:
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": target["benchmark_id"],
            "spotify_track_id": target["spotify_track_id"],
            "title": target["title"],
            "artists": target["artists"],
            "album": target.get("album"),
            "duration_ms": target.get("duration_ms"),
            "release_year": target.get("release_year"),
            "isrc": target.get("isrc"),
        }
    )


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5C.1 manifest schema")
    tracks = manifest.get("tracks")
    if not isinstance(tracks, list) or len(tracks) != 25:
        raise Stage5B1AValidationError("Stage 5C.1 manifest must contain exactly 25 tracks")
    counts = Counter(row.get("curation_group") for row in tracks)
    if counts != Counter({group: 5 for group in GROUPS}):
        raise Stage5B1AValidationError("Stage 5C.1 manifest must contain five groups of five")
    spotify_ids = [row.get("spotify_track_id") for row in tracks]
    video_ids = [row.get("selected_youtube_video_id") for row in tracks]
    if len(set(spotify_ids)) != len(spotify_ids):
        raise Stage5B1AValidationError("curated Spotify tracks must be distinct")
    if any(not value for value in video_ids):
        raise Stage5B1AValidationError("every curated track requires a frozen YouTube ID")
    if any(row.get("human_safe_label") not in SAFE_LABELS for row in tracks):
        raise Stage5B1AValidationError("every curated source must be historically human SAFE")
    if any(row.get("discovery_mode") not in {PRIMARY_MULTI_ARTIST, "SINGLE_ARTIST_ZERO_RESULT_FALLBACK"} for row in tracks):
        raise Stage5B1AValidationError("every curated source requires query provenance")


def build_curated_manifest(
    project_root: str | Path,
    *,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    plan_path = Path(plan_path) if plan_path else root / "configs/stage5c1_curated_25.json"
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    plan = _json(plan_path)
    if plan.get("schema_version") != "stage5c1-curation-plan-v1":
        raise Stage5B1AValidationError("unexpected curation-plan schema")
    groups = plan.get("groups")
    if not isinstance(groups, dict) or tuple(groups) != GROUPS:
        raise Stage5B1AValidationError("curation plan must define ordered groups A-E")

    evidence = _historical_evidence(root)
    contract_path = root / "reports/holistic_stage4a_dual/audio_representation_v1.json"
    contract = load_contract(contract_path)
    selector_path = root / "src/audio_similarity/stage5b3_minimal_selector.py"
    decomposition_path = root / "src/audio_similarity/stage5b4c_artist_decomposition.py"
    source_paths = (
        plan_path,
        root / "reports/stage5b3_minimal_selector/minimal_selector_decisions.json",
        root / "reports/stage5b5_representative_v4/automated_selector_decisions.json",
        root / "reports/stage5b5_representative_v4/human_review.csv",
        selector_path,
        decomposition_path,
        contract_path,
    )

    output: list[dict[str, Any]] = []
    for group in GROUPS:
        group_config = groups[group]
        configured_tracks = group_config.get("tracks")
        if not isinstance(configured_tracks, list) or len(configured_tracks) != 5:
            raise Stage5B1AValidationError(f"group {group} must contain exactly five tracks")
        for position, selected in enumerate(configured_tracks, start=1):
            spotify_id = selected.get("spotify_track_id")
            historical = evidence.get(spotify_id)
            if historical is None:
                raise Stage5B1AValidationError(f"no frozen SAFE evidence for {spotify_id}")
            if historical["human_label"] not in SAFE_LABELS:
                raise Stage5B1AValidationError(f"curated source is not human SAFE: {spotify_id}")
            decision = historical["decision"]
            target = decision["spotify_target"]
            candidate = decision["selected_candidate"]
            track = _track_from_target(target)
            query_plan = build_artist_decomposition_plan(track)
            discovery_mode = decision.get("discovery_mode") or candidate.get("discovery_mode")
            if discovery_mode is None:
                if candidate.get("query") != query_plan.primary.query:
                    raise Stage5B1AValidationError(
                        f"historical query does not match frozen Q0 for {spotify_id}"
                    )
                discovery_mode = PRIMARY_MULTI_ARTIST
            output.append(
                {
                    "manifest_index": len(output) + 1,
                    "stage5c1_track_id": f"stage5c1_{group}{position:02d}",
                    "spotify_track_id": spotify_id,
                    "title": target["title"],
                    "artists": target["artists"],
                    "album": target.get("album"),
                    "spotify_duration_ms": target.get("duration_ms"),
                    "release_year": target.get("release_year"),
                    "isrc": target.get("isrc"),
                    "curation_group": group,
                    "curation_group_name": group_config["name"],
                    "curation_rationale": selected["rationale"],
                    "expected_relationship_notes": group_config["expected_relationship"],
                    "selected_youtube_video_id": decision["selected_video_id"],
                    "selected_youtube_url": f"https://www.youtube.com/watch?v={decision['selected_video_id']}",
                    "selected_candidate_rank": decision["selected_rank"],
                    "selected_candidate_metadata": {
                        "title": candidate.get("title"),
                        "uploader": candidate.get("uploader"),
                        "channel": candidate.get("channel"),
                        "duration_seconds": candidate.get("duration_seconds"),
                        "view_count": candidate.get("view_count"),
                    },
                    "discovery_mode": discovery_mode,
                    "query_variant_index": decision.get("query_variant_index", candidate.get("query_variant_index", 0)),
                    "query_artist": candidate.get("query_artist"),
                    "successful_query": decision.get("successful_query") or candidate.get("query"),
                    "frozen_primary_query": query_plan.primary.query,
                    "selector_decision_metadata": {
                        "decision": decision["decision"],
                        "selection_reason": decision["selection_reason"],
                        "candidate_evaluations": decision["candidate_evaluations"],
                    },
                    "human_safe_label": historical["human_label"],
                    "human_safe_note": historical["human_note"],
                    "historical_evidence": {
                        "source_stage": historical["source_stage"],
                        "benchmark_id": target["benchmark_id"],
                        "decision_source": historical["decision_source"],
                        "review_source": historical["review_source"],
                    },
                }
            )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "manifest_state": "FROZEN_BEFORE_AUDIO_ACQUISITION",
        "post_freeze_substitutions": 0,
        "selection_basis": "Deliberately interpretable real-library tracks with frozen human-SAFE Stage 5B selected candidates.",
        "claim_boundary": "Integration and representation sanity check; not a representative quantitative benchmark.",
        "frozen_contracts": {
            "discovery": QUERY_CONTRACT_ID,
            "selection": "STAGE5B3_MINIMAL_YOUTUBE_PRIOR_V1",
            "representation": contract.representation_version,
            "representation_artifact_sha256": contract.artifact_sha256,
            "vector_contract_sha256": contract.vector_contract_sha256,
            "segment_centers_seconds": list(contract.centers_sec),
            "segment_duration_seconds": contract.segment_duration_sec,
            "clap_weight": contract.clap_weight,
            "muq_weight": contract.muq_weight,
        },
        "curation": {
            "track_count": 25,
            "group_order": list(GROUPS),
            "tracks_per_group": 5,
            "membership_frozen_before_embedding_results": True,
            "failed_track_substitution_allowed": False,
        },
        "source_artifacts": [_source(path, root) for path in source_paths],
        "tracks": output,
    }
    validate_manifest(manifest)
    return manifest


def freeze_curated_manifest(
    project_root: str | Path,
    *,
    plan_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    root = Path(project_root).resolve()
    output = Path(output_path) if output_path else root / "reports/stage5c1_curated_25_materialization/curated_manifest.json"
    if not output.is_absolute():
        output = root / output
    manifest = build_curated_manifest(root, plan_path=plan_path)
    atomic_json(output, manifest)
    digest = file_sha256(output)
    sha_path = output.with_suffix(".sha256")
    sha_path.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    return manifest, digest


def verify_frozen_manifest(manifest_path: str | Path) -> tuple[dict[str, Any], str]:
    path = Path(manifest_path)
    manifest = _json(path)
    validate_manifest(manifest)
    digest = file_sha256(path)
    sha_path = path.with_suffix(".sha256")
    if not sha_path.is_file():
        raise Stage5B1AValidationError("missing curated manifest SHA-256 sidecar")
    expected = sha_path.read_text(encoding="ascii").split()[0]
    if digest != expected:
        raise Stage5B1AValidationError("curated manifest changed after freeze")
    return manifest, digest
