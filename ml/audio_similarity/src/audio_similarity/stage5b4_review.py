"""Sequential human oracle and selector validation for Stage 5B.4 V3."""
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
from .stage5b4_representative_v3 import (
    AUTOMATED_COVERAGE_GATE,
    AUTOMATED_SAFE_PRECISION_GATE,
    BENCHMARK_ID,
    RAW_TOP1_GATE,
    SAMPLE_SIZE,
    STATUS_DISCOVERY_COMPLETE,
    TOP3_REPLICATION_GATE,
    Stage5B4Config,
    _json,
    load_v3_manifest,
)


LABELS = ("IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN")
SAFE_LABELS = frozenset({"IDEAL", "ACCEPTABLE"})
REVIEW_SCHEMA_VERSION = "stage5b4-representative-v3-human-review-v1"
QUEUE_SCHEMA_VERSION = "stage5b4-representative-v3-human-review-queue-v1"
TOPK_SCHEMA_VERSION = "stage5b4-human-topk-metrics-v1"
VETO_SCHEMA_VERSION = "stage5b4-veto-analysis-v1"
FAILURE_SCHEMA_VERSION = "stage5b4-failure-analysis-v1"
ARTIFACT_SCHEMA_VERSION = "stage5b4-representative-v3-artifact-manifest-v1"
STATUS_REVIEW_READY = "STAGE5B4_HUMAN_REVIEW_READY"
STATUS_COMPLETE = "STAGE5B4_REPRESENTATIVE_V3_COMPLETE"
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


def first_safe_rank(rows: list[dict[str, str]]) -> int | None:
    for row in sorted(rows, key=lambda item: int(item["youtube_rank"])):
        if row["candidate_review_label"] in SAFE_LABELS:
            return int(row["youtube_rank"])
    return None


def oracle_next_rank(rows: list[dict[str, str]]) -> int | None:
    """Return the next sequential Top-3 rank, independent of the selector."""

    for row in sorted(rows, key=lambda item: int(item["youtube_rank"])):
        label = row["candidate_review_label"]
        if label in SAFE_LABELS:
            return None
        if not label:
            return int(row["youtube_rank"])
    return None


def oracle_complete(rows: list[dict[str, str]]) -> bool:
    return first_safe_rank(rows) is not None or all(
        row["candidate_review_label"] for row in rows
    )


def next_review_requirement(
    rows: list[dict[str, str]], selected_rank: int | None
) -> tuple[str, int] | None:
    next_rank = oracle_next_rank(rows)
    if not oracle_complete(rows):
        if next_rank is None:
            raise Stage5B1AValidationError("invalid incomplete V3 oracle state")
        return "TOP3_ORACLE", next_rank
    if selected_rank is not None:
        selected = next(
            row for row in rows if int(row["youtube_rank"]) == selected_rank
        )
        if not selected["candidate_review_label"]:
            return "SELECTOR_VALIDATION", selected_rank
    return None


def _read_review_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Stage 5B.4 review columns")
        rows = list(reader)
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        identity = (row["benchmark_id"], row["youtube_rank"], row["candidate_video_id"])
        if identity in seen or not YOUTUBE_VIDEO_ID.fullmatch(row["candidate_video_id"]):
            raise Stage5B1AValidationError("invalid Stage 5B.4 review identity")
        seen.add(identity)
        if row["review_schema_version"] != REVIEW_SCHEMA_VERSION:
            raise Stage5B1AValidationError("unexpected Stage 5B.4 review schema")
        label = row["candidate_review_label"].strip().upper()
        if label and label not in LABELS:
            raise Stage5B1AValidationError("invalid Stage 5B.4 human label")
        row["candidate_review_label"] = label
        if len(row["candidate_note"]) > MAX_NOTE_LENGTH or len(row["track_note"]) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("Stage 5B.4 review note is too long")
    return rows


