"""Isolated synthetic corpus continuation; never uses a real key, source, or rating."""
import copy
from decimal import Decimal

import pytest

from audio_similarity.gemini_frozen100.export import export
from audio_similarity.gemini_frozen100.prepare import CORPUS, LIBRARY, inventory
from audio_similarity.gemini_frozen100.runner import CorpusLedger, Frozen100Runner
from audio_similarity.gemini_style_pilot.budget import BudgetStopped
from audio_similarity.gemini_style_pilot.runner import RunStopped
from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import digest, freeze_json, hashes, read
from tests.test_gemini_free_genre import fixture as prior_fixture, FreeProvider


def fixture(root):
    prior, provider = prior_fixture(root)
    for _ in range(18):
        prior.next()
    prior.freeze_profiles()
    run = root / 'corpus'
    run.mkdir()
    (run / 'prompt.txt').write_text(prior.prompt)
    freeze_json(run / 'response_schema.json', prior.schema_for('A01'))
    rows, schemas = [], {}
    for i in range(1, 101):
        old = prior.manifest['tracks'][i - 1] if i <= 16 else None
        pid, neutral = f'F{i:03d}', f'N{i:03d}'
        path = run / 'prepared' / f'{neutral}.flac'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes((prior.run / 'prepared' / old['prepared']['prepared_filename']).read_bytes() if old else f'SYNTHETIC {i}'.encode())
        prepared = copy.deepcopy(old['prepared']) if old else {
            'prepared_filename': path.name, 'prepared_sha256': file_sha256(path), 'duration_seconds': 150,
            'source_sha256': file_sha256(path), 'full_recording_preserved': True, 'identity_metadata_removed': True}
        cache = None
        if old:
            index = next(j for j, s in enumerate(prior.manifest['schedule'], 1) if s['pilot_id'] == old['pilot_id'])
            result = prior.verified_result(index)
            cache = {'source_run': str(prior.run.relative_to(root)), 'source_attempt': index,
                     'source_pilot_id': old['pilot_id'], 'cache_key': result['cache_key'],
                     'result_sha256': file_sha256(prior.result_path(index)), 'source_manifest_sha256': prior.manifest_sha}
        provenance = run / 'provenance' / f'{pid}.json'
        freeze_json(provenance, {'synthetic': True})
        schemas[pid] = f'schemas/{neutral}.json'
        freeze_json(run / schemas[pid], prior.schema_for('A01'))
        rows.append({'pilot_id': pid, 'neutral_id': neutral, 'spotify_track_id': f'{i:022d}',
                     'catalog_title': f'Synthetic {i}', 'catalog_artists': ['Synthetic'], 'eligible': True,
                     'source_sha256': prepared['source_sha256'], 'prepared': prepared,
                     'cached_profile': cache, 'provenance_path': str(provenance.relative_to(root))})
    for name in ('source_inventory.json', 'prepared_inventory.json'):
        freeze_json(run / name, {'tracks': rows, 'blocked': []})
    (run / 'protocol.md').write_text('SYNTHETIC frozen protocol')
    freeze_json(run / 'authorization.json', {'synthetic': True})
    inputs = hashes(list(run.rglob('*')), root)
    protected = hashes(list(prior.run.rglob('*')), root)
    m = copy.deepcopy(prior.manifest)
    m.update(schema_version='gemini-frozen100-v1', tracks=rows, response_schemas=schemas,
             prepared_root=str((run / 'prepared').relative_to(root)), max_attempts=84, prior_attempts=38,
             combined_attempt_cap=122, prior_settled_usd='.23869650', spend_cap_usd='1.76130350',
             genre_examples=None, genre_definitions=None,
             schedule=[{'pilot_id': t['pilot_id'], 'repeat': False} for t in rows[16:]],
             cached_profiles={t['pilot_id']: t['cached_profile'] for t in rows[:16]},
             input_hashes=inputs, critical_input_hashes={k: v for k, v in inputs.items() if not k.endswith('.flac')},
             protected_hashes=protected, implementation_hashes={}, implementation_sha256=digest({}))
    freeze_json(run / 'execution_manifest.json', m)
    provider = FreeProvider(run)
    return Frozen100Runner(root, run, transport_factory=provider.factory), provider


def test_100_profiles_reuse_16_no_provider_replay_deterministic_export_and_history(tmp_path):
    runner, provider = fixture(tmp_path)
    for i in range(1, 85):
        assert runner.next()['attempt'] == i
    assert provider.generations == 84
    runner.transport_factory = lambda: pytest.fail('replay dispatched provider')
    before = hashes(list(runner.directory.rglob('*')), runner.run)
    assert runner.next()['new_generation_calls'] == 0
    frozen = runner.freeze_profiles()
    assert frozen['replay'] == {'status': 'CACHE_REPLAY_VERIFIED', 'cached_prior_profiles': 16,
        'new_validated_profiles': 84, 'invalid_profiles': 0, 'unique_profiles': 100, 'new_api_calls': 0}
    assert hashes(list(runner.directory.rglob('*')), runner.run) == before
    report = tmp_path / 'report'
    result = export(runner, report)
    assert result['profile_status_counts'] == {'uncertain': 100}  # Valid abstention is not failure.
    original = hashes(list(report.rglob('*')), report)
    assert export(runner, report) == result
    assert hashes(list(report.rglob('*')), report) == original
    assert len(read(report / 'classifications.json')) == 100
    assert all(b'TEST-KEY-NEVER-LOG' not in p.read_bytes() for p in report.rglob('*') if p.is_file())


