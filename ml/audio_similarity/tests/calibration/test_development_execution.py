"""No inference/API access: reference parity and execution-boundary contracts."""
import numpy as np
import pytest

from audio_similarity.calibration.contracts import Clap, ContractError, Role
from audio_similarity.calibration.development_bundle import genre_pair, project
from audio_similarity.calibration.development_evaluation import bootstrap_weights, evaluate_many
from audio_similarity.calibration.development_profiles import DevelopmentLedger
from audio_similarity.calibration.ranking import Model
from audio_similarity.calibration.search import cluster_uncertainty, evaluate, select_inner
from audio_similarity.calibration.splits import grouped_folds
from audio_similarity.calibration.synthetic import fixture


@pytest.mark.parametrize('model', [Model(Clap.CENTERED, .2, .1, .75), Model(Clap.METHOD_C, .6, .035, .5)])
def test_vectorized_parity_and_replay(tmp_path, model):
    f = fixture(groups=6, members=8)
    folds = grouped_folds(f.corpus, [p.playlist_id for p in f.corpus.playlists], 2, Role.INNER, 'parity')
    reference = evaluate(f, model, folds, repetitions=2, bootstrap_draws=40)
    actual = evaluate_many(f, [model], folds, repetitions=2, draws=40, output=tmp_path)[model.identity]
    for key in ('macro', 'playlist_macro'):
        assert actual.summary[key] == pytest.approx(reference.summary[key], abs=1e-14)
    assert actual.uncertainty['standard_error'] == pytest.approx(reference.uncertainty['standard_error'], abs=1e-14)
    assert actual.uncertainty['interval95'] == pytest.approx(reference.uncertainty['interval95'], abs=1e-14)
    for fi, fold in enumerate(reference.fold_reports):
        for qi, q in enumerate(fold['scores']):
            meta = actual.fold_reports[fi]['scores'][qi]
            scores = np.load(tmp_path / meta['scores_file'])[0]
            order = np.load(tmp_path / meta['ranks_file'])[0]
            assert [meta['candidate_ids'][i] for i in order] == [r['candidate_recording_id'] for r in q['rows']]
            assert scores[order] == pytest.approx([r['Q'] for r in q['rows']], abs=1e-14)
    assert evaluate_many(f, [model], folds, repetitions=2, draws=40, output=tmp_path)[model.identity].identity == actual.identity


def test_bootstrap_duplicate_clusters_and_strata():
    rows = []
    # One credited curator owns two playlists; a duplicate group joins another
    # curator. Unequal mask counts and strata exercise hierarchical averaging.
    for i, (cluster, curator, stratum, n) in enumerate([
        ('a', 'c1', 'r', 2), ('a', 'c1', 'r', 3), ('a', 'c2', 'p', 2),
        ('b', 'c3', 'r', 1), ('c', 'c4', 'h', 4)]):
        for j in range(n):
            rows.append(dict(query_id=f'{i}/{j}', playlist_id=f'p{i}', cluster_id=cluster,
                curator_group_id=curator, stratum=stratum, ndcg20=(i+j)/10, recall20=.3, recall10=.1))
    weights = bootstrap_weights(rows, draws=70)
    samples = weights @ np.asarray([r['ndcg20'] for r in rows])
    old = cluster_uncertainty(rows, draws=70)
    assert weights.sum(axis=1) == pytest.approx(np.ones(70))
    assert np.std(samples, ddof=1) == pytest.approx(old['standard_error'], abs=1e-14)
    assert np.quantile(samples, [.025, .975]) == pytest.approx(old['interval95'], abs=1e-14)


def test_genre_unmatched_mass_gate_and_no_family_projection():
    concepts = {'family': {'kind': 'family', 'neighborhoods': {'n': 1}},
        's1': {'kind': 'style', 'neighborhoods': {'n': 1}},
        's2': {'kind': 'style', 'neighborhoods': {'n': .5}}}
    a = {'canonical': {'family': .5, 's1': 1}, 'specificStyleIds': ['s1']}
    b = {'canonical': {'family': .5, 's2': 1}, 'specificStyleIds': ['s2']}
    jc, jnr = genre_pair(a, b, concepts)
    assert jc == pytest.approx(.2)
    assert jnr == pytest.approx(.5)
    assert genre_pair(a, a, concepts) == (1, 0)
    assert genre_pair(a, b, concepts) == genre_pair(b, a, concepts)
    assert project({'family': 1}, concepts) == {}
    assert genre_pair(a, b | {'specificStyleIds': []}, concepts) == (0, 0)


def test_real_output_and_lockbox_cannot_select():
    f = fixture(groups=4, members=5)
    folds = grouped_folds(f.corpus, [p.playlist_id for p in f.corpus.playlists], 2, Role.LOCKBOX, 'lockbox')
    model = Model(Clap.CENTERED, 0, 0, 0)
    e = evaluate_many(f, [model], folds, repetitions=1, draws=10)[model.identity]
    with pytest.raises(ContractError, match='only inner'):
        select_inner([e], {model.identity: e})


