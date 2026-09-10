"""Synthetic provider only: open genre labels, unchanged safety/accounting contracts."""
import json
from decimal import Decimal

import httpx
import pytest

from audio_similarity.gemini_free_genre import PROMPT, free_schema, prepare, validate_free_profile
from audio_similarity.gemini_free_genre_runner import FreeGenreRunner
from audio_similarity.gemini_style_pilot.duration_revision import bounded_schema
from audio_similarity.gemini_style_pilot.manifest import PRIMARY_ORDER, make_manifest
from audio_similarity.gemini_style_pilot.runner import PilotRunner, RunStopped
from audio_similarity.stage5e3_artifacts import digest, freeze_json, hashes, read
from tests.test_gemini_style_runner import FIXTURE, FakeProvider, fixture_run, uncertain_profile


def profile():
    p = uncertain_profile()
    p.pop('unmapped_styles')
    return p


class FreeProvider(FakeProvider):
    def handle(self, request):
        if request.url.path.endswith(':countTokens'):
            self.calls.append((request.method, request.url.path))
            body = json.loads(request.content)['generateContentRequest']
            assert body['systemInstruction'] == {'parts': [{'text': PROMPT}]}
            assert body['generationConfig']['responseJsonSchema'] == bounded_schema(free_schema(read(FIXTURE / 'response_schema.json')), 150)
            assert len(body['contents'][0]['parts']) == 2
            assert not any(word in json.dumps(body).casefold() for word in ['hyperpop', 'digicore', 'boom_bap', 'weeknd', 'keshi'])
            return httpx.Response(200, json={} if self.fault == 'count' else {'totalTokens': 7000})
        response = super().handle(request)
        if request.url.path.endswith(':generateContent') and response.is_success and self.fault != 'schema':
            value = response.json()
            value['candidates'][0]['content']['parts'][0]['text'] = json.dumps(profile())
            return httpx.Response(response.status_code, json=value)
        return response


def fixture(tmp_path, fault=None):
    run = fixture_run(tmp_path)
    m = make_manifest(tmp_path, run, run / 'source_checks/inventory.json')
    (run / 'execution_manifest.json').unlink()  # Isolated fake fixture, never real history.
    (run / 'prompt.txt').write_text(PROMPT)
    base = free_schema(read(FIXTURE / 'response_schema.json'))
    schemas = {}
    for t in m['tracks']:
        schemas[t['pilot_id']] = f'schemas/{t["neutral_id"]}.json'
        freeze_json(run / schemas[t['pilot_id']], bounded_schema(base, 150))
    m.update(schema_version='gemini-free-genre-v1', max_attempts=18, prior_attempts=20,
             combined_attempt_cap=38, combined_spend_cap_usd='2', prior_settled_usd='0.14680800',
             spend_cap_usd='1.85319200', ontology=None, reusable_uploads={},
             response_schemas=schemas, prepared_root=str((run / 'prepared').relative_to(tmp_path)),
             implementation_hashes={}, implementation_sha256=digest({}),
             schedule=[{'pilot_id': p, 'repeat': False} for p in PRIMARY_ORDER]
                       + [{'pilot_id': p, 'repeat': True} for p in ['A01', 'A03']])
    m['input_hashes'].update(hashes([run / 'prompt.txt', *[run / p for p in schemas.values()]], tmp_path))
    freeze_json(run / 'execution_manifest.json', m)
    provider = FreeProvider(run, fault=fault)
    return FreeGenreRunner(tmp_path, run, transport_factory=provider.factory), provider


def test_free_genres_have_no_mapping_and_preserve_output_verbatim():
    schema = bounded_schema(free_schema(read(FIXTURE / 'response_schema.json')), 150)
    p = profile()
    p.update(status='classified', primary_family='An unrestricted musical family',
             primary_style='An unfamiliar style label', secondary_styles=['another free style'])
    assert validate_free_profile(json.dumps(p), schema=schema, duration=150) == p
    assert 'enum' not in schema['properties']['primary_style']
    assert 'enum' not in schema['properties']['secondary_families']['items']
    assert 'hyperpop' not in PROMPT.casefold()


@pytest.mark.parametrize('fault', ['duplicate', 'empty_label', 'long_label', 'timestamp', 'nan', 'extra_field', 'not_music'])
def test_invalid_free_profiles_are_never_repaired(fault):
    p = profile()
    if fault == 'duplicate': p['secondary_styles'] = [' Space pop ', 'space POP']
    if fault == 'empty_label': p['primary_style'] = '  '
    if fault == 'long_label': p['primary_style'] = 'a' * 121
    if fault in ('timestamp', 'nan'):
        p['audio_evidence'] = [{'start_seconds': 0, 'end_seconds': 151 if fault == 'timestamp' else float('nan'), 'observation': 'Synthetic'}]
    if fault == 'extra_field': p['made_up'] = 1
    if fault == 'not_music': p.update(status='not_music', primary_style='some style')
    with pytest.raises(ValueError):
        validate_free_profile(json.dumps(p), schema=bounded_schema(free_schema(read(FIXTURE / 'response_schema.json')), 150), duration=150)