def test_accounted_invalid_output_after_smokes_is_null_then_continues_without_retry(tmp_path):
    runner, provider = fixture(tmp_path)
    runner.next(); runner.next()
    provider.fault = 'schema'
    assert runner.next()['status'] == 'INVALID_PROFILE_NO_RETRY'
    assert runner.verified_failure(3)['profile'] is None
    assert not runner.result_path(3).exists()
    provider.fault = None
    assert runner.next()['attempt'] == 4
    assert provider.generations == 4
    assert runner.replay(require_complete=False)['invalid_profiles'] == 1


@pytest.mark.parametrize('fault', ['schema', 'audio', 'usage', 'http', 'connection'])
def test_smoke_or_unaccounted_failure_stops_without_retry(tmp_path, fault):
    runner, provider = fixture(tmp_path)
    provider.fault = fault
    with pytest.raises(ValueError): runner.next()
    assert provider.generations == 1
    with pytest.raises(RunStopped, match='previous operational failure'): runner.next()
    assert provider.generations == 1


def test_prior_cache_audio_or_request_context_cannot_be_substituted(tmp_path):
    runner, provider = fixture(tmp_path)
    runner.tracks['F001']['prepared']['duration_seconds'] = 149
    with pytest.raises(RunStopped, match='exactly compatible'): runner.verify_prior_cache()
    assert provider.generations == 0


def test_changed_prompt_or_protected_history_stops_without_api(tmp_path):
    runner, provider = fixture(tmp_path)
    with pytest.raises(ValueError, match='freeze all profiles'): export(runner, tmp_path / 'early')
    (runner.run / 'prompt.txt').write_text('a different prompt')
    with pytest.raises(ValueError, match='integrity mismatch'): runner.next()
    assert provider.generations == 0


def test_corpus_ledger_cap_includes_all_prior_costs_and_stops_unsettled_attempt(tmp_path):
    ledger = CorpusLedger(tmp_path, prior_spend='.23869650', spend_cap='1.76130350')
    result = ledger.reserve(counted_input=7000, max_output_tokens=8192, request_sha256='a'*64,
                            manifest_sha256='b'*64, neutral_id='N017')
    assert Decimal(result['reserved_upper_cost_usd']) == Decimal('.817152')
    with pytest.raises(BudgetStopped, match='unresolved'):
        ledger.reserve(counted_input=7000, max_output_tokens=8192, request_sha256='a'*64,
                       manifest_sha256='b'*64, neutral_id='N018')
    with pytest.raises(BudgetStopped): CorpusLedger(tmp_path / 'bad', prior_spend='.24', spend_cap='2')
    with pytest.raises(BudgetStopped): CorpusLedger(tmp_path / 'bad2', prior_spend='.24', spend_cap='1.76', max_attempts=85)


def test_inventory_keeps_all_100_and_exposes_source_quarantine_correction_and_provenance_failures(tmp_path):
    tracks, old, current = [], [], {}
    for i in range(1, 101):
        tid = f'{i:022d}'
        path = tmp_path / '.research_audio' / tid / 'audio.mp3'
        path.parent.mkdir(parents=True)
        path.write_bytes(f'SYNTHETIC {i}'.encode())
        sha = file_sha256(path)
        tracks.append({'spotify_track_id': tid, 'title': f'Synthetic {i}', 'artists': ['Synthetic'],
                       'source_sha256': sha, 'retained_source_path': str(path.relative_to(tmp_path))})
        current[tid] = {'sha256': sha}
        freeze_json(path.parent / 'provenance.json', {'spotify_track_id': tid, 'source_sha256': sha,
                                                    'full_decode_validated': i != 19})
        if i <= 16:
            old.append({'spotify_track_id': tid, 'pilot_id': f'P{i}', 'neutral_id': f'N{i:03d}', 'prepared': {'source_sha256': sha}})
    freeze_json(tmp_path / CORPUS / 'source_manifest.json', {'track_count': 100, 'tracks': tracks})
    freeze_json(tmp_path / CORPUS / 'preparation_manifest.json', {'source_manifest.json': file_sha256(tmp_path / CORPUS / 'source_manifest.json')})
    freeze_json(tmp_path / '.research_audio/song_space/v3/audio-index.json', current)
    freeze_json(tmp_path / LIBRARY / 'source_quarantines.json', {'tracks': [{'spotify_track_id': f'{17:022d}'}]})
    freeze_json(tmp_path / LIBRARY / 'source_corrections.json', {'corrections': [{'spotify_track_id': f'{18:022d}'}]})
    result = inventory(tmp_path, {'tracks': old})
    assert len(result['tracks']) == 100 and len(result['blocked']) == 3
    assert [r['status'] for r in result['blocked']] == ['QUARANTINED_SOURCE',
        'CURRENT_SOURCE_DIFFERS_FROM_FROZEN_SOURCE_REQUIRES_EXPLICIT_VERSION_DECISION', 'INCOMPATIBLE_SOURCE_PROVENANCE']
    assert len({t['neutral_id'] for t in result['tracks']}) == 100
    path = tmp_path / tracks[19]['retained_source_path']
    path.write_bytes(b'REPLACED SOURCE')
    assert len(inventory(tmp_path, {'tracks': old})['blocked']) == 4
