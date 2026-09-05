from __future__ import annotations

import csv

from audio_similarity.stage5b3_minimal_selector import (
    EXPERIMENT_ID,
    REVIEW_COLUMNS,
    REVIEW_SCHEMA_VERSION,
)
from audio_similarity.stage5b3_review_store import Stage5B3ReviewStore


def test_stage5b3_review_store_autosaves_label_and_note(tmp_path) -> None:
    review = tmp_path / "human_review.csv"
    row = {column: "" for column in REVIEW_COLUMNS}
    row.update({
        "review_schema_version": REVIEW_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "benchmark_id": "stage5b_youtube_prior_v1_001",
        "spotify_track_id": "spotify-track",
        "expected_title": "Song",
        "expected_artists": "Artist",
        "expected_album": "Album",
        "expected_duration_seconds": "180",
        "selected_rank": "2",
        "candidate_video_id": "abcdefghijk",
        "candidate_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "candidate_title": "Song (Lyrics)",
        "candidate_uploader": "Uploader",
        "candidate_channel": "Channel",
        "candidate_duration_seconds": "181",
        "candidate_view_count": "123",
    })
    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)

    store = Stage5B3ReviewStore(review)
    assert store.session()["progress"]["remaining_candidates"] == 1
    store.submit(
        "stage5b_youtube_prior_v1_001",
        "abcdefghijk",
        "acceptable",
        "Same recording.",
        "Checked the candidate.",
    )
    session = store.session()
    assert session["progress"]["remaining_candidates"] == 0
    assert session["cases"][0]["candidates"][0]["review"] == {
        "label": "ACCEPTABLE",
        "note": "Same recording.",
    }
    assert session["cases"][0]["track_note"] == "Checked the candidate."
