from dataclasses import asdict, replace
import json
import math

import numpy as np
import pytest

from audio_similarity.calibration.contracts import Catalog, Clap, ContractError, Corpus, Layer, Query, Role, digest
from audio_similarity.calibration.features import PairFeatures, matrix_hash
from audio_similarity.calibration.ranking import Model, ablations, grid, pair_score, playlist_score, rank_query, reconstruction_metrics
from audio_similarity.calibration.synthetic import fixture


def modified(features, changes=None, corpus=None, genre=None):
    corpus = corpus or features.corpus
    matrices = dict(features.matrices) | (changes or {})
    matrices['R'] = (1 - matrices['Jc']) * matrices['Jnr']
    identities = {k: replace(v, matrix_sha256=matrix_hash(matrices[k]),
                  source_order_sha256=digest(tuple(r.source_sha256 for r in corpus.recordings))) for k, v in features.identities.items()}
    return PairFeatures(corpus, features.track_ids, matrices, identities,
                        np.asarray(features.genre_available if genre is None else genre))


def test_grid_and_refitted_registry():
    assert len(grid(deduplicate_clap=False)) == 792
    assert len(grid()) == len({m.identity for m in grid()}) == 756
    assert sum(m.rho == 1 for m in grid()) == 36
    assert sum(m.w_c == 0 for m in grid()) == 21
    for m in grid():
        assert 0 <= m.w_n <= m.w_c <= .1
    arms = ablations()
    assert len(arms['m3_canonical']) == 8 and len(arms['m3_residual']) == 36
    assert len(arms['centered30_v1/audio_mixture']) == 11
    assert len(arms['method_c_full_song/joint_residual']) == 396
    with pytest.raises(ContractError): Model('method_c_full_song', .5, 0, 0)
    with pytest.raises(ContractError): Model(Clap.CENTERED, .5, 0, .25)
    with pytest.raises(ContractError): Model(Clap.CENTERED, float('nan'), 0, 0)


def test_feature_replay_and_fail_closed(tmp_path):
    f = fixture(groups=3)
    f.save(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    loaded = PairFeatures.load(tmp_path)
    assert loaded.identity == f.identity
    loaded.save(tmp_path)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError): loaded.matrices['M'][0, 1] = .9
    with pytest.raises(ContractError):
        PairFeatures(f.corpus, f.track_ids[::-1], f.matrices, f.identities, np.asarray(f.genre_available))
    identities = dict(f.identities)
    identities['M'] = replace(identities['M'], source_order_sha256=digest('wrong source'))
    with pytest.raises(ContractError): PairFeatures(f.corpus, f.track_ids, f.matrices, identities, np.asarray(f.genre_available))
    with pytest.raises(ContractError): replace(f.identities['C_center30'], representation_id=Clap.METHOD_C.value)
    (tmp_path / 'M.npy').write_bytes(b'corrupt')
    with pytest.raises(ContractError): PairFeatures.load(tmp_path)
    raw = asdict(f.corpus)
    raw['recordings'][0]['artist_group_ids'] = list(raw['recordings'][0]['artist_group_ids'])
    raw['unexpected'] = True
    with pytest.raises(ContractError): Corpus.from_dict(raw)


def test_missing_genre_noop_and_representation_independence():
    f = fixture(groups=3)
    a, b = f.track_ids[:2]
    c30 = pair_score(f, Model(Clap.CENTERED, 0, 0, 0), a, b)['F']
    cm = pair_score(f, Model(Clap.METHOD_C, 0, 0, 0), a, b)['F']
    assert c30 != cm
    mask = np.ones(len(f.track_ids), dtype=bool)
    mask[0] = False
    changes = {}
    for key in ('Jc', 'Jnr'):
        changes[key] = f.matrices[key].copy()
        changes[key][0, :] = changes[key][:, 0] = 0
    no_genre = modified(f, changes, genre=mask)
    assert pair_score(no_genre, Model(Clap.CENTERED, .5, .1, 1), a, b)['F'] == pair_score(no_genre, Model(Clap.CENTERED, .5, 0, 0), a, b)['F']
    with pytest.raises(ContractError): PairFeatures(f.corpus, f.track_ids, f.matrices, f.identities, mask)