def test_eighteen_calls_then_replay_without_provider_or_primary_overwrite(tmp_path):
    runner, provider = fixture(tmp_path)
    assert runner.next()['attempt'] == 1
    assert not (runner.directory / 'smoke_gate.json').exists()
    assert runner.next()['attempt'] == 2
    assert read(runner.directory / 'smoke_gate.json')['semantic_agreement_checked'] is False
    for i in range(3, 17): assert runner.next()['attempt'] == i
    primary_hashes = hashes(list((runner.directory / 'profiles').glob('*')), runner.run)
    assert runner.next()['repeat'] is True
    assert runner.next()['repeat'] is True
    assert provider.generations == 18
    assert primary_hashes == hashes(list((runner.directory / 'profiles').glob('*')), runner.run)
    before = hashes(list(runner.directory.rglob('*')), runner.run)
    runner.transport_factory = lambda: pytest.fail('cache replay constructed a provider')
    assert runner.next()['new_generation_calls'] == 0
    assert runner.replay() == {'status': 'CACHE_REPLAY_VERIFIED', 'validated_attempts': 18, 'unique_profiles': 16, 'new_api_calls': 0}
    runner.freeze_profiles()
    assert hashes(list(runner.directory.rglob('*')), runner.run) == before
    assert read(runner.directory / 'attempts/policy.json')['cap_usd'] == '1.85319200'
    assert all(b'TEST-KEY-NEVER-LOG' not in p.read_bytes() for p in runner.directory.rglob('*') if p.is_file())


@pytest.mark.parametrize('fault,paid', [('upload_hash', 0), ('count', 0), ('http', 1),
    ('connection', 1), ('usage', 1), ('tier', 1), ('audio', 1), ('schema', 1), ('finish', 1)])
def test_failed_attempt_stops_without_automatic_retry(tmp_path, fault, paid):
    runner, provider = fixture(tmp_path, fault)
    with pytest.raises(ValueError): runner.next()
    assert provider.generations == paid
    before = list(provider.calls)
    with pytest.raises(RunStopped, match='previous operational failure'): runner.next()
    assert provider.calls == before
    assert not list(runner.directory.glob('profiles/*.json'))


def test_interruption_cannot_dispatch_again_and_tampered_input_blocks_access(tmp_path):
    runner, provider = fixture(tmp_path)
    runner.ledger().reserve(counted_input=7000, max_output_tokens=8192, request_sha256='a'*64,
        manifest_sha256=runner.manifest_sha, neutral_id='N001')
    with pytest.raises(RunStopped, match='interrupted'): runner.next()
    assert not provider.calls
    (runner.run / 'prompt.txt').write_text('changed prompt')
    with pytest.raises(ValueError, match='integrity mismatch'): runner.next()
    assert not provider.calls


def test_cache_key_changes_with_free_prompt_config_audio_and_implementation(tmp_path):
    runner, _ = fixture(tmp_path)
    original = runner.key('A01')
    for field, value in [('implementation_sha256', 'c'*64), ('model_id', 'changed-model')]:
        before = runner.manifest[field]
        runner.manifest[field] = value
        assert runner.key('A01') != original
        runner.manifest[field] = before
    runner.tracks['A01']['prepared']['prepared_sha256'] = 'd'*64
    assert runner.key('A01') != original


def test_prepare_accounts_for_prior_paid_calls_and_preserves_prior_artifacts(tmp_path, monkeypatch):
    prior = fixture_run(tmp_path)
    make_manifest(tmp_path, prior, prior / 'source_checks/inventory.json')
    provider = FakeProvider(prior)
    original = PilotRunner(tmp_path, prior, transport_factory=provider.factory)
    for _ in range(20): original.next()
    original.freeze_profiles()
    report = tmp_path / 'original_public_report'
    ledger = []
    for index in range(1, 21):
        result = original.verified_result(index)
        freeze_json(report / 'attempts' / f'call-{index:02d}.raw_response.json', read(prior / result['response_file']))
        ledger.append({'global_attempt': index, 'settled_standard_rate_usd': result['actual_cost_usd']})
    freeze_json(report / 'usage_ledger.json', ledger)
    freeze_json(report / 'artifact_manifest.json', {'files': hashes(list(report.rglob('*')), report)})
    before = hashes(list(prior.rglob('*')) + list(report.rglob('*')), tmp_path)
    approval = tmp_path / 'approval.json'
    freeze_json(approval, {'owner_message': 'try again but let gemini auto derive the genres'})
    monkeypatch.setattr('audio_similarity.gemini_free_genre.implementation_files', lambda: [])
    m = prepare(tmp_path, prior, tmp_path / 'new_arm', report, approval)
    assert Decimal(m['prior_settled_usd']) == Decimal('0.18')
    assert Decimal(m['spend_cap_usd']) == Decimal('1.82')
    assert m['ontology'] is None and m['max_attempts'] == 18
    assert hashes(list(prior.rglob('*')) + list(report.rglob('*')), tmp_path) == before
    runner = FreeGenreRunner(tmp_path, tmp_path / 'new_arm', transport_factory=lambda: pytest.fail('provider'))
    assert len(runner.reuse_uploads()['reused_uploads']) == 16
    assert runner.replay(require_complete=False)['new_api_calls'] == 0
