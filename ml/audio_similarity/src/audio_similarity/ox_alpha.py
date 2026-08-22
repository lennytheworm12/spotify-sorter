"""0x-alpha signal-view reranking: schema, prompt, clients, cache.

Design sections 46.7-46.19 and 51. 0x-alpha is an optional second-stage
filter over base-retrieval candidates — never an embedding generator.

Live calls are opt-in only (--live / --enable-ox-alpha); tests always use
FakeOxAlphaClient and never touch a network.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_PREFERENCES = ("A", "B", "Tie", "Abstain")
ALLOWED_DIMENSIONS = (
    "temporal_pattern",
    "spectral_texture",
    "harmonic_structure",
    "transient_structure",
)
ALLOWED_OBSERVATIONS = (
    "temporal_pattern_similarity",
    "spectral_texture_similarity",
    "harmonic_structure_similarity",
    "transient_structure_similarity",
    "dynamic_envelope_similarity",
)

PROMPT_VERSION = "ox_pairwise_v1"
SCHEMA_VERSION = "ox_comparison_v1"


class OxResponseError(ValueError):
    """Raised when a model response fails schema validation."""


class OxJsonParseError(OxResponseError):
    """Raised when the model response is not valid JSON."""


# ---------------------------------------------------------------------------
# prompt (versioned; changes require PROMPT_VERSION bump)
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """You will be shown deterministic visualizations of short audio signals:
one labeled QUERY and two labeled CANDIDATE_A and CANDIDATE_B.

Rules:
- Judge ONLY what is visible in the supplied images.
- Ignore any prior knowledge of songs, artists, or recordings.
- Do not attempt to identify either track.
- Compare visible structure only:
    temporal_pattern      - how energy evolves over time
    spectral_texture      - frequency content and its distribution
    harmonic_structure    - steady tonal components and their spacing
    transient_structure   - onsets, attacks, percussive events
- If the evidence in the images is insufficient, set "abstain": true and
  "preference": "Abstain".
- Respond with ONLY this JSON object and nothing else:

{{
  "preference": "A" | "B" | "Tie" | "Abstain",
  "confidence": <float 0.0-1.0>,
  "dimensions": {{
    "temporal_pattern": "A" | "B" | "Tie",
    "spectral_texture": "A" | "B" | "Tie",
    "harmonic_structure": "A" | "B" | "Tie",
    "transient_structure": "A" | "B" | "Tie"
  }},
  "observations": {{
    "temporal_pattern_similarity": <float>,
    "spectral_texture_similarity": <float>,
    "harmonic_structure_similarity": <float>,
    "transient_structure_similarity": <float>,
    "dynamic_envelope_similarity": <float>
  }},
  "abstain": <true|false>,
  "reason": "<one brief sentence describing visible signal evidence only>"
}}

