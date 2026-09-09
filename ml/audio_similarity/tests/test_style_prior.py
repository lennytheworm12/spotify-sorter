import numpy as np
import pytest
from audio_similarity.style_prior import distributions, distances, make_folds
from audio_similarity.style_prior_extract import cached, validate
from audio_similarity.style_prior_analysis import discrimination, penalty_cv, signal_passes


def test_distribution_and_distance():
    p = distributions([[1, 0], [0, 1], [1, 0]])
    d = distances(p)
    np.testing.assert_allclose(d, d.T, atol=1e-15)
    np.testing.assert_array_equal(d.diagonal(), 0)
    assert d[0, 1] > .999 and d[0, 2] == 0
    assert np.isfinite(distributions([[0, 0]])).all()
    with pytest.raises(ValueError):
        distributions([[float('nan')]])


def test_cache_replay_identity_and_corruption(tmp_path):
    calls = []
    def infer():
        calls.append(1)
        return np.ones((2, 400), np.float32) * .5
    a, hit, key = cached(tmp_path, {'source': 'a', 'config': 1}, infer)
    assert not hit
    b, hit, _ = cached(tmp_path, {'source': 'a', 'config': 1}, infer)
    assert hit and len(calls) == 1
    np.testing.assert_array_equal(a, b)
    cached(tmp_path, {'source': 'a', 'config': 2}, infer)
    assert len(calls) == 2
    (tmp_path / (key + '.npz')).write_bytes(b'bad')
    with pytest.raises(ValueError, match='integrity'):
        cached(tmp_path, {'source': 'a', 'config': 1}, infer)


@pytest.mark.parametrize('x', [np.zeros((0, 400)), np.zeros((4, 399)), np.full((2, 400), np.nan), np.full((2, 400), 1.1)])
def test_invalid_predictions(x):
    with pytest.raises(ValueError):
        validate(x)


def test_folds_disjoint_deterministic_artist_alias():
    tracks = [{'spotify_track_id': str(i), 'source_sha256': str(i), 'youtube_video_id': str(i), 'artists': [str(i // 2)]} for i in range(12)]
    pairs = [{'tracks': ['0', '2'], 'rating': 5}, {'tracks': ['0', '4'], 'rating': 1}]
    folds = make_folds(tracks, pairs)
    assert folds == make_folds(list(reversed(tracks)), pairs)
    for fold in folds:
        assert not set(fold['train']) & set(fold['heldout'])
        assert not {int(t) // 2 for t in fold['train']} & {int(t) // 2 for t in fold['heldout']}
        for name in ('train', 'heldout'):
            assert all({p['anchor'], p['preferred'], p['other']} <= set(fold[name]) for p in fold[name + '_preferences'])


def test_auc_direction_unknown_not_negative():
    pairs = [{'tracks': ['a', 'b'], 'rating': 5}, {'tracks': ['a', 'c'], 'rating': 1}, {'tracks': ['a', 'd'], 'rating': 3}]
    values = {('a', 'b'): .1, ('a', 'c'): .8, ('a', 'd'): 0}
    result = discrimination(pairs, values, values)
    assert result['macro_auc']['point'] == 1 and result['comparisons'] == 1
    assert discrimination(pairs, values, values, .05)['anchors'] == 0


def test_penalty_uses_train_only_and_tie_prefers_zero():
    config = {'minimum_fold_preferences': 1, 'minimum_fold_anchors': 1, 'conditional_penalty': {'lambdas': [0, .4]}}
    fold = {'fold': 0, 'train': ['a', 'b', 'c'], 'heldout': ['d', 'e', 'f'],
            'train_preferences': [{'anchor': 'a', 'preferred': 'b', 'other': 'c', 'gap': 4}],
            'heldout_preferences': [{'anchor': 'd', 'preferred': 'e', 'other': 'f', 'gap': 4}]}
    score = {('a', 'b'): .7, ('a', 'c'): .5, ('d', 'e'): .1, ('d', 'f'): .2}
    distance = {k: 0 for k in score}
    assert penalty_cv(score, distance, [fold], config)['folds'][0]['lambda'] == 0
    fold['heldout_preferences'][0]['anchor'] = 'a'
    with pytest.raises(ValueError, match='leakage'):
        penalty_cv(score, distance, [fold], config)
