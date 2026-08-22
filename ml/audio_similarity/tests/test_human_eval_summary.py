"""Human-eval summary tests (gates from Phase 1 doc section 16)."""

from __future__ import annotations

import pandas as pd
import pytest

from audio_similarity.cli.summarize_human_eval import summarize


def write_sheets(tmp_path, factor_rows, ab_rows, ab_key_rows):
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    pd.DataFrame(factor_rows).to_csv(sheets / "judgments_factor.csv", index=False)
    if ab_rows is not None:
        pd.DataFrame(ab_rows).to_csv(sheets / "judgments_ab.csv", index=False)
        pd.DataFrame(ab_key_rows).to_csv(sheets / "key_ab.csv", index=False)
    return sheets


def make_factor_rows(ratings):
    return [
        {
            "cell_id": f"1:{f}:{i}",
            "query_track_id": 1,
            "target_factor": f,
            "neighbor_rank": i,
            "rating": r,
            "neighbor_title": "t",
            "neighbor_artist": "a",
        }
        for f in ("melody", "rhythm", "timbre")
        for i, r in enumerate(ratings)
    ]


def test_utility_gates_pass_and_fail(tmp_path):
    rows = []
    # melody: median 2.5, all >=2 -> PASS
    for i, r in enumerate([2, 3, 2, 3]):
        rows.append({"cell_id": f"1:melody:{i}", "query_track_id": 1, "target_factor": "melody", "neighbor_rank": i + 1, "rating": r})
    # rhythm: median 1, mostly <2 -> FAIL
    for i, r in enumerate([0, 1, 1, 2]):
        rows.append({"cell_id": f"2:rhythm:{i}", "query_track_id": 2, "target_factor": "rhythm", "neighbor_rank": i + 1, "rating": r})

    report = summarize(write_sheets(tmp_path, rows, None, None))
    assert report["factor_gate_pass"]["melody"] is True
    assert report["factor_gate_pass"]["rhythm"] is False
    assert report["factor_utility"]["melody"]["median_rating"] == pytest.approx(2.5)
    assert report["factor_utility"]["melody"]["share_rating_ge_2"] == pytest.approx(1.0)


def test_x_ratings_excluded_from_stats_but_counted(tmp_path):
    rows = [
        {"cell_id": f"3:timbre:{i}", "query_track_id": 3, "target_factor": "timbre", "neighbor_rank": i + 1, "rating": r}
        for i, r in enumerate(["X", "2", "3"])
    ]
    report = summarize(write_sheets(tmp_path, rows, None, None))
    timbre = report["factor_utility"]["timbre"]
    assert timbre["n_rated"] == 2
    assert timbre["n_excluded_x"] == 1


def test_invalid_rating_raises(tmp_path):
    rows = make_factor_rows(["9"])
    with pytest.raises(ValueError, match="invalid ratings"):
        summarize(write_sheets(tmp_path, rows, None, None))


def test_ab_preference_rate(tmp_path):
    ab_rows = [
        {"ab_id": "1:melody:1", "question": "q", "choice": "A"},
        {"ab_id": "1:melody:2", "question": "q", "choice": "B"},
        {"ab_id": "1:melody:3", "question": "q", "choice": "A"},
        {"ab_id": "1:melody:4", "question": "q", "choice": "Tie"},  # excluded
        {"ab_id": "5:rhythm:1", "question": "q", "choice": "B"},
        {"ab_id": "5:rhythm:2", "question": "q", "choice": "B"},
    ]
    key_rows = [
        {"ab_id": "1:melody:1", "a_representation": "merit_melody", "b_representation": "mert_general"},
        {"ab_id": "1:melody:2", "a_representation": "merit_melody", "b_representation": "mert_general"},
        {"ab_id": "1:melody:3", "a_representation": "mert_general", "b_representation": "merit_melody"},
        {"ab_id": "1:melody:4", "a_representation": "merit_melody", "b_representation": "mert_general"},
        {"ab_id": "5:rhythm:1", "a_representation": "merit_rhythm", "b_representation": "mert_general"},
        {"ab_id": "5:rhythm:2", "a_representation": "merit_rhythm", "b_representation": "mert_general"},
    ]
    report = summarize(write_sheets(tmp_path, [], ab_rows, key_rows))
    melody = report["ab_factor_control"]["melody"]
    assert melody["merit_wins"] == 2
    assert melody["mert_wins"] == 1
    assert melody["preference_rate"] == pytest.approx(2 / 3)
    assert melody["gate_wins_more_than_losses"] is True

    rhythm = report["ab_factor_control"]["rhythm"]
    assert rhythm["preference_rate"] == 0.0
    assert rhythm["gate_wins_more_than_losses"] is False
