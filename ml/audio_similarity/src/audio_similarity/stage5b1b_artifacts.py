"""Feature datasets, DEV diagnostics, and held-out review contracts."""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .stage5b1a_models import Stage5B1AValidationError
from .stage5b1b_features import FEATURE_SCHEMA_VERSION, extract_track_features


DATASET_SCHEMA_VERSION = "stage5b1b-feature-dataset-v1"
REVIEW_SCHEMA_VERSION = "stage5b1b-heldout-review-v1"
REVIEW_LABELS = {"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"}
REVIEW_COLUMNS = [
    "review_schema_version",
    "stable_track_id",
    "expected_title",
    "expected_artists",
    "expected_album",
    "expected_duration_seconds",
    "expected_release_year",
    "case_tags",
    "case_rationale",
    "query",
    "candidate_rank",
    "candidate_video_id",
    "candidate_url",
    "candidate_title",
    "candidate_uploader",
    "candidate_channel",
    "candidate_duration_seconds",
    "candidate_view_count",
    "source_type",
    "title_similarity",
    "version_relationships",
    "recording_eligible_feature",
    "ineligible_feature_reasons",
    "candidate_review_label",
    "candidate_note",
    "track_note",
]


def atomic_json(path: str | Path, value: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(output)


def materialize_features(
    results: dict[str, Any], *, manifest_sha256: str, dataset_role: str
) -> dict[str, Any]:
    tracks = results.get("tracks")
    if not isinstance(tracks, list):
        raise Stage5B1AValidationError("discovery results tracks must be an array")
    output = []
    candidate_count = 0
    for row in tracks:
        if not isinstance(row, dict) or not isinstance(row.get("track"), dict):
            raise Stage5B1AValidationError("invalid discovery track row")
        from .stage5b1a_models import SpotifyTrack

        track = SpotifyTrack.from_dict(row["track"])
        candidates = row.get("candidates")
        if not isinstance(candidates, list):
            raise Stage5B1AValidationError("invalid discovery candidates")
        features = extract_track_features(track, candidates)
        candidate_count += len(features)
        output.append(
            {
                "track": track.to_dict(),
                "case_tags": list(row.get("case_tags") or []),
                "case_rationale": row.get("case_rationale"),
                "query": row.get("query"),
                "error": row.get("error"),
                "warnings": list(row.get("warnings") or []),
                "candidates": [
                    {"candidate": candidate, "features": feature}
                    for candidate, feature in zip(candidates, features)
                ],
            }
        )
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_role": dataset_role,
        "manifest_sha256": manifest_sha256,
        "track_count": len(output),
        "candidate_pair_count": candidate_count,
        "tracks": output,
    }


