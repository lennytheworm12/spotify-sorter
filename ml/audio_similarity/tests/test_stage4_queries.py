from __future__ import annotations

import pandas as pd

from audio_similarity.stage4_queries import largest_remainder, select_queries


def manifest():
    rows=[]
    for corpus in ("musdb18","medleydb"):
        for i in range(70):
            rows.append({"corpus":corpus,"track_id":f"{corpus}:{i:03}","artist":f"artist{i//2}","genre":f"genre{i%7}","duration_sec":60+i,"decode_status":"ok"})
    return pd.DataFrame(rows)


def test_largest_remainder_exact_target():
    allocation=largest_remainder({"a":3,"b":7,"c":10},7)
    assert sum(allocation.values())==7 and all(allocation[k] <= n for k,n in {"a":3,"b":7,"c":10}.items())


def test_query_freeze_is_reproducible_source_balanced_and_pre_score():
    first=select_queries(manifest(),123)
    second=select_queries(manifest(),123)
    assert first==second
    assert "score" not in str(first).casefold()
    for corpus in ("musdb18","medleydb"):
        block=first["corpora"][corpus]
        assert len(block["queries"])==40 and len(block["technical_reserves"])==10
        assert sum(row["tranche"]=="INTERIM" for row in block["queries"])==20
        assert sum(row["tranche"]=="CONTINUATION" for row in block["queries"])==20
        assert not ({r["track_id"] for r in block["queries"]} & {r["track_id"] for r in block["technical_reserves"]})
