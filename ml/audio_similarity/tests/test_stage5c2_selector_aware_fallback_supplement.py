from __future__ import annotations

import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/stage5c2_selector_aware_fallback_supplement"
FROZEN = ROOT / "reports/stage5c2_representative_100"


def _json(name: str) -> dict:
    return json.loads((REPORT / name).read_text(encoding="utf-8"))


def test_targeted_supplement_recovers_both_owner_supplied_sources() -> None:
    result = _json("targeted_discovery.json")
    assert result["verdict"] == "SELECTOR_AWARE_FALLBACK_TARGETED_VALIDATED"
    by_id = {row["stage5c2_track_id"]: row for row in result["tracks"]}
    assert by_id["stage5c2_008"]["owner_reference_recovered"] is True
    assert by_id["stage5c2_008"]["selector_aware_result"]["selected_video_id"] == (
        "v224EdAkZr8"
    )
    love = by_id["stage5c2_019"]
    assert love["owner_reference_recovered"] is True
    assert love["selector_aware_result"]["selected_video_id"] == "i4YFngxyJ0k"
    assert love["selector_aware_result"]["query_variant_index"] == 4
    assert love["selector_aware_result"]["total_provider_requests"] == 4


def test_supplement_preserves_frozen_stage5c2_inputs_and_selector() -> None:
    result = _json("targeted_discovery.json")
    for name, expected in result["frozen_stage5c2_input_sha256"].items():
        assert file_sha256(FROZEN / name) == expected
    assert result["scope_guards"] == {
        "historical_stage5c2_rewritten": False,
        "stage5b3_selector_modified": False,
        "media_downloads": 0,
        "candidate_pool_merges": 0,
        "production_activation": False,
        "broad_corpus_search": False,
    }


def test_supplement_artifact_manifest_hashes_are_portable_and_valid() -> None:
    manifest = _json("artifact_manifest.json")
    for record in manifest["artifacts"].values():
        assert not Path(record["path"]).is_absolute()
        path = ROOT / record["path"]
        assert path.stat().st_size == record["size_bytes"]
        assert file_sha256(path) == record["sha256"]
