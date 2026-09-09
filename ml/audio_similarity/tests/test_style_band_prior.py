"""Synthetic contracts; no new human ratings or audio/model inference."""
from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest

from audio_similarity.stage5e3_artifacts import read, freeze_json, hashes, verify_hashes
from audio_similarity.stage5g1_evidence import preferences
from audio_similarity.style_band_math import mapping, aggregate, adjust
from audio_similarity.style_band_metrics import (
    validate_folds, select, crossings, correction_summary, top_changes, cluster_interval, verdict)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return read(ROOT / 'configs/style_band_prior_v1.json')


def test_complete_general_mapping(config):
    classes = read(ROOT / 'reports/style_prior_pilot/v2/model_metadata.json')['classes']
    bands, matrix, records = mapping(classes, config)
    assert matrix.shape == (400, 14) and len(records) == 400
    np.testing.assert_allclose(matrix.sum(axis=1), 1, atol=1e-12)
    assert matrix[classes.index('Hip Hop---Instrumental'), bands.index('beats')] == 1
    assert matrix[classes.index('Hip Hop---Jazzy Hip-Hop'), bands.index('rap')] == .5
    assert matrix[classes.index('Rock---Lo-Fi'), bands.index('beats')] == 0
    assert matrix[classes.index('Funk / Soul---Contemporary R&B'), bands.index('soul_rnb')] == 1
    bad = deepcopy(config)
    bad['style_overrides']['a fabricated style'] = {'rap': 1}
    with pytest.raises(ValueError, match='unknown override'):
        mapping(classes, bad)


def test_hierarchical_distance_soft_neighbors_and_abstention(config):
    config = deepcopy(config)
    config['style_overrides'] = {'Hip Hop---Instrumental': {'beats': 1}}
    classes = ['Hip Hop---Conscious', 'Hip Hop---Instrumental', 'Classical---Baroque', 'Non-Music---Dialogue']
    raw = np.vstack([np.eye(4), np.zeros(4), [1, 0, 0, 0], [1, 0, 0, 1]])
    result = aggregate(raw, classes, config)
    distance = result['distance']
    assert distance[0, 1] == pytest.approx(.5, abs=1e-5)
    assert distance[0, 2] == pytest.approx(1, abs=1e-5)
    np.testing.assert_allclose(distance, distance.T, atol=1e-15)
    np.testing.assert_array_equal(distance.diagonal(), 0)
    np.testing.assert_array_equal(distance[3:5], 0)
    assert distance[0, 5] == 0 and result['known_fraction'][6] == .5
    np.testing.assert_allclose(result['band_profiles'].sum(axis=1), 1)
    np.testing.assert_allclose(result['parent_profiles'].sum(axis=1), 1)
    np.testing.assert_allclose(result['band_mass'].sum(axis=1), raw.sum(axis=1))
    np.testing.assert_allclose(distance[6, 2], .5 * distance[0, 2])
    for invalid in (np.full((1, 4), np.nan), np.full((1, 4), -1), np.ones((1, 3)), np.full((1, 4), 1.1)):
        with pytest.raises(ValueError):
            aggregate(invalid, classes, config)


def fixture_evidence():
    tracks = [{'spotify_track_id': str(i), 'source_sha256': str(i), 'youtube_video_id': str(i), 'artists': [str(i)]} for i in range(9)]
    pairs = [{'tracks': [str(i), str(i+1)], 'rating': 5} for i in (0, 3, 6)]
    pairs += [{'tracks': [str(i), str(i+2)], 'rating': 1} for i in (0, 3, 6)]
    folds = []
    for k in range(3):
        test = [str(i) for i in range(3*k, 3*k+3)]
        train = sorted({t['spotify_track_id'] for t in tracks} - set(test))
        folds.append({'fold': k, 'train': train, 'heldout': test,
                      'train_preferences': preferences(pairs, train)[0], 'heldout_preferences': preferences(pairs, test)[0]})
    return tracks, pairs, folds


def test_fold_integrity_artist_source_and_human_label_leakage():
    tracks, pairs, folds = fixture_evidence()
    validate_folds(tracks, pairs, folds)
    bad = deepcopy(tracks)
    bad[0]['artists'] = ['3']
    with pytest.raises(ValueError, match='artist/source leakage'):
        validate_folds(bad, pairs, folds)
    with pytest.raises(ValueError, match='duplicate or conflicting'):
        validate_folds(tracks, pairs + [pairs[0]], folds)
    bad = deepcopy(folds)
    bad[0]['train_preferences'].append(bad[0]['heldout_preferences'][0])
    with pytest.raises(ValueError, match='label leakage'):
        validate_folds(tracks, pairs, bad)


