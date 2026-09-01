from __future__ import annotations

from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b1b_manifest import load_heldout_manifest


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "reports" / "stage5b1b" / "heldout_tracks.json"
EXPECTED_SHA256 = "39557ede8f07bde129ad23d2bc64a0faf0fff755356cd87f2054e14f91d81e5a"


def test_heldout_manifest_is_frozen_hash_locked_and_distinct_from_dev():
    manifest = load_heldout_manifest(MANIFEST, expected_sha256=EXPECTED_SHA256)
    assert file_sha256(MANIFEST) == EXPECTED_SHA256
    assert len(manifest.tracks) == 50
    assert manifest.stable_track_ids == tuple(f"s5b1b_{index:03d}" for index in range(1, 51))
    assert all(item.track.duration_ms for item in manifest.tracks)
    assert not any(value.startswith("s5b1a_") for value in manifest.stable_track_ids)


def test_heldout_manifest_covers_predeclared_difficult_case_families():
    manifest = load_heldout_manifest(MANIFEST, expected_sha256=EXPECTED_SHA256)
    tags = {tag for item in manifest.tracks for tag in item.case_tags}
    for expected in (
        "straightforward_studio",
        "named_remix",
        "live",
        "remaster",
        "taylors_version",
        "acoustic",
        "extended_mix",
        "explicit_version",
        "k_pop",
        "label_hosted",
        "music_video_theatrical_intro",
        "cover_recording",
        "international",
        "non_english",
        "diacritics",
        "small_artist",
    ):
        assert expected in tags


def test_heldout_manifest_hash_change_is_a_hard_failure(tmp_path):
    changed = tmp_path / "heldout.json"
    changed.write_bytes(MANIFEST.read_bytes() + b"\n")
    with pytest.raises(Stage5B1AValidationError, match="SHA-256 mismatch"):
        load_heldout_manifest(changed, expected_sha256=EXPECTED_SHA256)
