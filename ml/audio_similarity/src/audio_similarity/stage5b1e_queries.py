"""Frozen query construction and configuration for Stage 5B.1E."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a_config import QueryConfig
from .stage5b1a_discovery import build_search_query
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1c_normalization import parse_tier2_title


CONFIG_SCHEMA_VERSION = "stage5b1e-natural-query-config-v1"
EXPERIMENT_ID = "stage5b1e_natural_query_evaluation_v1"
STRATEGY_IDS = (
    "Q0_CURRENT_CONTROL",
    "Q1_NATURAL_SPOTIFY_TITLE",
    "Q2_NATURAL_TITLE_PLUS_ARTIST",
    "Q3_CORE_TITLE_ARTIST_VERSION",
)


@dataclass(frozen=True)
class QueryStrategy:
    strategy_id: str
    description: str


@dataclass(frozen=True)
class Stage5B1EConfig:
    path: Path
    sha256: str
    project_root: Path
    challenge_config_path: Path
    frozen_inputs: dict[str, dict[str, str]]
    provider: YtDlpProviderConfig
    sleep_between_queries_seconds: float
    strategies: tuple[QueryStrategy, ...]
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
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Stage5B1AValidationError(f"{name} must be numeric")
    result = float(value)
    if not low <= result <= high:
        raise Stage5B1AValidationError(f"{name} must be between {low} and {high}")
    return result


def load_stage5b1e_config(path: str | Path) -> Stage5B1EConfig:
    config_path = Path(path).resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1E config schema")
    if raw.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected Stage 5B.1E experiment ID")
    root = config_path.parent.parent.resolve()
    inputs = _object(raw.get("frozen_inputs"), "frozen_inputs")
    required_inputs = {
        "challenge_config", "challenge_discovery", "strong_metadata_decisions",
        "challenge_human_review", "challenge_sol_evaluations", "challenge_sol_mapping",
        "tier2_human_audit", "strong_metadata_human_audit",
    }
    if set(inputs) != required_inputs:
        raise Stage5B1AValidationError("Stage 5B.1E frozen inputs are incomplete")
    frozen_inputs: dict[str, dict[str, str]] = {}
    for name, value in inputs.items():
        item = _object(value, f"frozen_inputs.{name}")
        relative = _text(item.get("path"), f"frozen_inputs.{name}.path")
        digest = _text(item.get("sha256"), f"frozen_inputs.{name}.sha256")
        resolved = (root / relative).resolve()
        if not resolved.is_relative_to(root) or len(digest) != 64:
            raise Stage5B1AValidationError(f"invalid frozen input: {name}")
        frozen_inputs[name] = {"path": relative, "sha256": digest}

    provider_raw = _object(raw.get("provider"), "provider")
    if provider_raw.get("candidate_limit") != 5 or provider_raw.get("search_prefix") != "ytsearch5:":
        raise Stage5B1AValidationError("Stage 5B.1E requires ytsearch5")
    if provider_raw.get("extract_flat") != "in_playlist":
        raise Stage5B1AValidationError("Stage 5B.1E requires flat metadata search")
    for name in ("skip_download", "simulate", "ignore_user_config", "sequential_requests"):
        if provider_raw.get(name) is not True:
            raise Stage5B1AValidationError(f"provider.{name} must remain true")
    if provider_raw.get("cache_enabled") is not False:
        raise Stage5B1AValidationError("yt-dlp cache must remain disabled")
    timeout = provider_raw.get("socket_timeout_seconds")
    attempts = provider_raw.get("max_attempts")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 120:
        raise Stage5B1AValidationError("provider timeout out of bounds")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 3:
        raise Stage5B1AValidationError("provider attempts out of bounds")
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
            provider_raw.get("retry_backoff_seconds"), "provider.retry_backoff_seconds", 0, 30
        ),
        sleep_between_tracks_seconds=_bounded_number(
            provider_raw.get("sleep_between_tracks_seconds"),
            "provider.sleep_between_tracks_seconds", 0, 30,
        ),
    )
    strategy_rows = raw.get("query_strategies")
    if not isinstance(strategy_rows, list):
        raise Stage5B1AValidationError("query_strategies must be an array")
    strategies = tuple(
        QueryStrategy(
            strategy_id=_text(row.get("strategy_id"), "query_strategies.strategy_id"),
            description=_text(row.get("description"), "query_strategies.description"),
        )
        for row in strategy_rows if isinstance(row, dict)
    )
    if tuple(row.strategy_id for row in strategies) != STRATEGY_IDS:
        raise Stage5B1AValidationError("Stage 5B.1E query strategies changed")
    artifacts_raw = _object(raw.get("artifacts"), "artifacts")
    required_artifacts = {
        "strategies", "discovery", "comparison", "replays", "audit_queue",
        "human_review", "report", "manifest",
    }
    if set(artifacts_raw) != required_artifacts:
        raise Stage5B1AValidationError("Stage 5B.1E artifact paths are incomplete")
    artifacts = {}
    for name, value in artifacts_raw.items():
        resolved = (root / _text(value, f"artifacts.{name}")).resolve()
        if not resolved.is_relative_to(root):
            raise Stage5B1AValidationError(f"artifact path escapes project: {name}")
        artifacts[name] = resolved
    return Stage5B1EConfig(
        path=config_path,
        sha256=file_sha256(config_path),
        project_root=root,
        challenge_config_path=(root / frozen_inputs["challenge_config"]["path"]).resolve(),
        frozen_inputs=frozen_inputs,
        provider=provider,
        sleep_between_queries_seconds=_bounded_number(
            provider_raw.get("sleep_between_queries_seconds"),
            "provider.sleep_between_queries_seconds", 0, 30,
        ),
        strategies=strategies,
        artifacts=artifacts,
    )


def verify_frozen_inputs(config: Stage5B1EConfig) -> dict[str, str]:
    actual = {
        name: file_sha256(config.project_root / item["path"])
        for name, item in config.frozen_inputs.items()
    }
    changed = [name for name, digest in actual.items() if digest != config.frozen_inputs[name]["sha256"]]
    if changed:
        raise Stage5B1AValidationError(f"Stage 5B.1E frozen inputs changed: {changed}")
    return actual


def _clean(value: str) -> str:
    return " ".join(value.split())


def build_natural_query(track: SpotifyTrack, strategy_id: str) -> str:
    """Build one predeclared query without song-specific behavior."""

    title = _clean(track.title)
    primary_artist = _clean(track.artists[0])
    if strategy_id == "Q0_CURRENT_CONTROL":
        config = QueryConfig(
            variant_id="quoted-primary-artist-title-official-v1",
            template='"{primary_artist}" "{normalized_title}" official',
            normalize_featured_artist_noise=True,
        )
        return build_search_query(track, config)
    if strategy_id == "Q1_NATURAL_SPOTIFY_TITLE":
        return title
    if strategy_id == "Q2_NATURAL_TITLE_PLUS_ARTIST":
        return f"{title} {primary_artist}"
    if strategy_id == "Q3_CORE_TITLE_ARTIST_VERSION":
        parsed = parse_tier2_title(track.title, candidate=False)
        version_parts = [
            _clean(item.raw).strip(" -–—:|()[]'\"")
            for item in parsed.versions
            if _clean(item.raw).strip(" -–—:|()[]'\"")
        ]
        fields = [primary_artist, _clean(parsed.core_title), *dict.fromkeys(version_parts)]
        return " ".join(field for field in fields if field)
    raise Stage5B1AValidationError(f"unknown Stage 5B.1E query strategy: {strategy_id}")


def build_query_strategy_artifact(config: Stage5B1EConfig, tracks: list[SpotifyTrack]) -> dict[str, Any]:
    verify_frozen_inputs(config)
    rows = []
    for track in tracks:
        rows.append({
            "stable_track_id": track.stable_track_id,
            "target": track.to_dict(),
            "queries": [
                {"strategy_id": strategy.strategy_id, "query": build_natural_query(track, strategy.strategy_id)}
                for strategy in config.strategies
            ],
        })
    return {
        "schema_version": "stage5b1e-query-strategies-v1",
        "experiment_id": EXPERIMENT_ID,
        "config_sha256": config.sha256,
        "track_count": len(rows),
        "strategy_count": len(config.strategies),
        "strategies": [strategy.__dict__ for strategy in config.strategies],
        "tracks": rows,
        "frozen_before_discovery": True,
        "production_query_activated": False,
    }
