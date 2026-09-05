"""Strict configuration for the frozen Stage 5B.1A2 yt-dlp experiment."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stage5b1a_config import GateConfig, QueryConfig
from .stage5b1a_models import Stage5B1AValidationError, file_sha256


CONFIG_SCHEMA_VERSION = "stage5b1a2-ytdlp-config-v1"
EXPERIMENT_ID = "stage5b1a2_ytdlp_youtube_search_feasibility"


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"{name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage5B1AValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _bounded_number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise Stage5B1AValidationError(f"{name} must be between {low} and {high}")
    return float(value)


@dataclass(frozen=True)
class YtDlpProviderConfig:
    candidate_limit: int
    search_prefix: str
    extract_flat: str
    skip_download: bool
    simulate: bool
    ignore_user_config: bool
    cache_enabled: bool
    socket_timeout_seconds: int
    max_attempts: int
    retry_backoff_seconds: float
    sleep_between_tracks_seconds: float

    def search_expression(self, query: str) -> str:
        return f"{self.search_prefix}{query}"

    def metadata_only_options(self) -> dict[str, Any]:
        return {
            "cachedir": False,
            "extract_flat": self.extract_flat,
            "ignoreconfig": self.ignore_user_config,
            "ignoreerrors": False,
            "lazy_playlist": False,
            "noprogress": True,
            "playlistend": self.candidate_limit,
            "quiet": True,
            "retries": 0,
            "simulate": self.simulate,
            "skip_download": self.skip_download,
            "socket_timeout": self.socket_timeout_seconds,
        }


@dataclass(frozen=True)
class Stage5B1A2Config:
    path: Path
    sha256: str
    project_root: Path
    manifest_path: Path
    manifest_sha256: str
    provider: YtDlpProviderConfig
    query: QueryConfig
    gate: GateConfig
    artifacts: dict[str, Path]
    comparison_sources: dict[str, Path]


def _inside_paths(project_root: Path, values: dict[str, Any], name: str) -> dict[str, Path]:
    paths = {}
    for key, relative in values.items():
        path = (project_root / _text(relative, f"{name}.{key}")).resolve()
        if not path.is_relative_to(project_root):
            raise Stage5B1AValidationError(f"{name}.{key} must remain inside the project root")
        paths[key] = path
    return paths


def load_ytdlp_config(path: str | Path) -> Stage5B1A2Config:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1A2 config schema")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected Stage 5B.1A2 experiment ID")
    project_root = config_path.parent.parent

    manifest = _object(payload.get("manifest"), "manifest")
    digest = _text(manifest.get("expected_sha256"), "manifest.expected_sha256")
    if len(digest) != 64:
        raise Stage5B1AValidationError("manifest.expected_sha256 must be a SHA-256 digest")
    manifest_path = (project_root / _text(manifest.get("path"), "manifest.path")).resolve()
    if not manifest_path.is_relative_to(project_root):
        raise Stage5B1AValidationError("manifest path must remain inside the project root")

    raw_provider = _object(payload.get("provider"), "provider")
    candidate_limit = raw_provider.get("candidate_limit")
    if candidate_limit != 5 or raw_provider.get("search_prefix") != "ytsearch5:":
        raise Stage5B1AValidationError("yt-dlp discovery must use frozen ytsearch5 top-5 search")
    required_true = ("skip_download", "simulate", "ignore_user_config", "sequential_requests")
    if any(raw_provider.get(key) is not True for key in required_true):
        raise Stage5B1AValidationError("yt-dlp metadata-only and sequential safeguards must remain enabled")
    if raw_provider.get("cache_enabled") is not False:
        raise Stage5B1AValidationError("yt-dlp cache must remain disabled for this experiment")
    if raw_provider.get("extract_flat") != "in_playlist":
        raise Stage5B1AValidationError("yt-dlp must use flat search-result metadata")
    timeout = raw_provider.get("socket_timeout_seconds")
    attempts = raw_provider.get("max_attempts")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 120:
        raise Stage5B1AValidationError("provider socket timeout is out of bounds")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 3:
        raise Stage5B1AValidationError("provider max_attempts is out of bounds")
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
            raw_provider.get("retry_backoff_seconds"), "provider.retry_backoff_seconds", 0, 30
        ),
        sleep_between_tracks_seconds=_bounded_number(
            raw_provider.get("sleep_between_tracks_seconds"),
            "provider.sleep_between_tracks_seconds",
            0,
            30,
        ),
    )

    raw_query = _object(payload.get("query_strategy"), "query_strategy")
    if raw_query.get("template") != '"{primary_artist}" "{normalized_title}" official':
        raise Stage5B1AValidationError("Stage 5B.1A2 must reuse the frozen Firecrawl query template")
    if raw_query.get("query_variant_id") != "quoted-primary-artist-title-official-v1":
        raise Stage5B1AValidationError("Stage 5B.1A2 must reuse the frozen query variant")
    if raw_query.get("featured_artist_noise_normalization") is not True:
        raise Stage5B1AValidationError("featured-artist query normalization must remain enabled")
    query = QueryConfig(
        variant_id=raw_query["query_variant_id"],
        template=raw_query["template"],
        normalize_featured_artist_noise=True,
    )

    raw_gate = _object(payload.get("feasibility_gate"), "feasibility_gate")
    if (
        raw_gate.get("pass_min_recall_at_5") != 0.9
        or raw_gate.get("conditional_min_recall_at_5") != 0.8
        or raw_gate.get("fail_below_recall_at_5") != 0.8
        or raw_gate.get("primary_metric") != "recall_at_5"
    ):
        raise Stage5B1AValidationError("the frozen 90%/80% feasibility gate changed")
    gate = GateConfig(
        pass_min_recall_at_5=0.9,
        conditional_min_recall_at_5=0.8,
        primary_metric="recall_at_5",
        scope_note=_text(raw_gate.get("scope_note"), "feasibility_gate.scope_note"),
    )

    raw_artifacts = _object(payload.get("artifacts"), "artifacts")
    required_artifacts = {
        "comparison", "discovery_results", "implementation_report", "metrics",
        "review", "review_template", "run_status",
    }
    if set(raw_artifacts) != required_artifacts:
        raise Stage5B1AValidationError("Stage 5B.1A2 artifact paths are incomplete")
    raw_sources = _object(payload.get("comparison_sources"), "comparison_sources")
    if set(raw_sources) != {"firecrawl_results", "firecrawl_metrics"}:
        raise Stage5B1AValidationError("Stage 5B.1A2 comparison sources are incomplete")
    return Stage5B1A2Config(
        path=config_path,
        sha256=file_sha256(config_path),
        project_root=project_root,
        manifest_path=manifest_path,
        manifest_sha256=digest,
        provider=provider,
        query=query,
        gate=gate,
        artifacts=_inside_paths(project_root, raw_artifacts, "artifacts"),
        comparison_sources=_inside_paths(project_root, raw_sources, "comparison_sources"),
    )
