import csv
import itertools
import json
from pathlib import Path

from audio_similarity.stage5b1a2_comparison import build_provider_comparison
from audio_similarity.stage5b1a2_config import load_ytdlp_config
from audio_similarity.stage5b1a2_experiment import AWAITING_REVIEW, run_ytdlp_experiment
from audio_similarity.stage5b1a2_review import (
    METRICS_SCHEMA_VERSION,
    REVIEW_COLUMNS,
    load_ytdlp_review_labels,
    write_review_csv,
)
from audio_similarity.stage5b1a2_ytdlp import (
    YtDlpBackendResponse,
    YtDlpDiscoveryAdapter,
    YtDlpSearchError,
)
from audio_similarity.stage5b1a_models import load_frozen_manifest
from audio_similarity.stage5b1a_review import ReviewLabel, compute_metrics


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1a2_ytdlp.json"


def inputs():
    config = load_ytdlp_config(CONFIG)
    manifest = load_frozen_manifest(config.manifest_path, expected_sha256=config.manifest_sha256)
    return config, manifest


class SequentialBackend:
    version = "fake-ytdlp"

    def __init__(self, fail_query=None):
        self.fail_query = fail_query
        self.calls = []

    def search(self, expression):
        self.calls.append(expression)
        if self.fail_query and self.fail_query in expression:
            raise YtDlpSearchError(
                "YTDLP_EXTRACTION_ERROR", "injected", attempts=1, retryable=False, warnings=("warning",)
            )
        return YtDlpBackendResponse(
            {
                "entries": [
                    {
                        "_type": "url",
                        "ie_key": "Youtube",
                        "id": "dQw4w9WgXcQ",
                        "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
                        "title": "candidate",
                        "uploader": "uploader",
                        "channel": "channel",
                        "duration": 213,
                    }
                ]
            },
            (),
            self.version,
        )


def test_experiment_is_sequential_paced_failure_isolated_and_download_free():
    config, manifest = inputs()
    backend = SequentialBackend(fail_query="Crazy in Love")
    adapter = YtDlpDiscoveryAdapter(config.provider, config.query, backend, sleep=lambda _: None)
    clocks = itertools.count()
    pacing = []
    timers = iter((10.0, 55.0))
    results = run_ytdlp_experiment(
        manifest,
        config,
        adapter,
        clock=lambda: f"time-{next(clocks):03d}",
        timer=lambda: next(timers),
        sleep=pacing.append,
    )
    assert results["status"] == AWAITING_REVIEW
    assert len(backend.calls) == 25
    assert len(pacing) == 24 and set(pacing) == {1.0}
    assert results["summary"] == {
        "tracks": 25,
        "ytdlp_search_failures": 1,
        "tracks_with_zero_youtube_candidates": 1,
        "deduplicated_candidate_video_ids": 24,
        "tracks_with_warnings": 1,
        "warning_count": 1,
    }
    assert results["elapsed_wall_seconds"] == 45.0
    assert set(results["media_activity"].values()) == {0}
    assert results["tracks"][2]["error"]["category"] == "YTDLP_EXTRACTION_ERROR"
    assert results["tracks"][3]["error"] is None
    assert all(row["request"]["download"] is False for row in results["tracks"])


def test_review_contains_rich_candidate_metadata_and_no_automatic_labels(tmp_path):
    config, manifest = inputs()
    backend = SequentialBackend()
    results = run_ytdlp_experiment(
        manifest,
        config,
        YtDlpDiscoveryAdapter(config.provider, config.query, backend),
        clock=lambda: "fixed",
        timer=iter((0.0, 1.0)).__next__,
        sleep=lambda _: None,
    )
    output = tmp_path / "review.csv"
    write_review_csv(output, manifest, results)
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == REVIEW_COLUMNS
    assert rows[0]["candidate_1_video_id"] == "dQw4w9WgXcQ"
    assert rows[0]["candidate_1_uploader"] == "uploader"
    assert rows[0]["candidate_1_channel"] == "channel"
    assert rows[0]["candidate_1_duration_seconds"] == "213.0"
    assert rows[0]["review_label"] == ""
    labels = load_ytdlp_review_labels(output, candidate_counts={value: 1 for value in manifest.stable_track_ids})
    assert all(label.label == "" for label in labels)


