from __future__ import annotations

import csv

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b1b_artifacts import (
    REVIEW_COLUMNS,
    dev_diagnostics,
    load_heldout_review,
    materialize_features,
    write_heldout_review,
)


def results():
    return {
        "tracks": [
            {
                "track": {
                    "stable_track_id": "heldout-001",
                    "spotify_track_id": None,
                    "title": "Roses - Imanbek Remix",
                    "artists": ["SAINt JHN", "Imanbek"],
                    "album": "Roses (Imanbek Remix)",
                    "duration_ms": 176000,
                    "release_year": 2019,
                    "isrc": None,
                },
                "case_tags": ["named_remix"],
                "case_rationale": "Named-remix fixture.",
                "query": '"SAINt JHN" "Roses - Imanbek Remix" official',
                "error": None,
                "warnings": [],
                "candidates": [
                    {
                        "rank": 1,
                        "youtube_video_id": "abcdefghijk",
                        "canonical_url": "https://www.youtube.com/watch?v=abcdefghijk",
                        "title": "SAINt JHN - Roses (Imanbek Remix) (Official Audio)",
                        "uploader": "SAINt JHN",
                        "channel": "SAINt JHN",
                        "duration_seconds": 176,
                        "view_count": 1000,
                    },
                    {
                        "rank": 2,
                        "youtube_video_id": "lmnopqrstuv",
                        "canonical_url": "https://www.youtube.com/watch?v=lmnopqrstuv",
                        "title": "SAINt JHN - Roses (Tiësto Remix)",
                        "uploader": "Label",
                        "channel": "Label",
                        "duration_seconds": 175,
                        "view_count": None,
                    },
                ],
            }
        ]
    }


def test_feature_dataset_keeps_encoders_independent_and_views_weak():
    dataset = materialize_features(results(), manifest_sha256="a" * 64, dataset_role="HELD_OUT_UNLABELED")
    assert dataset["candidate_pair_count"] == 2
    first, second = dataset["tracks"][0]["candidates"]
    assert first["features"]["recording_eligible"] is True
    assert first["features"]["weak_evidence"]["relative_view_strength"] == 1.0
    assert second["features"]["recording_eligible"] is False
    assert second["features"]["weak_evidence"]["relative_view_strength"] is None


def test_review_is_one_row_per_candidate_and_labels_start_blank(tmp_path):
    dataset = materialize_features(results(), manifest_sha256="a" * 64, dataset_role="HELD_OUT_UNLABELED")
    path = tmp_path / "review.csv"
    write_heldout_review(path, dataset)
    rows = load_heldout_review(path)
    assert len(rows) == 2
    assert rows[0]["candidate_review_label"] == ""
    assert rows[0]["source_type"] == "OFFICIAL_AUDIO"
    assert list(rows[0]) == REVIEW_COLUMNS


@pytest.mark.parametrize("label", ["IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"])
def test_review_accepts_each_candidate_label(tmp_path, label):
    dataset = materialize_features(results(), manifest_sha256="a" * 64, dataset_role="HELD_OUT_UNLABELED")
    path = tmp_path / "review.csv"
    write_heldout_review(path, dataset)
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["candidate_review_label"] = label
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    assert load_heldout_review(path)[0]["candidate_review_label"] == label


def test_review_rejects_unknown_label(tmp_path):
    dataset = materialize_features(results(), manifest_sha256="a" * 64, dataset_role="HELD_OUT_UNLABELED")
    path = tmp_path / "review.csv"
    write_heldout_review(path, dataset)
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["candidate_review_label"] = "MATCH"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(Stage5B1AValidationError):
        load_heldout_review(path)


def test_dev_diagnostics_preserve_notes_verbatim():
    dataset = materialize_features(results(), manifest_sha256="a" * 64, dataset_role="DEV_ONLY")
    diagnostics = dev_diagnostics(
        dataset,
        {"heldout-001": {"review_label": "1", "optional_note": "exact note  !"}},
    )
    assert diagnostics["dataset_role"] == "DEV_ONLY_NOT_HELD_OUT"
    assert diagnostics["tracks"][0]["human_review_note_verbatim"] == "exact note  !"
