"""yt-dlp human-review CSV built on the frozen Stage 5B metric semantics."""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

from .stage5b1a_models import FrozenTrackManifest, Stage5B1AValidationError
from .stage5b1a_review import ReviewLabel, load_review_labels


METRICS_SCHEMA_VERSION = "stage5b1a2-ytdlp-metrics-v1"
BASE_COLUMNS = [
    "stable_track_id", "spotify_track_id", "expected_title", "expected_artists",
    "expected_album", "expected_release_year", "case_tags", "case_rationale", "query",
]
CANDIDATE_COLUMNS = [
    f"candidate_{rank}_{field}"
    for rank in range(1, 6)
    for field in (
        "url", "video_id", "title", "uploader", "channel", "duration_seconds",
        "availability", "live_status", "description",
    )
]
REVIEW_COLUMNS = BASE_COLUMNS + CANDIDATE_COLUMNS + ["review_label", "optional_note"]


def _candidate_values(candidate: dict[str, Any] | None) -> list[str]:
    if candidate is None:
        return [""] * 9
    return [
        str(candidate.get("canonical_url") or candidate.get("url") or ""),
        str(candidate.get("youtube_video_id") or ""),
        str(candidate.get("title") or ""),
        str(candidate.get("uploader") or ""),
        str(candidate.get("channel") or ""),
        str(candidate.get("duration_seconds") if candidate.get("duration_seconds") is not None else ""),
        str(candidate.get("availability") or ""),
        str(candidate.get("live_status") or ""),
        str(candidate.get("description") or ""),
    ]


def review_rows(manifest: FrozenTrackManifest, results: dict | None = None) -> list[dict[str, str]]:
    result_by_id: dict[str, dict] = {}
    if results is not None:
        raw_rows = results.get("tracks")
        if not isinstance(raw_rows, list):
            raise Stage5B1AValidationError("yt-dlp results tracks must be an array")
        for value in raw_rows:
            stable_id = value.get("track", {}).get("stable_track_id") if isinstance(value, dict) else None
            if not isinstance(stable_id, str) or stable_id in result_by_id:
                raise Stage5B1AValidationError("yt-dlp results have invalid or duplicate track IDs")
            result_by_id[stable_id] = value
        if set(result_by_id) != set(manifest.stable_track_ids):
            raise Stage5B1AValidationError("yt-dlp results do not match the frozen manifest")
    output = []
    for item in manifest.tracks:
        track = item.track
        discovered = result_by_id.get(track.stable_track_id)
        candidates = discovered.get("candidates", []) if discovered else []
        if not isinstance(candidates, list) or len(candidates) > 5:
            raise Stage5B1AValidationError("invalid yt-dlp candidate array")
        row = {
            "stable_track_id": track.stable_track_id,
            "spotify_track_id": track.spotify_track_id or "",
            "expected_title": track.title,
            "expected_artists": " | ".join(track.artists),
            "expected_album": track.album or "",
            "expected_release_year": str(track.release_year or ""),
            "case_tags": " | ".join(item.case_tags),
            "case_rationale": item.case_rationale,
            "query": discovered.get("query", "") if discovered else "",
            "review_label": "",
            "optional_note": "",
        }
        for rank in range(1, 6):
            candidate = candidates[rank - 1] if rank <= len(candidates) else None
            for field, value in zip(
                (
                    "url", "video_id", "title", "uploader", "channel", "duration_seconds",
                    "availability", "live_status", "description",
                ),
                _candidate_values(candidate),
            ):
                row[f"candidate_{rank}_{field}"] = value
        output.append(row)
    return output


def write_review_csv(
    path: str | Path,
    manifest: FrozenTrackManifest,
    results: dict | None = None,
    *,
    overwrite: bool = False,
) -> None:
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"yt-dlp review artifact already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(review_rows(manifest, results))
    temporary.replace(output)


def load_ytdlp_review_labels(
    path: str | Path,
    *,
    candidate_counts: dict[str, int] | None = None,
) -> tuple[ReviewLabel, ...]:
    return load_review_labels(
        path,
        candidate_counts=candidate_counts,
        expected_columns=REVIEW_COLUMNS,
    )
