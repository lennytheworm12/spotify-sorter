"""Frozen deterministic targeted-query construction for Stage 5B.1D."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1c_normalization import parse_tier2_title


CONFIG_SCHEMA_VERSION = "stage5b1d-targeted-rediscovery-config-v1"
EXPERIMENT_ID = "stage5b1d_targeted_rediscovery_diagnostic_v1"
MAX_QUERY_VARIANTS = 3
EXPECTED_VARIANTS = (
    (
        "artist-core-exact-version-v1",
        '"{primary_artist}" "{core_title}" "{exact_version}"',
    ),
    (
        "core-version-credited-artists-v1",
        '"{core_title}" "{exact_version}" {credited_artists}',
    ),
    (
        "artist-combined-version-official-audio-v1",
        '"{primary_artist}" "{core_title} - {exact_version}" official audio',
    ),
)
_QUERY_PRESENTATION_NOISE = re.compile(
    r"\b(?:official\s+(?:music\s+)?video|official\s+audio|official\s+lyric\s+video|"
    r"lyric\s+video|lyrics?|letra(?:\s+video\s+oficial)?|visualizer)\b",
    re.I,
)
_EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]")


@dataclass(frozen=True)
class TargetedQueryVariant:
    variant_id: str
    template: str


@dataclass(frozen=True)
class Stage5B1DConfig:
    path: Path
    sha256: str
    project_root: Path
    challenge_config_path: Path
    frozen_inputs: dict[str, dict[str, str]]
    provider: YtDlpProviderConfig
    sleep_between_queries_seconds: float
    sleep_between_tracks_seconds: float
    variants: tuple[TargetedQueryVariant, ...]
    artifacts: dict[str, Path]


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"{name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage5B1AValidationError(f"{name} must be non-empty text")
    return value.strip()


def _bounded_number(value: Any, name: str, low: float, high: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not low <= float(value) <= high
    ):
        raise Stage5B1AValidationError(f"{name} must be between {low} and {high}")
    return float(value)


def load_stage5b1d_config(path: str | Path) -> Stage5B1DConfig:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1D config schema")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected Stage 5B.1D experiment ID")
    project_root = config_path.parent.parent
    raw_inputs = _object(payload.get("frozen_inputs"), "frozen_inputs")
    required_inputs = {
        "challenge_config",
        "challenge_discovery",
        "strong_metadata_decisions",
        "remaining_tail_diagnostic",
    }
    if set(raw_inputs) != required_inputs:
        raise Stage5B1AValidationError("Stage 5B.1D frozen inputs are incomplete")
    frozen_inputs: dict[str, dict[str, str]] = {}
    for name, raw_value in raw_inputs.items():
        value = _object(raw_value, f"frozen_inputs.{name}")
        relative = _text(value.get("path"), f"frozen_inputs.{name}.path")
        digest = _text(value.get("sha256"), f"frozen_inputs.{name}.sha256")
        resolved = (project_root / relative).resolve()
        if not resolved.is_relative_to(project_root) or len(digest) != 64:
            raise Stage5B1AValidationError(f"invalid frozen input identity: {name}")
        frozen_inputs[name] = {"path": relative, "sha256": digest}
    challenge_config_path = (
        project_root / frozen_inputs["challenge_config"]["path"]
    ).resolve()

    raw_provider = _object(payload.get("provider"), "provider")
    if (
        raw_provider.get("candidate_limit") != 5
        or raw_provider.get("search_prefix") != "ytsearch5:"
        or raw_provider.get("extract_flat") != "in_playlist"
    ):
        raise Stage5B1AValidationError("rediscovery must use metadata-only ytsearch5")
    for name in ("skip_download", "simulate", "ignore_user_config", "sequential_requests"):
        if raw_provider.get(name) is not True:
            raise Stage5B1AValidationError(f"provider.{name} must remain true")
    if raw_provider.get("cache_enabled") is not False:
        raise Stage5B1AValidationError("yt-dlp cache must remain disabled")
    timeout = raw_provider.get("socket_timeout_seconds")
    attempts = raw_provider.get("max_attempts")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 120:
        raise Stage5B1AValidationError("provider timeout is out of bounds")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 3:
        raise Stage5B1AValidationError("provider attempts are out of bounds")
    provider = YtDlpProviderConfig(
        candidate_limit=5,
        search_prefix="ytsearch5:",
        extract_flat="in_playlist",
        skip_download=True,
        simulate=True,
        ignore_user_config=True,
        cache_enabled=False,
        socket_timeout_seconds=timeout,
        max_attempts=attempts,
        retry_backoff_seconds=_bounded_number(
            raw_provider.get("retry_backoff_seconds"),
            "provider.retry_backoff_seconds",
            0,
            30,
        ),
        sleep_between_tracks_seconds=_bounded_number(
            raw_provider.get("sleep_between_tracks_seconds"),
            "provider.sleep_between_tracks_seconds",
            0,
            30,
        ),
    )
    query_delay = _bounded_number(
        raw_provider.get("sleep_between_queries_seconds"),
        "provider.sleep_between_queries_seconds",
        0,
        30,
    )
    raw_variants = payload.get("query_variants")
    if not isinstance(raw_variants, list) or not 1 <= len(raw_variants) <= MAX_QUERY_VARIANTS:
        raise Stage5B1AValidationError("targeted query count must be between 1 and 3")
    variants = tuple(
        TargetedQueryVariant(
            variant_id=_text(row.get("variant_id"), "query_variants.variant_id"),
            template=_text(row.get("template"), "query_variants.template"),
        )
        for row in raw_variants
        if isinstance(row, dict)
    )
    if tuple((row.variant_id, row.template) for row in variants) != EXPECTED_VARIANTS:
        raise Stage5B1AValidationError("targeted query variants changed")
    raw_artifacts = _object(payload.get("artifacts"), "artifacts")
    required_artifacts = {
        "queries",
        "discovery",
        "features",
        "decisions",
        "audit_queue",
        "human_review",
        "report",
        "manifest",
    }
    if set(raw_artifacts) != required_artifacts:
        raise Stage5B1AValidationError("Stage 5B.1D artifact paths are incomplete")
    artifacts = {}
    for name, relative_value in raw_artifacts.items():
        relative = _text(relative_value, f"artifacts.{name}")
        resolved = (project_root / relative).resolve()
        if not resolved.is_relative_to(project_root):
            raise Stage5B1AValidationError(f"artifact path escapes project: {name}")
        artifacts[name] = resolved
    return Stage5B1DConfig(
        path=config_path,
        sha256=file_sha256(config_path),
        project_root=project_root,
        challenge_config_path=challenge_config_path,
        frozen_inputs=frozen_inputs,
        provider=provider,
        sleep_between_queries_seconds=query_delay,
        sleep_between_tracks_seconds=provider.sleep_between_tracks_seconds,
        variants=variants,
        artifacts=artifacts,
    )


def verify_stage5b1d_frozen_inputs(config: Stage5B1DConfig) -> dict[str, str]:
    actual = {
        name: file_sha256(config.project_root / value["path"])
        for name, value in config.frozen_inputs.items()
    }
    changed = {
        name: digest for name, digest in actual.items()
        if digest != config.frozen_inputs[name]["sha256"]
    }
    if changed:
        raise Stage5B1AValidationError(f"Stage 5B.1D frozen inputs changed: {sorted(changed)}")
    return actual


def build_targeted_queries(
    track: SpotifyTrack, variants: tuple[TargetedQueryVariant, ...]
) -> dict[str, Any]:
    parsed = parse_tier2_title(track.title, candidate=False)
    exact_version_parts = [
        cleaned
        for descriptor in parsed.versions
        if (
            cleaned := " ".join(
                _EMPTY_BRACKETS.sub(
                    " ", _QUERY_PRESENTATION_NOISE.sub(" ", descriptor.raw)
                ).split()
            ).strip(" -–—:|()[]'\"")
        )
    ]
    if not exact_version_parts:
        raise Stage5B1AValidationError(
            "targeted rediscovery requires explicit target-version evidence"
        )
    exact_version = " ".join(dict.fromkeys(exact_version_parts))
    fields = {
        "primary_artist": track.artists[0],
        "core_title": parsed.core_title,
        "exact_version": exact_version,
        "credited_artists": " ".join(f'"{artist}"' for artist in track.artists),
    }
    rows = [
        {
            "variant_id": variant.variant_id,
            "query": " ".join(variant.template.format(**fields).split()),
        }
        for variant in variants
    ]
    if len({row["query"] for row in rows}) != len(rows):
        raise Stage5B1AValidationError("targeted query variants must be distinct")
    return {
        "stable_track_id": track.stable_track_id,
        "target": track.to_dict(),
        "structured_identity": {
            "primary_artist": track.artists[0],
            "credited_artists": list(track.artists),
            "core_title": parsed.core_title,
            "normalized_core_title": parsed.normalized_core_title,
            "version_descriptors": [item.to_dict() for item in parsed.versions],
            "exact_version_phrase": exact_version,
        },
        "queries": rows,
    }