def _group_review_rows(
    path: Path, expected_ids: list[str] | None = None
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in _read_review_rows(path):
        grouped.setdefault(row["benchmark_id"], []).append(row)
    if expected_ids is not None:
        if set(grouped) - set(expected_ids):
            raise Stage5B1AValidationError("Stage 5B.4 review has unknown track identities")
        grouped = {benchmark_id: grouped.get(benchmark_id, []) for benchmark_id in expected_ids}
    if len(grouped) != SAMPLE_SIZE or any(len(rows) > 3 for rows in grouped.values()):
        raise Stage5B1AValidationError("Stage 5B.4 review track/candidate count changed")
    output = {
        benchmark_id: sorted(rows, key=lambda row: int(row["youtube_rank"]))
        for benchmark_id, rows in grouped.items()
    }
    if any(
        [int(row["youtube_rank"]) for row in rows] != list(range(1, len(rows) + 1))
        for rows in output.values()
    ):
        raise Stage5B1AValidationError("Stage 5B.4 candidate ranks changed")
    return output


def _decision_ranks(path: Path) -> dict[str, int | None]:
    value = _json(path)
    if value.get("human_labels_visible") is not False or len(value.get("tracks", [])) != SAMPLE_SIZE:
        raise Stage5B1AValidationError("invalid frozen Stage 5B.4 decisions")
    return {row["benchmark_id"]: row["selected_rank"] for row in value["tracks"]}


def write_human_review_artifacts(config: Stage5B4Config) -> tuple[dict[str, Any], Path]:
    manifest = load_v3_manifest(config)
    discovery_path = config.output_dir / "youtube_top3_discovery.json"
    decisions_path = config.output_dir / "automated_selector_decisions.json"
    discovery = _json(discovery_path)
    if discovery.get("status") != STATUS_DISCOVERY_COMPLETE:
        raise Stage5B1AValidationError("frozen V3 discovery must complete before review")
    ranks = _decision_ranks(decisions_path)
    targets = {row["benchmark_id"]: row for row in manifest["tracks"]}
    cases = []
    review_rows = []
    for track_row in discovery["tracks"]:
        benchmark_id = track_row["benchmark_id"]
        target = targets[benchmark_id]
        candidates = track_row["outcome"].get("candidates", [])
        if len(candidates) > 3 or [row["rank"] for row in candidates] != list(
            range(1, len(candidates) + 1)
        ):
            raise Stage5B1AValidationError(
                "V3 human oracle candidate ranks changed"
            )
        cases.append({
            "benchmark_id": benchmark_id,
            "spotify_target": target,
            "query": track_row["query"],
            "candidate_count": len(candidates),
            "unavailable": not candidates,
            "discovery_error": track_row["outcome"].get("error"),
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
                "search_query": track_row["query"],
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
        "status": STATUS_REVIEW_READY,
        "benchmark_manifest_sha256": config.manifest_sha256,
        "discovery_sha256": file_sha256(discovery_path),
        "automated_decisions_sha256": file_sha256(decisions_path),
        "protocol": "SEQUENTIAL_NATIVE_RANKS_UNTIL_FIRST_SAFE_THEN_SELECTOR_SUPPLEMENT",
        "automated_decisions_visible_to_reviewer": False,
        "safe_labels": sorted(SAFE_LABELS),
        "rank1_non_safe_reason_required": True,
        "track_count": len(cases),
        "candidate_count": len(review_rows),
        "selector_supplement_candidate_count": sum(rank not in (None, 1) for rank in ranks.values()),
        "cases": cases,
    }
    atomic_json(config.output_dir / "human_review_queue.json", queue)
    review_path = config.output_dir / "human_review.csv"
    if review_path.exists():
        existing = _read_review_rows(review_path)
        expected = [
            (row["benchmark_id"], str(row["youtube_rank"]), row["candidate_video_id"])
            for row in review_rows
        ]
        actual = [
            (row["benchmark_id"], row["youtube_rank"], row["candidate_video_id"])
            for row in existing
        ]
        if actual != expected:
            raise Stage5B1AValidationError("existing Stage 5B.4 review identities changed")
        return queue, review_path
    temporary = review_path.with_suffix(review_path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(review_rows)
    temporary.replace(review_path)
    return queue, review_path


class Stage5B4ReviewStore:
    """Autosave sequential oracle labels, then any hidden selector supplement."""

    def __init__(self, review_path: str | Path, decisions_path: str | Path) -> None:
        self.review_path = Path(review_path).resolve()
        self.decisions_path = Path(decisions_path).resolve()
        self._selected_ranks = _decision_ranks(self.decisions_path)
        queue = _json(self.review_path.parent / "human_review_queue.json")
        self._queue_cases = {
            row["benchmark_id"]: row for row in queue.get("cases", [])
        }
        if set(self._queue_cases) != set(self._selected_ranks):
            raise Stage5B1AValidationError("V3 review queue/selector identities differ")
        self._lock = threading.RLock()
        self._read_grouped()

    def _read_grouped(self) -> dict[str, list[dict[str, str]]]:
        grouped = _group_review_rows(self.review_path, list(self._selected_ranks))
        if set(grouped) != set(self._selected_ranks):
            raise Stage5B1AValidationError("V3 review/selector track identities differ")
        return grouped

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
                selected_rank = self._selected_ranks[benchmark_id]
                requirement = next_review_requirement(rows, selected_rank)
                reviewed += sum(bool(row["candidate_review_label"]) for row in rows)
                if requirement is None:
                    completed += 1
                    visible = [row for row in rows if row["candidate_review_label"]]
                    phase = "COMPLETE"
                    next_rank = None
                elif requirement[0] == "TOP3_ORACLE":
                    phase, next_rank = requirement
                    visible = rows[:next_rank]
                else:
                    phase, next_rank = requirement
                    visible = [
                        row for row in rows
                        if row["candidate_review_label"]
                        or int(row["youtube_rank"]) == next_rank
                    ]
                target = queue_case["spotify_target"]
                cases.append({
                    "stable_track_id": benchmark_id,
                    "track": {
                        "title": target["title"],
                        "artists": target["artists"],
                        "album": target.get("album"),
                        "duration_seconds": target["duration_ms"] / 1000,
                        "release_year": target.get("release_year"),
                    },
                    "query": queue_case["query"],
                    "track_note": rows[0]["track_note"] if rows else "",
                    "candidate_unavailable": not rows,
                    "discovery_error": queue_case.get("discovery_error"),
                    "review_complete": requirement is None,
                    "review_phase": phase,
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
                        "reason_required_for_non_safe": int(row["youtube_rank"]) == 1,
                        "review": {
                            "label": row["candidate_review_label"],
                            "note": row["candidate_note"],
                        },
                        "is_current": next_rank == int(row["youtube_rank"]),
                    } for row in visible],
                })
            return {
                "schema_version": "stage5b4-representative-v3-review-session-v1",
                "mode": "stage5b4_representative_v3_review",
                "labels": list(LABELS),
                "export_filename": "stage5b4-representative-v3-human-review.csv",
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
            raise Stage5B1AValidationError("invalid Stage 5B.4 review label")
        if len(candidate_note) > MAX_NOTE_LENGTH or len(track_note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("Stage 5B.4 review note is too long")
        with self._lock:
            grouped = self._read_grouped()
            rows = grouped.get(stable_track_id)
            target = next(
                (row for row in rows or [] if row["candidate_video_id"] == video_id),
                None,
            )
            if target is None:
                raise Stage5B1AValidationError("unknown Stage 5B.4 review identity")
            requirement = next_review_requirement(
                rows or [], self._selected_ranks[stable_track_id]
            )
            target_rank = int(target["youtube_rank"])
            if (
                label
                and not target["candidate_review_label"]
                and (requirement is None or target_rank != requirement[1])
            ):
                raise Stage5B1AValidationError("review the required V3 candidate first")
            target["candidate_review_label"] = label
            target["candidate_note"] = candidate_note
            flat_rows = _read_review_rows(self.review_path)
            updates = {
                (row["benchmark_id"], row["candidate_video_id"]): row
                for grouped_rows in grouped.values()
                for row in grouped_rows
            }
            for row in flat_rows:
                updated = updates[(row["benchmark_id"], row["candidate_video_id"])]
                row.update(updated)
                if row["benchmark_id"] == stable_track_id:
                    row["track_note"] = track_note
            temporary = self.review_path.with_suffix(
                self.review_path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
            )
            with temporary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(flat_rows)
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
    grouped = _group_review_rows(review_path, list(ranks))
    incomplete = [
        benchmark_id
        for benchmark_id, rows in grouped.items()
        if next_review_requirement(rows, ranks[benchmark_id]) is not None
    ]
    if incomplete:
        raise Stage5B1AValidationError(
            f"Stage 5B.4 human review incomplete for {len(incomplete)} tracks"
        )
    missing_reasons = [
        benchmark_id
        for benchmark_id, rows in grouped.items()
        if rows
        if rows[0]["candidate_review_label"] in {"WRONG", "UNCERTAIN"}
        and not rows[0]["candidate_note"].strip()
    ]
    if missing_reasons:
        raise Stage5B1AValidationError(
            f"Stage 5B.4 rank-1 failure reason missing for {len(missing_reasons)} tracks"
        )
    return grouped


def _failure_category(row: dict[str, str]) -> str:
    text = " ".join((
        row["candidate_title"], row["candidate_description"], row["candidate_note"]
    )).casefold()
    patterns = (
        ("COVER_OR_ALTERNATE_PERFORMER", r"\bcover(?:ed)?\b|tribute|male version|female version"),
        ("INSTRUMENTAL_OR_KARAOKE", r"\binstrumental\b|\binst\.?\b|karaoke|without vocals"),
        ("MULTI_TRACK_OR_NOT_ISOLATED", r"\bfull album\b|\bplaylist\b|\bcompilation\b|hour(?:s)? mix"),
        ("WRONG_REMIX_OR_VERSION", r"\bremix\b|extended|radio edit|sped|slowed|reverb|nightcore|bass boost"),
        ("LIVE_VS_STUDIO", r"\blive\b|concert|stage|fancam|performance|musiccore"),
        ("WRONG_LANGUAGE_OR_VERSION", r"english version|japanese version|korean version|chinese version"),
        ("LYRIC_OR_FAN_EDIT_UNSUITABLE", r"lyrics?|fan.?made|\bamv\b"),
    )
    for category, pattern in patterns:
        if re.search(pattern, text):
            return category
    if row["candidate_review_label"] == "UNCERTAIN":
        return "METADATA_INSUFFICIENT"
    return "TITLE_OR_ARTIST_AMBIGUITY_OR_SEARCH_ODDITY"


def _label_counts(values: list[str]) -> dict[str, int]:
    counts = Counter(values)
    return {label: counts[label] for label in LABELS}


def compute_v3_metrics(
    grouped: dict[str, list[dict[str, str]]],
    decisions: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    tracks = {row["benchmark_id"]: row for row in decisions["tracks"]}
    top1_counts = _label_counts([
        rows[0]["candidate_review_label"] for rows in grouped.values() if rows
    ])
    top1_unavailable = sum(not rows for rows in grouped.values())
    first_safe = {
        benchmark_id: first_safe_rank(rows) for benchmark_id, rows in grouped.items()
    }
    first_counts = Counter(
        f"rank_{rank}" if rank is not None else "none" for rank in first_safe.values()
    )
    top1_safe = sum(rank == 1 for rank in first_safe.values())
    top2_safe = sum(rank is not None and rank <= 2 for rank in first_safe.values())
    top3_safe = sum(rank is not None and rank <= 3 for rank in first_safe.values())
    topk = {
        "schema_version": TOPK_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "denominator_tracks": SAMPLE_SIZE,
        "top1_label_counts": top1_counts,
        "top1_unavailable_count": top1_unavailable,
        "top1_safe_count": top1_safe,
        "top1_safe_rate": top1_safe / SAMPLE_SIZE,
        "top2_safe_count": top2_safe,
        "top2_safe_recall": top2_safe / SAMPLE_SIZE,
        "top3_safe_count": top3_safe,
        "top3_safe_recall": top3_safe / SAMPLE_SIZE,
        "first_safe_rank_distribution": {
            key: first_counts[key] for key in ("rank_1", "rank_2", "rank_3", "none")
        },
        "reviewed_candidate_count": sum(
            bool(row["candidate_review_label"])
            for rows in grouped.values() for row in rows
        ),
        "selector_supplemental_judgment_count": sum(
            track["selected_rank"] is not None
            and first_safe[benchmark_id] is not None
            and track["selected_rank"] > first_safe[benchmark_id]
            for benchmark_id, track in tracks.items()
        ),
        "gates": {
            "raw_top1": {"minimum": RAW_TOP1_GATE, "passed": top1_safe / SAMPLE_SIZE >= RAW_TOP1_GATE},
            "top3_replication": {"minimum": TOP3_REPLICATION_GATE, "passed": top3_safe / SAMPLE_SIZE >= TOP3_REPLICATION_GATE},
        },
    }
    selected_rows = []
    for benchmark_id, track in tracks.items():
        rank = track["selected_rank"]
        if rank is None:
            continue
        row = grouped[benchmark_id][rank - 1]
        selected_rows.append((track, row))
    selected_labels = [row["candidate_review_label"] for _, row in selected_rows]
    selected_counts = _label_counts(selected_labels)
    safe = selected_counts["IDEAL"] + selected_counts["ACCEPTABLE"]
    coverage = len(selected_rows) / SAMPLE_SIZE
    precision = safe / len(selected_rows) if selected_rows else 0.0
    automated = {
        "denominator_tracks": SAMPLE_SIZE,
        "auto_select_count": len(selected_rows),
        "auto_select_coverage": coverage,
        "match_uncertain_count": SAMPLE_SIZE - len(selected_rows),
        "selected_rank_distribution": {
            f"rank_{rank}": sum(track["selected_rank"] == rank for track in tracks.values())
            for rank in (1, 2, 3)
        } | {"none": sum(track["selected_rank"] is None for track in tracks.values())},
        "human_label_counts": selected_counts,
        "human_safe_count": safe,
        "human_safe_precision": precision,
        "human_wrong_rate": selected_counts["WRONG"] / len(selected_rows) if selected_rows else 0.0,
        "human_uncertain_rate": selected_counts["UNCERTAIN"] / len(selected_rows) if selected_rows else 0.0,
        "gates": {
            "coverage": {"minimum": AUTOMATED_COVERAGE_GATE, "passed": coverage >= AUTOMATED_COVERAGE_GATE},
            "safe_precision": {"minimum": AUTOMATED_SAFE_PRECISION_GATE, "passed": precision >= AUTOMATED_SAFE_PRECISION_GATE},
        },
        "human_labels_used_in_decisions": False,
    }
    veto_cases = []
    for benchmark_id, track in tracks.items():
        if not track["candidate_evaluations"]:
            continue
        first = track["candidate_evaluations"][0]
        if not first["vetoed"]:
            continue
        rank1 = grouped[benchmark_id][0]
        selected_label = None
        if track["selected_rank"] is not None:
            selected_label = grouped[benchmark_id][track["selected_rank"] - 1]["candidate_review_label"]
        veto_cases.append({
            "benchmark_id": benchmark_id,
            "target_title": track["spotify_target"]["title"],
            "rank1_video_id": first["video_id"],
            "rank1_title": first["title"],
            "rank1_human_label": rank1["candidate_review_label"],
            "rank1_human_note": rank1["candidate_note"],
            "veto_reasons": first["veto_reasons"],
            "duration_delta_seconds": first["absolute_duration_delta_seconds"],
            "selector_decision": track["decision"],
            "selected_rank": track["selected_rank"],
            "selected_video_id": track["selected_video_id"],
            "selected_human_label": selected_label,
            "harmful_false_veto": (
                rank1["candidate_review_label"] in SAFE_LABELS
                and (selected_label not in SAFE_LABELS)
            ),
        })

    def veto_summary(reason: str) -> dict[str, Any]:
        cases = [row for row in veto_cases if reason in row["veto_reasons"]]
        labels = _label_counts([row["rank1_human_label"] for row in cases])
        fallbacks = _label_counts([
            row["selected_human_label"] for row in cases if row["selected_human_label"]
        ])
        return {
            "total": len(cases),
            "rank1_human_labels": labels,
            "rank1_safe_false_positive_count": labels["IDEAL"] + labels["ACCEPTABLE"],
            "rank1_wrong_true_positive_count": labels["WRONG"],
            "rank1_uncertain_count": labels["UNCERTAIN"],
            "fallback_human_labels": fallbacks,
            "fallback_rank_distribution": dict(sorted(Counter(
                str(row["selected_rank"]) if row["selected_rank"] is not None else "none"
                for row in cases
            ).items())),
        }

    veto = {
        "schema_version": VETO_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "all_rank1_veto_count": len(veto_cases),
        "duration_veto": veto_summary("DURATION_ANOMALY_GT_20_SECONDS"),
        "live_veto": veto_summary("UNREQUESTED_LIVE_OR_PERFORMANCE"),
        "harmful_false_veto_count": sum(row["harmful_false_veto"] for row in veto_cases),
        "cases": veto_cases,
    }
    top1_failures = []
    for benchmark_id, rows in grouped.items():
        if not rows:
            top1_failures.append({
                "benchmark_id": benchmark_id,
                "target_title": tracks[benchmark_id]["spotify_target"]["title"],
                "rank1": {
                    "video_id": None,
                    "title": None,
                    "human_label": "UNAVAILABLE",
                    "human_reason": "No candidate metadata was returned for the frozen query.",
                    "category": "CANDIDATE_POOL_UNAVAILABLE",
                },
                "first_safe_rank": None,
            })
            continue
        if rows[0]["candidate_review_label"] in SAFE_LABELS:
            continue
        top1_failures.append({
            "benchmark_id": benchmark_id,
            "target_title": rows[0]["expected_title"],
            "rank1": {
                "video_id": rows[0]["candidate_video_id"],
                "title": rows[0]["candidate_title"],
                "human_label": rows[0]["candidate_review_label"],
                "human_reason": rows[0]["candidate_note"],
                "category": _failure_category(rows[0]),
            },
            "first_safe_rank": first_safe[benchmark_id],
        })
    top3_misses = []
    for benchmark_id, rank in first_safe.items():
        if rank is not None:
            continue
        rows = grouped[benchmark_id]
        top3_misses.append({
            "benchmark_id": benchmark_id,
            "target": {
                "title": tracks[benchmark_id]["spotify_target"]["title"],
                "artists": tracks[benchmark_id]["spotify_target"]["artists"],
                "album": tracks[benchmark_id]["spotify_target"].get("album"),
            },
            "candidates": [{
                "rank": int(row["youtube_rank"]),
                "video_id": row["candidate_video_id"],
                "title": row["candidate_title"],
                "human_label": row["candidate_review_label"],
                "human_note": row["candidate_note"],
                "category": _failure_category(row),
            } for row in rows],
            "track_note": rows[0]["track_note"] if rows else "",
        })
    selected_wrong_categories = Counter(
        _failure_category(row) for _, row in selected_rows
        if row["candidate_review_label"] == "WRONG"
    )
    systematic = sorted(
        category for category, count in selected_wrong_categories.items() if count >= 2
    )
    failure = {
        "schema_version": FAILURE_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "top1_failure_count": len(top1_failures),
        "top1_failure_categories": dict(sorted(Counter(
            row["rank1"]["category"] for row in top1_failures
        ).items())),
        "top1_failures": top1_failures,
        "top3_miss_count": len(top3_misses),
        "top3_misses": top3_misses,
        "automated_wrong_categories": dict(sorted(selected_wrong_categories.items())),
        "concerning_systematic_automated_wrong_families": systematic,
    }
    return topk, automated, veto, failure


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def write_closeout_artifacts(config: Stage5B4Config) -> dict[str, Any]:
    decisions_path = config.output_dir / "automated_selector_decisions.json"
    review_path = config.output_dir / "human_review.csv"
    decisions = _json(decisions_path)
    grouped = validate_complete_review(review_path, decisions_path)
    topk, automated, veto, failure = compute_v3_metrics(grouped, decisions)
    metrics_path = config.output_dir / "automated_selector_metrics.json"
    existing_metrics = _json(metrics_path)
    automated_metrics = existing_metrics | {"human_outcomes": automated}
    atomic_json(metrics_path, automated_metrics)
    atomic_json(config.output_dir / "human_topk_metrics.json", topk)
    atomic_json(config.output_dir / "veto_analysis.json", veto)
    atomic_json(config.output_dir / "failure_analysis.json", failure)
    prior_replicated = (
        topk["top1_safe_rate"] >= RAW_TOP1_GATE
        and topk["top3_safe_recall"] >= TOP3_REPLICATION_GATE
    )
    selector_passed = (
        automated["gates"]["coverage"]["passed"]
        and automated["gates"]["safe_precision"]["passed"]
    )
    systematic = failure["concerning_systematic_automated_wrong_families"]
    if not prior_replicated:
        verdict = "YOUTUBE_PRIOR_NOT_REPLICATED"
    elif not selector_passed or systematic:
        verdict = "YOUTUBE_PRIOR_VALIDATED_BUT_SELECTOR_REJECTED"
    elif veto["harmful_false_veto_count"]:
        verdict = "MINIMAL_SELECTOR_VALIDATED_WITH_VETO_REFINEMENT_NEEDED"
    else:
        verdict = "MINIMAL_SELECTOR_VALIDATED"
    rank1 = topk["top1_label_counts"]
    lines = [
        "# Stage 5B.4 — Fresh V3 YouTube-Prior Validation",
        "",
        "## Frozen design",
        "",
        "This benchmark freezes natural unquoted Spotify-title-plus-primary-artist `ytsearch3` discovery and the exact Stage 5B.3 two-veto selector. Human labels never affect automated decisions. No threshold, veto, query, candidate, or rank was changed after manifest freeze.",
        "",
        f"- manifest SHA-256: `{config.manifest_sha256}`",
        f"- discovery SHA-256: `{file_sha256(config.output_dir / 'youtube_top3_discovery.json')}`",
        f"- Stage 5B.3 implementation SHA-256: `{config.selector_source_sha256}`",
        "- production activation: **false**",
        "- audio/video downloads: **0 / 0**",
        "",
        "## Raw YouTube and human Top-3 oracle",
        "",
        f"- Top-1 SAFE: **{topk['top1_safe_count']}/{SAMPLE_SIZE} ({_pct(topk['top1_safe_rate'])})**",
        f"- Top-1 IDEAL / ACCEPTABLE / WRONG / UNCERTAIN: **{rank1['IDEAL']} / {rank1['ACCEPTABLE']} / {rank1['WRONG']} / {rank1['UNCERTAIN']}**",
        f"- Top-1 unavailable: **{topk['top1_unavailable_count']}**",
        f"- Top-2 SAFE Recall: **{topk['top2_safe_count']}/{SAMPLE_SIZE} ({_pct(topk['top2_safe_recall'])})**",
        f"- Top-3 SAFE Recall: **{topk['top3_safe_count']}/{SAMPLE_SIZE} ({_pct(topk['top3_safe_recall'])})**",
        f"- first SAFE rank: `{topk['first_safe_rank_distribution']}`",
        f"- total human candidate judgments: **{topk['reviewed_candidate_count']}**",
        f"- supplemental selector judgments: **{topk['selector_supplemental_judgment_count']}**",
        "",
        "## Frozen automated selector",
        "",
        f"- AUTO_SELECT coverage: **{automated['auto_select_count']}/{SAMPLE_SIZE} ({_pct(automated['auto_select_coverage'])})**",
        f"- MATCH_UNCERTAIN: **{automated['match_uncertain_count']}**",
        f"- selected ranks: `{automated['selected_rank_distribution']}`",
        f"- selected human IDEAL / ACCEPTABLE / WRONG / UNCERTAIN: **{automated['human_label_counts']['IDEAL']} / {automated['human_label_counts']['ACCEPTABLE']} / {automated['human_label_counts']['WRONG']} / {automated['human_label_counts']['UNCERTAIN']}**",
        f"- SAFE precision: **{automated['human_safe_count']}/{automated['auto_select_count']} ({_pct(automated['human_safe_precision'])})**",
        "",
        "## Veto audit",
        "",
        f"- all rank-1 vetoes: **{veto['all_rank1_veto_count']}**",
        f"- duration vetoes: **{veto['duration_veto']['total']}**; human SAFE false positives **{veto['duration_veto']['rank1_safe_false_positive_count']}**; WRONG true positives **{veto['duration_veto']['rank1_wrong_true_positive_count']}**; UNCERTAIN **{veto['duration_veto']['rank1_uncertain_count']}**",
        f"- live vetoes: **{veto['live_veto']['total']}**; human SAFE false positives **{veto['live_veto']['rank1_safe_false_positive_count']}**; WRONG true positives **{veto['live_veto']['rank1_wrong_true_positive_count']}**; UNCERTAIN **{veto['live_veto']['rank1_uncertain_count']}**",
        f"- harmful false vetoes (SAFE rank 1 replaced by non-SAFE or abstention): **{veto['harmful_false_veto_count']}**",
        "",
        "## Failures",
        "",
        f"- Top-1 failures: **{failure['top1_failure_count']}**",
        f"- Top-1 failure families: `{failure['top1_failure_categories']}`",
        f"- Top-3 misses: **{failure['top3_miss_count']}**",
        f"- systematic automated WRONG families: `{systematic}`",
        "",
        "| Spotify target | Rank-1 label | Human reason | First SAFE rank |",
        "|---|---:|---|---:|",
        *[
            f"| {_markdown_cell(row['target_title'])} | {row['rank1']['human_label']} | {_markdown_cell(row['rank1']['human_reason'])} | {row['first_safe_rank'] or 'none'} |"
            for row in failure["top1_failures"]
        ],
        "",
        "## Independent comparison",
        "",
        "| Evidence set | Raw Top-1 SAFE | Top-3 SAFE Recall | Automated coverage | Automated SAFE precision |",
        "|---|---:|---:|---:|---:|",
        "| Stage 5B.2 raw prior | 97.00% | 100.00% | — | — |",
        "| Stage 5B.3 calibration | — | — | 99.00% | 97.98% |",
        "| Representative V1 proof-heavy resolver | — | — | 81.00% | 97.53% |",
        f"| Fresh Representative V3 | {_pct(topk['top1_safe_rate'])} | {_pct(topk['top3_safe_recall'])} | {_pct(automated['auto_select_coverage'])} | {_pct(automated['human_safe_precision'])} |",
        "",
        "These datasets remain separate. Raw Top-1 quality, the human Top-3 oracle, and automated selector behavior answer different questions.",
        "",
        "## Architecture decision",
        "",
        f"**{verdict}**",
        "",
        "The V3 benchmark is evaluation-only. No production activation or benchmark-driven tuning occurred. Any future veto refinement must use new calibration evidence and then another untouched validation set.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "uv run python -m audio_similarity.cli.stage5b4_representative_v3 freeze-manifest",
        "uv run python -m audio_similarity.cli.stage5b4_representative_v3 discover",
        "uv run python -m audio_similarity.cli.stage5b4_representative_v3 run-selector",
        "uv run python -m audio_similarity.cli.stage5b4_representative_v3 build-review",
        "uv run python -m audio_similarity.cli.stage5b4_representative_v3 closeout",
        "```",
    ]
    report_path = config.output_dir / "representative_v3_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    artifact_names = (
        "benchmark_manifest.json", "benchmark_manifest.sha256", "benchmark_config.json",
        "youtube_top3_discovery.json", "automated_selector_decisions.json",
        "automated_selector_metrics.json", "human_review.csv", "human_review_queue.json",
        "human_topk_metrics.json", "veto_analysis.json", "failure_analysis.json",
        "representative_v3_report.md",
    )
    manifest = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "status": STATUS_COMPLETE,
        "verdict": verdict,
        "artifacts": {
            name: {
                "sha256": file_sha256(config.output_dir / name),
                "size_bytes": (config.output_dir / name).stat().st_size,
            }
            for name in artifact_names
        },
        "scope_guards": {
            "selector_tuning": False,
            "query_tuning": False,
            "post_freeze_substitutions": 0,
            "human_labels_used_in_automated_decisions": False,
            "production_activation": False,
            "audio_downloads": 0,
            "video_downloads": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }
    atomic_json(config.output_dir / "artifact_manifest.json", manifest)
    return {
        "status": STATUS_COMPLETE,
        "verdict": verdict,
        "top1_safe_rate": topk["top1_safe_rate"],
        "top3_safe_recall": topk["top3_safe_recall"],
        "automated_coverage": automated["auto_select_coverage"],
        "automated_safe_precision": automated["human_safe_precision"],
    }
