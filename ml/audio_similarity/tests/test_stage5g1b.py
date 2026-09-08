"""Zero-shot study contracts, independent of real human outcomes."""
import numpy as np
import pytest
from audio_similarity.stage5g1b_probes import cached_text, normalize_rows, profiles, compare, js_distance, prompt_list
from audio_similarity.stage5g1b_analysis import summarize, axis_gate


def test_cache_replay_and_identity(tmp_path):
    calls = []
    def forward(prompts):
        calls.append(prompts)
        return np.ones((len(prompts), 512))
    a, n, key = cached_text(tmp_path, {'checkpoint': 'one'}, ['first'], forward)
    b, replay, again = cached_text(tmp_path, {'checkpoint': 'one'}, ['first'])
    assert n == 1 and replay == 0 and len(calls) == 1 and key == again
    np.testing.assert_array_equal(a, b)
    with pytest.raises(ValueError):
        cached_text(tmp_path, {'checkpoint': 'two'}, ['first'])
    with pytest.raises(ValueError):
        cached_text(tmp_path, {'checkpoint': 'one'}, ['changed'])
    (tmp_path / key / 'vectors.npz').write_bytes(b'corrupt')
    with pytest.raises(ValueError):
        cached_text(tmp_path, {'checkpoint': 'one'}, ['first'])


def test_invalid_embeddings():
    for value in [np.zeros((1, 512)), np.ones((1, 16)), np.full((1, 512), np.nan)]:
        with pytest.raises(ValueError):
            normalize_rows(value)


def test_profiles_symmetry_abstention_and_prompts():
    config = {'axes': {'a': [['x', 'xx'], ['y', 'yy']]}, 'prompt_templates': ['{}.', '{}!'],
              'temperature': .07, 'minimum_cosine_margin': .02}
    assert prompt_list(config) == ['x.', 'y.', 'xx!', 'yy!']
    text = np.eye(512)[:2];text = np.concatenate([text, text])
    a = profiles(np.eye(512)[:1], text, config)['a']
    b = profiles(np.eye(512)[1:2], text, config)['a']
    assert a['reliable'] and b['reliable']
    assert compare(a, b) == compare(b, a)
    assert compare(a, b)['flag'] is True
    assert compare(a, a)['distance'] == 0 and compare(a, a)['flag'] is False
    ambiguous = profiles(np.ones((1, 512)), text, config)['a']
    assert not ambiguous['reliable'] and compare(a, ambiguous)['flag'] is None
    assert 0 <= js_distance([.9, .1], [.1, .9]) <= 1


def test_anchor_macro_unknown_and_ambiguous():
    rows = [{'tracks': ['a', 'b'], 'rating': 1, 'distance': .9, 'flag': True},
            {'tracks': ['a', 'c'], 'rating': 5, 'distance': .1, 'flag': None},
            {'tracks': ['a', 'd'], 'rating': 3, 'distance': 100, 'flag': True}]
    result = summarize(rows)
    assert result == summarize(rows)
    assert result['anchors'] == 1 and result['macro_auc'] == 1
    assert result['bad']['pairs'] == 1 and result['good']['pairs'] == 1
    assert result['good']['abstention_rate'] == 1
    assert summarize([])['macro_auc'] is None


def test_gate_requires_every_control():
    cfg = {'gate': {'minimum_anchors': 20, 'minimum_macro_auc': .65, 'minimum_bad_flag_rate': .5,
                   'maximum_good_flag_rate': .2, 'minimum_neighbor_anchors': 10, 'minimum_leave_artist_out_auc': .55}}
    result = {'anchors': 25, 'macro_auc': .7, 'interval': [.6, .8], 'bad': {'flag_rate': .6}, 'good': {'flag_rate': .1}}
    assert axis_gate(result, [result, result], result, result, result, {'artist': .6}, cfg)
    assert not axis_gate(result, [result, result], result, result, result, {}, cfg)
    assert not axis_gate(result, [result, result], result, result, dict(result, anchors=2), {'artist': .6}, cfg)
