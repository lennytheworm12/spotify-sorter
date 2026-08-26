import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch

from audio_similarity.holistic_batch import _excerpt_bounds
from audio_similarity.stage2_residuals import (MERIT_KEYS, MIR_KEYS, cache_identity,
    canonicalize_ratings, extract_track, pair_residuals, stage2_excerpt_bounds,
    validate_input_hashes)


def test_canonicalization_preserves_agreeing_and_flags_conflicting_logs():
    frame = pd.DataFrame([
        {"trial_id": "q:1", "choice": "A", "choice_log": json.dumps([{"v":"A","by":"x"},{"v":"A","by":"y"}])},
        {"trial_id": "q:2", "choice": "A", "choice_log": json.dumps([{"v":"A","by":"x"},{"v":"B","by":"y"}])},
        {"trial_id": "q:3", "choice": "Tie", "choice_log": ""},
        {"trial_id": "q:4", "choice": "Neither", "choice_log": ""},
    ])
    canonical, raw = canonicalize_ratings(frame)
    assert len(raw) == 6
    assert canonical.set_index("trial_id").loc["q:1", "canonical_label"] == "A"
    conflict = canonical.set_index("trial_id").loc["q:2"]
    assert conflict.label_status == "RATER_CONFLICT" and conflict.canonical_label == ""
    assert set(canonical.canonical_label) >= {"Tie", "Neither"}


def test_center5_v1_alias_uses_exact_stage1_bounds():
    wav = np.zeros(30 * 24000, np.float32)
    stage1 = _excerpt_bounds(wav, "center5", 24000)
    assert stage2_excerpt_bounds(wav, _cfg()) == stage1
    assert stage1 == (12 * 24000 + 12000, 17 * 24000 + 12000)


def test_input_hash_validation_accepts_exact_and_rejects_mutation(tmp_path):
    paths = {}
    for name in ("ratings", "trial_keys", "competitive_model_pairs", "manifest"):
        path = tmp_path / name; path.write_text(name); paths[name] = path
    emb = tmp_path / "embedding"; emb.write_text("embedding")
    import hashlib
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    cfg = {"inputs": {**{name: path.name for name, path in paths.items()},
        **{f"{name}_sha256": digest(path) for name, path in paths.items()},
        "embeddings": {"base": {"path": emb.name, "sha256": digest(emb)}}}}
    assert len(validate_input_hashes(cfg, tmp_path)) == 5
    paths["ratings"].write_text("changed")
    import pytest
    with pytest.raises(ValueError, match="SHA256_MISMATCH:ratings"):
        validate_input_hashes(cfg, tmp_path)


def _cfg():
    return {"excerpt":{"strategy":"center5_v1","sample_rate":24000,"channels":"mono","seconds":5},
            "inputs":{"revisions":{"mir_features_sha256":"m","merit_encoder_sha256":"x"}}}


def test_cache_identity_is_deterministic_and_versioned():
    a = cache_identity("abc", _cfg())
    assert a == cache_identity("abc", _cfg())
    changed = _cfg(); changed["inputs"]["revisions"]["mir_features_sha256"] = "m2"
    assert a != cache_identity("abc", changed)


def test_extract_is_finite_complete_and_resumable_with_fake_merit(tmp_path, monkeypatch):
    import audio_similarity.audio as audio
    monkeypatch.setattr(audio, "preprocess_file", lambda _: torch.linspace(-1, 1, 30 * 24000))
    calls = {"n":0}
    class FakeMerit:
        def encode_waveform(self, wav):
            calls["n"] += 1
            unit = np.ones(128, np.float32) / np.sqrt(128)
            return SimpleNamespace(melody=unit, rhythm=unit, timbre=unit)
    first = extract_track(tmp_path/"x.mp3", "abc", _cfg(), tmp_path/"cache", FakeMerit())
    second = extract_track(tmp_path/"x.mp3", "abc", _cfg(), tmp_path/"cache", FakeMerit())
    assert (first, second, calls["n"]) == ("EXTRACTED", "EXISTING", 1)
    with np.load(next((tmp_path/"cache").glob("*.npz"))) as z:
        assert all(k in z for k in MIR_KEYS + MERIT_KEYS)
        assert all(np.isfinite(z[k]).all() for k in MIR_KEYS + MERIT_KEYS)


def test_pair_residuals_emit_every_predeclared_component():
    rng = np.random.default_rng(2)
    f = {"chroma_sequence":abs(rng.normal(size=(12,20))), "onset_envelope":abs(rng.normal(size=20)),
         "periodicity_profile":abs(rng.normal(size=10)), "tempo_bpm":np.asarray(120.),
         "timbre_vector":rng.normal(size=50), "merit_melody":rng.normal(size=128),
         "merit_rhythm":rng.normal(size=128), "merit_timbre":rng.normal(size=128)}
    out = pair_residuals(f, f)
    assert len(out) == 11 and all(np.isfinite(list(out.values())))
