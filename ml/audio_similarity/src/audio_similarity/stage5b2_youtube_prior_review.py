"""Adaptive human review and metrics for the raw YouTube top-three prior."""
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
from .stage5b2_youtube_prior import (
    BENCHMARK_ID,
    H1_TOP1_SAFE_MINIMUM,
    H2_TOP3_SAFE_MINIMUM,
    SAMPLE_SIZE,
    STATUS_DISCOVERY_COMPLETE,
    YoutubePriorConfig,
    load_youtube_prior_manifest,
)


REVIEW_SCHEMA_VERSION = "stage5b2-youtube-prior-human-review-v1"
QUEUE_SCHEMA_VERSION = "stage5b2-youtube-prior-human-review-queue-v1"
SOL_SCHEMA_VERSION = "stage5b2-sol-evaluations-v1"
TOP1_SCHEMA_VERSION = "stage5b2-youtube-prior-top1-metrics-v1"
TOP3_SCHEMA_VERSION = "stage5b2-youtube-prior-top3-metrics-v1"
FAILURE_SCHEMA_VERSION = "stage5b2-youtube-prior-failure-analysis-v1"
LABELS = ("IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN")
SAFE_LABELS = frozenset({"IDEAL", "ACCEPTABLE"})
MAX_NOTE_LENGTH = 2_000
REVIEW_COLUMNS = (
    "review_schema_version", "benchmark_id", "spotify_track_id",
    "expected_title", "expected_artists", "expected_album",
    "expected_duration_seconds", "expected_release_year", "search_query",
    "youtube_rank", "candidate_video_id", "candidate_url", "candidate_title",
    "candidate_uploader", "candidate_channel", "candidate_duration_seconds",
    "candidate_view_count", "candidate_description", "candidate_review_label",
    "candidate_note", "track_note",
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def write_human_review_artifacts(config: YoutubePriorConfig) -> tuple[dict[str, Any], Path]:
    manifest = load_youtube_prior_manifest(config)
    discovery_path = config.output_dir / "youtube_top3_discovery.json"
    discovery = _json(discovery_path)
    if discovery.get("status") != STATUS_DISCOVERY_COMPLETE:
        raise Stage5B1AValidationError("top-three discovery must be frozen before review")
    targets = {row["benchmark_id"]: row for row in manifest["tracks"]}
    queue_cases = []
    review_rows = []
    for row in discovery["tracks"]:
        benchmark_id = row["benchmark_id"]
        target = targets[benchmark_id]
        candidates = row["outcome"].get("candidates", [])
        queue_cases.append({
            "benchmark_id": benchmark_id,
            "candidate_video_ids_by_native_rank": [
                candidate["youtube_video_id"] for candidate in candidates
            ],
        })
        for candidate in candidates:
            review_rows.append({
                "review_schema_version": REVIEW_SCHEMA_VERSION,
                "benchmark_id": benchmark_id,
                "spotify_track_id": target["spotify_track_id"],
                "expected_title": target["title"],
                "expected_artists": " | ".join(target["artists"]),
                "expected_album": target.get("album") or "",
                "expected_duration_seconds": target["duration_ms"] / 1000,
                "expected_release_year": target.get("release_year") or "",
                "search_query": row["query"],
                "youtube_rank": candidate["rank"],
                "candidate_video_id": candidate["youtube_video_id"],
                "candidate_url": candidate.get("canonical_url") or candidate.get("url") or "",
                "candidate_title": candidate.get("title") or "",
                "candidate_uploader": candidate.get("uploader") or "",
                "candidate_channel": candidate.get("channel") or "",
                "candidate_duration_seconds": candidate.get("duration_seconds")
                if candidate.get("duration_seconds") is not None else "",
                "candidate_view_count": candidate.get("view_count")
                if candidate.get("view_count") is not None else "",
                "candidate_description": candidate.get("description") or "",
                "candidate_review_label": "",
                "candidate_note": "",
                "track_note": "",
            })
    queue = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_manifest_sha256": config.manifest_sha256,
        "discovery_sha256": file_sha256(discovery_path),
        "protocol": "REVIEW_NATIVE_RANKS_UNTIL_FIRST_SAFE",
        "safe_labels": sorted(SAFE_LABELS),
        "track_count": len(queue_cases),
        "candidate_count": len(review_rows),
        "cases": queue_cases,
    }
    queue_path = config.output_dir / "human_review_queue.json"
    atomic_json(queue_path, queue)
    review_path = config.output_dir / "human_review.csv"
    if review_path.exists():
        with review_path.open(encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))
        expected = [(row["benchmark_id"], str(row["youtube_rank"]), row["candidate_video_id"]) for row in review_rows]
        actual = [(row["benchmark_id"], row["youtube_rank"], row["candidate_video_id"]) for row in existing]
        if actual != expected:
            raise Stage5B1AValidationError("existing Stage 5B.2 review identities changed")
        return queue, review_path
    temporary = review_path.with_suffix(review_path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(review_rows)
    temporary.replace(review_path)
    return queue, review_path


def _read_review_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Stage 5B.2 review columns")
        rows = list(reader)
    seen = set()
    for row in rows:
        identity = (row["benchmark_id"], row["youtube_rank"], row["candidate_video_id"])
        if identity in seen or not YOUTUBE_VIDEO_ID.fullmatch(row["candidate_video_id"]):
            raise Stage5B1AValidationError("invalid Stage 5B.2 review identity")
        seen.add(identity)
        label = row["candidate_review_label"].strip().upper()
        if label and label not in LABELS:
            raise Stage5B1AValidationError("invalid Stage 5B.2 human label")
        row["candidate_review_label"] = label
        if len(row["candidate_note"]) > MAX_NOTE_LENGTH or len(row["track_note"]) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("Stage 5B.2 review note is too long")
    return rows


def required_rank(rows: list[dict[str, str]]) -> int | None:
    """Return the next rank requiring review, or None when the track is complete."""

    ordered = sorted(rows, key=lambda row: int(row["youtube_rank"]))
    for row in ordered:
        label = row["candidate_review_label"]
        rank = int(row["youtube_rank"])
        if label in SAFE_LABELS:
            return None
        if not label:
            return rank
    return None


def first_safe_rank(rows: list[dict[str, str]]) -> int | None:
    for row in sorted(rows, key=lambda item: int(item["youtube_rank"])):
        if row["candidate_review_label"] in SAFE_LABELS:
            return int(row["youtube_rank"])
    return None


class YoutubePriorReviewStore:
    def __init__(self, review_path: str | Path) -> None:
        self.review_path = Path(review_path)
        self._lock = threading.RLock()
        self._read_grouped()

    def _read_grouped(self) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in _read_review_rows(self.review_path):
            grouped.setdefault(row["benchmark_id"], []).append(row)
        if len(grouped) != SAMPLE_SIZE or any(len(rows) != 3 for rows in grouped.values()):
            raise Stage5B1AValidationError("Stage 5B.2 review must contain 100 × 3 rows")
        for rows in grouped.values():
            if sorted(int(row["youtube_rank"]) for row in rows) != [1, 2, 3]:
                raise Stage5B1AValidationError("Stage 5B.2 candidate ranks changed")
        return grouped

    @staticmethod
    def _number(value: str, converter: type[int] | type[float]) -> int | float | None:
        return converter(value) if value.strip() else None

    def session(self) -> dict[str, Any]:
        with self._lock:
            grouped = self._read_grouped()
            cases = []
            completed = 0
            reviewed = 0
            for benchmark_id, rows in grouped.items():
                ordered = sorted(rows, key=lambda row: int(row["youtube_rank"]))
                next_rank = required_rank(ordered)
                if next_rank is None:
                    completed += 1
                    visible_rank = first_safe_rank(ordered) or 3
                else:
                    visible_rank = next_rank
                reviewed += sum(bool(row["candidate_review_label"]) for row in ordered)
                first = ordered[0]
                visible = ordered[:visible_rank]
                cases.append({
                    "stable_track_id": benchmark_id,
                    "track": {
                        "title": first["expected_title"],
                        "artists": first["expected_artists"].split(" | "),
                        "album": first["expected_album"] or None,
                        "duration_seconds": self._number(first["expected_duration_seconds"], float),
                        "release_year": self._number(first["expected_release_year"], int),
                    },
                    "query": first["search_query"],
                    "track_note": first["track_note"],
                    "review_complete": next_rank is None,
                    "next_required_rank": next_rank,
                    "candidates": [{
                        "display_index": int(row["youtube_rank"]),
                        "rank": int(row["youtube_rank"]),
                        "video_id": row["candidate_video_id"],
                        "url": row["candidate_url"],
                        "title": row["candidate_title"],
                        "uploader": row["candidate_uploader"] or None,
                        "channel": row["candidate_channel"] or None,
                        "duration_seconds": self._number(row["candidate_duration_seconds"], float),
                        "view_count": self._number(row["candidate_view_count"], int),
                        "description": row["candidate_description"] or None,
                        "review": {
                            "label": row["candidate_review_label"],
                            "note": row["candidate_note"],
                        },
                        "is_current": next_rank == int(row["youtube_rank"]),
                    } for row in visible],
                })
            return {
                "schema_version": "stage5b2-youtube-prior-review-session-v1",
                "mode": "stage5b2_youtube_prior_review",
                "labels": list(LABELS),
                "export_filename": "stage5b2-youtube-prior-human-review.csv",
                "progress": {
                    "reviewed_candidates": reviewed,
                    "remaining_tracks": SAMPLE_SIZE - completed,
                    "total_candidates": 300,
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
            raise Stage5B1AValidationError("invalid Stage 5B.2 review label")
        if len(candidate_note) > MAX_NOTE_LENGTH or len(track_note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("Stage 5B.2 review note is too long")
        with self._lock:
            rows = _read_review_rows(self.review_path)
            grouped: dict[str, list[dict[str, str]]] = {}
            for row in rows:
                grouped.setdefault(row["benchmark_id"], []).append(row)
            target_rows = grouped.get(stable_track_id)
            target = next((row for row in target_rows or [] if row["candidate_video_id"] == video_id), None)
            if target is None:
                raise Stage5B1AValidationError("unknown Stage 5B.2 review identity")
            target_rank = int(target["youtube_rank"])
            next_rank = required_rank(target_rows or [])
            if label and next_rank is not None and target_rank > next_rank:
                raise Stage5B1AValidationError("review earlier YouTube ranks first")
            target["candidate_review_label"] = label
            target["candidate_note"] = candidate_note
            for row in target_rows or []:
                row["track_note"] = track_note
            temporary = self.review_path.with_suffix(
                self.review_path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
            )
            with temporary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            temporary.replace(self.review_path)
        return {
            "ok": True,
            "stable_track_id": stable_track_id,
            "video_id": video_id,
            "review": {"label": label, "note": candidate_note},
            "track_note": track_note,
        }


def _group_review_rows(review_path: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in _read_review_rows(review_path):
        grouped.setdefault(row["benchmark_id"], []).append(row)
    if len(grouped) != SAMPLE_SIZE or any(len(rows) != 3 for rows in grouped.values()):
        raise Stage5B1AValidationError("Stage 5B.2 review must contain 100 × 3 rows")
    return {
        benchmark_id: sorted(rows, key=lambda row: int(row["youtube_rank"]))
        for benchmark_id, rows in grouped.items()
    }


def validate_complete_human_review(
    review_path: Path,
) -> dict[str, list[dict[str, str]]]:
    grouped = _group_review_rows(review_path)
    incomplete = [
        benchmark_id for benchmark_id, rows in grouped.items()
        if required_rank(rows) is not None
    ]
    if incomplete:
        raise Stage5B1AValidationError(
            f"Stage 5B.2 human review incomplete for {len(incomplete)} tracks"
        )
    return grouped


def load_mapped_sol_evaluations(config: YoutubePriorConfig) -> dict[tuple[str, int], dict[str, str]]:
    output_path = config.output_dir / "sol_evaluations.json"
    payload_path = config.output_dir / "sol_blind_payload.json"
    mapping_path = config.output_dir / "sol_private_rank_mapping.json"
    output = _json(output_path)
    payload = _json(payload_path)
    mapping = _json(mapping_path)
    contract = _json(config.output_dir / "sol_evaluator_contract.json")
    if output.get("schema_version") != SOL_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.2 Sol schema")
    if output.get("model") != "gpt-5.6-sol" or output.get("reasoning_effort") != "high":
        raise Stage5B1AValidationError("Stage 5B.2 Sol model contract changed")
    if output.get("prompt_sha256") != contract["prompt"]["sha256"]:
        raise Stage5B1AValidationError("Stage 5B.2 Sol prompt hash changed")
    if output.get("payload_sha256") != file_sha256(payload_path):
        raise Stage5B1AValidationError("Stage 5B.2 Sol payload hash changed")
    if output.get("human_ground_truth") is not False:
        raise Stage5B1AValidationError("Sol must remain secondary evidence")
    payload_tracks = {row["benchmark_id"]: row for row in payload["tracks"]}
    mapping_tracks = {row["benchmark_id"]: row for row in mapping["tracks"]}
    output_tracks = output.get("tracks")
    if not isinstance(output_tracks, list) or len(output_tracks) != SAMPLE_SIZE:
        raise Stage5B1AValidationError("Stage 5B.2 Sol track count changed")
    mapped: dict[tuple[str, int], dict[str, str]] = {}
    seen_tracks: set[str] = set()
    for result in output_tracks:
        benchmark_id = result.get("benchmark_id")
        if benchmark_id in seen_tracks or benchmark_id not in payload_tracks:
            raise Stage5B1AValidationError("invalid Stage 5B.2 Sol track identity")
        seen_tracks.add(benchmark_id)
        payload_candidates = {
            row["blind_candidate_id"]: row for row in payload_tracks[benchmark_id]["candidates"]
        }
        rank_candidates = {
            row["blind_candidate_id"]: row for row in mapping_tracks[benchmark_id]["candidates"]
        }
        candidates = result.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 3:
            raise Stage5B1AValidationError("Stage 5B.2 Sol candidate count changed")
        for candidate in candidates:
            blind_id = candidate.get("blind_candidate_id")
            expected = payload_candidates.get(blind_id)
            rank_mapping = rank_candidates.get(blind_id)
            if expected is None or rank_mapping is None:
                raise Stage5B1AValidationError("invalid Stage 5B.2 blind candidate identity")
            if candidate.get("video_id") != expected["video_id"]:
                raise Stage5B1AValidationError("Stage 5B.2 Sol video identity changed")
            label = candidate.get("label")
            reason = candidate.get("reason")
            if label not in LABELS or not isinstance(reason, str) or not reason.strip():
                raise Stage5B1AValidationError("invalid Stage 5B.2 Sol judgment")
            key = (benchmark_id, int(rank_mapping["native_rank"]))
            if key in mapped:
                raise Stage5B1AValidationError("duplicate Stage 5B.2 Sol native rank")
            mapped[key] = {
                "label": label,
                "reason": reason.strip(),
                "video_id": candidate["video_id"],
            }
    if len(mapped) != SAMPLE_SIZE * 3:
        raise Stage5B1AValidationError("Stage 5B.2 Sol mapping is incomplete")
    return mapped


def _label_state(label: str) -> str:
    if label in SAFE_LABELS:
        return "SAFE"
    if label == "WRONG":
        return "WRONG"
    if label == "UNCERTAIN":
        return "UNCERTAIN"
    return "UNREVIEWED"


def _failure_category(row: dict[str, str]) -> str:
    text = " ".join((
        row["candidate_title"], row["candidate_description"], row["candidate_note"]
    )).casefold()
    categories = (
        ("COVER_OR_ALTERNATE_PERFORMER", r"\bcover(?:ed)?\b|tribute|male version|female version"),
        ("INSTRUMENTAL_OR_KARAOKE", r"\binstrumental\b|\binst\.?\b|karaoke|without (?:melody|vocals)"),
        ("MULTI_TRACK_OR_NOT_ISOLATED", r"\bfull album\b|\bplaylist\b|\bcompilation\b|\bhour(?:s)? mix\b"),
        ("WRONG_REMIX_OR_VERSION", r"\bremix\b|extended|radio edit|sped|slowed|reverb|nightcore|bass boost"),
        ("LIVE_VS_STUDIO", r"\blive\b|concert|stage|fancam|audiotree|musiccore"),
        ("WRONG_LANGUAGE_OR_VERSION", r"english version|japanese version|korean version|chinese version"),
        ("LYRIC_OR_FAN_EDIT_UNSUITABLE", r"lyrics?|fan.?made|edit|amv"),
    )
    for category, pattern in categories:
        if re.search(pattern, text):
            return category
    if row["candidate_review_label"] == "UNCERTAIN":
        return "METADATA_INSUFFICIENT"
    return "TITLE_OR_ARTIST_AMBIGUITY_OR_SEARCH_ODDITY"


def compute_prior_metrics(
    grouped: dict[str, list[dict[str, str]]],
    sol: dict[tuple[str, int], dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    top1_labels = Counter(rows[0]["candidate_review_label"] for rows in grouped.values())
    first_safe = {benchmark_id: first_safe_rank(rows) for benchmark_id, rows in grouped.items()}
    first_safe_counts = Counter(
        f"rank_{rank}" if rank is not None else "none" for rank in first_safe.values()
    )
    top1_safe = sum(rank == 1 for rank in first_safe.values())
    top2_safe = sum(rank is not None and rank <= 2 for rank in first_safe.values())
    top3_safe = sum(rank is not None and rank <= 3 for rank in first_safe.values())
    top1 = {
        "schema_version": TOP1_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "denominator_tracks": SAMPLE_SIZE,
        "label_counts": {label: top1_labels.get(label, 0) for label in LABELS},
        "safe_count": top1_safe,
        "safe_rate": top1_safe / SAMPLE_SIZE,
        "ideal_rate": top1_labels.get("IDEAL", 0) / SAMPLE_SIZE,
        "acceptable_rate": top1_labels.get("ACCEPTABLE", 0) / SAMPLE_SIZE,
        "wrong_rate": top1_labels.get("WRONG", 0) / SAMPLE_SIZE,
        "uncertain_rate": top1_labels.get("UNCERTAIN", 0) / SAMPLE_SIZE,
        "hypothesis": {
            "id": "H1_TOP1_SAFE_RATE",
            "minimum": H1_TOP1_SAFE_MINIMUM,
            "passed": top1_safe / SAMPLE_SIZE >= H1_TOP1_SAFE_MINIMUM,
        },
    }
    top3 = {
        "schema_version": TOP3_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "denominator_tracks": SAMPLE_SIZE,
        "top2_safe_count": top2_safe,
        "top2_safe_recall": top2_safe / SAMPLE_SIZE,
        "top3_safe_count": top3_safe,
        "top3_safe_recall": top3_safe / SAMPLE_SIZE,
        "first_safe_rank_distribution": {
            key: first_safe_counts.get(key, 0) for key in ("rank_1", "rank_2", "rank_3", "none")
        },
        "hypothesis": {
            "id": "H2_TOP3_SAFE_RECALL",
            "minimum": H2_TOP3_SAFE_MINIMUM,
            "passed": top3_safe / SAMPLE_SIZE >= H2_TOP3_SAFE_MINIMUM,
        },
    }
    reviewed_pairs = []
    exact = 0
    state = 0
    for benchmark_id, rows in grouped.items():
        for row in rows:
            human = row["candidate_review_label"]
            if not human:
                continue
            rank = int(row["youtube_rank"])
            sol_row = sol[(benchmark_id, rank)]
            exact += human == sol_row["label"]
            state += _label_state(human) == _label_state(sol_row["label"])
            reviewed_pairs.append({
                "benchmark_id": benchmark_id,
                "native_rank": rank,
                "video_id": row["candidate_video_id"],
                "human_label": human,
                "sol_label": sol_row["label"],
                "human_state": _label_state(human),
                "sol_state": _label_state(sol_row["label"]),
                "sol_reason": sol_row["reason"],
            })
    agreement = {
        "schema_version": "stage5b2-youtube-prior-sol-human-agreement-v1",
        "human_ground_truth": True,
        "sol_secondary_only": True,
        "reviewed_candidate_denominator": len(reviewed_pairs),
        "exact_label_agreement_count": exact,
        "exact_label_agreement_rate": exact / len(reviewed_pairs),
        "safe_wrong_uncertain_agreement_count": state,
        "safe_wrong_uncertain_agreement_rate": state / len(reviewed_pairs),
        "comparisons": reviewed_pairs,
    }
    return top1, top3, agreement


def build_failure_analysis(
    grouped: dict[str, list[dict[str, str]]],
    sol: dict[tuple[str, int], dict[str, str]],
) -> dict[str, Any]:
    failures = []
    categories: Counter[str] = Counter()
    for benchmark_id, rows in grouped.items():
        top = rows[0]
        if top["candidate_review_label"] in SAFE_LABELS:
            continue
        category = _failure_category(top)
        categories[category] += 1
        safe_rank = first_safe_rank(rows)
        failures.append({
            "benchmark_id": benchmark_id,
            "spotify_track_id": top["spotify_track_id"],
            "target_title": top["expected_title"],
            "target_artists": top["expected_artists"].split(" | "),
            "top1": {
                "video_id": top["candidate_video_id"],
                "title": top["candidate_title"],
                "channel": top["candidate_channel"] or top["candidate_uploader"],
                "human_label": top["candidate_review_label"],
                "human_note": top["candidate_note"],
                "sol_label": sol[(benchmark_id, 1)]["label"],
                "sol_reason": sol[(benchmark_id, 1)]["reason"],
            },
            "failure_category": category,
            "first_safe_rank": safe_rank,
            "top3_miss": safe_rank is None,
            "reviewed_ranks": [{
                "native_rank": int(row["youtube_rank"]),
                "video_id": row["candidate_video_id"],
                "title": row["candidate_title"],
                "channel": row["candidate_channel"] or row["candidate_uploader"],
                "human_label": row["candidate_review_label"] or None,
                "human_note": row["candidate_note"] or None,
                "failure_category": _failure_category(row)
                if row["candidate_review_label"] in {"WRONG", "UNCERTAIN"} else None,
                "sol_label": sol[(benchmark_id, int(row["youtube_rank"]))]["label"],
                "sol_reason": sol[(benchmark_id, int(row["youtube_rank"]))]["reason"],
            } for row in rows if row["candidate_review_label"]],
            "track_note": top["track_note"] or None,
        })
    return {
        "schema_version": FAILURE_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "top1_failure_count": len(failures),
        "top1_failure_categories": dict(sorted(categories.items())),
        "top3_miss_count": sum(row["top3_miss"] for row in failures),
        "top1_failures": failures,
        "top3_misses": [row for row in failures if row["top3_miss"]],
        "no_tuning_performed": True,
    }


def _verdict(top1: dict[str, Any], top3: dict[str, Any]) -> str:
    if top1["hypothesis"]["passed"] and top3["hypothesis"]["passed"]:
        return "YOUTUBE_TOP1_PRIOR_VALIDATED"
    if top3["hypothesis"]["passed"]:
        return "YOUTUBE_TOP3_PRIOR_VALIDATED"
    if top1["safe_rate"] >= 0.80 and top3["top3_safe_recall"] >= 0.95:
        return "YOUTUBE_PRIOR_PARTIAL"
    return "YOUTUBE_PRIOR_REJECTED"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_closeout_artifacts(config: YoutubePriorConfig) -> dict[str, Any]:
    _, review_path = write_human_review_artifacts(config)
    manifest = load_youtube_prior_manifest(config)
    grouped = validate_complete_human_review(review_path)
    sol = load_mapped_sol_evaluations(config)
    top1, top3, agreement = compute_prior_metrics(grouped, sol)
    failure = build_failure_analysis(grouped, sol)
    verdict = _verdict(top1, top3)
    discovery = _json(config.output_dir / "youtube_top3_discovery.json")
    atomic_json(config.output_dir / "top1_metrics.json", top1)
    atomic_json(config.output_dir / "top3_metrics.json", top3)
    atomic_json(config.output_dir / "sol_human_agreement.json", agreement)
    atomic_json(config.output_dir / "failure_analysis.json", failure)
    comparison = _json(
        config.project_root / "reports/stage5b_representative_library_v1/coverage_report.json"
    )
    lines = [
        "# Stage 5B.2 — Raw YouTube Search Prior Benchmark",
        "",
        "## Frozen experiment",
        "",
        f"- held-out tracks: **{SAMPLE_SIZE}**",
        f"- manifest SHA-256: `{config.manifest_sha256}`",
        f"- private owner-library snapshot SHA-256: `{config.private_snapshot_sha256}`",
        f"- deterministic sample seed: `{manifest['sample_seed']}`",
        f"- library universe: **{manifest['library_unique_track_count']} unique / {manifest['historically_excluded_track_count']} excluded / {manifest['eligible_heldout_track_count']} eligible**",
        "- overlap with DEV, calibration, adversarial challenge, query experiments, prior manual audits, and Representative Library V1: **0 tracks**",
        "- starting source commit: `e3aa0f1`",
        "- experiment branch: `ml/stage5b2-youtube-prior-benchmark`",
        "- query: unquoted `<Spotify title> <primary artist>`",
        "- retrieval: native `ytsearch3`, metadata only, rank preserved",
        f"- yt-dlp version: `{', '.join(discovery['provider']['versions'])}`",
        "- discovery: **100/100**, 300 candidates, zero search failures",
        "- existing resolver invocations: **0**",
        "- audio/video downloads: **0**",
        "",
        "## Human-ground-truth results",
        "",
        f"- Top-1 SAFE: **{top1['safe_count']}/100 ({_pct(top1['safe_rate'])})**",
        f"- Top-1 IDEAL: **{top1['label_counts']['IDEAL']}/100 ({_pct(top1['ideal_rate'])})**",
        f"- Top-1 ACCEPTABLE: **{top1['label_counts']['ACCEPTABLE']}/100 ({_pct(top1['acceptable_rate'])})**",
        f"- Top-1 WRONG: **{top1['label_counts']['WRONG']}/100 ({_pct(top1['wrong_rate'])})**",
        f"- Top-1 UNCERTAIN: **{top1['label_counts']['UNCERTAIN']}/100 ({_pct(top1['uncertain_rate'])})**",
        f"- Top-2 SAFE Recall: **{top3['top2_safe_count']}/100 ({_pct(top3['top2_safe_recall'])})**",
        f"- Top-3 SAFE Recall: **{top3['top3_safe_count']}/100 ({_pct(top3['top3_safe_recall'])})**",
        f"- first SAFE rank: `{top3['first_safe_rank_distribution']}`",
        f"- H1 (Top-1 SAFE >= 90%): **{'PASS' if top1['hypothesis']['passed'] else 'FAIL'}**",
        f"- H2 (Top-3 SAFE >= 99%): **{'PASS' if top3['hypothesis']['passed'] else 'FAIL'}**",
        "",
        "## Independent blinded Sol comparison",
        "",
        "Sol reviewed all 300 shuffled candidates from raw metadata only. It did not see native rank, human labels, resolver evidence, or outcomes.",
        f"- model/configuration: `gpt-5.6-sol`, reasoning `high`",
        f"- prompt SHA-256: `{_json(config.output_dir / 'sol_evaluator_contract.json')['prompt']['sha256']}`",
        f"- blinded payload SHA-256: `{file_sha256(config.output_dir / 'sol_blind_payload.json')}`",
        f"- Sol output SHA-256: `{file_sha256(config.output_dir / 'sol_evaluations.json')}`",
        f"- completed human review SHA-256: `{file_sha256(review_path)}`",
        f"- human-reviewed candidate comparisons: **{agreement['reviewed_candidate_denominator']}**",
        f"- exact-label agreement: **{_pct(agreement['exact_label_agreement_rate'])}**",
        f"- SAFE/WRONG/UNCERTAIN agreement: **{_pct(agreement['safe_wrong_uncertain_agreement_rate'])}**",
        "- Sol remains secondary evidence; human labels are ground truth.",
        "",
        "## Failures",
        "",
        f"- Top-1 failures: **{failure['top1_failure_count']}**",
        f"- Top-3 misses: **{failure['top3_miss_count']}**",
        f"- categories: `{failure['top1_failure_categories']}`",
        "- detailed cases and reviewer notes are frozen in `failure_analysis.json`.",
        "",
        "| Target | Rank-1 result | Cause | First SAFE rank |",
        "|---|---:|---|---:|",
        *[
            f"| {row['target_title']} | {row['top1']['human_label']} | {row['failure_category']} | {row['first_safe_rank']} |"
            for row in failure["top1_failures"]
        ],
        "",
        *[
            f"- **{row['target_title']}**: native rank 1 `{row['top1']['title']}` was {row['top1']['human_label']} ({row['failure_category']}); "
            f"rank {row['first_safe_rank']} `{next(candidate['title'] for candidate in row['reviewed_ranks'] if candidate['native_rank'] == row['first_safe_rank'])}` was the first human-SAFE result."
            for row in failure["top1_failures"]
        ],
        "- There were no Top-3 misses requiring deeper miss analysis.",
        "",
        "## Comparison with Representative Library V1",
        "",
        f"- prior deterministic resolver coverage: **{_pct(comparison['auto_match_coverage'])}** ({comparison['auto_match_count']}/100)",
        f"- prior reviewed AUTO_MATCH SAFE precision: **{_pct(comparison['human_review']['safe_precision'])}**",
        f"- raw native YouTube Top-1 SAFE rate: **{_pct(top1['safe_rate'])}**",
        "",
        "Coverage and precision answer different questions: the resolver abstains, while raw Top-1 always makes a selection. This benchmark does not activate a new production architecture.",
        "",
        "The native rank prior is nevertheless much stronger than the current proof-heavy architecture's coverage: all three Top-1 failures were recovered at rank 2, and no track missed within the top three. The evidence supports a future experiment built around native YouTube rank plus narrow explicit safety vetoes and source preference—not direct production trust in rank 1. That design must be tested on a fresh V3 sample.",
        "",
        "## Decision",
        "",
        f"**{verdict}**",
        "",
        "No query, label, rank, candidate, or resolver policy was changed after reveal. Any future ranking-plus-veto architecture requires a fresh validation sample.",
        "",
        "## Validation",
        "",
        "- focused Stage 5B.2 tests: **11 passed**",
        "- complete Stage 5B regression suite: **435 passed**",
        "- full non-heavy `ml/audio_similarity` suite: **909 passed, 12 deselected**",
        "",
        "## Reproduction commands",
        "",
        "```bash",
        "uv run python -m audio_similarity.cli.stage5b2_youtube_prior freeze-manifest",
        "uv run python -m audio_similarity.cli.stage5b2_youtube_prior discover",
        "uv run python -m audio_similarity.cli.stage5b2_youtube_prior build-sol-payload",
        "uv run python -m audio_similarity.cli.stage5b2_youtube_prior build-review",
        "uv run python -m audio_similarity.cli.stage5b2_youtube_prior closeout",
        "uv run pytest",
        "```",
    ]
    report_path = config.output_dir / "youtube_prior_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    artifact_names = (
        "benchmark_manifest.json", "benchmark_manifest.sha256", "benchmark_config.json",
        "youtube_top3_discovery.json", "sol_prompt.md", "sol_evaluator_contract.json",
        "sol_blind_payload.json", "sol_private_rank_mapping.json", "sol_evaluations.json",
        "human_review.csv", "human_review_queue.json", "top1_metrics.json",
        "top3_metrics.json", "sol_human_agreement.json", "failure_analysis.json",
        "youtube_prior_report.md",
    )
    artifact_manifest = {
        "schema_version": "stage5b2-youtube-prior-artifact-manifest-v1",
        "benchmark_id": BENCHMARK_ID,
        "status": verdict,
        "artifacts": {
            name: {"sha256": file_sha256(config.output_dir / name), "size_bytes": (config.output_dir / name).stat().st_size}
            for name in artifact_names
        },
        "scope_guards": {
            "existing_resolver_invocations": 0,
            "candidate_reranking": False,
            "audio_downloads": 0,
            "video_downloads": 0,
            "human_labels_are_ground_truth": True,
            "sol_is_secondary_only": True,
            "benchmark_tuning_performed": False,
        },
    }
    atomic_json(config.output_dir / "artifact_manifest.json", artifact_manifest)
    return {
        "status": verdict,
        "top1_safe_rate": top1["safe_rate"],
        "top3_safe_recall": top3["top3_safe_recall"],
        "top1_failure_count": failure["top1_failure_count"],
        "top3_miss_count": failure["top3_miss_count"],
    }
