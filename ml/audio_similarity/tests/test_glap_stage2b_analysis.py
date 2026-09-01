from __future__ import annotations

import pandas as pd
import pytest

from audio_similarity.glap_stage2b_analysis import _correlation, _metric_block, _prediction


def test_prediction_and_query_macro_metric_preserve_stage2b_tie_semantics():
    assert _prediction(0.1) == "A"
    assert _prediction(-0.1) == "B"
    assert _prediction(0.0) == "TIE"
    frame = pd.DataFrame(
        {
            "glap_margin": [1.0, -1.0, 0.0, 1.0],
            "binary_label_a_wins": [1, 1, 1, 1],
            "query_id": [1, 1, 1, 2],
        }
    )
    result = _metric_block(frame)
    assert result["pairwise_accuracy"] == pytest.approx(0.625)
    assert result["query_macro_accuracy"] == pytest.approx((0.5 + 1.0) / 2)
    assert result["tie_count"] == 1


def test_correlation_reports_linear_and_rank_relationships():
    result = _correlation([1, 2, 3], [2, 4, 6])
    assert result == {"count": 3, "pearson": pytest.approx(1.0), "spearman": pytest.approx(1.0)}
