"""Isolated synthetic audio/provider data only. Never accesses the real dataset/key."""
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from audio_similarity.calibration.contracts import ContractError, digest, file_hash, freeze_json
from audio_similarity.calibration.gemini_full_budget import FullLedger, spending
from audio_similarity.calibration.gemini_full_inputs import DEV, METHOD_C, RUN, read
from audio_similarity.calibration.gemini_full_manifest import freeze_execution, validate_approval
from audio_similarity.calibration.gemini_full_runner import FullRunner, freeze_profiles, load_execution
from audio_similarity.calibration.gemini_full_features import genre_matrices
from audio_similarity.gemini_free_genre import free_schema
from audio_similarity.gemini_free_genre_point import POINT_PROMPT, point_schema
from audio_similarity.gemini_style_pilot.budget import BudgetStopped
from audio_similarity.gemini_style_pilot.manifest import CONFIG, MODEL, environment
from tests.test_gemini_free_genre import FreeProvider
from tests.test_gemini_style_runner import FIXTURE


def policy(cap='20', attempts=4):
    return {'input_token_limit': 1048576, 'spend_cap_usd': cap, 'max_attempts': attempts,
        'rates': {'input': '0.75', 'output_including_thinking': '3.75', 'valid_through': '2026-12-31'},
        'authorization_sha256': 'a' * 64}


def reserve(ledger):
    return ledger.reserve(counted_input=7000, max_output_tokens=8192,
        request_sha256='a' * 64, manifest_sha256='b' * 64, neutral_id='N001')


def test_global_cap_cannot_be_spent_again_by_second_batch(tmp_path):
    p = policy(cap='1')
    first = FullLedger(tmp_path / 'batch_0001/execution/attempts', tmp_path, p, 2)
    second = FullLedger(tmp_path / 'batch_0002/execution/attempts', tmp_path, p, 2)
    reserve(first)
    with pytest.raises(BudgetStopped, match='unresolved global'):
        reserve(second)
    first.settle(1, {'promptTokenCount': 400000, 'candidatesTokenCount': 1000, 'totalTokenCount': 401000})
    assert Decimal(spending(tmp_path)['actual_cost_usd']) == Decimal('.30375')
    with pytest.raises(BudgetStopped, match='approved global cap'):
        reserve(second)
    assert not list(second.directory.glob('*.reservation.json'))


def test_global_attempt_allowance_and_policies_are_immutable(tmp_path):
    p = policy(attempts=1)
    first = FullLedger(tmp_path / 'batch_0001/execution/attempts', tmp_path, p, 1)
    reserve(first)
    first.settle(1, {'promptTokenCount': 1, 'candidatesTokenCount': 1, 'totalTokenCount': 2})
    second = FullLedger(tmp_path / 'batch_0002/execution/attempts', tmp_path, p, 1)
    with pytest.raises(BudgetStopped, match='global generation'):
        reserve(second)
    with pytest.raises(ContractError, match='immutable'):
        FullLedger(first.directory, tmp_path, p | {'spend_cap_usd': '30'}, 1)


