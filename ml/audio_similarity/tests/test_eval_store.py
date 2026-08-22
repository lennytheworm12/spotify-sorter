"""Evaluator session-store tests (human-eval infrastructure)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from audio_similarity.eval_store import SheetStore
from tests.helpers import save_wav, synth_waveform


@pytest.fixture
def eval_env(tmp_path: Path) -> SheetStore:
    sheets = tmp_path / "sheets"
    sheets.mkdir()

    # two queries (1, 2) and three neighbor tracks (10, 11, 12)
    audio_root = tmp_path / "audio"
    manifest_rows = []
    for tid in [1, 2, 10, 11, 12]:
        sub = audio_root / f"{tid:03d}"
        sub.mkdir(parents=True)
        save_wav(sub / f"{tid:06d}.wav", synth_waveform(0.3, seed=tid), 24000)
        manifest_rows.append(
            {
                "track_id": tid,
                "relative_audio_path": f"{tid:03d}/{tid:06d}.wav",
                "title": f"title{tid}",
                "artist": f"artist{tid}",
                "top_genre": f"g{tid % 2}",
                "decode_status": "SUCCESS",
            }
        )
    manifest_path = tmp_path / "manifest.parquet"
    pd.DataFrame(manifest_rows).to_parquet(manifest_path, index=False)

    factor = pd.DataFrame(
        [
            {"cell_id": "1:melody:1", "query_track_id": 1, "target_factor": "melody",
             "neighbor_rank": 1, "rating": "", "neighbor_title": "t10", "neighbor_artist": "a"},
            {"cell_id": "1:rhythm:1", "query_track_id": 1, "target_factor": "rhythm",
             "neighbor_rank": 1, "rating": "", "neighbor_title": "t11", "neighbor_artist": "a"},
            {"cell_id": "2:timbre:1", "query_track_id": 2, "target_factor": "timbre",
             "neighbor_rank": 1, "rating": "", "neighbor_title": "t12", "neighbor_artist": "a"},
        ]
    )
    factor.to_csv(sheets / "judgments_factor.csv", index=False)
    pd.DataFrame(
        [
            {"cell_id": "1:melody:1", "representation": "merit_melody", "neighbor_track_id": 10},
            {"cell_id": "1:rhythm:1", "representation": "merit_rhythm", "neighbor_track_id": 11},
            {"cell_id": "2:timbre:1", "representation": "merit_timbre", "neighbor_track_id": 12},
        ]
    ).to_csv(sheets / "key_factor.csv", index=False)

    ab = pd.DataFrame(
        [{"ab_id": "1:melody:1", "question": "q", "a_title": "tA", "a_artist": "x",
          "b_title": "tB", "b_artist": "y", "choice": ""}]
    )
    ab.to_csv(sheets / "judgments_ab.csv", index=False)
    pd.DataFrame(
        [{"ab_id": "1:melody:1", "a_representation": "merit_melody",
          "b_representation": "mert_general", "a_track_id": 10, "b_track_id": 11}]
    ).to_csv(sheets / "key_ab.csv", index=False)

    return SheetStore(sheets, manifest_path, audio_root)


def test_session_hides_representation_names_and_raw_neighbor_ids(eval_env):
    session = eval_env.build_session()
    blob = repr(session)
    assert "merit_" not in blob and "mert_general" not in blob
    for cell in session["factor_cells"]:
        assert not hasattr(cell, "neighbor_track_id")
        assert "neighbor_track_id" not in cell
        # rater-visible context + playable URLs are present
        assert cell["query_audio"].startswith("/audio/track/")
        assert cell["neighbor_audio"].startswith("/audio/track/")
    for trial in session["ab_trials"]:
        assert "a_representation" not in trial and "b_representation" not in trial


def test_progress_counts(eval_env):
    progress = eval_env.build_session()["progress"]
    assert progress["factor_total"] == 3 and progress["factor_rated"] == 0
    assert progress["ab_total"] == 1 and progress["ab_rated"] == 0


def test_rate_factor_cell_persists_atomically(eval_env):
    eval_env.rate_factor_cell("1:melody:1", "2")
    frame = pd.read_csv(eval_env.sheets_dir / "judgments_factor.csv", dtype=str)
    rating = frame.loc[frame["cell_id"] == "1:melody:1", "rating"].iloc[0]
    assert rating == "2"
    assert not (eval_env.sheets_dir / "judgments_factor.csv.tmp").exists()
    assert eval_env.build_session()["progress"]["factor_rated"] == 1


def test_invalid_rating_rejected_without_write(eval_env):
    with pytest.raises(ValueError):
        eval_env.rate_factor_cell("1:melody:1", "5")
    with pytest.raises(ValueError):
        eval_env.rate_factor_cell("1:melody:1", "great")
    frame = pd.read_csv(eval_env.sheets_dir / "judgments_factor.csv", dtype=str)
    assert frame.loc[frame["cell_id"] == "1:melody:1", "rating"].isna().all()


def test_unknown_cell_rejected(eval_env):
    with pytest.raises(KeyError):
        eval_env.rate_factor_cell("999:melody:9", "2")


def test_x_rating_accepted(eval_env):
    eval_env.rate_factor_cell("1:melody:1", "x")  # case-insensitive
    frame = pd.read_csv(eval_env.sheets_dir / "judgments_factor.csv", dtype=str)
    assert frame.loc[frame["cell_id"] == "1:melody:1", "rating"].iloc[0] == "X"


def test_rate_ab_trial_roundtrip(eval_env):
    eval_env.rate_ab_trial("1:melody:1", "tie")
    frame = pd.read_csv(eval_env.sheets_dir / "judgments_ab.csv", dtype=str)
    assert frame.loc[frame["ab_id"] == "1:melody:1", "choice"].iloc[0] == "Tie"
    with pytest.raises(ValueError):
        eval_env.rate_ab_trial("1:melody:1", "maybe")


def test_audio_resolution_for_blinded_ab_sides(eval_env):
    a = eval_env.audio_path_for_request("ab", "1:melody:1", "a")
    b = eval_env.audio_path_for_request("ab", "1:melody:1", "b")
    assert a is not None and b is not None and a != b
    assert a.exists() and b.exists()


def test_missing_audio_returns_none(eval_env):
    assert eval_env.audio_path_for_request("track", "999") is None
