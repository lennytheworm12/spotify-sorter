"""Strict predeclared configuration for Stage 5B.1A."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .stage5b1a_models import EXPERIMENT_ID, Stage5B1AValidationError, file_sha256


CONFIG_SCHEMA_VERSION = "stage5b1a-firecrawl-config-v1"


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"{name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage5B1AValidationError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class ProviderConfig:
    endpoint: str
    api_key_environment_variable: str
    discovery_version: str
    candidate_limit: int
    provider_result_limit: int
    include_domains: tuple[str, ...]
    sources: tuple[dict[str, str], ...]
    country: str
    highlights: bool
    request_timeout_ms: int
    max_attempts: int
    retry_backoff_seconds: float

    def request_payload(self, query: str) -> dict[str, Any]:
        return {
            "query": query,
            "limit": self.provider_result_limit,
            "sources": [dict(source) for source in self.sources],
            "includeDomains": list(self.include_domains),
            "country": self.country,
            "highlights": self.highlights,
            "timeout": self.request_timeout_ms,
        }


@dataclass(frozen=True)
class QueryConfig:
    variant_id: str
    template: str
    normalize_featured_artist_noise: bool


@dataclass(frozen=True)
class GateConfig:
    pass_min_recall_at_5: float
    conditional_min_recall_at_5: float
    primary_metric: str
    scope_note: str


@dataclass(frozen=True)
class Stage5B1AConfig:
    path: Path
    sha256: str
    project_root: Path
    manifest_path: Path
    manifest_sha256: str
    provider: ProviderConfig
    query: QueryConfig
    gate: GateConfig
    artifacts: dict[str, Path]


def load_config(path: str | Path) -> Stage5B1AConfig:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1A config schema")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected Stage 5B.1A experiment ID")
    project_root = config_path.parent.parent

    manifest = _object(payload.get("manifest"), "manifest")
    manifest_sha256 = _text(manifest.get("expected_sha256"), "manifest.expected_sha256")
    if len(manifest_sha256) != 64:
        raise Stage5B1AValidationError("manifest.expected_sha256 must be a SHA-256 digest")
    manifest_path = (project_root / _text(manifest.get("path"), "manifest.path")).resolve()
    if not manifest_path.is_relative_to(project_root):
        raise Stage5B1AValidationError("manifest path must remain inside the project root")

    provider = _object(payload.get("provider"), "provider")
    endpoint = _text(provider.get("endpoint"), "provider.endpoint")
    endpoint_parts = urlsplit(endpoint)
    if (
        endpoint_parts.scheme != "https"
        or endpoint_parts.hostname != "api.firecrawl.dev"
        or endpoint_parts.path != "/v2/search"
        or endpoint_parts.query
    ):
        raise Stage5B1AValidationError("Firecrawl endpoint must be exactly https://api.firecrawl.dev/v2/search")
    candidate_limit = provider.get("candidate_limit")
    provider_result_limit = provider.get("provider_result_limit")
    if not isinstance(candidate_limit, int) or candidate_limit != 5:
        raise Stage5B1AValidationError("the frozen candidate limit must be 5")
    if (
        not isinstance(provider_result_limit, int)
        or not candidate_limit <= provider_result_limit <= 100
    ):
        raise Stage5B1AValidationError("invalid provider result limit")
    domains = provider.get("include_domains")
    if not isinstance(domains, list) or not domains or not all(isinstance(x, str) for x in domains):
        raise Stage5B1AValidationError("provider.include_domains must be a non-empty string array")
    if set(domains) != {"youtube.com", "youtu.be"} or len(domains) != 2:
        raise Stage5B1AValidationError("Firecrawl discovery must include only the frozen YouTube domains")
    sources = provider.get("sources")
    if sources != [{"type": "web"}]:
        raise Stage5B1AValidationError("Stage 5B.1A must use only Firecrawl web search")
    if provider.get("sequential_requests") is not True:
        raise Stage5B1AValidationError("Stage 5B.1A requests must remain sequential")
    if provider.get("highlights") is not False:
        raise Stage5B1AValidationError("Firecrawl highlights must remain disabled")
    timeout_ms = provider.get("request_timeout_ms")
    max_attempts = provider.get("max_attempts")
    backoff = provider.get("retry_backoff_seconds")
    if not isinstance(timeout_ms, int) or not 1_000 <= timeout_ms <= 120_000:
        raise Stage5B1AValidationError("provider request timeout is out of bounds")
    if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 5:
        raise Stage5B1AValidationError("provider max_attempts is out of bounds")
    if not isinstance(backoff, (int, float)) or not 0 <= float(backoff) <= 30:
        raise Stage5B1AValidationError("provider retry backoff is out of bounds")
    provider_config = ProviderConfig(
        endpoint=endpoint,
        api_key_environment_variable=_text(
            provider.get("api_key_environment_variable"),
            "provider.api_key_environment_variable",
        ),
        discovery_version=_text(provider.get("discovery_version"), "provider.discovery_version"),
        candidate_limit=candidate_limit,
        provider_result_limit=provider_result_limit,
        include_domains=tuple(domains),
        sources=tuple(dict(source) for source in sources),
        country=_text(provider.get("country"), "provider.country"),
        highlights=False,
        request_timeout_ms=timeout_ms,
        max_attempts=max_attempts,
        retry_backoff_seconds=float(backoff),
    )

    query = _object(payload.get("query_strategy"), "query_strategy")
    template = _text(query.get("template"), "query_strategy.template")
    if set(part for part in ("{primary_artist}", "{normalized_title}") if part in template) != {
        "{primary_artist}",
        "{normalized_title}",
    }:
        raise Stage5B1AValidationError("query template must contain artist and title placeholders")
    query_config = QueryConfig(
        variant_id=_text(query.get("query_variant_id"), "query_strategy.query_variant_id"),
        template=template,
        normalize_featured_artist_noise=query.get("featured_artist_noise_normalization") is True,
    )

    gate = _object(payload.get("feasibility_gate"), "feasibility_gate")
    pass_min = gate.get("pass_min_recall_at_5")
    conditional_min = gate.get("conditional_min_recall_at_5")
    if pass_min != 0.9 or conditional_min != 0.8 or gate.get("fail_below_recall_at_5") != 0.8:
        raise Stage5B1AValidationError("the frozen 90%/80% feasibility gate changed")
    if gate.get("primary_metric") != "recall_at_5":
        raise Stage5B1AValidationError("Recall@5 must remain the primary metric")
    gate_config = GateConfig(
        pass_min_recall_at_5=pass_min,
        conditional_min_recall_at_5=conditional_min,
        primary_metric="recall_at_5",
        scope_note=_text(gate.get("scope_note"), "feasibility_gate.scope_note"),
    )

    raw_artifacts = _object(payload.get("artifacts"), "artifacts")
    required_artifacts = {
        "discovery_results",
        "implementation_report",
        "metrics",
        "review",
        "review_template",
        "run_status",
    }
    if set(raw_artifacts) != required_artifacts:
        raise Stage5B1AValidationError("Stage 5B.1A artifact paths are incomplete")
    artifacts = {}
    for name, relative in raw_artifacts.items():
        artifact_path = (project_root / _text(relative, f"artifacts.{name}")).resolve()
        if not artifact_path.is_relative_to(project_root):
            raise Stage5B1AValidationError(f"artifacts.{name} must remain inside the project root")
        artifacts[name] = artifact_path
    return Stage5B1AConfig(
        path=config_path,
        sha256=file_sha256(config_path),
        project_root=project_root,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        provider=provider_config,
        query=query_config,
        gate=gate_config,
        artifacts=artifacts,
    )