def test_development_budget_is_bounded_and_immutable(tmp_path):
    ledger = DevelopmentLedger(tmp_path, 283)
    assert str(ledger.cap) == '5'
    assert ledger.max_attempts == 283
    DevelopmentLedger(tmp_path, 283)
    with pytest.raises(ContractError, match='immutable'):
        DevelopmentLedger(tmp_path, 284)
    with pytest.raises(ContractError, match='cap'):
        DevelopmentLedger(tmp_path / 'bad', 301)


def test_whole_registry_executes_on_identical_queries():
    from audio_similarity.calibration.ranking import ablations
    f = fixture(groups=6, members=5)
    folds = grouped_folds(f.corpus, [p.playlist_id for p in f.corpus.playlists], 2, Role.INNER, 'all-models')
    registry = ablations()
    models = {m.identity: m for candidates in registry.values() for m in candidates}
    assert len(models) == 792
    values = evaluate_many(f, list(models.values()), folds, repetitions=1, draws=10)
    choices = {arm: select_inner([values[m.identity] for m in candidates], values) for arm, candidates in registry.items()}
    assert len(choices) == 14
    assert all(c['status'] == 'READY' for c in choices.values())
    assert len({e.catalog_hashes for e in values.values()}) == 1


def test_stale_source_cannot_be_reused_as_current_embedding():
    import hashlib
    import sqlite3
    from audio_similarity.calibration.development_audio import cached_vector
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE pooled (source_sha256 TEXT, embedding BLOB, embedding_sha256 TEXT)')
    raw = np.eye(1, 512, dtype='<f4').tobytes()
    db.execute('INSERT INTO pooled VALUES (?, ?, ?)', ('old-source', raw, hashlib.sha256(raw).hexdigest()))
    assert cached_vector(db, 'pooled', 'source_sha256=?', ('current-source',)) == (None, None)
    value, _ = cached_vector(db, 'pooled', 'source_sha256=?', ('old-source',))
    assert value.shape == (512,)
    db.execute('UPDATE pooled SET embedding_sha256=?', ('0'*64,))
    with pytest.raises(ContractError, match='hash/shape'):
        cached_vector(db, 'pooled', 'source_sha256=?', ('old-source',))
    db.close()


def test_development_split_preserves_pending_and_original_duplicate_groups():
    from audio_similarity.calibration.development_search import development_plan
    from audio_similarity.calibration.splits import source_clusters
    f = fixture(groups=6, members=20)
    plan = {'formal_confirmation': False, 'production_activation': False, 'lockbox': None,
        'owner_authorization': 'explicit synthetic test authorization', 'development_exception': 'test only',
        'outer_folds': 2, 'inner_folds': 2, 'split_seed': 'test-development',
        'tracks': [{'request_id': r.recording_id, 'in_sample': True, 'purge_group': r.version_group_id,
            'artists': r.artist_group_ids, 'source_sha256': r.source_sha256} for r in f.corpus.recordings],
        'playlists': [{'playlist_id': p.playlist_id, 'sample_request_ids': p.recording_ids,
            'curator': p.curator_group_id, 'provenance_resolution': 'test', 'source_note_sha256': '0'*64,
            'stratum': p.stratum, 'title': p.source_title, 'source_description': '',
            'declared_intent': 'test', 'source_url': 'test', 'source_path': 'test'} for p in f.corpus.playlists],
        'source_clusters': {p.playlist_id: p.playlist_id for p in f.corpus.playlists}}
    plan['source_clusters']['p1'] = 'p0'
    c, nested = development_plan(plan)
    assert c.evidence_kind == 'REAL'
    assert all(not p.source_ready and p.audio_permission == 'PENDING' for p in c.playlists)
    clusters = source_clusters(c)
    assert clusters['p0'] == clusters['p1']
    for fold in nested:
        for part in (fold.outer, *fold.inner):
            assert not set(part.fit_recordings) & set(part.evaluation_recordings)
            assert not {clusters[p] for p in part.fit_playlists} & {clusters[p] for p in part.evaluation_playlists}
    with pytest.raises(ContractError, match='development-only'):
        development_plan(plan | {'production_activation': True})


def test_offline_model_client_never_uses_proxy_or_network(monkeypatch):
    from audio_similarity.calibration.development_offline import offline_client
    from huggingface_hub.errors import OfflineModeIsEnabled
    monkeypatch.setenv('ALL_PROXY', 'socks5://127.0.0.1:1')
    with offline_client() as client:
        with pytest.raises(OfflineModeIsEnabled, match='local-cache-only'):
            client.get('https://offline.invalid/model')
