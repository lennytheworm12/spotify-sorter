from __future__ import annotations

import copy
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest
import yaml

from audio_similarity.stage2b_contract import (
    ContractError,
    generate_query_split,
    load_contract,
    normalize_artist,
    validate_contract_shape,
    validate_input_hashes,
    validate_split,
)

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs" / "holistic_stage2b_fusion.yaml"


def test_frozen_contract_and_real_input_hashes_validate():
    config = load_contract(CONFIG)
    checked = validate_input_hashes(config, ROOT)
    assert len(checked) == 13
    assert config["provenance"]["encoders"]["muq_mulan_large"]["revision"] == "2e01c796b71dca71b45251384c04cd7b237c9020"


def test_contract_rejects_revision_or_model_protocol_drift():
    config = load_contract(CONFIG)
    changed = copy.deepcopy(config)
    changed["selection"]["fusion_model"]["fit_intercept"] = True
    with pytest.raises(ContractError, match="no intercept"):
        validate_contract_shape(changed)
    changed = copy.deepcopy(config)
    changed["selection"]["permitted_representation_sets"].pop()
    with pytest.raises(ContractError, match="seven representation"):
        validate_contract_shape(changed)


def test_hash_validation_fails_closed(tmp_path):
    config = load_contract(CONFIG)
    reduced = copy.deepcopy(config)
    target = tmp_path / "query.csv"
    target.write_text("changed", encoding="utf-8")
    reduced["inputs"]["manifest"] = {"path": "query.csv", "sha256": "0" * 64}
    with pytest.raises(ContractError, match="SHA-256 mismatch"):
        validate_input_hashes(reduced, tmp_path)


def test_artist_normalization_is_unicode_casefolded_and_whitespace_collapsed():
    assert normalize_artist("  STRAẞE\t Music  ") == normalize_artist("strasse music")
    assert normalize_artist("Ａrtist") == "artist"


def test_real_split_is_deterministic_exact_and_artist_grouped():
    source = ROOT / "reports/holistic_stage1a/frozen_queries.csv"
    first = generate_query_split(source, 20260829)
    second = generate_query_split(source, 20260829)
    assert first == second
    assert first["counts"] == {"TRAIN": 16, "VALIDATION": 8, "TEST": 16}
    validate_split(first["queries"])
    per_genre = Counter((row["top_genre"], row["split"]) for row in first["queries"])
    for genre in {row["top_genre"] for row in first["queries"]}:
        assert [per_genre[(genre, split)] for split in ("TRAIN", "VALIDATION", "TEST")] == [2, 1, 2]
    howie = {row["split"] for row in first["queries"] if row["artist_normalized"] == "howie mitchell"}
    assert len(howie) == 1


def test_split_rejects_cross_split_artist_overlap():
    source = ROOT / "reports/holistic_stage1a/frozen_queries.csv"
    items = generate_query_split(source, 20260829)["queries"]
    repeated = [row for row in items if row["artist_normalized"] == "howie mitchell"]
    repeated[0]["split"] = "VALIDATION" if repeated[1]["split"] != "VALIDATION" else "TRAIN"
    with pytest.raises(ContractError, match="artist group"):
        validate_split(items)
