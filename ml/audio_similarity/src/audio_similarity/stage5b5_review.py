"""Blinded review and end-to-end metrics for Representative Library V4."""
from __future__ import annotations

import csv
import json
import os
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from .stage5b1a_discovery import YOUTUBE_VIDEO_ID
from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b3_minimal_selector import AUTO_SELECT
from .stage5b5_representative_v4 import (
    AUTOMATED_COVERAGE_GATE,
    AUTOMATED_SAFE_PRECISION_GATE,
    BENCHMARK_ID,
    RAW_TOP1_GATE,
    SAMPLE_SIZE,
    STATUS_DISCOVERY_COMPLETE,
    STATUS_SELECTOR_FROZEN_HIDDEN,
    TOP3_SAFE_GATE,
    Stage5B5Config,
    _json,
    load_v4_manifest,
)


LABELS = ("IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN")
SAFE_LABELS = frozenset({"IDEAL", "ACCEPTABLE"})
REVIEW_SCHEMA_VERSION = "stage5b5-representative-v4-human-review-v1"
QUEUE_SCHEMA_VERSION = "stage5b5-representative-v4-review-queue-v1"
FINAL_METRICS_SCHEMA_VERSION = "stage5b5-representative-v4-final-metrics-v1"
FAILURE_SCHEMA_VERSION = "stage5b5-representative-v4-failure-analysis-v1"
ARTIFACT_SCHEMA_VERSION = "stage5b5-representative-v4-artifact-manifest-v1"
STATUS_REVIEW_READY = "STAGE5B5_BLINDED_REVIEW_READY"
STATUS_COMPLETE = "STAGE5B5_REPRESENTATIVE_V4_COMPLETE"
MAX_NOTE_LENGTH = 2_000
REVIEW_COLUMNS = (
    "review_schema_version",
    "benchmark_id",
    "spotify_track_id",
    "expected_title",
    "expected_artists",
    "expected_album",
    "expected_duration_seconds",
    "expected_release_year",
    "discovery_mode",
    "query_variant_index",
    "query_artist",
    "search_query",
    "youtube_rank",
    "candidate_video_id",
    "candidate_url",
    "candidate_title",
    "candidate_uploader",
    "candidate_channel",
    "candidate_duration_seconds",
    "candidate_view_count",
    "candidate_description",
    "candidate_review_label",
    "candidate_note",
    "track_note",
)
ARTIFACT_NAMES = (
    "benchmark_manifest.json",
    "benchmark_manifest.sha256",
    "benchmark_config.json",
    "youtube_top3_discovery.json",
    "automated_selector_decisions.json",
    "preliminary_selector_metrics.json",
    "human_review_queue.json",
    "human_review.csv",
    "final_metrics.json",
    "failure_analysis.json",
    "representative_v4_report.md",
)


def first_safe_rank(rows: list[dict[str, str]]) -> int | None:
    for row in sorted(rows, key=lambda item: int(item["youtube_rank"])):
        if row["candidate_review_label"] in SAFE_LABELS:
            return int(row["youtube_rank"])
    return None


def _oracle_next_rank(rows: list[dict[str, str]]) -> int | None:
    for row in sorted(rows, key=lambda item: int(item["youtube_rank"])):
        if row["candidate_review_label"] in SAFE_LABELS:
            return None
        if not row["candidate_review_label"]:
            return int(row["youtube_rank"])
    return None


def _oracle_complete(rows: list[dict[str, str]]) -> bool:
    return not rows or first_safe_rank(rows) is not None or all(
        row["candidate_review_label"] for row in rows
    )


