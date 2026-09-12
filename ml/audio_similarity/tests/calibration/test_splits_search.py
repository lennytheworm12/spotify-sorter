from dataclasses import asdict, replace

import pytest

from audio_similarity.calibration.contracts import ContractError, Layer, Role, digest, freeze_json
from audio_similarity.calibration.ranking import Clap, Model
from audio_similarity.calibration.search import evaluate, exhaustive_synthetic, load_selection_evaluation, nested_synthetic, select_inner, summaries
from audio_similarity.calibration.splits import audit_roles, grouped_folds, make_partition, nested_plan, query_masks, reserve_lockbox, source_clusters
from audio_similarity.calibration.synthetic import fixture


def test_nested_track_and_group_separation_and_replay():
    corpus = fixture().corpus
    lock = reserve_lockbox(corpus, [p.playlist_id for p in corpus.playlists], 1, 'fixed', inspected_recordings=corpus.playlists[0].recording_ids)
    assert 'p0' not in lock.partition.evaluation_playlists
    plan = nested_plan(corpus, lock.partition.fit_playlists, allowed=lock.partition.fit_recordings)
    assert plan == nested_plan(corpus, lock.partition.fit_playlists, allowed=lock.partition.fit_recordings)
    for fold in plan:
        assert not set(fold.outer.fit_recordings) & set(fold.outer.evaluation_recordings)
        for inner in fold.inner:
            assert set(inner.fit_recordings + inner.evaluation_recordings) <= set(fold.outer.fit_recordings)
            assert not set(inner.fit_recordings) & set(inner.evaluation_recordings)
            assert not set(inner.fit_recordings + inner.evaluation_recordings) & set(lock.partition.evaluation_recordings)
        cat, queries, _ = query_masks(corpus, fold.outer, repetitions=8)
        assert all(len(q.hidden_ids) == 1 and len(q.seed_ids) == 4 for q in queries)
        assert len(queries) == 8 * len(fold.outer.evaluation_playlists)
        assert query_masks(corpus, fold.outer, repetitions=8) == (cat, queries, ())


def test_curator_duplicate_grouping_and_version_purging():
    corpus = fixture(groups=4).corpus
    playlists = list(corpus.playlists)
    playlists[1] = replace(playlists[1], curator_group_id=playlists[0].curator_group_id)
    playlists[3] = replace(playlists[3], recording_ids=playlists[2].recording_ids)
    corpus = replace(corpus, playlists=tuple(playlists))
    clusters = source_clusters(corpus)
    assert clusters['p0'] == clusters['p1'] and clusters['p2'] == clusters['p3']
    with pytest.raises(ContractError): make_partition(corpus, ['p0'], ['p1'], Role.INNER, 'x')
    with pytest.raises(ContractError): grouped_folds(corpus, [p.playlist_id for p in playlists], 3, Role.OUTER, 'x')
    corpus = fixture(groups=3).corpus
    records = list(corpus.recordings)
    records[0] = replace(records[0], version_group_id=records[5].version_group_id)
    corpus = replace(corpus, recordings=tuple(records))
    split = make_partition(corpus, ['p0'], ['p1'], Role.INNER, 'x')
    assert records[0].recording_id in split.purged_recordings
    assert records[0].recording_id not in split.fit_recordings
    audit = audit_roles(corpus, {Role.RANKING: ['p0'], Role.FINAL: ['p1']},
                       {Role.RANKING: corpus.playlists[0].recording_ids, Role.FINAL: corpus.playlists[1].recording_ids})
    assert audit['status'] == 'INSUFFICIENT_DATA'


