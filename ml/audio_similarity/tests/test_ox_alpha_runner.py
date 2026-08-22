"""Live-gate and guardrail tests for the ox-alpha smoke runner.

These tests never issue network requests: live mode without credentials is
refused, and over-cap plans abort before any call.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys

import pytest

smoke = importlib.import_module("audio_similarity.cli.ox_alpha_smoke")


def test_synthetic_cases_are_deterministic_and_distinct():
    a = smoke.synthetic_cases(3)
    b = smoke.synthetic_cases(3)
    assert [c["case_id"] for c in a] == [c["case_id"] for c in b]
    assert not (a[0]["query"].tobytes() == a[1]["query"].tobytes())
    assert len(a) == 3


def test_render_case_views_returns_all_three_views():
    cases = smoke.synthetic_cases(1)
    cfg = smoke.RendererConfig(image_width=64, image_height=32)
    views = smoke.render_case_views(cases[0]["query"], cases[0]["sample_rate"], cfg)
    assert set(views) == {"waveform", "linear_stft", "log_mel"}
    assert all(v.startswith(b"\x89PNG") for v in views.values())


def test_planned_request_math():
    # 6 cases x 3 views x 3 replicates = 54 planned by default config
    assert 6 * len(smoke.VIEWS) * smoke.REPLICATES == 54


def test_budget_aborts_over_cap_before_any_call(tmp_path):
    args = argparse_namespace(live=False, cases=2, max_requests=5, cache=str(tmp_path / "c.jsonl"))
    with pytest.raises(ValueError, match="--max-requests"):
        # run_smoke raises during planning, before any request is issued
        smoke.run_smoke(args)


class argparse_namespace:
    def __init__(self, **kw):
        self.live = False
        self.enable_ox_alpha = False
        self.model = "fake-ox-alpha"
        self.cases = 2
        self.max_requests = 100
        self.cache = "unused.jsonl"
        self.force = False
        self.source = "synthetic"
        self.manifest = "data/manifests/fma_small.parquet"
        self.embeddings = "artifacts/phase1_full/embeddings.parquet"
        self.audio_root = "data/fma/fma_small"
        self.queries = "reports/phase1_queries.csv"
        for k, v in kw.items():
            setattr(self, k, v)


def test_fake_mode_run_completes_and_caches(tmp_path):
    cache_path = tmp_path / "cache.jsonl"
    args = argparse_namespace(cache=str(cache_path))
    exit_code = smoke.run_smoke(args)
    assert exit_code == 0
    cache = smoke.OxResultCache(cache_path)
    records = cache.records()
    assert len(records) == 2 * len(smoke.VIEWS) * smoke.REPLICATES  # 18
    assert all(r["parse_status"] == "ok" for r in records)


def test_live_refusal_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    completed = subprocess.run(
        [sys.executable, "-m", "audio_similarity.cli.ox_alpha_smoke", "--live"],
        capture_output=True,
        text=True,
        cwd=".",
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert completed.returncode == 2
    assert "REFUSING" in completed.stderr
