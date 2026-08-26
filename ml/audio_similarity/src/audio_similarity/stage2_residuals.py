"""Provenance-safe extraction and table construction for exploratory Stage 2A."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .holistic_batch import _excerpt_bounds
from .mir_features import TrackFeatures, extract_features
from .mir_metrics import melody_components, rhythm_components, timbre_components

MIR_KEYS = ("chroma_mean", "chroma_sequence", "onset_envelope", "periodicity_profile", "tempo_bpm", "timbre_vector")
MERIT_KEYS = ("merit_melody", "merit_rhythm", "merit_timbre")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(path: str | Path) -> tuple[dict, Path]:
    path = Path(path).resolve()
    cfg = yaml.safe_load(path.read_text())
    return cfg, path.parent.parent


def validate_input_hashes(cfg: dict, root: Path) -> dict[str, str]:
    checked = {}
    inp = cfg["inputs"]
    pairs = [("ratings", "ratings_sha256"), ("trial_keys", "trial_keys_sha256"),
             ("competitive_model_pairs", "competitive_model_pairs_sha256"),
             ("manifest", "manifest_sha256")]
    for name, hash_name in pairs:
        actual = sha256_file(root / inp[name])
        if actual != inp[hash_name]:
            raise ValueError(f"SHA256_MISMATCH:{name}: expected {inp[hash_name]}, got {actual}")
        checked[name] = actual
    for name, spec in inp["embeddings"].items():
        actual = sha256_file(root / spec["path"])
        if actual != spec["sha256"]:
            raise ValueError(f"SHA256_MISMATCH:embedding:{name}: expected {spec['sha256']}, got {actual}")
        checked[f"embedding:{name}"] = actual
    return checked


def canonicalize_ratings(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Return one non-silently-selected label per trial and all raw judgments."""
    raw: list[dict] = []
    rows = []
    for trial_id, group in frame.fillna("").groupby("trial_id", sort=False):
        judgments = []
        for _, row in group.iterrows():
            log = json.loads(row.get("choice_log", "") or "[]")
            if log:
                judgments.extend({"trial_id": trial_id, **entry} for entry in log)
            elif row.get("choice", ""):
                judgments.append({"trial_id": trial_id, "v": row["choice"], "by": row.get("rated_by", ""), "legacy": True})
        raw.extend(judgments)
        labels = {str(j["v"]) for j in judgments}
        base = group.iloc[0].to_dict()
        if not labels:
            status, label, reason = "UNRATED", "", "UNRATED"
        elif len(labels) > 1:
            status, label, reason = "RATER_CONFLICT", "", "RATER_CONFLICT"
        else:
            status, label, reason = "CANONICAL", next(iter(labels)), ""
        rows.append({**base, "canonical_label": label, "label_status": status,
                     "raw_judgment_count": len(judgments), "exclusion_reason": reason})
    return pd.DataFrame(rows), raw