def next_review_requirement(
    rows: list[dict[str, str]], selected_rank: int | None
) -> tuple[str, int] | None:
    if not _oracle_complete(rows):
        rank = _oracle_next_rank(rows)
        if rank is None:
            raise Stage5B1AValidationError("invalid V4 oracle state")
        return "TOP3_ORACLE", rank
    if selected_rank is not None:
        selected = next(
            (row for row in rows if int(row["youtube_rank"]) == selected_rank),
            None,
        )
        if selected is None:
            raise Stage5B1AValidationError("selector rank is absent from candidate pool")
        if not selected["candidate_review_label"]:
            return "BLIND_COVERAGE_SUPPLEMENT", selected_rank
    return None


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Stage 5B.5 review columns")
        rows = list(reader)
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        identity = (row["benchmark_id"], row["youtube_rank"], row["candidate_video_id"])
        if identity in seen or not YOUTUBE_VIDEO_ID.fullmatch(row["candidate_video_id"]):
            raise Stage5B1AValidationError("invalid Stage 5B.5 review identity")
        seen.add(identity)
        if row["review_schema_version"] != REVIEW_SCHEMA_VERSION:
            raise Stage5B1AValidationError("unexpected Stage 5B.5 review schema")
        label = row["candidate_review_label"].strip().upper()
        if label and label not in LABELS:
            raise Stage5B1AValidationError("invalid Stage 5B.5 human label")
        row["candidate_review_label"] = label
        if len(row["candidate_note"]) > MAX_NOTE_LENGTH or len(row["track_note"]) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("Stage 5B.5 review note is too long")
    return rows


def _group_rows(
    path: Path, expected_ids: list[str]
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {
        benchmark_id: [] for benchmark_id in expected_ids
    }
    for row in _read_rows(path):
        if row["benchmark_id"] not in grouped:
            raise Stage5B1AValidationError("review contains unknown V4 track")
        grouped[row["benchmark_id"]].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: int(row["youtube_rank"]))
        if len(rows) > 3 or [int(row["youtube_rank"]) for row in rows] != list(
            range(1, len(rows) + 1)
        ):
            raise Stage5B1AValidationError("V4 review candidate ranks changed")
    return grouped


def _decision_ranks(path: Path) -> dict[str, int | None]:
    value = _json(path)
    if (
        value.get("status") != STATUS_SELECTOR_FROZEN_HIDDEN
        or value.get("human_labels_visible") is not False
        or len(value.get("tracks", [])) != SAMPLE_SIZE
    ):
        raise Stage5B1AValidationError("invalid hidden V4 selector decisions")
    return {row["benchmark_id"]: row["selected_rank"] for row in value["tracks"]}


