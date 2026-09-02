"""Frozen fresh-challenge orchestration for Stage 5B.1B Part C."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .stage5b1a2_config import Stage5B1A2Config, load_ytdlp_config
from .stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpSearchError
from .stage5b1a_discovery import build_search_query
from .stage5b1a_models import (
    FeasibilityTrack,
    Stage5B1AValidationError,
    file_sha256,
)
from .stage5b1b_artifacts import atomic_json, materialize_features
from .stage5b1b_identity import normalize_text
from .stage5b1b_resolver import (
    AUTO_MATCH,
    DurationBoundaries,
    PolicySpec,
    policy_variants,
    resolve_dataset,
)


CONFIG_SCHEMA_VERSION = "stage5b1b-fresh-challenge-config-v1"
MANIFEST_SCHEMA_VERSION = "stage5b1b-fresh-challenge-track-manifest-v1"
POLICY_BUNDLE_SCHEMA_VERSION = "stage5b1b-fresh-challenge-policy-bundle-v1"
EXPERIMENT_ID = "stage5b1b_fresh_challenge_validation_v1"
DISCOVERY_SCHEMA_VERSION = "stage5b1b-fresh-challenge-discovery-v1"
DECISIONS_SCHEMA_VERSION = "stage5b1b-fresh-challenge-policy-decisions-v1"
POLICY_IDS = ("POLICY_CONSERVATIVE_V1", "POLICY_BALANCED_V1")
TRACK_COUNT = 50


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage5B1AValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _inside(root: Path, value: Any, name: str) -> Path:
    path = (root / _text(value, name)).resolve()
    if not path.is_relative_to(root):
        raise Stage5B1AValidationError(f"{name} must remain within project root")
    return path


@dataclass(frozen=True)
class ChallengeManifest:
    path: Path
    sha256: str
    tracks: tuple[FeasibilityTrack, ...]
    purpose: str

    @property
    def stable_track_ids(self) -> tuple[str, ...]:
        return tuple(row.track.stable_track_id for row in self.tracks)


@dataclass(frozen=True)
class ChallengeConfig:
    path: Path
    sha256: str
    root: Path
    starting_commit: str
    policy_bundle_path: Path
    policy_bundle_sha256: str
    manifest_path: Path
    manifest_sha256: str
    dev_manifest_path: Path
    dev_manifest_sha256: str
    calibration_manifest_path: Path
    calibration_manifest_sha256: str
    discovery: Stage5B1A2Config
    evaluator: dict[str, Any]
    audit: dict[str, Any]
    artifacts: dict[str, Path]


def _bound_artifact(root: Path, raw: Any, name: str) -> tuple[Path, str]:
    if not isinstance(raw, dict) or set(raw) != {"path", "sha256"}:
        raise Stage5B1AValidationError(f"{name} must bind path and sha256")
    path = _inside(root, raw["path"], f"{name}.path")
    expected = _text(raw["sha256"], f"{name}.sha256")
    if len(expected) != 64 or file_sha256(path) != expected:
        raise Stage5B1AValidationError(f"frozen artifact changed: {name}")
    return path, expected


def load_challenge_config(path: str | Path) -> ChallengeConfig:
    config_path = Path(path).resolve()
    raw = _json_object(config_path)
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION or raw.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected fresh-challenge config identity")
    if raw.get("production_auto_match_activated") is not False:
        raise Stage5B1AValidationError("fresh challenge cannot activate production AUTO_MATCH")
    root = config_path.parent.parent.resolve()
    inputs = raw.get("inputs")
    evaluator = raw.get("evaluator")
    audit = raw.get("audit")
    artifacts = raw.get("artifacts")
    if not all(isinstance(value, dict) for value in (inputs, evaluator, audit, artifacts)):
        raise Stage5B1AValidationError("fresh-challenge config sections must be objects")
    policy_path, policy_sha = _bound_artifact(root, inputs.get("policy_bundle"), "policy_bundle")
    manifest_path, manifest_sha = _bound_artifact(root, inputs.get("challenge_manifest"), "challenge_manifest")
    dev_path, dev_sha = _bound_artifact(root, inputs.get("dev_manifest"), "dev_manifest")
    calibration_path, calibration_sha = _bound_artifact(
        root, inputs.get("calibration_manifest"), "calibration_manifest"
    )
    discovery_path, _ = _bound_artifact(root, inputs.get("discovery_config"), "discovery_config")
    if evaluator.get("model") != "gpt-5.6-sol" or evaluator.get("reasoning_effort") != "high":
        raise Stage5B1AValidationError("fresh challenge requires gpt-5.6-sol with high reasoning")
    if any(evaluator.get(key) is not True for key in ("isolated_working_directory", "ignore_user_config", "ignore_rules")):
        raise Stage5B1AValidationError("Sol isolation settings changed")
    if evaluator.get("tools_allowed") is not False:
        raise Stage5B1AValidationError("blinded Sol evaluator cannot use tools")
    _bound_artifact(root, evaluator.get("prompt"), "evaluator.prompt")
    _bound_artifact(root, evaluator.get("output_schema"), "evaluator.output_schema")
    fraction = audit.get("random_agreement_fraction")
    minimum = audit.get("minimum_conservative_random_tracks")
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not 0 < fraction <= 1:
        raise Stage5B1AValidationError("random agreement fraction must be in (0, 1]")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
        raise Stage5B1AValidationError("minimum conservative audit count must be positive")
    required_artifacts = {
        "discovery", "features", "policy_decisions", "blinded_sol_input",
        "blinded_sol_private_mapping", "sol_contract", "sol_evaluations",
        "comparison", "audit_queue", "human_review", "run_status", "report",
    }
    if set(artifacts) != required_artifacts:
        raise Stage5B1AValidationError("fresh-challenge artifact paths are incomplete")
    return ChallengeConfig(
        path=config_path,
        sha256=file_sha256(config_path),
        root=root,
        starting_commit=_text(raw.get("starting_commit"), "starting_commit"),
        policy_bundle_path=policy_path,
        policy_bundle_sha256=policy_sha,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        dev_manifest_path=dev_path,
        dev_manifest_sha256=dev_sha,
        calibration_manifest_path=calibration_path,
        calibration_manifest_sha256=calibration_sha,
        discovery=load_ytdlp_config(discovery_path),
        evaluator=evaluator,
        audit=audit,
        artifacts={key: _inside(root, value, f"artifacts.{key}") for key, value in artifacts.items()},
    )


def load_challenge_manifest(path: str | Path, *, expected_sha256: str) -> ChallengeManifest:
    manifest_path = Path(path)
    if file_sha256(manifest_path) != expected_sha256:
        raise Stage5B1AValidationError("fresh challenge manifest hash changed")
    raw = _json_object(manifest_path)
    if raw.get("schema_version") != MANIFEST_SCHEMA_VERSION or raw.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected fresh challenge manifest identity")
    if raw.get("frozen_before_discovery") is not True or raw.get("frozen_before_policy_execution") is not True:
        raise Stage5B1AValidationError("fresh manifest was not frozen before evaluation")
    rows = raw.get("tracks")
    if not isinstance(rows, list) or len(rows) != TRACK_COUNT:
        raise Stage5B1AValidationError(f"fresh challenge must contain exactly {TRACK_COUNT} tracks")
    tracks = tuple(FeasibilityTrack.from_dict(row) for row in rows)
    ids = [row.track.stable_track_id for row in tracks]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise Stage5B1AValidationError("fresh challenge track IDs must be unique and sorted")
    if any(row.track.duration_ms is None or row.track.release_year is None for row in tracks):
        raise Stage5B1AValidationError("fresh challenge requires target duration and release year")
    return ChallengeManifest(
        path=manifest_path,
        sha256=expected_sha256,
        tracks=tracks,
        purpose=_text(raw.get("purpose"), "purpose"),
    )


def _manifest_identities(path: Path) -> set[tuple[str, str]]:
    rows = _json_object(path).get("tracks")
    if not isinstance(rows, list):
        raise Stage5B1AValidationError(f"manifest tracks missing: {path}")
    return {
        (normalize_text(row["track"]["title"]), normalize_text(row["track"]["artists"][0]))
        for row in rows
    }


def verify_non_overlap(config: ChallengeConfig, manifest: ChallengeManifest) -> dict[str, Any]:
    fresh = {
        (normalize_text(row.track.title), normalize_text(row.track.artists[0]))
        for row in manifest.tracks
    }
    dev = _manifest_identities(config.dev_manifest_path)
    calibration = _manifest_identities(config.calibration_manifest_path)
    overlap_dev = sorted(fresh & dev)
    overlap_calibration = sorted(fresh & calibration)
    if overlap_dev or overlap_calibration:
        raise Stage5B1AValidationError("fresh challenge overlaps prior DEV/calibration tracks")
    return {
        "fresh_track_count": len(fresh),
        "dev_track_count": len(dev),
        "calibration_track_count": len(calibration),
        "dev_overlap": overlap_dev,
        "calibration_overlap": overlap_calibration,
    }


def load_frozen_policies(config: ChallengeConfig) -> tuple[DurationBoundaries, dict[str, PolicySpec]]:
    if file_sha256(config.policy_bundle_path) != config.policy_bundle_sha256:
        raise Stage5B1AValidationError("frozen policy bundle hash changed")
    raw = _json_object(config.policy_bundle_path)
    if raw.get("schema_version") != POLICY_BUNDLE_SCHEMA_VERSION or raw.get("frozen_before_challenge_manifest") is not True:
        raise Stage5B1AValidationError("invalid frozen policy bundle")
    boundaries = DurationBoundaries(**raw["duration_boundaries"])
    policies = {policy_id: PolicySpec(**raw["policies"][policy_id]) for policy_id in POLICY_IDS}
    implementation = {spec.policy_id: asdict(spec) for spec in policy_variants() if spec.policy_id in POLICY_IDS}
    if {key: asdict(value) for key, value in policies.items()} != implementation:
        raise Stage5B1AValidationError("runtime policy implementation diverges from frozen bundle")
    if file_sha256(config.root / "src/audio_similarity/stage5b1b_resolver.py") != raw["source_artifacts"]["resolver_implementation"]["sha256"]:
        raise Stage5B1AValidationError("frozen resolver implementation changed")
    return boundaries, policies


def run_discovery(
    config: ChallengeConfig,
    manifest: ChallengeManifest,
    adapter: YtDlpDiscoveryAdapter,
    *,
    clock: Callable[[], str] = _utc_now,
    timer: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    started_at, started = clock(), timer()
    rows: list[dict[str, Any]] = []
    provider = config.discovery.provider
    for index, item in enumerate(manifest.tracks):
        requested_at = clock()
        try:
            row = adapter.discover(item.track, limit=provider.candidate_limit).to_dict()
        except YtDlpSearchError as exc:
            query = build_search_query(item.track, config.discovery.query)
            row = {
                "track": item.track.to_dict(),
                "query": query,
                "request": {
                    "search_expression": provider.search_expression(query),
                    "options": provider.metadata_only_options(),
                    "download": False,
                },
                "provider": {"name": "yt_dlp", "version": adapter.backend.version, "attempts": exc.attempts},
                "normalized_results": [], "candidates": [], "candidate_video_ids": [],
                "warnings": list(exc.warnings), "error": exc.to_dict(),
            }
        row.update({
            "case_tags": list(item.case_tags),
            "case_rationale": item.case_rationale,
            "requested_at_utc": requested_at,
            "completed_at_utc": clock(),
        })
        rows.append(row)
        if index + 1 < len(manifest.tracks):
            sleeper(provider.sleep_between_tracks_seconds)
    result = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "status": "DISCOVERY_COMPLETE",
        "manifest_sha256": manifest.sha256,
        "config_sha256": config.sha256,
        "query": {"variant_id": config.discovery.query.variant_id, "template": config.discovery.query.template},
        "provider": {
            "name": "yt_dlp", "version": adapter.backend.version,
            "search_prefix": provider.search_prefix, "candidate_limit": provider.candidate_limit,
            "metadata_only_options": provider.metadata_only_options(), "sequential": True,
            "sleep_between_tracks_seconds": provider.sleep_between_tracks_seconds,
        },
        "started_at_utc": started_at,
        "completed_at_utc": clock(),
        "elapsed_wall_seconds": max(0.0, timer() - started),
        "media_activity": {"audio_downloads": 0, "video_downloads": 0, "stage5a_calls": 0, "clap_calls": 0, "muq_calls": 0},
        "tracks": rows,
    }
    result["summary"] = {
        "tracks": len(rows),
        "tracks_with_candidates": sum(bool(row["candidates"]) for row in rows),
        "zero_candidate_tracks": sum(not row["candidates"] for row in rows),
        "search_failures": sum(row["error"] is not None for row in rows),
        "candidate_count": sum(len(row["candidates"]) for row in rows),
        "tracks_with_warnings": sum(bool(row["warnings"]) for row in rows),
        "warning_count": sum(len(row["warnings"]) for row in rows),
    }
    return result


def load_discovery(config: ChallengeConfig, manifest: ChallengeManifest) -> dict[str, Any]:
    raw = _json_object(config.artifacts["discovery"])
    if raw.get("schema_version") != DISCOVERY_SCHEMA_VERSION or raw.get("manifest_sha256") != manifest.sha256:
        raise Stage5B1AValidationError("fresh discovery identity changed")
    if any(raw.get("media_activity", {}).values()):
        raise Stage5B1AValidationError("fresh discovery performed forbidden media/model work")
    rows = raw.get("tracks")
    if not isinstance(rows, list) or [row.get("track", {}).get("stable_track_id") for row in rows] != list(manifest.stable_track_ids):
        raise Stage5B1AValidationError("fresh discovery coverage/order changed")
    for row in rows:
        candidates = row.get("candidates")
        if not isinstance(candidates, list) or len(candidates) > 5:
            raise Stage5B1AValidationError("invalid fresh discovery candidates")
        ids = [candidate.get("youtube_video_id") for candidate in candidates]
        ranks = [candidate.get("rank") for candidate in candidates]
        if len(ids) != len(set(ids)) or ranks != list(range(1, len(candidates) + 1)):
            raise Stage5B1AValidationError("fresh candidates are duplicated or misordered")
    return raw


def materialize_and_resolve(config: ChallengeConfig, manifest: ChallengeManifest) -> dict[str, Any]:
    discovery = load_discovery(config, manifest)
    features = materialize_features(
        discovery, manifest_sha256=manifest.sha256, dataset_role="FRESH_CHALLENGE_UNLABELED"
    )
    boundaries, policies = load_frozen_policies(config)
    decisions = {
        policy_id: resolve_dataset(features, policies[policy_id], boundaries)
        for policy_id in POLICY_IDS
    }
    conservative = {
        row["stable_track_id"]: row["decision"] for row in decisions[POLICY_IDS[0]]["tracks"]
    }
    balanced = {
        row["stable_track_id"]: row["decision"] for row in decisions[POLICY_IDS[1]]["tracks"]
    }
    conservative_ids = {key for key, value in conservative.items() if value["status"] == AUTO_MATCH}
    balanced_ids = {key for key, value in balanced.items() if value["status"] == AUTO_MATCH}
    output = {
        "schema_version": DECISIONS_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "manifest_sha256": manifest.sha256,
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "features_sha256": None,
        "policy_bundle_sha256": config.policy_bundle_sha256,
        "policies": decisions,
        "comparison": {
            "conservative_auto_match_count": len(conservative_ids),
            "balanced_auto_match_count": len(balanced_ids),
            "balanced_incremental_auto_match_count": len(balanced_ids - conservative_ids),
            "balanced_incremental_track_ids": sorted(balanced_ids - conservative_ids),
            "both_auto_match_different_candidate_track_ids": sorted(
                key for key in conservative_ids & balanced_ids
                if conservative[key]["selected_video_id"] != balanced[key]["selected_video_id"]
            ),
        },
        "production_auto_match_activated": False,
    }
    atomic_json(config.artifacts["features"], features)
    output["features_sha256"] = file_sha256(config.artifacts["features"])
    atomic_json(config.artifacts["policy_decisions"], output)
    return output