def cache_identity(audio_sha256: str, cfg: dict) -> str:
    payload = {"audio_sha256": audio_sha256, "excerpt": cfg["excerpt"],
               "revisions": cfg["inputs"]["revisions"]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def cache_path(cache_dir: Path, audio_sha256: str, cfg: dict) -> Path:
    return cache_dir / f"{cache_identity(audio_sha256, cfg)}.npz"


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    if not path.exists():
        return {}
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def _save_npz(path: Path, values: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **values)
    tmp.replace(path)


def extract_track(path: Path, audio_sha256: str, cfg: dict, cache_dir: Path, merit_encoder=None) -> str:
    """Extract a center5_v1 track. Existing complete portions are resumed."""
    from .audio import preprocess_file
    cp = cache_path(cache_dir, audio_sha256, cfg)
    values = _load_npz(cp)
    need_mir = not all(k in values for k in MIR_KEYS)
    need_merit = merit_encoder is not None and not all(k in values for k in MERIT_KEYS)
    if need_mir or need_merit:
        wav = preprocess_file(path)
        # Stage 1 persisted the provenance name ``center5_v1`` while its
        # sampler registry calls the identical implementation ``center5``.
        strategy = "center5" if cfg["excerpt"]["strategy"] == "center5_v1" else cfg["excerpt"]["strategy"]
        start, end = _excerpt_bounds(wav, strategy, cfg["excerpt"]["sample_rate"])
        excerpt = wav[start:end]
        expected = cfg["excerpt"]["seconds"] * cfg["excerpt"]["sample_rate"]
        if len(excerpt) != expected:
            raise ValueError(f"EXCERPT_LENGTH:{path}:{len(excerpt)} != {expected}")
        if need_mir:
            f = extract_features(excerpt.numpy(), cfg["excerpt"]["sample_rate"])
            values.update(chroma_mean=f.chroma_mean, chroma_sequence=f.chroma_sequence,
                          onset_envelope=f.onset_envelope, periodicity_profile=f.periodicity_profile,
                          tempo_bpm=np.asarray(f.tempo_bpm), timbre_vector=f.timbre_vector)
        if need_merit:
            out = merit_encoder.encode_waveform(excerpt)
            values.update(merit_melody=out.melody, merit_rhythm=out.rhythm, merit_timbre=out.timbre)
        values["cache_identity"] = np.asarray(cache_identity(audio_sha256, cfg))
        values["source_audio_sha256"] = np.asarray(audio_sha256)
        _save_npz(cp, values)
    required = MIR_KEYS + (MERIT_KEYS if merit_encoder is not None else ())
    if not all(k in values for k in required):
        raise ValueError(f"INCOMPLETE_CACHE:{path}")
    for key in required:
        if not np.isfinite(np.asarray(values[key], dtype=float)).all():
            raise ValueError(f"NONFINITE_FEATURE:{path}:{key}")
    return "EXISTING" if not (need_mir or need_merit) else "EXTRACTED"


def required_track_ids(cfg: dict, root: Path) -> list[int]:
    keys = json.loads((root / cfg["inputs"]["trial_keys"]).read_text())["trials"].values()
    return sorted({int(v[k]) for v in keys for k in ("query_track_id", "candidate_a", "candidate_b")})


def _cos(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    den = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / den) if den else 0.0


def pair_residuals(q: dict, c: dict) -> dict[str, float]:
    mel = melody_components(q["chroma_sequence"], c["chroma_sequence"])
    rhy = rhythm_components(q["onset_envelope"], c["onset_envelope"], q["periodicity_profile"],
                            c["periodicity_profile"], float(q["tempo_bpm"]), float(c["tempo_bpm"]))
    tim = timbre_components(q["timbre_vector"], c["timbre_vector"])
    out = {"chroma_global_cos": mel.chroma_global_cos, "chroma_dtw_sim": mel.chroma_dtw_sim,
           "transposition_best_cos": mel.transposition_best_cos, "onset_cos_fixed": rhy.onset_cos_fixed,
           "onset_dtw_sim": rhy.onset_dtw_sim, "tempogram_cos": rhy.tempogram_cos,
           "log_tempo_ratio": -abs(float(np.log(max(float(q['tempo_bpm']), 1e-6) / max(float(c['tempo_bpm']), 1e-6)))),
           "timbre_cos": tim.timbre_cos}
    if all(k in q and k in c for k in MERIT_KEYS):
        out.update(merit_melody_cos=_cos(q["merit_melody"], c["merit_melody"]),
                   merit_rhythm_cos=_cos(q["merit_rhythm"], c["merit_rhythm"]),
                   merit_timbre_cos=_cos(q["merit_timbre"], c["merit_timbre"]))
    return out


def load_embedding_map(path: Path) -> tuple[dict[int, np.ndarray], str]:
    df = pd.read_parquet(path)
    ok = df[df.status == "SUCCESS"]
    return {int(r.track_id): np.asarray(r.embedding, float) for r in ok.itertuples()}, str(ok.analysis_key.iloc[0])


def build_trial_table(cfg: dict, root: Path) -> tuple[pd.DataFrame, list[dict]]:
    validate_input_hashes(cfg, root)
    ratings = pd.read_csv(root / cfg["inputs"]["ratings"], dtype=str).fillna("")
    canonical, raw = canonicalize_ratings(ratings)
    keys = json.loads((root / cfg["inputs"]["trial_keys"]).read_text())["trials"]
    manifest = pd.read_parquet(root / cfg["inputs"]["manifest"]).set_index("track_id")
    embeddings = {name: load_embedding_map(root / spec["path"]) for name, spec in cfg["inputs"]["embeddings"].items()}
    cache_dir = root / cfg["paths"]["cache_dir"]
    feature_maps = {}
    for tid in required_track_ids(cfg, root):
        sha = str(manifest.loc[tid, "audio_sha256"])
        feature_maps[tid] = _load_npz(cache_path(cache_dir, sha, cfg))
    rows = []
    components = [x for xs in cfg["components"].values() for x in xs] + cfg["diagnostics"]
    for r in canonical.itertuples():
        key = keys[r.trial_id]; q, a, b = (int(key[x]) for x in ("query_track_id", "candidate_a", "candidate_b"))
        kind = key["kind"]
        slice_name = "anchor_negative" if kind == "anchor_negative" else ("direct_disagreement" if kind.startswith("disagree:") else "competitive_rank2")
        reason = r.exclusion_reason
        if r.canonical_label in ("Tie", "Neither"):
            reason = r.canonical_label.upper()
        row = {"trial_id": r.trial_id, "query_track_id": q, "candidate_a_id": a, "candidate_b_id": b,
               "trial_kind": kind, "slice": slice_name, "canonical_label": r.canonical_label,
               "label_status": r.label_status, "raw_judgment_count": r.raw_judgment_count,
               "primary_eligible": bool(r.label_status == "CANONICAL" and r.canonical_label in ("A", "B") and slice_name != "anchor_negative"),
               "exclusion_reason": reason, "excerpt_strategy": cfg["excerpt"]["strategy"]}
        for name, (emap, analysis_key) in embeddings.items():
            row[f"{name}_sim_a"] = _cos(emap[q], emap[a]); row[f"{name}_sim_b"] = _cos(emap[q], emap[b])
            row[f"{name}_analysis_key"] = analysis_key
        if not feature_maps[q] or not feature_maps[a] or not feature_maps[b]:
            raise ValueError(f"MISSING_FEATURE_COVERAGE:{r.trial_id}")
        sa, sb = pair_residuals(feature_maps[q], feature_maps[a]), pair_residuals(feature_maps[q], feature_maps[b])
        for comp in components:
            if comp not in sa or comp not in sb:
                raise ValueError(f"MISSING_COMPONENT:{r.trial_id}:{comp}")
            row[f"{comp}_sim_a"], row[f"{comp}_sim_b"] = sa[comp], sb[comp]
        row["feature_cache_key_q"] = str(feature_maps[q]["cache_identity"])
        row["feature_cache_key_a"] = str(feature_maps[a]["cache_identity"])
        row["feature_cache_key_b"] = str(feature_maps[b]["cache_identity"])
        rows.append(row)
    table = pd.DataFrame(rows).sort_values("trial_id").reset_index(drop=True)
    if len(table) != 136 or table.trial_id.nunique() != 136:
        raise ValueError(f"TRIAL_DENOMINATOR:{len(table)}/{table.trial_id.nunique()}")
    primary = table[table.primary_eligible]
    numeric = [c for c in table if c.endswith("_sim_a") or c.endswith("_sim_b")]
    if primary[numeric].isna().any().any() or not np.isfinite(primary[numeric].to_numpy(float)).all():
        raise ValueError("INCOMPLETE_PRIMARY_FEATURE_COVERAGE")
    return table, raw