def test_metrics_reuse_same_recall_denominator_and_gate_keys():
    config, _ = inputs()
    results = {
        "experiment_id": "stage5b1a2_ytdlp_youtube_search_feasibility",
        "tracks": [
            {"track": {"stable_track_id": "a"}, "candidates": [{}], "error": None},
            {"track": {"stable_track_id": "b"}, "candidates": [{}], "error": None},
            {"track": {"stable_track_id": "c"}, "candidates": [], "error": {"category": "failure"}},
        ],
    }
    metrics = compute_metrics(
        results,
        (ReviewLabel("a", "1", ""), ReviewLabel("b", "3", ""), ReviewLabel("c", "NOT_IN_TOP_5", "")),
        config.gate,
        metrics_schema_version=METRICS_SCHEMA_VERSION,
        request_failure_key="ytdlp_search_failure_count",
    )
    assert metrics["recall_at_1"]["value"] == 1 / 3
    assert metrics["recall_at_3"]["value"] == 2 / 3
    assert metrics["recall_at_5"]["value"] == 2 / 3
    assert metrics["ytdlp_search_failure_count"] == 1
    assert metrics["feasibility_verdict"] == "FAIL"


def test_provider_comparison_is_coverage_only_until_both_metrics_exist(tmp_path):
    config, manifest = inputs()
    results = run_ytdlp_experiment(
        manifest,
        config,
        YtDlpDiscoveryAdapter(config.provider, config.query, SequentialBackend()),
        clock=lambda: "fixed",
        timer=iter((0.0, 1.0)).__next__,
        sleep=lambda _: None,
    )
    comparison = build_provider_comparison(
        config.comparison_sources["firecrawl_results"],
        results,
        firecrawl_metrics_path=tmp_path / "firecrawl-missing.json",
        ytdlp_metrics_path=tmp_path / "ytdlp-missing.json",
    )
    assert comparison["comparison_scope"] == "coverage_and_metadata_only"
    assert comparison["correctness_comparison_status"] == "PENDING_HUMAN_REVIEW_FOR_BOTH_PROVIDERS"
    assert comparison["providers"]["firecrawl"]["coverage"]["tracks"] == 25
    assert comparison["providers"]["yt_dlp"]["coverage"]["tracks_with_candidates"] == 25
    assert comparison["providers"]["yt_dlp"]["metadata_richness"]["populated_candidate_fields"]["duration_seconds"] == 25


def test_provider_comparison_supports_recall_only_after_complete_labels(tmp_path):
    config, manifest = inputs()
    results = run_ytdlp_experiment(
        manifest,
        config,
        YtDlpDiscoveryAdapter(config.provider, config.query, SequentialBackend()),
        clock=lambda: "fixed",
        timer=iter((0.0, 1.0)).__next__,
        sleep=lambda _: None,
    )
    metrics = {
        "recall_at_1": {"numerator": 20, "denominator": 25, "value": 0.8},
        "recall_at_3": {"numerator": 23, "denominator": 25, "value": 0.92},
        "recall_at_5": {"numerator": 24, "denominator": 25, "value": 0.96},
        "feasibility_verdict": "PASS",
    }
    firecrawl_metrics = tmp_path / "firecrawl.json"
    ytdlp_metrics = tmp_path / "ytdlp.json"
    firecrawl_metrics.write_text(json.dumps(metrics))
    ytdlp_metrics.write_text(json.dumps(metrics))
    comparison = build_provider_comparison(
        config.comparison_sources["firecrawl_results"],
        results,
        firecrawl_metrics_path=firecrawl_metrics,
        ytdlp_metrics_path=ytdlp_metrics,
    )
    assert comparison["comparison_scope"] == "coverage_metadata_and_human_recall"
    assert comparison["correctness_comparison_status"] == "AVAILABLE"
    assert comparison["providers"]["yt_dlp"]["correctness"]["recall_at_5"]["value"] == 0.96