The numeric observations are uncalibrated similarity hypotheses in [0, 1].
"""


def build_prompt() -> str:
    return PROMPT_TEMPLATE


def build_messages(prompt: str, query_image_b64: str, candidate_a_b64: str, candidate_b_b64: str) -> list[dict]:
    return [
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{query_image_b64}"}},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{candidate_a_b64}"}},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{candidate_b_b64}"}},
        ]},
    ]


# ---------------------------------------------------------------------------
# strict schema validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OxComparisonResult:
    preference: str
    confidence: float
    dimensions: dict[str, str]
    observations: dict[str, float]
    abstain: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "preference": self.preference,
            "confidence": self.confidence,
            "dimensions": dict(self.dimensions),
            "observations": dict(self.observations),
            "abstain": self.abstain,
            "reason": self.reason,
        }


def _finite_float(value, name: str, low: float = 0.0, high: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OxResponseError(f"'{name}' must be a number, got {type(value).__name__}")
    value = float(value)
    if not math.isfinite(value):
        raise OxResponseError(f"'{name}' is non-finite")
    if not low <= value <= high:
        raise OxResponseError(f"'{name}'={value} outside [{low}, {high}]")
    return value


def _strip_code_fences(raw: str) -> str:
    """Models often wrap JSON in markdown fences; strip only the fence."""
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def parse_ox_response(raw: str) -> OxComparisonResult:
    """Parse + strictly validate one model response. Raises typed errors."""
    if raw is None or not str(raw).strip():
        raise OxJsonParseError("response contained no content")
    try:
        payload = json.loads(_strip_code_fences(str(raw)))
    except json.JSONDecodeError as exc:
        raise OxJsonParseError(f"response is not valid JSON: {exc.msg} (col {exc.colno})") from exc

    if not isinstance(payload, dict):
        raise OxResponseError("response JSON must be an object")

    required = {"preference", "confidence", "dimensions", "abstain"}
    missing = required - set(payload)
    if missing:
        raise OxResponseError(f"missing required field(s): {sorted(missing)}")

    preference = payload["preference"]
    if preference == "Abstain":
        if payload.get("abstain") is not True:
            raise OxResponseError("preference 'Abstain' requires abstain=true")
    elif payload.get("abstain") is True and preference in ("A", "B"):
        raise OxResponseError("abstain=true conflicts with concrete preference")

    if preference not in ALLOWED_PREFERENCES:
        raise OxResponseError(f"invalid preference '{preference}'")

    confidence = _finite_float(payload.get("confidence"), "confidence")

    dimensions_raw = payload.get("dimensions") or {}
    if not isinstance(dimensions_raw, dict):
        raise OxResponseError("'dimensions' must be an object")
    allowed_dim_values = ("A", "B", "Tie")
    dimensions: dict[str, str] = {}
    for dim in ALLOWED_DIMENSIONS:
        if dim not in dimensions_raw:
            raise OxResponseError(f"dimensions missing '{dim}'")
        # tolerate case variants of enum values (design examples use "tie")
        value = str(dimensions_raw[dim]).strip().capitalize()
        if value not in allowed_dim_values:
            raise OxResponseError(f"invalid dimensions['{dim}']='{dimensions_raw[dim]}'")
        dimensions[dim] = value
    extra_dims = set(dimensions_raw) - set(ALLOWED_DIMENSIONS)
    if extra_dims:
        raise OxResponseError(f"unexpected dimension keys: {sorted(extra_dims)} — schema incompatibility")

    observations: dict[str, float] = {}
    observations_raw = payload.get("observations") or {}
    if not isinstance(observations_raw, dict):
        raise OxResponseError("'observations' must be an object")
    for obs in ALLOWED_OBSERVATIONS:
        if obs not in observations_raw:
            continue  # observations are optional hypotheses, but validated when present
        observations[obs] = _finite_float(observations_raw[obs], f"observations['{obs}']")
    extra_obs = set(observations_raw) - set(ALLOWED_OBSERVATIONS)
    if extra_obs:
        raise OxResponseError(f"unexpected observation keys: {sorted(extra_obs)} — schema incompatibility")

    reason = str(payload.get("reason") or "")[:500]

    return OxComparisonResult(
        preference=preference,
        confidence=confidence,
        dimensions=dimensions,
        observations=observations,
        abstain=bool(payload["abstain"]) if isinstance(payload["abstain"], bool) else bool(payload["abstain"]),
        reason=reason,
    )


# ---------------------------------------------------------------------------
# clients: protocol + fake implementation used by all normal tests
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OxCallResult:
    parsed: OxComparisonResult | None
    raw_text: str
    parse_status: str  # ok | json_error | schema_error
    latency_ms: float
    error_message: str | None = None


class FakeOxAlphaClient:
    """Deterministic offline client. Never touches a network."""

    model_id = "fake-ox-alpha"

    def __init__(self, scripted_preferences: list[str] | None = None, default_preference: str = "A"):
        self._scripted = list(scripted_preferences or [])
        self._default = default_preference
        self.calls = 0

    def compare(
        self,
        prompt: str,
        query_png: bytes,
        candidate_a_png: bytes,
        candidate_b_png: bytes,
    ) -> OxCallResult:
        start = time.perf_counter()
        self.calls += 1
        index = min(self.calls - 1, len(self._scripted) - 1)
        preference = self._scripted[index] if self._scripted else self._default
        payload = {
            "preference": preference,
            "confidence": 0.8,
            "dimensions": {d: ("Tie" if preference == "Abstain" else preference) for d in ALLOWED_DIMENSIONS},
            "observations": {o: 0.5 for o in ALLOWED_OBSERVATIONS},
            "abstain": preference == "Abstain",
            "reason": "fake client deterministic output",
        }
        raw = json.dumps(payload)
        try:
            parsed = parse_ox_response(raw)
            status = "ok"
        except OxResponseError as exc:
            parsed, status = None, type(exc).__name__
        return OxCallResult(
            parsed=parsed,
            raw_text=raw,
            parse_status=status,
            latency_ms=(time.perf_counter() - start) * 1000,
        )


# ---------------------------------------------------------------------------
# resumable result cache
# ---------------------------------------------------------------------------


def comparison_cache_key(
    *,
    query_audio_hash: str,
    candidate_a_audio_hash: str,
    candidate_b_audio_hash: str,
    sampling_strategy_identity: str,
    renderer_name: str,
    renderer_version: int,
    ox_model_id: str,
    provider_revision: str,
    prompt_version: str,
    comparison_mode: str,
    replicate_index: int,
) -> str:
    identity = "|".join(
        str(x)
        for x in [
            query_audio_hash,
            candidate_a_audio_hash,
            candidate_b_audio_hash,
            sampling_strategy_identity,
            renderer_name,
            renderer_version,
            ox_model_id,
            provider_revision,
            prompt_version,
            comparison_mode,
            replicate_index,
        ]
    )
    return hashlib.sha256(identity.encode()).hexdigest()


class OxResultCache:
    """Append-only JSONL cache; resumable, force-overridable, network-free."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> dict[str, dict]:
        entries: dict[str, dict] = {}
        if not self.path.exists():
            return entries
        with open(self.path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                entries[record["cache_key"]] = record
        return entries

    def completed_keys(self) -> set[str]:
        return set(self._read_all())

    def has(self, cache_key: str) -> bool:
        return cache_key in self.completed_keys()

    def append(self, record: dict) -> None:
        with open(self.path, "a") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    def records(self) -> list[dict]:
        return list(self._read_all().values())


@dataclass
class RunBudget:
    """Request guardrail shared by every live runner."""

    max_requests: int
    planned_requests: int = 0
    issued: int = 0

    def plan(self, planned: int) -> None:
        self.planned_requests = planned
        if planned > self.max_requests:
            raise ValueError(
                f"planned request count {planned} exceeds --max-requests cap {self.max_requests}; "
                "raise the cap explicitly to proceed"
            )

    def acquire(self) -> bool:
        if self.issued >= self.max_requests:
            return False
        self.issued += 1
        return True