def write_human_review_artifacts(config: Stage5B5Config) -> tuple[dict[str, Any], Path]:
    manifest = load_v4_manifest(config)
    discovery_path = config.output_dir / "youtube_top3_discovery.json"
    decisions_path = config.output_dir / "automated_selector_decisions.json"
    discovery = _json(discovery_path)
    if discovery.get("status") != STATUS_DISCOVERY_COMPLETE:
        raise Stage5B1AValidationError("complete V4 discovery is required for review")
    ranks = _decision_ranks(decisions_path)
    targets = {row["benchmark_id"]: row for row in manifest["tracks"]}
    cases = []
    review_rows = []
    for track_row in discovery["tracks"]:
        benchmark_id = track_row["benchmark_id"]
        target = targets[benchmark_id]
        outcome = track_row["discovery"]
        candidates = outcome["candidates"]
        cases.append(
            {
                "benchmark_id": benchmark_id,
                "spotify_target": target,
                "candidate_count": len(candidates),
                "candidate_video_ids_by_native_rank": [
                    candidate["youtube_video_id"] for candidate in candidates
                ],
                "discovery_mode": outcome["discovery_mode"],
                "successful_query": outcome["successful_query"],
                "discovery_error": outcome["error"],
            }
        )
        for candidate in candidates:
            review_rows.append(
                {
                    "review_schema_version": REVIEW_SCHEMA_VERSION,
                    "benchmark_id": benchmark_id,
                    "spotify_track_id": target["spotify_track_id"],
                    "expected_title": target["title"],
                    "expected_artists": " | ".join(target["artists"]),
                    "expected_album": target.get("album") or "",
                    "expected_duration_seconds": target["duration_ms"] / 1000,
                    "expected_release_year": target.get("release_year") or "",
                    "discovery_mode": outcome["discovery_mode"] or "",
                    "query_variant_index": (
                        outcome["query_variant_index"]
                        if outcome["query_variant_index"] is not None
                        else ""
                    ),
                    "query_artist": outcome["query_artist"] or "",
                    "search_query": outcome["successful_query"] or outcome["query_plan"]["primary"]["query"],
                    "youtube_rank": candidate["rank"],
                    "candidate_video_id": candidate["youtube_video_id"],
                    "candidate_url": candidate.get("canonical_url") or candidate.get("url") or "",
                    "candidate_title": candidate.get("title") or "",
                    "candidate_uploader": candidate.get("uploader") or "",
                    "candidate_channel": candidate.get("channel") or "",
                    "candidate_duration_seconds": (
                        candidate.get("duration_seconds")
                        if candidate.get("duration_seconds") is not None
                        else ""
                    ),
                    "candidate_view_count": (
                        candidate.get("view_count")
                        if candidate.get("view_count") is not None
                        else ""
                    ),
                    "candidate_description": candidate.get("description") or "",
                    "candidate_review_label": "",
                    "candidate_note": "",
                    "track_note": "",
                }
            )
    queue = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "status": STATUS_REVIEW_READY,
        "benchmark_manifest_sha256": config.manifest_sha256,
        "discovery_sha256": file_sha256(discovery_path),
        "protocol": "SEQUENTIAL_NATIVE_RANKS_UNTIL_SAFE_PLUS_BLIND_SELECTED_RANK_SUPPLEMENT",
        "selector_decisions_visible_to_reviewer": False,
        "safe_labels": sorted(SAFE_LABELS),
        "rank1_non_safe_reason_required": True,
        "track_count": len(cases),
        "candidate_count": len(review_rows),
        "cases": cases,
    }
    if any("selected" in key for key in queue):
        raise Stage5B1AValidationError("selector output leaked into V4 review queue")
    atomic_json(config.output_dir / "human_review_queue.json", queue)
    review_path = config.output_dir / "human_review.csv"
    if review_path.exists():
        existing = _read_rows(review_path)
        expected = [
            (row["benchmark_id"], str(row["youtube_rank"]), row["candidate_video_id"])
            for row in review_rows
        ]
        actual = [
            (row["benchmark_id"], row["youtube_rank"], row["candidate_video_id"])
            for row in existing
        ]
        if actual != expected:
            raise Stage5B1AValidationError("existing V4 review identities changed")
        return queue, review_path
    temporary = review_path.with_suffix(review_path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(review_rows)
    temporary.replace(review_path)
    return queue, review_path


class Stage5B5ReviewStore:
    """Expose only the next blinded judgment while retaining autosave semantics."""

    def __init__(self, review_path: str | Path, decisions_path: str | Path) -> None:
        self.review_path = Path(review_path).resolve()
        self.decisions_path = Path(decisions_path).resolve()
        self._selected_ranks = _decision_ranks(self.decisions_path)
        queue = _json(self.review_path.parent / "human_review_queue.json")
        self._queue_cases = {row["benchmark_id"]: row for row in queue["cases"]}
        if set(self._queue_cases) != set(self._selected_ranks):
            raise Stage5B1AValidationError("V4 review and decision identities differ")
        self._lock = threading.RLock()
        self._read_grouped()

    def _read_grouped(self) -> dict[str, list[dict[str, str]]]:
        return _group_rows(self.review_path, list(self._selected_ranks))

    @staticmethod
    def _number(value: str, kind: type[int] | type[float]) -> int | float | None:
        return kind(value) if value.strip() else None

    def session(self) -> dict[str, Any]:
        with self._lock:
            grouped = self._read_grouped()
            cases = []
            completed = 0
            reviewed = 0
            for benchmark_id, rows in grouped.items():
                queue_case = self._queue_cases[benchmark_id]
                requirement = next_review_requirement(
                    rows, self._selected_ranks[benchmark_id]
                )
                reviewed += sum(bool(row["candidate_review_label"]) for row in rows)
                if requirement is None:
                    completed += 1
                    visible = [row for row in rows if row["candidate_review_label"]]
                    phase = "COMPLETE"
                    next_rank = None
                else:
                    phase, next_rank = requirement
                    visible = [
                        row
                        for row in rows
                        if row["candidate_review_label"]
                        or int(row["youtube_rank"]) == next_rank
                    ]
                target = queue_case["spotify_target"]
                cases.append(
                    {
                        "stable_track_id": benchmark_id,
                        "track": {
                            "title": target["title"],
                            "artists": target["artists"],
                            "album": target.get("album"),
                            "duration_seconds": target["duration_ms"] / 1000,
                            "release_year": target.get("release_year"),
                        },
                        "query": queue_case["successful_query"],
                        "discovery_mode": queue_case["discovery_mode"],
                        "candidate_unavailable": not rows,
                        "discovery_error": queue_case["discovery_error"],
                        "review_complete": requirement is None,
                        "review_phase": phase,
                        "next_required_rank": next_rank,
                        "selector_decision_visible": False,
                        "candidates": [
                            {
                                "rank": int(row["youtube_rank"]),
                                "video_id": row["candidate_video_id"],
                                "url": row["candidate_url"],
                                "title": row["candidate_title"],
                                "uploader": row["candidate_uploader"] or None,
                                "channel": row["candidate_channel"] or None,
                                "duration_seconds": self._number(
                                    row["candidate_duration_seconds"], float
                                ),
                                "view_count": self._number(row["candidate_view_count"], int),
                                "description": row["candidate_description"] or None,
                                "review": {
                                    "label": row["candidate_review_label"],
                                    "note": row["candidate_note"],
                                },
                                "is_current": int(row["youtube_rank"]) == next_rank,
                            }
                            for row in visible
                        ],
                    }
                )
            return {
                "schema_version": "stage5b5-representative-v4-review-session-v1",
                "mode": "stage5b5_representative_v4_review",
                "labels": list(LABELS),
                "export_filename": "stage5b5-representative-v4-human-review.csv",
                "selector_decisions_visible": False,
                "progress": {
                    "reviewed_candidates": reviewed,
                    "remaining_tracks": SAMPLE_SIZE - completed,
                    "total_candidates": sum(len(rows) for rows in grouped.values()),
                    "completed_tracks": completed,
                    "total_tracks": SAMPLE_SIZE,
                },
                "cases": cases,
            }

    def submit(
        self,
        stable_track_id: str,
        video_id: str,
        label: str,
        candidate_note: str = "",
        track_note: str = "",
    ) -> dict[str, Any]:
        label = str(label or "").strip().upper()
        candidate_note = str(candidate_note or "")
        track_note = str(track_note or "")
        if label not in (*LABELS, ""):
            raise Stage5B1AValidationError("invalid Stage 5B.5 review label")
        if len(candidate_note) > MAX_NOTE_LENGTH or len(track_note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("Stage 5B.5 review note is too long")
        with self._lock:
            grouped = self._read_grouped()
            rows = grouped.get(stable_track_id, [])
            target = next(
                (row for row in rows if row["candidate_video_id"] == video_id), None
            )
            if target is None:
                raise Stage5B1AValidationError("unknown Stage 5B.5 review identity")
            requirement = next_review_requirement(
                rows, self._selected_ranks[stable_track_id]
            )
            if (
                label
                and not target["candidate_review_label"]
                and (requirement is None or int(target["youtube_rank"]) != requirement[1])
            ):
                raise Stage5B1AValidationError("review the required V4 candidate first")
            target["candidate_review_label"] = label
            target["candidate_note"] = candidate_note
            all_rows = _read_rows(self.review_path)
            updates = {
                (row["benchmark_id"], row["candidate_video_id"]): row
                for grouped_rows in grouped.values()
                for row in grouped_rows
            }
            for row in all_rows:
                row.update(updates[(row["benchmark_id"], row["candidate_video_id"])])
                if row["benchmark_id"] == stable_track_id:
                    row["track_note"] = track_note
            temporary = self.review_path.with_suffix(
                self.review_path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
            )
            with temporary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(all_rows)
            temporary.replace(self.review_path)
        return {
            "ok": True,
            "stable_track_id": stable_track_id,
            "video_id": video_id,
            "review": {"label": label, "note": candidate_note},
            "track_note": track_note,
        }


def validate_complete_review(
    review_path: Path, decisions_path: Path
) -> dict[str, list[dict[str, str]]]:
    ranks = _decision_ranks(decisions_path)
    grouped = _group_rows(review_path, list(ranks))
    incomplete = [
        benchmark_id
        for benchmark_id, rows in grouped.items()
        if next_review_requirement(rows, ranks[benchmark_id]) is not None
    ]
    if incomplete:
        raise Stage5B1AValidationError(
            f"Stage 5B.5 human review incomplete for {len(incomplete)} tracks"
        )
    missing_reasons = [
        benchmark_id
        for benchmark_id, rows in grouped.items()
        if rows
        and rows[0]["candidate_review_label"] in {"WRONG", "UNCERTAIN"}
        and not rows[0]["candidate_note"].strip()
    ]
    if missing_reasons:
        raise Stage5B1AValidationError(
            f"Stage 5B.5 rank-1 reason missing for {len(missing_reasons)} tracks"
        )
    return grouped


def _label_counts(values: list[str]) -> dict[str, int]:
    counts = Counter(values)
    return {label: counts[label] for label in LABELS}


def _failure_category(row: dict[str, str]) -> str:
    text = " ".join(
        (row["candidate_title"], row["candidate_description"], row["candidate_note"])
    ).casefold()
    patterns = (
        ("COVER_OR_ALTERNATE_PERFORMER", r"\bcover(?:ed)?\b|tribute"),
        ("INSTRUMENTAL_OR_KARAOKE", r"\binstrumental\b|karaoke|without vocals"),
        ("MULTI_TRACK_OR_NOT_ISOLATED", r"\bfull album\b|playlist|compilation|hour mix"),
        ("WRONG_REMIX_OR_VERSION", r"\bremix\b|extended|sped|slowed|nightcore"),
        ("LIVE_VS_STUDIO", r"\blive\b|concert|stage|fancam|performance"),
        ("LYRIC_OR_FAN_EDIT_UNSUITABLE", r"lyrics?|fan.?made|\bamv\b"),
    )
    for category, pattern in patterns:
        if re.search(pattern, text):
            return category
    if row["candidate_review_label"] == "UNCERTAIN":
        return "METADATA_INSUFFICIENT"
    return "TITLE_ARTIST_AMBIGUITY_OR_SEARCH_ODDITY"


def compute_final_metrics(
    grouped: dict[str, list[dict[str, str]]],
    decisions: dict[str, Any],
    discovery: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    decision_rows = {row["benchmark_id"]: row for row in decisions["tracks"]}
    first_safe = {
        benchmark_id: first_safe_rank(rows) for benchmark_id, rows in grouped.items()
    }
    first_safe_counts = Counter(
        f"rank_{rank}" if rank is not None else "none"
        for rank in first_safe.values()
    )
    top1_safe = sum(rank == 1 for rank in first_safe.values())
    top2_safe = sum(rank is not None and rank <= 2 for rank in first_safe.values())
    top3_safe = sum(rank is not None for rank in first_safe.values())
    top1_labels = _label_counts(
        [rows[0]["candidate_review_label"] for rows in grouped.values() if rows]
    )
    selected_rows = []
    for benchmark_id, decision in decision_rows.items():
        selected_rank = decision["selected_rank"]
        if selected_rank is None:
            continue
        selected_rows.append((decision, grouped[benchmark_id][selected_rank - 1]))
    selected_labels = _label_counts(
        [row["candidate_review_label"] for _, row in selected_rows]
    )
    automated_safe = selected_labels["IDEAL"] + selected_labels["ACCEPTABLE"]
    auto_count = len(selected_rows)
    coverage = auto_count / SAMPLE_SIZE
    precision = automated_safe / auto_count if auto_count else 0.0
    safe_yield = automated_safe / SAMPLE_SIZE
    discovery_summary = discovery["summary"]
    trigger_count = discovery_summary["fallback_trigger_count"]
    attempts = [
        attempt
        for track in discovery["tracks"]
        for attempt in track["discovery"]["attempts"]
    ]
    q0_times = [
        attempt["elapsed_seconds"]
        for attempt in attempts
        if attempt["query_variant_index"] == 0
    ]
    fallback_times = [
        attempt["elapsed_seconds"]
        for attempt in attempts
        if attempt["query_variant_index"] > 0
    ]
    criteria = {
        "raw_top1_safe": top1_safe / SAMPLE_SIZE >= RAW_TOP1_GATE,
        "top3_safe": top3_safe / SAMPLE_SIZE >= TOP3_SAFE_GATE,
        "automated_coverage": coverage >= AUTOMATED_COVERAGE_GATE,
        "automated_safe_precision": precision >= AUTOMATED_SAFE_PRECISION_GATE,
        "human_labels_excluded_from_decisions": decisions["scope_guards"][
            "human_labels_used_in_decisions"
        ]
        is False,
        "frozen_contracts_unchanged": decisions["selector"]["modified_for_v4"] is False,
    }
    verdict = (
        "REPRESENTATIVE_V4_FINAL_VALIDATION_PASSED"
        if all(criteria.values())
        else "REPRESENTATIVE_V4_FINAL_VALIDATION_FAILED"
    )
    metrics = {
        "schema_version": FINAL_METRICS_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "verdict": verdict,
        "denominator_tracks": SAMPLE_SIZE,
        "criteria": criteria,
        "discovery": {
            "tracks_with_candidates": discovery_summary["tracks_with_candidates"],
            "candidate_discovery_rate": discovery_summary["tracks_with_candidates"] / SAMPLE_SIZE,
            "q0_success_count": discovery_summary["primary_success_count"],
            "q0_success_rate": discovery_summary["primary_success_count"] / SAMPLE_SIZE,
            "fallback_trigger_count": trigger_count,
            "fallback_trigger_rate": trigger_count / SAMPLE_SIZE,
            "fallback_recovery_count": discovery_summary["fallback_success_count"],
            "fallback_recovery_rate_when_triggered": (
                discovery_summary["fallback_success_count"] / trigger_count
                if trigger_count
                else None
            ),
            "provider_error_count": discovery_summary["provider_error_count"],
            "unresolved_zero_candidate_count": discovery_summary[
                "all_query_variants_empty_count"
            ],
            "provider_request_count": discovery_summary["provider_request_count"],
            "request_amplification": discovery_summary["provider_request_count"] / SAMPLE_SIZE,
            "latency_seconds": {
                "q0_total": sum(q0_times),
                "q0_mean": sum(q0_times) / len(q0_times),
                "fallback_total": sum(fallback_times),
                "fallback_mean_per_request": (
                    sum(fallback_times) / len(fallback_times) if fallback_times else None
                ),
            },
        },
        "human_oracle": {
            "top1_label_counts": top1_labels,
            "top1_unavailable_count": sum(not rows for rows in grouped.values()),
            "top1_safe_count": top1_safe,
            "top1_safe_rate": top1_safe / SAMPLE_SIZE,
            "top2_safe_count": top2_safe,
            "top2_safe_rate": top2_safe / SAMPLE_SIZE,
            "top3_safe_count": top3_safe,
            "top3_safe_rate": top3_safe / SAMPLE_SIZE,
            "first_safe_rank_distribution": {
                key: first_safe_counts[key]
                for key in ("rank_1", "rank_2", "rank_3", "none")
            },
            "reviewed_candidate_count": sum(
                bool(row["candidate_review_label"])
                for rows in grouped.values()
                for row in rows
            ),
        },
        "automated_selection": {
            "auto_select_count": auto_count,
            "automated_coverage": coverage,
            "match_uncertain_count": SAMPLE_SIZE - auto_count,
            "selected_rank_distribution": {
                f"rank_{rank}": sum(
                    row["selected_rank"] == rank for row in decision_rows.values()
                )
                for rank in (1, 2, 3)
            }
            | {"none": sum(row["selected_rank"] is None for row in decision_rows.values())},
            "selected_human_label_counts": selected_labels,
            "human_safe_count": automated_safe,
            "human_safe_precision": precision,
            "end_to_end_automated_safe_yield": safe_yield,
            "wrong_selection_count": selected_labels["WRONG"],
            "wrong_selection_rate_all_tracks": selected_labels["WRONG"] / SAMPLE_SIZE,
            "uncertain_selection_count": selected_labels["UNCERTAIN"],
            "unresolved_or_manual_tail_count": SAMPLE_SIZE - automated_safe,
            "unresolved_or_manual_tail_rate": (
                SAMPLE_SIZE - automated_safe
            )
            / SAMPLE_SIZE,
        },
        "scope_guards": {
            "query_tuning": False,
            "selector_tuning": False,
            "human_labels_used_in_decisions": False,
            "post_freeze_substitutions": 0,
            "alternate_provider_fallbacks": 0,
            "production_activation": False,
            "audio_downloads": 0,
            "video_downloads": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }
    failures = []
    for benchmark_id, rows in grouped.items():
        decision = decision_rows[benchmark_id]
        safe_rank = first_safe[benchmark_id]
        selected_rank = decision["selected_rank"]
        selected_label = (
            rows[selected_rank - 1]["candidate_review_label"]
            if selected_rank is not None
            else None
        )
        if safe_rank == 1 and selected_label in SAFE_LABELS:
            continue
        failures.append(
            {
                "benchmark_id": benchmark_id,
                "target_title": decision["spotify_target"]["title"],
                "first_safe_rank": safe_rank,
                "selector_decision": decision["decision"],
                "selected_rank": selected_rank,
                "selected_human_label": selected_label,
                "rank1": (
                    {
                        "video_id": rows[0]["candidate_video_id"],
                        "title": rows[0]["candidate_title"],
                        "human_label": rows[0]["candidate_review_label"],
                        "human_note": rows[0]["candidate_note"],
                        "category": _failure_category(rows[0]),
                    }
                    if rows
                    else None
                ),
            }
        )
    failure = {
        "schema_version": FAILURE_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "case_count": len(failures),
        "top3_miss_count": sum(row["first_safe_rank"] is None for row in failures),
        "automated_wrong_count": selected_labels["WRONG"],
        "cases": failures,
    }
    return metrics, failure


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def write_closeout_artifacts(
    config: Stage5B5Config,
    *,
    focused_passed: int,
    stage5b_passed: int | None = None,
    full_passed: int | None = None,
    full_deselected: int | None = None,
) -> dict[str, Any]:
    decisions_path = config.output_dir / "automated_selector_decisions.json"
    decisions = _json(decisions_path)
    discovery = _json(config.output_dir / "youtube_top3_discovery.json")
    grouped = validate_complete_review(
        config.output_dir / "human_review.csv", decisions_path
    )
    metrics, failure = compute_final_metrics(grouped, decisions, discovery)
    metrics["verification"] = {
        "focused": focused_passed,
        "stage5b_regressions": stage5b_passed,
        "full_non_heavy": full_passed,
        "full_deselected": full_deselected,
    }
    metrics["criteria"]["tests_passed"] = focused_passed > 0 and (
        stage5b_passed is None or stage5b_passed > 0
    ) and (full_passed is None or full_passed > 0)
    if not all(metrics["criteria"].values()):
        metrics["verdict"] = "REPRESENTATIVE_V4_FINAL_VALIDATION_FAILED"
    atomic_json(config.output_dir / "final_metrics.json", metrics)
    atomic_json(config.output_dir / "failure_analysis.json", failure)
    _write_report(config, metrics, failure)
    implementation = {
        "benchmark": "src/audio_similarity/stage5b5_representative_v4.py",
        "review": "src/audio_similarity/stage5b5_review.py",
        "cli": "src/audio_similarity/cli/stage5b5_representative_v4.py",
        "review_server": "src/audio_similarity/cli/stage5b5_review_server.py",
        "tests": "tests/test_stage5b5_representative_v4.py",
    }
    manifest = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "status": STATUS_COMPLETE,
        "verdict": metrics["verdict"],
        "artifacts": {
            name: {
                "sha256": file_sha256(config.output_dir / name),
                "size_bytes": (config.output_dir / name).stat().st_size,
            }
            for name in ARTIFACT_NAMES
        },
        "implementation": {
            name: {
                "path": path,
                "sha256": file_sha256(config.project_root / path),
                "size_bytes": (config.project_root / path).stat().st_size,
            }
            for name, path in implementation.items()
        },
        "scope_guards": metrics["scope_guards"],
    }
    atomic_json(config.output_dir / "artifact_manifest.json", manifest)
    return {
        "status": STATUS_COMPLETE,
        "verdict": metrics["verdict"],
        "end_to_end_automated_safe_yield": metrics["automated_selection"][
            "end_to_end_automated_safe_yield"
        ],
        "automated_safe_precision": metrics["automated_selection"][
            "human_safe_precision"
        ],
        "automated_coverage": metrics["automated_selection"]["automated_coverage"],
    }


def _write_report(
    config: Stage5B5Config, metrics: dict[str, Any], failure: dict[str, Any]
) -> None:
    manifest = load_v4_manifest(config)
    discovery = metrics["discovery"]
    oracle = metrics["human_oracle"]
    automated = metrics["automated_selection"]
    lines = [
        "# Stage 5B.5 — Representative Library V4 Final Validation",
        "",
        f"**Verdict: `{metrics['verdict']}`.**",
        "",
        "## Frozen pipeline",
        "",
        "```text",
        "Spotify metadata",
        "  -> Q0: raw sanitized title + first 3 credited artists",
        "  -> zero only: title + artist 1, then 2, then 3",
        "  -> first non-empty native Top-3",
        "  -> Stage 5B.3 minimal selector",
        "  -> automated selection or manual tail",
        "```",
        "",
        f"- manifest SHA-256: `{config.manifest_sha256}`",
        f"- sample seed: `{manifest['sample_seed']}`",
        f"- library / excluded / eligible / sampled: **{manifest['library_unique_track_count']} / {manifest['historically_excluded_track_count']} / {manifest['eligible_heldout_track_count']} / {SAMPLE_SIZE}**",
        "- overlap with V1/V2/V3/5B.4A-C: **0**",
        "- post-freeze substitutions: **0**",
        "",
        "## Discovery",
        "",
        f"- candidate discovery: **{discovery['tracks_with_candidates']}/{SAMPLE_SIZE} ({_pct(discovery['candidate_discovery_rate'])})**",
        f"- Q0 success: **{discovery['q0_success_count']}/{SAMPLE_SIZE} ({_pct(discovery['q0_success_rate'])})**",
        f"- fallback triggered / recovered: **{discovery['fallback_trigger_count']} / {discovery['fallback_recovery_count']}**",
        f"- fallback recovery when triggered: **{_pct(discovery['fallback_recovery_rate_when_triggered'])}**",
        f"- provider errors / unresolved empty: **{discovery['provider_error_count']} / {discovery['unresolved_zero_candidate_count']}**",
        f"- provider requests / amplification: **{discovery['provider_request_count']} / {discovery['request_amplification']:.2f}x**",
        "",
        "## Blinded human oracle",
        "",
        f"- Top-1 SAFE: **{oracle['top1_safe_count']}/{SAMPLE_SIZE} ({_pct(oracle['top1_safe_rate'])})**",
        f"- Top-3 SAFE: **{oracle['top3_safe_count']}/{SAMPLE_SIZE} ({_pct(oracle['top3_safe_rate'])})**",
        f"- first SAFE ranks: `{oracle['first_safe_rank_distribution']}`",
        f"- reviewed candidates: **{oracle['reviewed_candidate_count']}**",
        "",
        "## Frozen automated selector",
        "",
        f"- coverage: **{automated['auto_select_count']}/{SAMPLE_SIZE} ({_pct(automated['automated_coverage'])})**",
        f"- SAFE precision: **{automated['human_safe_count']}/{automated['auto_select_count']} ({_pct(automated['human_safe_precision'])})**",
        f"- end-to-end automated SAFE yield: **{automated['human_safe_count']}/{SAMPLE_SIZE} ({_pct(automated['end_to_end_automated_safe_yield'])})**",
        f"- WRONG selections: **{automated['wrong_selection_count']} ({_pct(automated['wrong_selection_rate_all_tracks'])})**",
        f"- unresolved/manual tail: **{automated['unresolved_or_manual_tail_count']} ({_pct(automated['unresolved_or_manual_tail_rate'])})**",
        "",
        "## Failure audit",
        "",
        f"- noteworthy cases: **{failure['case_count']}**",
        f"- Top-3 misses: **{failure['top3_miss_count']}**",
        f"- automated WRONG: **{failure['automated_wrong_count']}**",
        "",
        "| Target | First SAFE | Selector rank | Selected label |",
        "|---|---:|---:|---|",
        *[
            f"| {_cell(row['target_title'])} | {row['first_safe_rank'] or 'none'} | {row['selected_rank'] or 'none'} | {row['selected_human_label'] or 'none'} |"
            for row in failure["cases"]
        ],
        "",
        "## Decision",
        "",
        (
            "The complete frozen discovery and selection stack passed its held-out gates. This report validates the candidate architecture; it does not production-activate it."
            if metrics["verdict"] == "REPRESENTATIVE_V4_FINAL_VALIDATION_PASSED"
            else "The frozen stack did not pass every held-out gate. Preserve this benchmark unchanged and investigate only in a new calibration phase."
        ),
        "",
        "## Reproduction",
        "",
        "```bash",
        "uv run python -m audio_similarity.cli.stage5b5_representative_v4 freeze-manifest",
        "uv run python -m audio_similarity.cli.stage5b5_representative_v4 discover",
        "uv run python -m audio_similarity.cli.stage5b5_representative_v4 run-selector",
        "uv run python -m audio_similarity.cli.stage5b5_representative_v4 build-review",
        "uv run python -m audio_similarity.cli.stage5b5_representative_v4 closeout",
        "```",
        "",
        "No query or selector tuning, candidate substitution, media download, CLAP/MuQ run, or production activation occurred.",
        "",
    ]
    (config.output_dir / "representative_v4_report.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
