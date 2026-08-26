from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from audio_similarity.stage2b_contract import ContractError
from audio_similarity.stage2b_dataset import build_fusion_dataset, delta_features, swap_features

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/holistic_stage2b_fusion_single_reviewer.yaml"
REPORT = ROOT / "reports/holistic_stage2b"


def test_delta_is_exactly_antisymmetric_and_rejects_wrong_shape():
    a = np.array([0.7, -0.2, 0.1])
    b = np.array([0.4, 0.5, -0.3])
    delta = delta_features(a, b)
    np.testing.assert_array_equal(swap_features(delta), delta_features(b, a))
    with pytest.raises(ContractError, match="exactly three"):
        delta_features([1, 2], [3, 4])


def test_real_fusion_dataset_is_deterministic_complete_and_provenanced():
    first = build_fusion_dataset(CONFIG, ROOT)
    first_bytes = (REPORT / "fusion_dataset.csv").read_bytes()
    second = build_fusion_dataset(CONFIG, ROOT)
    assert first == second
    assert (REPORT / "fusion_dataset.csv").read_bytes() == first_bytes
    assert first["row_count"] == 240
    assert first["binary_row_count"] + first["excluded_row_count"] == 240
    assert first["anti_symmetry_validated"] is True
    frame = pd.read_csv(REPORT / "fusion_dataset.csv")
    assert set(frame["split"]) == {"TRAIN", "VALIDATION", "TEST"}
    assert set(frame["exclusion_reason"].dropna()) <= {"tie", "neither"}
    for column in ("delta_clap", "delta_mert", "delta_muq"):
        assert np.isfinite(frame[column]).all()
    assert frame["config_sha256"].nunique() == 1
    manifest = json.loads((REPORT / "fusion_dataset_manifest.json").read_text())
    assert manifest["fusion_dataset_sha256"] == first["fusion_dataset_sha256"]
