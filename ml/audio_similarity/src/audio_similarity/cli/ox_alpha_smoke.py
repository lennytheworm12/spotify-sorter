"""Live-gated 0x-alpha smoke experiment runner (design section 51.4 OX-P1).

Normal usage NEVER calls the provider. Live execution requires:

    --live  AND  OPENROUTER_API_KEY in the environment

Before any request is issued, this tool prints model ID, prompt version,
renderer versions, planned request count, max cap, and cache location.
Requests are cached and resumable; completed cache keys are skipped unless
--force is given. The hard --max-requests cap aborts planning if exceeded.

Example:
    python -m audio_similarity.cli.ox_alpha_smoke --live \
        --model openrouter/0x-alpha --cases 6 --max-requests 54
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

from audio_similarity.ox_alpha import (
    PROMPT_VERSION,
    FakeOxAlphaClient,
    OxCallResult,
    OxResultCache,
    RunBudget,
    build_messages,
    build_prompt,
    comparison_cache_key,
    parse_ox_response,
)
from audio_similarity.signal_views import (
    RendererConfig,
    render_linear_stft_v1,
    render_log_mel_v1,
    render_waveform_v1,
)
from audio_similarity.sampling import sample_segments

DEFAULT_MODEL = "stealth/ox-alpha"
VIEWS = ("waveform", "linear_stft", "log_mel")
REPLICATES = 3
SAMPLING_IDENTITY = "three20_v1"


def synthetic_cases(count: int) -> list[dict]:
    """Deterministic synthetic query/candidate pairs for plumbing smoke tests."""
    cases: list[dict] = []
    rng = np.random.default_rng(20260822)
    sr = 24000
    for i in range(count):
        t = np.arange(sr * 35) / sr
        f_query = 220.0 * (2 ** (i / 12))
        f_a = f_query * (2 ** (0.25 * ((-1) ** i)))   # candidate A near-query tone
        f_b = 40.0 + 30.0 * (i % 5)                    # candidate B unrelated low tone
        def wave(freq: float) -> np.ndarray:
            return (np.sin(2 * np.pi * freq * t) + 0.05 * rng.normal(size=len(t))).astype(np.float64)
        cases.append(
            {
                "case_id": f"synthetic-{i}",
                "query": wave(f_query),
                "candidate_a": wave(f_a),
                "candidate_b": wave(f_b),
                "sample_rate": sr,
                "query_audio_hash": f"syn-q-{i}",
                "a_audio_hash": f"syn-a-{i}",
                "b_audio_hash": f"syn-b-{i}",
            }
        )
    return cases


def real_fma_cases(
    count: int,
    manifest_path: str,
    embeddings_path: str,
    audio_root: str,
    queries_csv: str | None = None,
    candidate_b_rank: int = 12,
) -> list[dict]:
    """Real-music smoke cases driven by Phase 1 retrieval.

    Candidate A is a near-top base-retrieval neighbor; candidate B is a
    clearly lower-ranked neighbor. Both are real FMA clips; identity stays
    hidden behind opaque labels. Requires local FMA + Phase 1 embeddings.
    """
    import torch  # local decode only

    from audio_similarity.audio import preprocess_file
    from audio_similarity.manifest import load_manifest
    from audio_similarity.retrieval import RetrievalIndex

    manifest = load_manifest(manifest_path)
    index = RetrievalIndex(embeddings_path, manifest)
    meta = manifest.set_index("track_id")

    if queries_csv and Path(queries_csv).exists():
        query_ids = [int(t) for t in pd_read_col(queries_csv)]
    else:
        step = max(1, len(index.track_ids) // count)
        query_ids = [int(t) for t in index.track_ids[::step][:count]]

    sr_expected = 24000
    cases: list[dict] = []
    for n, qid in enumerate(query_ids[:count]):
        neighbors = index.search("timbre", qid, k=candidate_b_rank + 2, exclude_same_artist=True)
        cand_a = next(nbr for nbr in neighbors if nbr.rank == 2)
        cand_b = next(nbr for nbr in neighbors if nbr.rank == min(candidate_b_rank, len(neighbors)))

        def load(tid: int) -> np.ndarray:
            path = Path(audio_root) / meta.at[tid, "relative_audio_path"]
            wav = preprocess_file(path)
            assert wav.shape[0] == sr_expected * 30
            return wav.numpy().astype(np.float64)

        cases.append(
            {
                "case_id": f"fma-{qid}",
                "query": load(qid),
                "candidate_a": load(int(cand_a.track_id)),
                "candidate_b": load(int(cand_b.track_id)),
                "sample_rate": sr_expected,
                "query_audio_hash": str(meta.at[qid, "audio_sha256"]),
                "a_audio_hash": str(meta.at[int(cand_a.track_id), "audio_sha256"]),
                "b_audio_hash": str(meta.at[int(cand_b.track_id), "audio_sha256"]),
            }
        )
    return cases


def pd_read_col(queries_csv: str) -> list[int]:
    import pandas as pd

    frame = pd.read_csv(queries_csv)
    return list(frame["track_id"].astype(int))


def render_case_views(waveform: np.ndarray, sample_rate: int, config: RendererConfig) -> dict[str, bytes]:
    return {
        "waveform": render_waveform_v1(waveform, sample_rate, config).image_png,
        "linear_stft": render_linear_stft_v1(waveform, sample_rate, config).image_png,
        "log_mel": render_log_mel_v1(waveform, sample_rate, config).image_png,
    }


class OpenRouterClient:
    """Minimal live client; exists only behind the --live gate."""

    model_id: str

    def __init__(self, model: str, api_key_env: str = "OPENROUTER_API_KEY"):
        key = os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"{api_key_env} not set — refusing to attempt live calls")
        self.model_id = model
        self._key = key
        self.provider_revision = "unavailable"

    def compare(self, prompt: str, query_png: bytes, a_png: bytes, b_png: bytes) -> OxCallResult:
        start = time.perf_counter()

        def b64(data: bytes) -> str:
            return base64.b64encode(data).decode()

        messages = build_messages(prompt, b64(query_png), b64(a_png), b64(b_png))
        body = json.dumps({
            "model": self.model_id,
            "messages": messages,
            "temperature": 0,
        }).encode()
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.loads(response.read())
            choice = payload["choices"][0]["message"]
            text = choice.get("content")
            if not text:
                reason = str(choice.get("finish_reason") or payload.get("error") or "empty content")
                return OxCallResult(None, "", "provider_error",
                                    (time.perf_counter() - start) * 1000,
                                    error_message=f"empty completion ({reason[:200]})")
            revision = str(payload.get("model", self.model_id))
        except Exception as exc:  # provider/network failure -> typed call result
            return OxCallResult(None, "", "provider_error", (time.perf_counter() - start) * 1000,
                                error_message=str(exc)[:300])
        try:
            parsed = parse_ox_response(text)
            status = "ok"
        except Exception as exc:
            return OxCallResult(None, text[:500], "schema_error",
                                (time.perf_counter() - start) * 1000, error_message=str(exc)[:300])
        self.provider_revision = revision
        return OxCallResult(parsed, text[:500], "ok", (time.perf_counter() - start) * 1000)


def run_smoke(args: argparse.Namespace) -> int:
    cfg = RendererConfig(image_width=768, image_height=384)
    if getattr(args, "source", "synthetic") == "fma":
        print(f"  case source:        FMA Small via Phase 1 retrieval ({args.embeddings})")
        cases = real_fma_cases(
            args.cases,
            manifest_path=args.manifest,
            embeddings_path=args.embeddings,
            audio_root=args.audio_root,
            queries_csv=args.queries,
        )
    else:
        print("  case source:        synthetic tones")
        cases = synthetic_cases(args.cases)
    prompt = build_prompt()
    client = OpenRouterClient(args.model) if args.live else FakeOxAlphaClient()
    mode = "LIVE" if args.live else "FAKE"

    comparisons_per_case = len(VIEWS)
    planned = len(cases) * comparisons_per_case * REPLICATES
    budget = RunBudget(max_requests=args.max_requests)

    print("=" * 62)
    print("ox-alpha smoke plan")
    print(f"  mode:               {mode}")
    print(f"  model id:           {client.model_id}")
    print(f"  prompt version:     {PROMPT_VERSION}")
    print(f"  renderer versions:  waveform_v1 / linear_stft_v1 / log_mel_v1")
    print(f"  sampling identity:  {SAMPLING_IDENTITY}")
    print(f"  planned requests:   {planned} ({len(cases)} cases x {len(VIEWS)} views x {REPLICATES})")
    print(f"  max request cap:    {args.max_requests}")
    print(f"  cache location:     {args.cache}")
    print("=" * 62)
    budget.plan(planned)  # raises if over cap

    if not args.live:
        print("dry-run only (no --live): exercising fake client + cache resume path")

    cache = OxResultCache(args.cache)
    stats = {"ok": 0, "skipped_cached": 0, "parse_error": 0, "provider_error": 0}
    preferences_by_view: dict[str, list[str]] = {v: [] for v in VIEWS}

    for case in cases:
        # every role gets its OWN deterministic renders per view
        query_views = render_case_views(case["query"], case["sample_rate"], cfg)
        a_views = render_case_views(case["candidate_a"], case["sample_rate"], cfg)
        b_views = render_case_views(case["candidate_b"], case["sample_rate"], cfg)
        for view in VIEWS:
            for replicate in range(REPLICATES):
                key = comparison_cache_key(
                    query_audio_hash=case["query_audio_hash"],
                    candidate_a_audio_hash=case["a_audio_hash"],
                    candidate_b_audio_hash=case["b_audio_hash"],
                    sampling_strategy_identity=("fma_clip30_v1" if args.source == "fma" else SAMPLING_IDENTITY),
                    renderer_name=view,
                    renderer_version=1,
                    ox_model_id=client.model_id,
                    provider_revision=getattr(client, "provider_revision", "n/a"),
                    prompt_version=PROMPT_VERSION,
                    comparison_mode="pairwise",
                    replicate_index=replicate,
                )
                if cache.has(key) and not args.force:
                    stats["skipped_cached"] += 1
                    continue
                if not budget.acquire():
                    print("request cap reached — stopping early (cache keeps progress)")
                    _report(stats, preferences_by_view)
                    return 0
                try:
                    call = client.compare(prompt, query_views[view], a_views[view], b_views[view])
                except Exception as exc:  # one bad call must never kill the run
                    print(f"call failed ({case['case_id']}/{view}/rep{replicate}): {str(exc)[:150]}")
                    continue
                record = {
                    "cache_key": key,
                    "case_id": case["case_id"],
                    "view": view,
                    "replicate": replicate,
                    "parse_status": call.parse_status,
                    "latency_ms": round(call.latency_ms, 1),
                    "timestamp": time.time(),
                    "result": call.parsed.to_dict() if call.parsed else None,
                    "error_message": call.error_message,
                }
                cache.append(record)
                if call.parse_status == "ok" and call.parsed:
                    stats["ok"] += 1
                    preferences_by_view[view].append(call.parsed.preference)
                elif call.parse_status == "provider_error":
                    stats["provider_error"] += 1
                else:
                    stats["parse_error"] += 1

    _report(stats, preferences_by_view)
    return 0


def _report(stats: dict, preferences_by_view: dict[str, list[str]]) -> None:
    print(json.dumps({"stats": stats}, indent=2))
    for view, prefs in preferences_by_view.items():
        if not prefs:
            continue
        distinct = len(set(prefs)) > 1 or prefs.count(prefs[0]) == len(prefs)
        print(f"{view}: n={len(prefs)} self-consistency={prefs.count(max(set(prefs), key=prefs.count))}/{len(prefs)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="REQUIRED to issue real provider calls; without it the run uses the fake client")
    parser.add_argument("--enable-ox-alpha", action="store_true", help="alias of --live")
    parser.add_argument("--model", default=os.environ.get("OX_ALPHA_MODEL", DEFAULT_MODEL))
    parser.add_argument("--cases", type=int, default=6)
    parser.add_argument("--max-requests", type=int, default=50)
    parser.add_argument("--cache", default="reports/phase2/ox_alpha_cache.jsonl")
    parser.add_argument("--force", action="store_true", help="recompute completed cache entries")
    parser.add_argument("--source", choices=["synthetic", "fma"], default="synthetic")
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--embeddings", default="artifacts/phase1_full/embeddings.parquet")
    parser.add_argument("--audio-root", default="data/fma/fma_small")
    parser.add_argument("--queries", default="reports/phase1_queries.csv")
    args = parser.parse_args()

    live = args.live or args.enable_ox_alpha
    args.live = live
    if live and not os.environ.get("OPENROUTER_API_KEY"):
        print("REFUSING to run live: OPENROUTER_API_KEY is not set.", file=sys.stderr)
        return 2

    try:
        return run_smoke(args)
    except ValueError as exc:
        print(f"ABORTED before any request: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