def synthetic_execution(root, monkeypatch):
    """Four fake recordings, two neutral-ID batches, no real source/model files."""
    from audio_similarity.calibration import gemini_full_manifest as manifest_module
    from audio_similarity.calibration import gemini_full_runner as runner_module
    monkeypatch.setattr(manifest_module, 'producer_hashes', lambda _: {})
    monkeypatch.setattr(runner_module, 'producer_hashes', lambda _: {})
    base = point_schema(free_schema(read(FIXTURE / 'response_schema.json')))
    old = root / DEV / 'gemini'
    old.mkdir(parents=True)
    (old / 'prompt.txt').write_text(POINT_PROMPT)
    freeze_json(old / 'response_schema.json', base)
    rows, batches = [], []
    for batch in (1, 2):
        directory = root / RUN / f'batch_{batch:04d}'
        directory.mkdir(parents=True)
        (directory / 'prompt.txt').write_text(POINT_PROMPT)
        freeze_json(directory / 'response_schema.json', base)
        tracks = []
        for i in (1, 2):
            source = root / f'source-{batch}-{i}.bin'
            source.write_bytes(f'SYNTHETIC AUDIO BYTES {batch}-{i}'.encode())
            path = directory / 'prepared' / f'N{i:03d}.flac'
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(source.read_bytes())
            sha = file_hash(source)
            prepared = {'source_sha256': sha, 'source_path': str(source),
                'prepared_sha256': sha, 'prepared_filename': path.name, 'duration_seconds': 150,
                'full_recording_preserved': True, 'identity_metadata_removed': True}
            freeze_json(path.with_suffix('.json'), prepared)
            schema = point_schema(free_schema(read(FIXTURE / 'response_schema.json')))
            schema['properties']['audio_evidence']['items']['properties']['at_seconds']['maximum'] = 150
            name = f'schemas/T{i:03d}.json'
            freeze_json(directory / name, schema)
            sid = f'synthetic-{batch}-{i}'
            tracks.append({'pilot_id': f'T{i:03d}', 'neutral_id': f'N{i:03d}', 'recording_id': sid,
                'source_path': source.name, 'source_sha256': sha, 'prepared': prepared,
                'response_schema': name, 'response_schema_sha256': digest(schema)})
            rows.append({'recording_id': sid, 'source_path': source.name, 'audio_sha256': sha, 'profile': None})
        batches.append((directory, tracks))
    corpus = {'recordings': rows}
    freeze_json(root / METHOD_C / 'corpus.json', corpus)
    preflight = {'corpus_sha256': digest(corpus), 'corpus_path': str(METHOD_C / 'corpus.json'),
        'recordings': rows, 'counts': {'missing_profiles': 4}}
    freeze_json(root / RUN / 'preflight.json', preflight)
    psha = digest(preflight)
    batch_refs = []
    for batch, (directory, tracks) in enumerate(batches, 1):
        plan = {'batch': batch, 'tracks': tracks, 'preflight_sha256': psha,
            'model_id': MODEL, 'generation_config': CONFIG, 'environment': environment(),
            'prompt_sha256': file_hash(directory / 'prompt.txt'), 'base_schema_sha256': digest(base),
            'prepared_root': str((directory / 'prepared').relative_to(root))}
        freeze_json(directory / 'prepared_plan.json', plan)
        batch_refs.append({'path': str((directory / 'prepared_plan.json').relative_to(root)), 'sha256': digest(plan)})
    freeze_json(root / RUN / 'prepared.json', {'preflight_sha256': psha, 'batches': batch_refs})
    freeze_json(root / RUN / 'pricing_verification.json', policy()['rates'] | {'model_id': MODEL, 'tier': 'standard'})
    approval = {'schema': 'gemini-full-upload-authorization-v1', 'approved': True,
        'destination': 'Google Gemini API', 'corpus_sha256': digest(corpus), 'preflight_sha256': psha,
        'recording_ids_sha256': digest([t['recording_id'] for t in rows]),
        'max_new_generations': 4, 'spend_cap_usd': '20', 'owner_message': 'SYNTHETIC AUTHORIZATION ONLY'}
    freeze_json(root / 'approval.json', approval)
    execution = freeze_execution(root, root / 'approval.json')
    _, p, _ = load_execution(root)
    return execution, p


@pytest.mark.parametrize('field,value', [('spend_cap_usd', 'NaN'), ('approved', False),
    ('recording_ids_sha256', '0' * 64), ('max_new_generations', 100), ('destination', 'another provider')])
def test_upload_approval_cannot_expand_scope_or_omit_cap(tmp_path, monkeypatch, field, value):
    synthetic_execution(tmp_path, monkeypatch)
    approval = read(tmp_path / 'approval.json') | {field: value}
    preflight = read(tmp_path / RUN / 'preflight.json')
    with pytest.raises(ValueError):
        validate_approval(approval, preflight, digest(preflight))


def test_two_batches_preserve_paid_results_and_zero_transport_replay(tmp_path, monkeypatch):
    execution, p = synthetic_execution(tmp_path, monkeypatch)
    for batch in execution['batches']:
        directory = (tmp_path / batch['path']).parent
        provider = FreeProvider(directory)
        provider.point = True
        runner = FullRunner(tmp_path, directory, p, transport_factory=provider.factory)
        assert runner.execute_remaining() == 2
        assert provider.generations == 2
        before = {str(path): file_hash(path) for path in directory.rglob('*') if path.is_file()}
        runner.transport_factory = lambda: pytest.fail('completed replay constructed a transport')
        assert runner.execute_remaining() == 0
        assert {str(path): file_hash(path) for path in directory.rglob('*') if path.is_file()} == before
    from audio_similarity.calibration import gemini_full_runner
    monkeypatch.setattr(gemini_full_runner, 'GeminiTransport', lambda *a, **k: pytest.fail('freeze called provider'))
    first = freeze_profiles(tmp_path)
    assert len(first['profiles']) == 4 and first['replay_new_api_calls'] == 0
    assert first == freeze_profiles(tmp_path)
    assert spending(tmp_path / RUN)['generation_attempts'] == 4
    raw = next((tmp_path / RUN).glob('batch_*/execution/transport/*.response.bin'))
    raw.write_bytes(b'CORRUPTED SYNTHETIC EVIDENCE')
    with pytest.raises(ValueError):
        freeze_profiles(tmp_path)