def test_top_three_after_complete_score_and_symmetry():
    f = fixture(groups=1, members=5)
    c = np.eye(5); m = np.eye(5)
    c[0, 1:] = c[1:, 0] = [.75, .5, .25, 0]
    m[0, 1:] = m[1:, 0] = [0, .25, .5, 1]
    f = modified(f, {'C_center30': c, 'M': m})
    model = Model(Clap.CENTERED, .5, 0, 0)
    score = playlist_score(f, model, f.track_ids[0], f.track_ids)
    assert score['Q'] == (0.5 + .375 + .375) / 3
    assert score['top_support'][0]['recording_id'] == f.track_ids[4]
    assert score['seed_count'] == 4
    assert score['Q'] != (.75 + .5 + .25 + 1 + .5 + .25) / 6
    for a in f.track_ids:
        for b in f.track_ids:
            assert pair_score(f, model, a, b)['F'] == pair_score(f, model, b, a)['F']
    assert playlist_score(f, model, f.track_ids[0], (f.track_ids[0],))['Q'] is None


def test_duplicate_support_and_catalog_identity():
    f = fixture(groups=2)
    records = list(f.corpus.recordings)
    records[1] = replace(records[1], version_group_id=records[0].version_group_id)
    f = modified(f, corpus=replace(f.corpus, recordings=tuple(records)))
    model = Model(Clap.METHOD_C, 0, 0, 0)
    score = playlist_score(f, model, f.track_ids[0], f.track_ids[:3])
    assert score['seed_count'] == 1
    catalog = Catalog('cat', 'split', Role.INNER, tuple(sorted(f.track_ids)), 'fixed')
    query = Query('q', 'p0', 'snapshot0', 'group0', 'cluster', 'stratum0', Layer.ORIGINAL, Role.INNER, 'split',
                  (f.track_ids[0],), (f.track_ids[2],), catalog.identity, 'test')
    ranks = rank_query(f, model, query, catalog)
    assert f.track_ids[1] not in [r['candidate_recording_id'] for r in ranks]
    assert {r['observed_membership'] for r in ranks} == {'observed_positive', 'unlabeled'}
    with pytest.raises(ContractError): rank_query(f, model, query, replace(catalog, candidate_policy_id='changed'))
    with pytest.raises(ContractError): rank_query(f, model, replace(query, hidden_ids=(f.track_ids[1],)), catalog)
    with pytest.raises(ContractError): rank_query(f, model, replace(query, hidden_ids=(f.track_ids[-1],)), catalog)


def test_hand_calculated_metrics():
    ranks = list(range(12))
    result = reconstruction_metrics(ranks, [0, 2, 10])
    expected = (1 + 1 / math.log2(4) + 1 / math.log2(12)) / (1 + 1 / math.log2(3) + 1 / math.log2(4))
    assert result['ndcg20'] == pytest.approx(expected)
    assert result['recall10'] == 2 / 3 and result['recall20'] == 1
    assert reconstruction_metrics(ranks, [])['status'] == 'INSUFFICIENT_DATA'
    with pytest.raises(ContractError): reconstruction_metrics(ranks, [99])


def test_exact_m3_control_uses_saved_matrix():
    f = fixture(groups=2)
    custom = np.zeros_like(f.matrices['M3'])
    f = modified(f, {'M3': custom})
    model = ablations()['frozen_m3'][0]
    assert pair_score(f, model, *f.track_ids[:2])['F'] == 0
    assert pair_score(f, Model(Clap.METHOD_C, model.rho, 0, 0), *f.track_ids[:2])['F'] != 0
    with pytest.raises(ContractError): replace(model, clap=Clap.CENTERED)
