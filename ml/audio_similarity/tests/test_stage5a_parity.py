import sqlite3

import numpy as np
import pandas as pd
import pytest

from audio_similarity.stage4a_dual_scoring import normalized_mean
from audio_similarity.stage5a_parity import Stage5AParityError, verify_fma_small_parity


def cache(path, offset):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE segments (track_id INTEGER, center_sec INTEGER, embedding BLOB, status TEXT)")
    values = {}
    for track_id in (1, 2):
        values[track_id] = {}
        for center in (5, 15, 25):
            vector = np.arange(1, 5, dtype=np.float32) + track_id + center + offset
            vector /= np.linalg.norm(vector)
            values[track_id][center] = vector
            db.execute("INSERT INTO segments VALUES (?,?,?,'ok')", (track_id, center, vector.astype("<f4").tobytes()))
    db.commit()
    db.close()
    return values


def test_independent_clap_and_muq_fma_small_parity(tmp_path):
    clap = cache(tmp_path / "clap.sqlite", 0)
    muq = cache(tmp_path / "muq.sqlite", 10)
    rows = []
    for track_id in (1, 2):
        rows.append(
            {
                "track_id": track_id,
                "representation": "UNIFORM3_DUAL_MEAN",
                "clap_embedding": normalized_mean([clap[track_id][center] for center in (5, 15, 25)]).tolist(),
                "muq_embedding": normalized_mean([muq[track_id][center] for center in (5, 15, 25)]).tolist(),
            }
        )
    frozen = tmp_path / "frozen.parquet"
    pd.DataFrame(rows).to_parquet(frozen, index=False)
    result = verify_fma_small_parity(clap_cache=tmp_path / "clap.sqlite", muq_cache=tmp_path / "muq.sqlite", frozen_aggregates=frozen, atol=1e-7)
    assert result["passed"] and result["tracks"] == 2
    assert result["clap"]["maximum_absolute_error"] == 0
    assert result["muq"]["maximum_absolute_error"] == 0

    changed = pd.read_parquet(frozen)
    changed.at[0, "clap_embedding"] = (np.asarray(changed.at[0, "clap_embedding"]) + 0.01).tolist()
    changed.to_parquet(frozen, index=False)
    with pytest.raises(Stage5AParityError, match="clap"):
        verify_fma_small_parity(clap_cache=tmp_path / "clap.sqlite", muq_cache=tmp_path / "muq.sqlite", frozen_aggregates=frozen, atol=1e-7)
