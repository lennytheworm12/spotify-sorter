from dataclasses import replace
import socket

import numpy as np
import pytest

from audio_similarity.calibration.contracts import Clap, ContractError, Role, State, digest
from audio_similarity.calibration.output import (CalibrationHook, RankerFreeze, Strictness, Suitability,
    SuitabilityLabel, ValidatedThresholds, descriptive_row, preview, reference_percentile, suitability_readiness)
from audio_similarity.calibration.ranking import Model
from audio_similarity.calibration.readiness import summarize_inventory
from audio_similarity.calibration.synthetic import fixture
from tests.calibration.test_contracts_ranking import modified


def ranker(f):
    return RankerFreeze(Model(Clap.METHOD_C, .5, .05, .25), f.identity,
                        f.identities['Jc'].mapper_sha256, f.identities['Jc'].prompt_sha256,
                        digest('source-policy'), 'candidate-policy')


def test_reference_ties_equal_seed_sizes_and_replay():
    f = fixture(groups=5)
    f = modified(f, {key: np.ones_like(f.matrices[key]) * .5 for key in ('C_center30', 'C_method_c', 'M')})
    model = Model(Clap.CENTERED, 0, 0, 0)
    members = f.track_ids[:20]
    result = reference_percentile(f, model, f.track_ids[-1], members, snapshot_id='s')
    assert result['member_reference_percentile'] == .5
    assert result['reference_seed_size'] == 19 and result['reference_count'] == 20
    assert result == reference_percentile(f, model, f.track_ids[-1], members, snapshot_id='s')
    for row in result['member_references'] + [result['candidate_reference']]:
        assert len(row['subsets']) == 8
        assert all(len(s) == 19 and row['recording_id'] not in s for s in row['subsets'])
    invalid = reference_percentile(f, model, 'missing', members, snapshot_id='s')
    assert invalid['member_reference_percentile'] is None and invalid['status'] == 'INSUFFICIENT_DATA'
    short = reference_percentile(f, model, f.track_ids[-1], members[:19], snapshot_id='s')
    assert short['member_reference_percentile'] is None and short['status'] == 'INSUFFICIENT_DATA'
    rows = list(f.corpus.recordings)
    rows[1] = replace(rows[1], version_group_id=rows[0].version_group_id)
    dup = modified(f, corpus=replace(f.corpus, recordings=tuple(rows)))
    assert reference_percentile(dup, model, dup.track_ids[-1], members, snapshot_id='s')['status'] == 'INSUFFICIENT_DATA'


def test_strictness_nested_and_snapshot_no_mutation():
    f = fixture(groups=5)
    freeze = ranker(f)
    seeds = list(f.track_ids[:5]); before = seeds[:]
    policy = ValidatedThresholds(-.1, .1, .5, freeze.identity, freeze.candidate_policy_id,
                                 digest('synthetic-validation'), 'synthetic', 'SYNTHETIC')
    candidates = f.track_ids[5:]
    outputs = [preview(f, freeze, candidates, seeds, snapshot_id='snapshot', strictness=s,
                       policy=policy, domain_id='synthetic') for s in Strictness]
    ids = [{r['candidate_recording_id'] for r in out['rows'] if r['decision'] == 'recommend'} for out in outputs]
    assert ids[2] <= ids[1] <= ids[0]
    assert len({o['ranking_model_id'] for o in outputs}) == 1
    scores = [[(r['candidate_recording_id'], r['raw_playlist_score']) for r in o['rows']] for o in outputs]
    assert scores[0] == scores[1] == scores[2]
    assert seeds == before and all(o['playlist_writes'] == 0 for o in outputs)
    assert preview(f, freeze, reversed(candidates), seeds, snapshot_id='snapshot', strictness=Strictness.BROAD,
                   policy=policy, domain_id='synthetic') == outputs[0]
    uncalibrated = preview(f, freeze, candidates, seeds, snapshot_id='snapshot', strictness=Strictness.TIGHT)
    assert uncalibrated['status'] == 'NOT_CALIBRATED' and uncalibrated['threshold'] is None
    assert all(r['decision'] == 'not_calibrated' for r in uncalibrated['rows'])
    with pytest.raises(ContractError): replace(policy, tight=-1)
    unsupported = preview(f, freeze, candidates, seeds, snapshot_id='s', strictness=Strictness.BROAD, policy=policy, domain_id='other')
    assert unsupported['status'] == 'NEEDS_REVIEW' and unsupported['threshold'] is None
    assert all(r['decision'] == 'needs_review' for r in unsupported['rows'])


def test_suitability_evidence_and_hook_gate():
    f = fixture()
    freeze = ranker(f)
    assert suitability_readiness([], freeze)['status'] == 'NOT_CALIBRATED'
    selected = replace(freeze, selected=True, selection_evidence_sha256=digest('synthetic-selection'))
    assert suitability_readiness([], selected)['status'] == 'LABELS_REQUIRED'
    label = SuitabilityLabel('r', 'snapshot', Suitability.SUITABLE, 'audible-target', 'reviewer',
                             'source', 'policy', Role.OUTPUT, digest('human-ledger'))
    for origin in ('playlist_nonmembership', 'genre_mismatch', 'observed_member', 'model_prediction'):
        with pytest.raises(ContractError): replace(label, origin=origin)
    assert suitability_readiness([label], selected)['status'] == 'LABELS_REQUIRED'
    unknown = replace(label, label=Suitability.UNCERTAIN)
    assert suitability_readiness([label, unknown], selected)['counts']['uncertain'] == 1
    with pytest.raises(ContractError): CalibrationHook('sigmoid', State.LABELS, None).validate_fit_request()
    with pytest.raises(ContractError): CalibrationHook('sigmoid', State.READY, digest('protocol'), 'pair_F').validate_fit_request()
    assert CalibrationHook('isotonic', State.READY, digest('protocol')).validate_fit_request()['score_domain'] == 'raw_playlist_Q'


