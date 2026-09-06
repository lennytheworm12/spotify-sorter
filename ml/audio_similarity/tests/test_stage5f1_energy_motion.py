from __future__ import annotations

import json
from dataclasses import replace

import pytest
import torch

from audio_similarity.energy_motion_config import (
    ComparisonConfig,
    ExtractionConfig,
    canonical_sha256,
    default_config,
    load_config,
    validate_config,
)
from audio_similarity.energy_motion_loudness import parse_ebur128_summary
from audio_similarity.energy_motion_audio import extract_track, file_sha256
from audio_similarity.energy_motion_schema import FamilyResult, TrackFeatures
from audio_similarity.energy_motion_similarity import (
    compare_tracks,
    derived_track_features,
    fit_reference_scaler,
)
from audio_similarity.stage5f1_cache import FeatureCache


def _family(status="VALID", **values):
    return {"status": status, "reasons": [], "values": values}


def _track(index: int = 0):
    scale = 1 + index / 20
    return {
        "source_sha256": f"sha-{index}",
        "status": "SUCCESS",
        "activity": _family(
            onset_rate_hz=2 * scale,
            spectral_flux_q90=0.2 * scale,
        ),
        "percussion": _family(
            percussive_onset_rate_hz=1.5 * scale,
            percussive_energy_ratio=0.4 * scale,
        ),
        "dynamics": _family(
            dynamic_range_db=8 * scale,
            dynamic_complexity_db=2 * scale,
            dynamic_step_db=1 * scale,
        ),
        "source_level": _family(
            loudness_range_lu=5 * scale,
            integrated_loudness_lufs=-14 + index / 100,
        ),
        "pulse": _family(
            primary_bpm=120,
            pulse_reliability=0.8,
            metrical_certainty=0.9,
            exact_tempo_eligible=True,
            local_family_iqr_octaves=0.02 * scale,
            local_family_mad_octaves=0.01 * scale,
        ),
        "beat": _family(
            beat_strength_proxy=0.7,
            beat_onset_support=0.75,
            beat_interval_robust_cv=0.03 * scale,
        ),
        "metrical_profiles": [{
            "bpm": 120, "candidate_strength": 0.8, "support_duration_seconds": 20,
            "factors": {"0.5": 0.4, "1.0": 1.0, "2.0": 0.7, "4.0": 0.3},
        }],
    }


def test_config_is_frozen_and_rejects_invalid_or_source_loudness_similarity():
    config = default_config()
    assert config.sha256 == canonical_sha256(config.as_dict())
    with pytest.raises(ValueError, match="mel frequency"):
        validate_config(replace(config, extraction=replace(config.extraction, mel_fmax_hz=12000)))
    with pytest.raises(ValueError, match="excludes source loudness"):
        validate_config(replace(config, extraction=replace(config.extraction, raw_source_loudness_in_similarity=True)))


def test_config_file_rejects_missing_nested_keys(tmp_path):
    document = default_config().as_dict()
    del document["extraction"]["normalization_target_lufs"]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="extraction config keys"):
        load_config(path)


def test_loudness_parser_uses_final_summary():
    stderr = """
Summary:
  Integrated loudness:
    I:         -20.0 LUFS
  Loudness range:
    LRA:         2.0 LU
Summary:
  Integrated loudness:
    I:         -14.3 LUFS
  Loudness range:
    LRA:         6.2 LU
"""
    assert parse_ebur128_summary(stderr) == (-14.3, 6.2)
    with pytest.raises(ValueError, match="Summary"):
        parse_ebur128_summary("no summary")


def test_scaler_and_pair_comparison_are_symmetric_and_self_is_one():
    tracks = [_track(index) for index in range(40)]
    comparison = ComparisonConfig()
    scaler = fit_reference_scaler(tracks, comparison, "corpus-sha")
    left, right = tracks[4], tracks[19]
    lr = compare_tracks("a", "b", left, right, scaler, comparison).as_dict()
    rl = compare_tracks("b", "a", right, left, scaler, comparison).as_dict()
    assert lr["components"] == rl["components"]
    assert lr["feature_differences"] == rl["feature_differences"]
    self_pair = compare_tracks("a", "a", left, left, scaler, comparison).as_dict()
    for name in ("activity", "dynamics", "attack_texture", "pulse_stability", "felt_pace", "exact_tempo", "tempo_family", "subdivision"):
        component = self_pair["components"][name]
        if not component["abstain"]:
            assert component["similarity"] == pytest.approx(1.0)
        else:
            assert component["effective_mismatch"] == 0


def test_low_confidence_track_cannot_be_rescued_by_confident_partner():
    tracks = [_track(index) for index in range(40)]
    scaler = fit_reference_scaler(tracks, ComparisonConfig(), "corpus-sha")
    low = _track(1)
    low["pulse"] = _family("LOW_CONFIDENCE", primary_bpm=120, pulse_reliability=0.3)
    low["beat"] = _family("LOW_CONFIDENCE", beat_onset_support=0.8, beat_strength_proxy=None)
    pair = compare_tracks("low", "high", low, _track(2), scaler, ComparisonConfig()).as_dict()
    assert pair["components"]["tempo_family"]["abstain"] is True
    assert pair["components"]["tempo_family"]["effective_mismatch"] == 0


def test_arousal_proxy_excludes_source_loudness():
    tracks = [_track(index) for index in range(40)]
    scaler = fit_reference_scaler(tracks, ComparisonConfig(), "corpus-sha")
    a = _track(4)
    b = json.loads(json.dumps(a))
    b["source_sha256"] = "other"
    b["source_level"]["values"]["integrated_loudness_lufs"] = -35
    assert derived_track_features(a, scaler)["arousal_proxy_0_1"] == derived_track_features(b, scaler)["arousal_proxy_0_1"]


def test_cache_detects_corrupted_payload(tmp_path):
    cache = FeatureCache(tmp_path / "cache.sqlite")
    cache.put("key", "source", {"status": "SUCCESS", "value": 1})
    assert cache.get("key") == {"status": "SUCCESS", "value": 1}
    cache.db.execute("UPDATE feature_cache SET payload='{}' WHERE feature_key='key'")
    cache.db.commit()
    assert cache.get("key") is None
    assert cache.db.execute("SELECT reason FROM quarantine").fetchone()[0] == "PAYLOAD_HASH_MISMATCH"
    cache.close()


def test_schema_rejects_nonfinite_values():
    with pytest.raises(ValueError, match="non-finite"):
        FamilyResult("VALID", values={"bad": float("nan")})


def test_preliminary_source_floor_abstains_before_normalized_motion(tmp_path, monkeypatch):
    source = tmp_path / "short-audio.bin"
    source.write_bytes(b"fixture")
    waveform = torch.full((2, 5 * 8000), 0.1)
    monkeypatch.setattr("audio_similarity.energy_motion_audio.load_audio", lambda _path: (waveform, 8000))
    monkeypatch.setattr("audio_similarity.energy_motion_audio.measure_source_level", lambda *_args, **_kwargs: {
        "integrated_loudness_lufs": -20.0, "loudness_range_lu": 0.0,
        "source_rms_dbfs": -20.0, "sample_peak_dbfs": -20.0,
        "crest_factor_db": 0.0, "clipped_sample_fraction": 0.0,
    })
    monkeypatch.setattr("audio_similarity.energy_motion_audio.extract_motion",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("motion must abstain")))
    result = extract_track(source, file_sha256(source), ExtractionConfig(), "env", "implementation")
    assert result.status == "PARTIAL"
    assert result.normalization.status == "UNAVAILABLE"
    assert result.normalization.reasons == ("SOURCE_FLOOR",)
