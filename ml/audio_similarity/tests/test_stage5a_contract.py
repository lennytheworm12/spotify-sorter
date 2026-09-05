import json
from pathlib import Path

import pytest

from audio_similarity.stage5a_contract import RepresentationContractError, load_contract


CONTRACT = (
    Path(__file__).parents[1]
    / "reports/holistic_stage4a_dual/audio_representation_v1.json"
)


def test_loads_authoritative_audio_representation_v1():
    contract = load_contract(CONTRACT)
    assert contract.method == "UNIFORM3_DUAL_MEAN"
    assert contract.centers_sec == (5, 15, 25)
    assert contract.sample_rate == 24000
    assert contract.preprocessing_version == "fma_full_mono_24khz_no_pad_v1"
    assert [encoder.encoder_id for encoder in contract.encoders] == [
        "laion_clap",
        "muq_mulan_large",
    ]
    assert contract.clap_weight == 0.7172981519
    assert contract.muq_weight == 0.2827018481
    assert len(contract.artifact_sha256) == len(contract.vector_contract_sha256) == 64


@pytest.mark.parametrize(
    ("field", "value"),
    [("selected_k", 1), ("segment_centers_seconds", [15])],
)
def test_rejects_non_frozen_temporal_sampling(tmp_path, field, value):
    payload = json.loads(CONTRACT.read_text())
    payload["temporal_sampling"][field] = value
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(payload))
    with pytest.raises(RepresentationContractError, match="mismatch"):
        load_contract(changed)


def test_analysis_identity_changes_with_every_bound_identity():
    contract = load_contract(CONTRACT)
    base = dict(
        corpus="fma_small",
        corpus_version="v1",
        stable_track_id="1",
        source_audio_sha256="a" * 64,
        canonical_pcm_sha256="b" * 64,
        encoder_id="laion_clap",
    )
    identity = contract.encoder_analysis_identity(**base)
    for field, replacement in (
        ("corpus_version", "v2"),
        ("stable_track_id", "2"),
        ("source_audio_sha256", "c" * 64),
        ("canonical_pcm_sha256", "d" * 64),
        ("encoder_id", "muq_mulan_large"),
    ):
        assert contract.encoder_analysis_identity(**(base | {field: replacement})) != identity
