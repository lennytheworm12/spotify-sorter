"""Evaluator session-store tests (human-eval infrastructure)."""

from __future__ import annotations

import json
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

    pd.DataFrame(
        [{"trial_id": "1:H1", "query_track_id": 1, "a_title": "t10", "a_artist": "x",
          "b_title": "t11", "b_artist": "y", "question": "overall?", "choice": ""}]
    ).to_csv(sheets / "holistic_trials.csv", index=False)
    (sheets / "holistic_trial_keys.json").write_text(json.dumps({
        "trials": {"1:H1": {"candidate_a": 10, "candidate_b": 11}}
    }))

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


# ---------------------------------------------------------------------------
# reviewer attribution, notes, import
# ---------------------------------------------------------------------------


def test_rating_records_reviewer(eval_env):
    eval_env.rate_factor_cell("1:melody:1", "3", reviewer="alice")
    frame = pd.read_csv(eval_env.sheets_dir / "judgments_factor.csv", dtype=str)
    row = frame[frame["cell_id"] == "1:melody:1"].iloc[0]
    assert row["rating"] == "3"
    assert row["rated_by"] == "alice"


def test_note_persists_and_migrates_legacy_sheets(tmp_path):
    """Sheets created before note/rated_by columns must keep working."""
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    pd.DataFrame(
        [{"cell_id": "9:timbre:2", "query_track_id": 9, "target_factor": "timbre",
          "neighbor_rank": 2, "rating": "", "neighbor_title": "t", "neighbor_artist": "a"}]
    ).to_csv(sheets / "judgments_factor.csv", index=False)
    pd.DataFrame(
        [{"cell_id": "9:timbre:2", "representation": "merit_timbre", "neighbor_track_id": 12}]
    ).to_csv(sheets / "key_factor.csv", index=False)
    pd.DataFrame(
        [{"ab_id": "9:timbre:2", "question": "q", "a_title": "a", "a_artist": "x",
          "b_title": "b", "b_artist": "y", "choice": ""}]
    ).to_csv(sheets / "judgments_ab.csv", index=False)
    pd.DataFrame(
        [{"ab_id": "9:timbre:2", "a_representation": "m", "b_representation": "g",
          "a_track_id": 10, "b_track_id": 11}]
    ).to_csv(sheets / "key_ab.csv", index=False)

    manifest = pd.DataFrame(
        [
            {"track_id": 9, "relative_audio_path": "009/000009.wav", "title": "q",
             "artist": "qa", "top_genre": "g", "decode_status": "SUCCESS"},
            {"track_id": 12, "relative_audio_path": "012/000012.wav", "title": "n",
             "artist": "na", "top_genre": "g", "decode_status": "SUCCESS"},
        ]
    )
    manifest_path = tmp_path / "manifest.parquet"
    manifest.to_parquet(manifest_path, index=False)

    store = SheetStore(sheets, manifest_path, tmp_path)  # audio files absent; ok for notes
    store.set_note("factor", "9:timbre:2", "clip sounds corrupted", reviewer="bob")
    session = store.build_session()
    cell = session["factor_cells"][0]
    assert cell["note"] == "clip sounds corrupted"
    assert cell["rated_by"] == "bob"

    store.set_note("ab", "9:timbre:2", "A and B both plausible")
    assert session is not None


def test_import_ratings_fills_empty_only_by_default(eval_env):
    eval_env.rate_factor_cell("1:melody:1", "3", reviewer="alice")
    report = eval_env.import_ratings(
        factor_rows=[
            {"cell_id": "1:melody:1", "rating": "0"},  # conflicts -> skipped by default
            {"cell_id": "1:rhythm:1", "rating": "2"},
        ],
        ab_rows=[{"ab_id": "1:melody:1", "choice": "B"}],
    )
    frame = pd.read_csv(eval_env.sheets_dir / "judgments_factor.csv", dtype=str)
    assert frame.loc[frame["cell_id"] == "1:melody:1", "rating"].iloc[0] == "3"  # kept
    assert frame.loc[frame["cell_id"] == "1:rhythm:1", "rating"].iloc[0] == "2"
    assert report["factor"] == 1

    eval_env.import_ratings(
        factor_rows=[{"cell_id": "1:melody:1", "rating": "1"}],
        ab_rows=[],
        overwrite_existing=True,
    )
    frame = pd.read_csv(eval_env.sheets_dir / "judgments_factor.csv", dtype=str)
    assert frame.loc[frame["cell_id"] == "1:melody:1", "rating"].iloc[0] == "1"


def test_import_ignores_invalid_values_and_unknown_ids(eval_env):
    report = eval_env.import_ratings(
        factor_rows=[
            {"cell_id": "1:melody:1", "rating": "9"},
            {"cell_id": "nope", "rating": "3"},
        ],
        ab_rows=[{"ab_id": "nope", "choice": "A"}],
    )
    assert report["factor"] == 0


# ---------------------------------------------------------------------------
# multi-reviewer aggregation: never override, always log
# ---------------------------------------------------------------------------


def test_second_reviewer_does_not_override_primary(eval_env):
    eval_env.rate_factor_cell("1:melody:1", "2", reviewer="alice")
    eval_env.rate_factor_cell("1:melody:1", "3", reviewer="bob")

    frame = pd.read_csv(eval_env.sheets_dir / "judgments_factor.csv", dtype=str)
    row = frame[frame["cell_id"] == "1:melody:1"].iloc[0]
    assert row["rating"] == "2"                       # first judgment stands
    assert row["rated_by"] == "alice, bob"
    log = json.loads(row["rating_log"])
    assert [e["v"] for e in log] == ["2", "3"]
    assert [e["by"] for e in log] == ["alice", "bob"]