@pytest.mark.parametrize('fault', ['http', 'schema', 'finish', 'count', 'usage', 'upload_hash'])
def test_failure_stops_all_batches_without_retry(tmp_path, monkeypatch, fault):
    execution, p = synthetic_execution(tmp_path, monkeypatch)
    directory = (tmp_path / execution['batches'][0]['path']).parent
    provider = FreeProvider(directory, fault=fault)
    provider.point = True
    runner = FullRunner(tmp_path, directory, p, transport_factory=provider.factory)
    with pytest.raises(ValueError):
        runner.execute_remaining()
    calls = len(provider.calls)
    with pytest.raises(ValueError, match='prior failure'):
        runner.execute_remaining()
    second = FullRunner(tmp_path, (tmp_path / execution['batches'][1]['path']).parent, p,
                        transport_factory=lambda: pytest.fail('second batch bypassed failure'))
    with pytest.raises(ValueError, match='prior failure'):
        second.execute_remaining()
    assert len(provider.calls) == calls


def test_partial_profile_coverage_cannot_freeze_as_unknown(tmp_path, monkeypatch):
    synthetic_execution(tmp_path, monkeypatch)
    with pytest.raises(ContractError, match='missing/unsettled'):
        freeze_profiles(tmp_path)
    assert not (tmp_path / RUN / 'profiles_frozen.json').exists()


def test_source_mutation_prevents_upload(tmp_path, monkeypatch):
    execution, p = synthetic_execution(tmp_path, monkeypatch)
    (tmp_path / 'source-1-1.bin').write_bytes(b'CHANGED')
    runner = FullRunner(tmp_path, (tmp_path / execution['batches'][0]['path']).parent, p,
                        transport_factory=lambda: pytest.fail('changed source was uploaded'))
    with pytest.raises(ContractError, match='source changed'):
        runner.execute_remaining()


def test_lost_result_keeps_original_charge_and_never_repeats_call(tmp_path, monkeypatch):
    execution, p = synthetic_execution(tmp_path, monkeypatch)
    directory = (tmp_path / execution['batches'][0]['path']).parent
    provider = FreeProvider(directory)
    provider.point = True
    runner = FullRunner(tmp_path, directory, p, transport_factory=provider.factory)
    assert runner.execute_remaining() == 2
    before = spending(tmp_path / RUN)
    # Deliberate corruption of an isolated fixture, never a production ledger.
    runner.result_path(2).unlink()
    runner.transport_factory = lambda: pytest.fail('unaccounted result triggered another paid call')
    with pytest.raises(ContractError, match='interrupted/unaccounted'):
        runner.execute_remaining()
    assert spending(tmp_path / RUN) == before
    assert provider.generations == 2


def test_changed_prepared_audio_is_not_uploaded(tmp_path, monkeypatch):
    execution, p = synthetic_execution(tmp_path, monkeypatch)
    directory = (tmp_path / execution['batches'][0]['path']).parent
    (directory / 'prepared/N001.flac').write_bytes(b'OTHER RECORDING')
    runner = FullRunner(tmp_path, directory, p,
                        transport_factory=lambda: pytest.fail('changed prepared recording was uploaded'))
    with pytest.raises(ContractError, match='prepared audio changed'):
        runner.execute_remaining()


def test_sharded_reference_arithmetic_neutrality_and_recompute(tmp_path):
    concepts = {'family': {'kind': 'family', 'neighborhoods': {'n': 1}},
        's1': {'kind': 'style', 'neighborhoods': {'n': 1}},
        's2': {'kind': 'style', 'neighborhoods': {'n': .5}}}
    mapped = {'a': {'canonical': {'family': .5, 's1': 1}, 'specificStyleIds': ['s1']},
              'b': {'canonical': {'family': .5, 's2': 1}, 'specificStyleIds': ['s2']},
              'c': {'canonical': {'family': 1}, 'specificStyleIds': []}}
    ids = sorted(mapped)
    value = genre_matrices(tmp_path, ids, mapped, concepts, 'fixture', shard_size=2)
    assert value['Jc'][0, 1] == pytest.approx(.2)
    assert value['Jnr'][0, 1] == pytest.approx(.5)
    assert value['R'][0, 1] == pytest.approx(.4)
    assert list(np.diag(value['Jc'])) == [1, 1, 0]
    assert np.array_equal(value['R'], (1 - value['Jc']) * value['Jnr'])
    assert all(np.array_equal(a, a.T) and not a[2].any() for a in value.values())
    hashes = {str(p): file_hash(p) for p in tmp_path.iterdir()}
    again = genre_matrices(tmp_path, ids, mapped, concepts, 'fixture', shard_size=2, recompute=True)
    assert all(np.array_equal(value[k], again[k]) for k in value)
    assert hashes == {str(p): file_hash(p) for p in tmp_path.iterdir()}
    with pytest.raises(ContractError, match='incompatible'):
        genre_matrices(tmp_path, ids, mapped, concepts, 'different', shard_size=2)
    with pytest.raises(ContractError, match='mapping coverage'):
        genre_matrices(tmp_path, ids, {'a': mapped['a']}, concepts, 'fixture')