def test_selection_train_only_tie_zero_and_conservative_bound():
    score = {('a', 'b'): .50, ('a', 'c'): .52, ('d', 'e'): .4, ('d', 'f'): .5}
    distance = {('a', 'b'): 0, ('a', 'c'): 1, ('d', 'e'): 1, ('d', 'f'): 0}
    train = [{'anchor': 'a', 'preferred': 'b', 'other': 'c', 'gap': 4}]
    strength, _ = select(score, distance, train, [0, .025, .05, .1])
    assert strength == .025
    score[('d', 'e')], score[('d', 'f')] = -1, 1
    assert select(score, distance, train, [0, .025, .05, .1])[0] == strength
    assert select(score, {k: 0 for k in score}, train, [0, .025, .05, .1])[0] == 0
    with pytest.raises(ValueError):
        adjust(score, distance, .4)
    assert all(0 <= score[k] - v <= .1 + 1e-12 for k, v in adjust(score, distance, .1).items())


def test_corrections_damage_ties_and_unknown_candidates():
    score = {('a', 'b'): .5, ('a', 'c'): .52, ('a', 'd'): .51}
    ratings = {('a', 'b'): 5, ('a', 'c'): 1}
    constraints = [{'anchor': 'a', 'preferred': 'b', 'other': 'c', 'gap': 4}]
    adjusted = adjust(score, {('a', 'b'): 0, ('a', 'c'): 1, ('a', 'd'): 0}, .05)
    rows = crossings(score, adjusted, constraints, ratings)
    assert correction_summary(rows)['corrected_unique_pairs'] == 1
    assert correction_summary(crossings(adjusted, score, constraints, ratings))['broken_unique_pairs'] == 1
    changed = top_changes(score, adjusted, ['a'], ['a', 'b', 'c', 'd'], ratings, 1)
    assert changed['counts']['removed_bad']['directed'] == 1
    assert changed['counts']['added_unknown']['directed'] == 1
    assert changed['counts']['added_good']['directed'] == 0
    tie = score | {('a', 'b'): .52}
    assert correction_summary(crossings(score, tie, constraints, ratings))['corrected_orderings'] == 0


def test_group_bootstrap_and_verdict_require_breadth(config):
    tracks, _, _ = fixture_evidence()
    per = {str(i): .1 for i in range(9)}
    result = cluster_interval(per, tracks)
    assert result == cluster_interval(per, list(reversed(tracks)))
    assert result['low'] == pytest.approx(.1)
    regions = {str(i): {'anchors': 3, 'delta': {'point': .1}, 'per_anchor': {str(3*i+j): .1 for j in range(3)}} for i in range(3)}
    delta = {'point': .1, 'low': .05, 'high': .15}
    corrections = {'corrected_orderings': 3, 'broken_orderings': 1}
    assert verdict(delta, result, corrections, regions, delta, config)['outcome'].startswith('COMPLEMENTARY')
    assert verdict(delta, result, corrections, {'0': regions['0']}, delta, config)['outcome'] == 'STYLE_BAND_SHORTCUT_NOT_ESTABLISHED'


def test_synthetic_end_to_end_determinism_and_frozen_input_guard(tmp_path, monkeypatch, config):
    from audio_similarity import style_band_experiment as study
    tracks, pairs, folds = fixture_evidence()
    config = deepcopy(config)
    config.update(minimum_fold_preferences=1, minimum_fold_anchors=1)
    config['style_overrides'] = {}
    classes = ['Hip Hop---Conscious', 'Classical---Baroque']
    raw = np.array([[1, 0], [1, 0], [0, 1]] * 3)
    features = aggregate(raw, classes, config)
    ids = [t['spotify_track_id'] for t in tracks]
    scores = {(a, b): .5 for a in ids for b in ids if a < b}
    for i in (0, 3, 6):
        scores[(str(i), str(i+2))] = .52
    distance = {(a, b): float(features['distance'][int(a), int(b)]) for a, b in scores}
    monkeypatch.setattr(study, '_load', lambda root: (config, tracks, pairs, folds, features, np.eye(9), scores, distance, distance))
    run = tmp_path / study.RUN
    freeze_json(run / 'inventory.json', {'diagnostic_artist_exclusions': []})
    first = study.evaluate(tmp_path)
    assert first['corrections']['corrected_orderings'] == 3
    assert first['performance']['band']['point'] == 1
    before = hashes(list(run.iterdir()), run)
    assert study.evaluate(tmp_path) == first
    verify_hashes(run, before)
    with pytest.raises(ValueError, match='frozen artifact differs'):
        freeze_json(run / 'results.json', {})
    (run / 'results.json').write_text('{}')
    with pytest.raises(ValueError, match='integrity mismatch'):
        verify_hashes(run, before)