def test_same_reviewer_self_correction_updates_primary(eval_env):
    eval_env.rate_factor_cell("1:melody:1", "2", reviewer="alice")
    eval_env.rate_factor_cell("1:melody:1", "3", reviewer="alice")  # changed mind

    frame = pd.read_csv(eval_env.sheets_dir / "judgments_factor.csv", dtype=str)
    row = frame[frame["cell_id"] == "1:melody:1"].iloc[0]
    assert row["rating"] == "3"                        # her own entry updated
    log = json.loads(row["rating_log"])
    assert len(log) == 1                               # not a second opinion
    assert row["rated_by"] == "alice"


def test_session_reports_judgment_count(eval_env):
    eval_env.rate_factor_cell("1:melody:1", "2", reviewer="alice")
    eval_env.rate_factor_cell("1:melody:1", "3", reviewer="bob")
    session = eval_env.build_session()
    cell = next(c for c in session["factor_cells"] if c["cell_id"] == "1:melody:1")
    assert cell["n_ratings"] == 2


def test_ab_conflicting_choices_logged_not_overridden(eval_env):
    eval_env.rate_ab_trial("1:melody:1", "A", reviewer="alice")
    eval_env.rate_ab_trial("1:melody:1", "B", reviewer="bob")

    frame = pd.read_csv(eval_env.sheets_dir / "judgments_ab.csv", dtype=str)
    row = frame[frame["ab_id"] == "1:melody:1"].iloc[0]
    assert row["choice"] == "A"                        # primary preserved
    log = json.loads(row["choice_log"])
    assert [(e["v"], e["by"]) for e in log] == [("A", "alice"), ("B", "bob")]


def test_holistic_second_reviewer_is_preserved_and_reported(eval_env):
    eval_env.rate_holistic_trial("1:H1", "B", reviewer="cody")
    eval_env.rate_holistic_trial("1:H1", "A", reviewer="lenny")

    frame = pd.read_csv(eval_env.sheets_dir / "holistic_trials.csv", dtype=str)
    row = frame[frame["trial_id"] == "1:H1"].iloc[0]
    assert row["choice"] == "B"
    assert row["rated_by"] == "cody, lenny"
    assert "rating_log" not in frame.columns
    log = json.loads(row["choice_log"])
    assert [(e["v"], e["by"]) for e in log] == [("B", "cody"), ("A", "lenny")]

    session = eval_env.build_holistic_session()
    trial = session["trials"][0]
    assert trial["choice"] == "B"
    assert trial["rated_by"] == "cody, lenny"
    assert trial["n_ratings"] == 2
    assert session["progress"]["judgments_recorded"] == 2
    assert session["progress"]["judgments_target"] == 1
    assert session["progress"]["trials_started"] == 1


def test_legacy_primary_is_seeded_before_second_reviewer(eval_env):
    factor_path = eval_env.sheets_dir / "judgments_factor.csv"
    frame = pd.read_csv(factor_path, dtype=str).fillna("")
    mask = frame["cell_id"] == "1:melody:1"
    frame.loc[mask, "rating"] = "2"
    frame.loc[mask, "rated_by"] = "cody"
    frame.to_csv(factor_path, index=False)

    eval_env.rate_factor_cell("1:melody:1", "3", reviewer="lenny")

    row = pd.read_csv(factor_path, dtype=str).fillna("").loc[mask].iloc[0]
    assert row["rating"] == "2"
    assert row["rated_by"] == "cody, lenny"
    log = json.loads(row["rating_log"])
    assert [(e["v"], e["by"]) for e in log] == [("2", "cody"), ("3", "lenny")]
    assert log[0]["migrated"] is True


def test_import_conflict_preserves_and_logs(eval_env):
    eval_env.rate_factor_cell("1:melody:1", "3", reviewer="alice")
    report = eval_env.import_ratings(
        factor_rows=[{"cell_id": "1:melody:1", "rating": "0", "rated_by": "phone-sarah"}],
        ab_rows=[],
    )
    assert report["factor_logged"] == 1
    frame = pd.read_csv(eval_env.sheets_dir / "judgments_factor.csv", dtype=str)
    row = frame[frame["cell_id"] == "1:melody:1"].iloc[0]
    assert row["rating"] == "3"
    log = json.loads(row["rating_log"])
    assert any(e["by"] == "phone-sarah" and e["v"] == "0" for e in log)


def test_legacy_sheet_without_log_columns_still_rates(tmp_path):
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    pd.DataFrame(
        [{"cell_id": "5:rhythm:1", "query_track_id": 5, "target_factor": "rhythm",
          "neighbor_rank": 1, "rating": "", "neighbor_title": "t", "neighbor_artist": "a"}]
    ).to_csv(sheets / "judgments_factor.csv", index=False)
    pd.DataFrame(
        [{"cell_id": "5:rhythm:1", "representation": "m", "neighbor_track_id": 10}]
    ).to_csv(sheets / "key_factor.csv", index=False)

    manifest = pd.DataFrame(
        [{"track_id": 5, "relative_audio_path": "005/000005.wav", "title": "q",
          "artist": "qa", "top_genre": "g", "decode_status": "SUCCESS"}]
    )
    manifest_path = tmp_path / "manifest.parquet"
    manifest.to_parquet(manifest_path, index=False)

    store = SheetStore(sheets, manifest_path, tmp_path)
    store.rate_factor_cell("5:rhythm:1", "1", reviewer="carol")
    frame = pd.read_csv(sheets / "judgments_factor.csv", dtype=str)
    row = frame.iloc[0]
    assert row["rating"] == "1"
    assert json.loads(row["rating_log"])[0]["by"] == "carol"