def test_descriptive_offline_and_real_ranker_freeze_gate(monkeypatch):
    def prohibited(*a, **kw):
        pytest.fail('No network/model/playlist writes in descriptive machinery')
    monkeypatch.setattr(socket, 'create_connection', prohibited)
    f = fixture(groups=5)
    row = descriptive_row(f, ranker(f), f.track_ids[-1], f.track_ids[:-1], snapshot_id='s')
    assert row['suitability_probability'] is None and row['decision'] == 'not_calibrated'
    assert row['raw_playlist_score'] is not None and row['member_reference_score'] is not None
    assert 'raw_pair_score' not in row
    from tests.calibration.test_contracts_ranking import modified
    f = modified(f, corpus=replace(f.corpus, evidence_kind='REAL'))
    assert descriptive_row(f, ranker(f), f.track_ids[-1], f.track_ids[:-1], snapshot_id='s')['status'] == 'NOT_CALIBRATED'


def test_readiness_is_descriptive_not_fake_ready():
    inventory = {'recordings': [dict(recording_id='r', processed=True, centered30=True,
                  method_c=False, muq=True, canonical=False, errors=[], queue_state='COMPLETE')]}
    report = summarize_inventory(inventory)
    assert report['processed_recordings'] == 1
    assert report['missing_centered30'] == 0 and report['missing_method_c'] == 1
    assert report['feature_readiness'] == 'WAITING_FOR_FEATURES'
    assert report['output_descriptive_readiness'] == 'NOT_CALIBRATED'
    assert report['suitability_calibration_readiness'] == 'LABELS_REQUIRED'
    assert summarize_inventory(inventory) == report


def test_readiness_reads_cache_and_rejects_hash_mismatch(tmp_path, monkeypatch):
    import json
    import sqlite3
    from types import SimpleNamespace
    from audio_similarity.calibration.contracts import file_hash
    from audio_similarity.calibration.readiness import scan_batches
    from audio_similarity.stage5d0a_manifest import document_sha256
    root = tmp_path
    run = root / '.research_audio/run'
    run.mkdir(parents=True)
    source = root / '.research_audio/recording/source.webm'
    source.parent.mkdir()
    source.write_bytes(b'synthetic compressed fixture; no audio decoding is invoked')
    source_hash = file_hash(source)
    (source.parent / 'provenance.json').write_text(json.dumps({'spotify_track_id': 'recording',
                   'source_sha256': source_hash, 'full_decode_validated': True}))
    contract = SimpleNamespace(vector_contract_sha256=digest('contract'),
                               encoders=(SimpleNamespace(encoder_id='clap', dimension=2), SimpleNamespace(encoder_id='muq', dimension=2)),
                               encoder_analysis_identity=lambda **kw: kw['encoder_id'])
    monkeypatch.setattr('audio_similarity.calibration.readiness.load_contract', lambda path: contract)
    cache = root / 'artifacts/cache.sqlite'
    cache.parent.mkdir()
    with sqlite3.connect(cache) as db:
        for table in ('pooled', 'segments'):
            db.execute(f'CREATE TABLE {table} (encoder_analysis_identity TEXT,status TEXT,center_sec INTEGER,source_audio_sha256 TEXT,vector_contract_sha256 TEXT,embedding BLOB,embedding_sha256 TEXT)')
            import hashlib
            vector = np.array([1., 0.], dtype='<f4').tobytes()
            for encoder in ('clap', 'muq'):
                for center in ([0] if table == 'pooled' else [5, 15, 25]):
                    db.execute(f'INSERT INTO {table} VALUES (?,?,?,?,?,?,?)',
                               (encoder, 'SUCCESS', center, source_hash, contract.vector_contract_sha256, vector, hashlib.sha256(vector).hexdigest()))
    manifest = {'batches': [{'batch_number': 1, 'tracks': [{'local_recording_id': 'request'}]}]}
    (run / 'manifest.json').write_text(json.dumps(manifest))
    (run / 'manifest_hash.json').write_text(json.dumps({'sha256': document_sha256(manifest)}))
    batch = run / 'batch_0001'
    batch.mkdir()
    state = {'tracks': {'request': {'state': 'COMPLETE', 'result': {
        'source_sha256': source_hash, 'retained_relative_path': 'recording/source.webm',
        'representation': {'stable_track_id': 'recording', 'cache_path': 'artifacts/cache.sqlite',
            'source_audio_sha256': source_hash, 'vector_contract_sha256': contract.vector_contract_sha256,
            'corpus': 'synthetic', 'corpus_version': 'v1', 'canonical_pcm_sha256': digest('pcm')}}}}}
    (batch / 'state.json').write_text(json.dumps(state))
    before = cache.read_bytes()
    result = scan_batches(root, (run,))
    assert result['recordings'][0]['centered30'] and result['recordings'][0]['muq']
    assert not result['recordings'][0]['method_c']
    assert cache.read_bytes() == before
    state['tracks']['request']['result']['representation']['source_audio_sha256'] = digest('different')
    (batch / 'state.json').write_text(json.dumps(state))
    bad = summarize_inventory(scan_batches(root, (run,)))
    assert bad['hash_mismatches'] == 1 and bad['verified_centered30'] == 0