def load_dev_review(path: str | Path) -> dict[str, dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {row["stable_track_id"]: row for row in rows}


def dev_diagnostics(dataset: dict[str, Any], review_rows: dict[str, dict[str, str]]) -> dict[str, Any]:
    selected = []
    for row in dataset["tracks"]:
        stable_id = row["track"]["stable_track_id"]
        review = review_rows.get(stable_id, {})
        label = (review.get("review_label") or "").strip()
        if not label.isdigit():
            continue
        rank = int(label)
        candidate = row["candidates"][rank - 1]
        feature = candidate["features"]
        duration_values = [
            item["features"]["duration"]["absolute_duration_delta_seconds"]
            for item in row["candidates"]
            if item["features"]["duration"]["absolute_duration_delta_seconds"] is not None
        ]
        selected.append(
            {
                "stable_track_id": stable_id,
                "human_selected_rank": rank,
                "human_review_note_verbatim": review.get("optional_note") or "",
                "recording_eligible": feature["recording_eligible"],
                "has_explicit_version_conflict": feature["versions"]["has_explicit_version_conflict"],
                "source_type": feature["source"]["source_type"],
                "title_exact_normalized_match": feature["identity"]["title_exact_normalized_match"],
                "strongest_title_similarity": feature["identity"]["title_similarity"]
                == max(item["features"]["identity"]["title_similarity"] for item in row["candidates"]),
                "strongest_performer_evidence": feature["identity"]["artist_similarity"]
                == max(item["features"]["identity"]["artist_similarity"] for item in row["candidates"]),
                "closest_duration": (
                    feature["duration"]["absolute_duration_delta_seconds"] == min(duration_values)
                    if duration_values else None
                ),
            }
        )
    source_counts = Counter(item["source_type"] for item in selected)
    return {
        "schema_version": "stage5b1b-dev-diagnostics-v1",
        "dataset_role": "DEV_ONLY_NOT_HELD_OUT",
        "selected_track_count": len(selected),
        "selected_no_version_conflict_count": sum(not item["has_explicit_version_conflict"] for item in selected),
        "selected_recording_eligible_count": sum(item["recording_eligible"] for item in selected),
        "selected_closest_duration_count": sum(item["closest_duration"] is True for item in selected),
        "selected_closest_duration_evaluable_count": sum(item["closest_duration"] is not None for item in selected),
        "selected_exact_title_count": sum(item["title_exact_normalized_match"] for item in selected),
        "selected_strongest_title_similarity_count": sum(item["strongest_title_similarity"] for item in selected),
        "selected_strongest_performer_evidence_count": sum(item["strongest_performer_evidence"] for item in selected),
        "selected_source_type_counts": dict(sorted(source_counts.items())),
        "tracks": selected,
        "limitations": [
            "The 25 reviewed songs are DEV data and cannot establish held-out resolver accuracy.",
            "The original DEV manifest omitted Spotify duration_ms, so closest-duration diagnostics are not evaluable there.",
            "Human-selected rank is used only after feature materialization for diagnostics, never for feature calculation.",
        ],
    }


def heldout_review_rows(dataset: dict[str, Any]) -> Iterable[dict[str, str]]:
    for row in dataset["tracks"]:
        track = row["track"]
        for wrapped in row["candidates"]:
            candidate, feature = wrapped["candidate"], wrapped["features"]
            relationships = "; ".join(
                f"{item['family']}={item['relationship']}"
                for item in feature["versions"]["relationships"]
            )
            yield {
                "review_schema_version": REVIEW_SCHEMA_VERSION,
                "stable_track_id": track["stable_track_id"],
                "expected_title": track["title"],
                "expected_artists": " | ".join(track["artists"]),
                "expected_album": track.get("album") or "",
                "expected_duration_seconds": str(track["duration_ms"] / 1000.0),
                "expected_release_year": str(track.get("release_year") or ""),
                "case_tags": " | ".join(row["case_tags"]),
                "case_rationale": str(row.get("case_rationale") or ""),
                "query": str(row.get("query") or ""),
                "candidate_rank": str(candidate.get("rank") or ""),
                "candidate_video_id": str(candidate.get("youtube_video_id") or ""),
                "candidate_url": str(candidate.get("canonical_url") or candidate.get("url") or ""),
                "candidate_title": str(candidate.get("title") or ""),
                "candidate_uploader": str(candidate.get("uploader") or ""),
                "candidate_channel": str(candidate.get("channel") or ""),
                "candidate_duration_seconds": (
                    str(candidate["duration_seconds"])
                    if candidate.get("duration_seconds") is not None else ""
                ),
                "candidate_view_count": (
                    str(candidate["view_count"])
                    if candidate.get("view_count") is not None else ""
                ),
                "source_type": feature["source"]["source_type"],
                "title_similarity": f"{feature['identity']['title_similarity']:.6f}",
                "version_relationships": relationships,
                "recording_eligible_feature": str(feature["recording_eligible"]).lower(),
                "ineligible_feature_reasons": "; ".join(feature["ineligible_auto_match_reasons"]),
                "candidate_review_label": "",
                "candidate_note": "",
                "track_note": "",
            }


def write_heldout_review(path: str | Path, dataset: dict[str, Any], *, overwrite: bool = False) -> None:
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"held-out review artifact already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(heldout_review_rows(dataset))
    temporary.replace(output)


def load_heldout_review(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected held-out review columns")
        rows = list(reader)
    identities = set()
    for row in rows:
        label = row["candidate_review_label"].strip().upper()
        if label not in REVIEW_LABELS:
            raise Stage5B1AValidationError(f"invalid held-out candidate label: {label}")
        identity = (row["stable_track_id"], row["candidate_video_id"])
        if identity in identities:
            raise Stage5B1AValidationError("duplicate held-out candidate review identity")
        identities.add(identity)
    return rows
