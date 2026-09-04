from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5d0a_manifest import (
    MAX_BATCH_SIZE,
    build_batch_manifest,
    build_global_manifest,
    freeze_catalog_and_batch_one,
)


def catalog(count: int = 1_025) -> dict:
    return {
        "schema_version": "stage5d0a-commercial-seed-catalog-input-v1",
        "catalog_design": {
            "design_id": "TEST_COMMERCIAL_CATALOG_V1",
            "source_policy": "fixture",
        },
        "tracks": [
            {
                "spotify_track_id": f"{index:022d}",
                "title": f"Song {index}",
                "artists": [f"Artist {index % 31}"],
                "album": f"Album {index % 101}",
                "duration_ms": 180_000 + index,
                "release_year": 2000 + index % 27,
                "isrc": None,
                "source_memberships": [f"YEAR:{2000 + index % 27}"],
            }
            for index in range(count)
        ],
    }


def manifest(count: int = 1_025) -> dict:
    return build_global_manifest(catalog(count), catalog_input_sha256="a" * 64)


def test_global_manifest_and_batch_partition_are_deterministic() -> None:
    first = manifest()
    second = manifest()
    assert first == second
    assert first["unique_track_count"] == 1_025
    assert first["batch_count"] == 3
    batches = [build_batch_manifest(first, number) for number in (1, 2, 3)]
    assert [len(row["tracks"]) for row in batches] == [500, 500, 25]
    assigned = [
        track["spotify_track_id"]
        for batch in batches
        for track in batch["tracks"]
    ]
    assert len(assigned) == len(set(assigned)) == 1_025
    assert batches[0]["automatic_next_batch"] is False


def test_seeded_order_is_not_input_or_alphabetical_order() -> None:
    value = manifest(600)
    ids = [row["spotify_track_id"] for row in value["tracks"]]
    assert ids != sorted(ids)
    assert ids != [f"{index:022d}" for index in range(600)]


def test_spotify_id_deduplication_merges_source_memberships() -> None:
    source = catalog(2)
    duplicate = dict(source["tracks"][0])
    duplicate["source_memberships"] = ["ANOTHER_SOURCE"]
    source["tracks"].append(duplicate)
    value = build_global_manifest(source, catalog_input_sha256="b" * 64)
    row = next(
        item
        for item in value["tracks"]
        if item["spotify_track_id"] == duplicate["spotify_track_id"]
    )
    assert value["spotify_id_duplicate_count"] == 1
    assert row["source_memberships"] == ["ANOTHER_SOURCE", "YEAR:2000"]


def test_catalog_requires_explicit_design_and_2000_2026_bounds() -> None:
    missing = catalog()
    del missing["catalog_design"]
    with pytest.raises(Stage5B1AValidationError, match="design"):
        build_global_manifest(missing, catalog_input_sha256="c" * 64)
    invalid_year = catalog()
    invalid_year["tracks"][0]["release_year"] = 1999
    with pytest.raises(Stage5B1AValidationError, match="outside"):
        build_global_manifest(invalid_year, catalog_input_sha256="d" * 64)


def test_freeze_writes_only_global_and_batch_one_manifests(tmp_path: Path) -> None:
    source = tmp_path / "catalog.json"
    source.write_text(json.dumps(catalog()), encoding="utf-8")
    report = tmp_path / "report"
    global_manifest, batch = freeze_catalog_and_batch_one(source, report)
    assert len(batch["tracks"]) == MAX_BATCH_SIZE
    assert file_sha256(report / "global_seed_catalog_manifest.json") == (
        report / "global_seed_catalog_manifest.sha256"
    ).read_text(encoding="utf-8").strip()
    assert global_manifest["catalog_input_sha256"] == file_sha256(source)
    assert not list(report.glob("batch_000[2-9]_manifest.json"))
    freeze_catalog_and_batch_one(source, report)
    changed = json.loads(source.read_text(encoding="utf-8"))
    changed["tracks"][0]["title"] = "Changed"
    source.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(Stage5B1AValidationError, match="refusing"):
        freeze_catalog_and_batch_one(source, report)
