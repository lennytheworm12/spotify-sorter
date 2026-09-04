import json
from collections import Counter
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5c1_manifest import (
    build_curated_manifest,
    freeze_curated_manifest,
    verify_frozen_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_curated_manifest_is_deterministic_and_exactly_five_groups_of_five(tmp_path):
    first = build_curated_manifest(PROJECT_ROOT)
    second = build_curated_manifest(PROJECT_ROOT)

    assert first == second
    assert len(first["tracks"]) == 25
    assert Counter(row["curation_group"] for row in first["tracks"]) == Counter(
        {group: 5 for group in "ABCDE"}
    )
    assert len({row["spotify_track_id"] for row in first["tracks"]}) == 25
    assert all(row["human_safe_label"] in {"IDEAL", "ACCEPTABLE"} for row in first["tracks"])
    assert all(row["selected_youtube_url"].endswith(row["selected_youtube_video_id"]) for row in first["tracks"])

    output = tmp_path / "curated_manifest.json"
    _, first_sha = freeze_curated_manifest(PROJECT_ROOT, output_path=output)
    _, second_sha = freeze_curated_manifest(PROJECT_ROOT, output_path=output)
    assert first_sha == second_sha


def test_manifest_sha_detects_post_freeze_mutation(tmp_path):
    output = tmp_path / "curated_manifest.json"
    freeze_curated_manifest(PROJECT_ROOT, output_path=output)
    payload = json.loads(output.read_text())
    payload["tracks"][0]["title"] = "mutated"
    output.write_text(json.dumps(payload))

    with pytest.raises(Stage5B1AValidationError, match="changed after freeze"):
        verify_frozen_manifest(output)


def test_manifest_preserves_frozen_representation_and_selector_contracts():
    manifest = build_curated_manifest(PROJECT_ROOT)
    contracts = manifest["frozen_contracts"]
    assert contracts["discovery"] == "NATURAL_TITLE_FIRST3_ARTISTS_THEN_SINGLE_ARTIST_V1"
    assert contracts["selection"] == "STAGE5B3_MINIMAL_YOUTUBE_PRIOR_V1"
    assert contracts["segment_centers_seconds"] == [5, 15, 25]
    assert contracts["segment_duration_seconds"] == 5
    assert contracts["clap_weight"] == 0.7172981519
    assert contracts["muq_weight"] == 0.2827018481
