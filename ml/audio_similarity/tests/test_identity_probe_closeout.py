import pytest
from audio_similarity.identity_probe_closeout import incremental_control


def test_incremental_control_with_unknown_and_caliper():
    rows = [{'tracks': ['a', 'b'], 'rating': 1, 'distance': .8, 'pair_id': 'ab'},
            {'tracks': ['a', 'c'], 'rating': 5, 'distance': .2, 'pair_id': 'ac'},
            {'tracks': ['a', 'd'], 'rating': 3, 'distance': 1., 'pair_id': 'ad'}]
    result = incremental_control(rows, {'ab': .8, 'ac': .79, 'ad': .5}, .05)
    assert result['macro_auc_delta_vs_D'] == 1
    assert result['caliper_macro_auc'] == 1
    assert result['caliper_anchors'] == 1 and result['caliper_comparisons'] == 1
    restricted = incremental_control(rows, {'ab': .8, 'ac': .5, 'ad': .5}, .05)
    assert restricted['caliper_macro_auc'] is None
    assert incremental_control([], {}, .05)['macro_auc_delta_vs_D'] is None