def test_lockbox_outer_and_catalog_cannot_select(tmp_path):
    f = fixture(groups=4)
    ids = [p.playlist_id for p in f.corpus.playlists]
    inner = grouped_folds(f.corpus, ids, 2, Role.INNER, 'fixed')
    model = Model(Clap.CENTERED, .5, 0, 0)
    e = evaluate(f, model, inner, bootstrap_draws=8)
    assert select_inner([e], {model.identity: e})['selected_model_id'] == model.identity
    envelope = {'schema': 'inner-evaluation-v1', 'role': Role.INNER, 'evaluation': asdict(e), 'sha256': e.identity}
    freeze_json(tmp_path / 'inner.json', envelope)
    assert load_selection_evaluation(tmp_path / 'inner.json').identity == e.identity
    for role in (Role.OUTER, Role.LOCKBOX, Role.FINAL):
        outer = grouped_folds(f.corpus, ids, 2, role, 'fixed')
        held = evaluate(f, model, outer, bootstrap_draws=8)
        with pytest.raises(ContractError): select_inner([held], {model.identity: e})
        freeze_json(tmp_path / f'{role.value}.json', dict(envelope, role=role))
        with pytest.raises(ContractError): load_selection_evaluation(tmp_path / f'{role.value}.json')
    different_masks = evaluate(f, model, inner, repetitions=2, bootstrap_draws=8)
    with pytest.raises(ContractError): select_inner([e], {model.identity: different_masks})
    changed = replace(e, catalog_hashes=(digest('different'),))
    with pytest.raises(ContractError): select_inner([e], {model.identity: changed})


def test_simplicity_and_recall_guardrail():
    f = fixture(groups=4)
    folds = grouped_folds(f.corpus, [p.playlist_id for p in f.corpus.playlists], 2, Role.INNER, 'x')
    base = Model(Clap.METHOD_C, 0, 0, 0)
    more = Model(Clap.METHOD_C, 0, .05, .25)
    simple, complex_ = [evaluate(f, m, folds, bootstrap_draws=8) for m in (base, more)]
    # Explicit metric fixtures: exercise selection without tuning a real outcome.
    sm = {**simple.summary, 'macro': {'ndcg20': .8, 'recall20': .9, 'recall10': .8}}
    cm = {**complex_.summary, 'macro': {'ndcg20': .81, 'recall20': .9, 'recall10': .8}}
    simple = replace(simple, summary=sm, uncertainty={'standard_error': .03})
    complex_ = replace(complex_, summary=cm, uncertainty={'standard_error': .03})
    assert select_inner([simple, complex_], {base.identity: simple})['selected_model_id'] == base.identity
    complex_ = replace(complex_, summary={**cm, 'macro': dict(cm['macro'], recall20=.87)})
    assert select_inner([simple, complex_], {base.identity: simple})['reasons'][more.identity] == 'RECALL_GUARDRAIL'


def test_masks_do_not_overweight_playlist_or_curator():
    rows = []
    for i in range(8):
        rows.append(dict(query_id=f'a{i}', playlist_id='a', curator_group_id='g1', cluster_id='g1', stratum='s', ndcg20=1., recall20=1., recall10=1.))
    rows.append(dict(query_id='b', playlist_id='b', curator_group_id='g2', cluster_id='g2', stratum='s', ndcg20=0., recall20=0., recall10=0.))
    assert summaries(rows)['macro']['ndcg20'] == .5


def test_synthetic_nested_selection_guard_and_all_arms(monkeypatch, tmp_path):
    f = fixture(groups=6)
    small = {'audio': (Model(Clap.CENTERED, 0, 0, 0), Model(Clap.METHOD_C, 0, 0, 0))}
    monkeypatch.setattr('audio_similarity.calibration.search.ablations', lambda: small)
    plan = nested_plan(f.corpus, [p.playlist_id for p in f.corpus.playlists])
    result = nested_synthetic(f, plan, output=tmp_path, bootstrap_draws=8)
    assert len(result['folds']) == 3
    before = (tmp_path / 'nested_estimates.json').read_bytes()
    assert nested_synthetic(f, plan, output=tmp_path, bootstrap_draws=8) == result
    assert (tmp_path / 'nested_estimates.json').read_bytes() == before
    from tests.calibration.test_contracts_ranking import modified
    f = modified(f, corpus=replace(f.corpus, evidence_kind='REAL'))
    with pytest.raises(ContractError): exhaustive_synthetic(f, plan[0].inner)
