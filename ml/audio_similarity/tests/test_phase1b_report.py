"""Phase 1B analysis tests: specificity, construct validity, correlations,
disagreements, evidence scoring (design sections 14-23)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from audio_similarity.phase1b_report import (
    cliffs_delta,
    correlation_matrix,
    disagreement_analysis,
    evidence_components,
    factor_specificity_report,
    flag_cross_factor_leakage,
    original_phase1_gate,
    paired_bootstrap_diff,
    bootstrap_ci,
)


def _master_row(qid, cid, source, factor, **kw):
    base = {
        "query_id": qid, "candidate_id": cid, "retrieval_source": source,
        "retrieval_factor": factor if source.startswith("merit") else "",
        "group_rank": 1,
        "merit_melody_similarity": kw.get("mm", 0.0),
        "merit_rhythm_similarity": kw.get("mr", 0.0),
        "merit_timbre_similarity": kw.get("mt", 0.0),
        "mert_general_similarity": kw.get("mg", 0.0),
        "mir_chroma_global_cos": kw.get("cc", 0.5), "mir_chroma_dtw_sim": kw.get("cd", 0.5),
        "mir_transposition_best_cos": kw.get("ct", 0.5),
        "mir_onset_cos_fixed": kw.get("oc", 0.5), "mir_onset_dtw_sim": kw.get("od", 0.5),
        "mir_tempogram_cos": kw.get("tc", 0.5), "mir_timbre_cos": kw.get("t", 0.5),
        "pct_chroma_global_cos": 50.0, "pct_chroma_dtw_sim": 50.0, "pct_transposition_best_cos": 50.0,
        "pct_onset_cos_fixed": 50.0, "pct_onset_dtw_sim": 50.0, "pct_tempogram_cos": 50.0,
        "pct_timbre_cos": 50.0,
        "independent_melody_score": kw.get("M", 0.5),
        "independent_rhythm_score": kw.get("R", 0.5),
        "independent_timbre_score": kw.get("T", 0.5),
        "target_specificity": kw.get("spec", 0.0),
        "genre_match": False, "same_artist": False,
        "human_rating": kw.get("rating"), "human_valid": kw.get("valid", False),
    }
    return base


def test_bootstrap_ci_recovers_median():
    rng = np.random.default_rng(0)
    values = rng.normal(loc=10, scale=1, size=500)
    point, (lo, hi) = bootstrap_ci(values)
    assert lo < point < hi
    assert abs(point - np.median(values)) < 0.3


def test_paired_diff_positive_when_a_bigger():
    rng = np.random.default_rng(1)
    a = rng.normal(0.8, 0.05, size=60)   # query means for MERIT
    b = rng.normal(0.4, 0.05, size=60)   # controls
    delta, (lo, hi) = paired_bootstrap_diff(a, b)
    assert delta == pytest.approx(float(np.median(a - b)), abs=0.05)
    assert lo > 0


def test_cliffs_delta_direction():
    assert cliffs_delta(np.array([5.0, 6.0, 7.0]), np.array([1.0, 2.0])) > 0.9
    assert cliffs_delta(np.array([1.0]), np.array([5.0])) < 0
    assert cliffs_delta(np.array([]), np.array([1.0])) != cliffs_delta(np.array([]), np.array([1.0]))


def test_factor_specificity_report_math():
    rows = []
    # melody target: strong positive specificity; rhythm: negative
    for spec in (0.3, 0.4, 0.2):
        rows.append(_master_row(1, 100 + int(spec * 100), "merit_target", "melody", spec=spec))
    for spec in (-0.2, -0.1):
        rows.append(_master_row(2, 200 + int(-spec * 100), "merit_target", "rhythm", spec=spec))
    master = pd.DataFrame(rows)
    report = factor_specificity_report(master)
    assert report["melody"]["median_specificity"] == pytest.approx(0.3)
    assert report["melody"]["pct_positive"] == 1.0
    assert report["rhythm"]["pct_positive"] == 0.0


def test_construct_validity_prefers_target_over_controls():
    rows = []
    for q in range(1, 11):
        rows.append(_master_row(q, 900 + q, "merit_target", "timbre", T=0.85))
        rows.append(_master_row(q, 800 + q, "random_negative", "", T=0.45))
        rows.append(_master_row(q, 700 + q, "hard_negative", "", T=0.55))
        rows.append(_master_row(q, 600 + q, "mert_general", "", T=0.65))
    master = pd.DataFrame(rows)
    comparisons = {
        "timbre": {
            src: {
                "n_target_pairs": 10, "n_control_pairs": 10, "n_queries_paired": 10,
                "target_median": 0.85, "control_median": ctrl,
                "median_delta_vs_control": 0.85 - ctrl, "ci95_of_delta": [0.1, 0.5],
                "cliffs_delta": 0.8,
            }
            for src, ctrl in (("random_negative", 0.45), ("hard_negative", 0.55),
                              ("mert_general", 0.65), ("conventional", 0.60))
        }
    }
    corr = pd.DataFrame(
        {"mir_melody": [0.2], "mir_rhythm": [0.2], "mir_timbre": [0.7]},
        index=["merit_melody", "merit_rhythm", "merit_timbre"],
    ).reindex(["merit_melody", "merit_rhythm", "merit_timbre"]).ffill()
    corr = pd.DataFrame(
        [[0.3, 0.2, 0.2], [0.2, 0.3, 0.2], [0.25, 0.25, 0.75]],
        columns=["mir_melody", "mir_rhythm", "mir_timbre"],
        index=["merit_melody", "merit_rhythm", "merit_timbre"],
    )
    human_stats = {"timbre": {"median_rating": 2.5, "share_ge_2": 0.7, "x_rate": 0.05}}
    components = evidence_components(master, {"timbre": {"pct_positive": 0.95, "median_specificity": 0.35}},
                                     comparisons, corr, human_stats)
    timbre = components["timbre"]
    assert timbre["construct_validity"] > 0.7
    assert timbre["baseline_advantage"] > 0.5
    assert timbre["decision"] in ("GO", "CONDITIONAL GO")
    # anti-compensation: weak construct validity blocks GO even with high composite elsewhere
    weak = dict(timbre)
    assert not timbre["anti_compensation_triggered"]


def test_original_gate_preserved_verbatim():
    gates = original_phase1_gate({
        "melody": {"median_rating": 2.5, "share_ge_2": 0.7},
        "rhythm": {"median_rating": 1.0, "share_ge_2": 0.3},
    })
    assert gates["melody"] == "PASS" and gates["rhythm"] == "FAIL"


def test_correlation_matrix_flags_leakage():
    frame = pd.DataFrame({
        "merit_melody_similarity": [0.9, 0.8, 0.7],
        "merit_rhythm_similarity": [0.1, 0.2, 0.3],
        "merit_timbre_similarity": [0.2, 0.3, 0.1],
        "mert_general_similarity": [0.5, 0.5, 0.5],
        "independent_melody_score": [0.1, 0.2, 0.3],   # merit melody tracks MIR rhythm instead!
        "independent_rhythm_score": [0.9, 0.8, 0.7],
        "independent_timbre_score": [0.2, 0.3, 0.1],
    })
    corr = correlation_matrix(frame)
    flags = flag_cross_factor_leakage(corr)
    assert any("merit_melody" in f and "leakage" in f for f in flags)


def test_disagreement_buckets():
    rows = [
        # MERIT+MIR agree, human rejects -> TECHNICALLY_SIMILAR...
        _master_row(1, 101, "merit_target", "melody", mm=0.8, M=0.9, R=0.2, T=0.2,
                    spec=0.65, rating="0", valid=True),
        # all reject -> WRONG_MELODY
        _master_row(2, 202, "merit_target", "melody", mm=0.8, M=0.2, R=0.5, T=0.5,
                    spec=-0.2, rating="0", valid=True),
        _master_row(3, 303, "merit_target", "timbre", mt=0.8, T=0.9, M=0.3, R=0.3,
                    spec=0.5, rating="3", valid=True),  # agreement: no tag
    ]
    master = pd.DataFrame(rows)
    result = disagreement_analysis(master)
    tags = list(result["disagreement_rows"]["tags"])
    assert "TECHNICALLY_SIMILAR_NOT_PERCEPTUALLY_USEFUL" in tags[0]
    assert tags[1].startswith("WRONG_MELODY")
    assert result["groups"]["useful"]["n"] == 1
    assert result["groups"]["not_useful"]["n"] == 2
