"""Isolated fake-provider fixtures; no real audio, key, labels, or API requests."""
import base64
import copy
import json
from pathlib import Path

import httpx
import pytest

from audio_similarity.gemini_style_pilot.manifest import CONFIG, MODEL, PILOT_IDS, make_manifest
from audio_similarity.gemini_style_pilot.runner import PilotRunner, RunStopped
from audio_similarity.gemini_style_pilot.transport import GeminiTransport, TransportStopped
from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import freeze_json, hashes, read


FIXTURE = Path(__file__).parent / 'fixtures/gemini_style_pilot'


def fixture_run(root, *, blocked=False):
    run = root / 'research/isolated_fixture'
    model = run / 'contract/model'
    model.mkdir(parents=True)
    (model / 'prompt.txt').write_text('SYNTHETIC TEST ONLY. No real classifications.')
    (model / 'ontology.md').write_text('SYNTHETIC ONTOLOGY ONLY.')
    (model / 'response_schema.json').write_bytes((FIXTURE / 'response_schema.json').read_bytes())
    freeze_json(run / 'contract/style_allowed_families.json', read(FIXTURE / 'style_allowed_families.json'))
    tracks = []
    for i, pid in enumerate(PILOT_IDS, 1):
        path = run / 'prepared' / f'N{i:03d}.flac'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(f'SYNTHETIC BYTES {i}'.encode())
        sha = file_sha256(path)
        prepared = {'source_path': str(path), 'source_sha256': sha, 'prepared_filename': path.name,
                    'prepared_sha256': sha, 'duration_seconds': 150, 'full_recording_preserved': True,
                    'identity_metadata_removed': True}
        freeze_json(path.with_suffix('.json'), prepared)
        tracks.append({'pilot_id': pid, 'spotify_track_id': f'{i:022d}', 'neutral_id': f'N{i:03d}',
                       'eligible': not (blocked and pid == 'C04'), 'prepared': prepared})
    freeze_json(run / 'contract/private/candidates.json', [{k: t[k] for k in ['pilot_id', 'spotify_track_id']} for t in tracks])
    freeze_json(run / 'contract/input_hashes.json', hashes(list((run / 'contract').rglob('*')), run / 'contract'))
    freeze_json(run / 'source_checks/protected_hashes.json', {})
    freeze_json(run / 'source_checks/inventory.json', {'tracks': tracks})
    freeze_json(run / 'preflight/api_contract.json', {'requested_model': MODEL, 'generation_config': CONFIG,
                'rates_usd_per_million': {'input': '0.75', 'output_including_thinking': '3.75',
                                        'tier': 'standard', 'valid_through': '2026-12-31'}})
    freeze_json(run / 'preflight/model_access.json', {'model': {'name': f'models/{MODEL}',
                'inputTokenLimit': 1048576, 'outputTokenLimit': 65536}})
    return run


def uncertain_profile():
    return {'status': 'uncertain', 'primary_family': 'unknown', 'secondary_families': [],
            'primary_style': 'unknown', 'secondary_styles': [], 'vocal_role': 'unclear',
            'arrangement_focus': 'unclear', 'texture_tags': [], 'active_section_density': 'unclear',
            'section_variation': 'cannot_assess', 'certainty': {'family': 'unresolved', 'style': 'unresolved'},
            'audio_evidence': [], 'unmapped_styles': []}


class FakeProvider:
    def __init__(self, run, *, fault=None):
        self.run, self.fault, self.calls, self.generations, self.files = run, fault, [], 0, {}

    def factory(self):
        return GeminiTransport(self.run / 'execution/transport', 'TEST-KEY-NEVER-LOG',
            client=httpx.Client(transport=httpx.MockTransport(self.handle)), sleep=lambda _: None)

    def handle(self, request):
        self.calls.append((request.method, request.url.path))
        if request.url.path == '/upload/v1beta/files':
            neutral = json.loads(request.content)['file']['displayName']
            self.uploading = neutral
            return httpx.Response(200, headers={'x-goog-upload-url': 'https://generativelanguage.googleapis.com/upload/session'})
        if request.url.path == '/upload/session':
            neutral = self.uploading
            path = self.run / 'prepared' / f'{neutral}.flac'
            assert request.content == path.read_bytes()
            value = {'name': f'files/{neutral.lower()}', 'uri': f'https://generativelanguage.googleapis.com/v1beta/files/{neutral.lower()}',
                     'displayName': neutral, 'state': 'ACTIVE', 'mimeType': 'audio/flac',
                     'sizeBytes': str(path.stat().st_size), 'expirationTime': '2030-01-01T00:00:00Z',
                     'sha256Hash': base64.b64encode(bytes.fromhex(file_sha256(path))).decode()}
            if self.fault == 'upload_hash':
                value['sha256Hash'] = 'BAD'
            return httpx.Response(200, json={'file': value})
        body = json.loads(request.content)
        if request.url.path.endswith(':countTokens'):
            assert body['generateContentRequest']['model'] == f'models/{MODEL}'
            assert body['generateContentRequest']['generationConfig']['responseJsonSchema'] == read(FIXTURE / 'response_schema.json')
            if self.fault == 'count':
                return httpx.Response(200, json={})
            return httpx.Response(200, json={'totalTokens': 7000})
        assert request.url.path.endswith(':generateContent')
        self.generations += 1
        reservation = self.run / 'execution/attempts' / f'attempt-{self.generations:02d}.reservation.json'
        assert reservation.exists(), 'spend must be reserved before generation'
        assert read(reservation)['reserved_upper_cost_usd'] == '0.81715200'
        assert set(body) == {'systemInstruction', 'contents', 'generationConfig'}
        if self.fault == 'http':
            return httpx.Response(503, json={'error': 'synthetic unavailable'})
        if self.fault == 'connection':
            raise httpx.ConnectError('sensitive URL or key must never be logged')
        usage = {'promptTokenCount': 7000, 'candidatesTokenCount': 900, 'thoughtsTokenCount': 100,
                 'totalTokenCount': 8000, 'promptTokensDetails': [{'modality': 'AUDIO', 'tokenCount': 3900}],
                 'serviceTier': 'standard'}
        if self.fault == 'usage':
            del usage['totalTokenCount']
        if self.fault == 'audio':
            usage['promptTokensDetails'] = []
        if self.fault == 'tier':
            usage['serviceTier'] = 'priority'
        value = {'responseId': f'FAKE-RESPONSE-{self.generations}', 'modelVersion': 'FAKE-MODEL-VERSION',
                 'usageMetadata': usage, 'candidates': [{'finishReason': 'STOP',
                     'content': {'role': 'model', 'parts': [{'text': json.dumps(uncertain_profile())}]}}]}
        if self.fault == 'schema':
            value['candidates'][0]['content']['parts'][0]['text'] = '```json\n{}\n```'
        if self.fault == 'finish':
            value['candidates'][0]['finishReason'] = 'MAX_TOKENS'
        return httpx.Response(200, json=value)


def runner(root, fault=None):
    run = fixture_run(root)
    make_manifest(root, run, run / 'source_checks/inventory.json')
    provider = FakeProvider(run, fault=fault)
    return PilotRunner(root, run, transport_factory=provider.factory), provider


def test_source_gate_prevents_any_manifest_or_provider_call_and_rejects_substitution(tmp_path):
    run = fixture_run(tmp_path, blocked=True)
    with pytest.raises(ValueError, match='C04'):
        make_manifest(tmp_path, run, run / 'source_checks/inventory.json')
    assert not (run / 'execution_manifest.json').exists()
    with pytest.raises(ValueError, match='no frozen execution'):
        PilotRunner(tmp_path, run, transport_factory=lambda: pytest.fail('provider access'))
    inventory = read(run / 'source_checks/inventory.json')
    for t in inventory['tracks']:
        t['eligible'] = True
    inventory['tracks'][0]['spotify_track_id'] = 'CHANGED ID'
    path = run / 'source_checks/substituted.json'
    freeze_json(path, inventory)
    with pytest.raises(ValueError, match='substitutes'):
        make_manifest(tmp_path, run, path)


def test_all_twenty_attempts_smoke_order_uncertainty_cache_replay_and_no_primary_overwrite(tmp_path):
    value, provider = runner(tmp_path)
    assert value.next()['attempt'] == 1
    assert not (value.directory / 'smoke_gate.json').exists()
    assert value.next()['attempt'] == 2
    assert read(value.directory / 'smoke_gate.json')['semantic_agreement_checked'] is False
    for i in range(3, 17):
        assert value.next()['attempt'] == i
    primaries = hashes(list((value.directory / 'profiles').glob('*.json')), value.run)
    for i in range(17, 21):
        assert value.next()['repeat'] is True
    assert provider.generations == 20
    assert hashes(list((value.directory / 'profiles').glob('*.json')), value.run) == primaries
    before_calls = list(provider.calls)
    before = hashes(list(value.directory.rglob('*')), value.run)
    value.transport_factory = lambda: pytest.fail('cache replay created a transport')
    assert value.next() == {'status': 'ALL_ATTEMPTS_COMPLETE', 'new_generation_calls': 0}
    assert value.replay()['unique_profiles'] == 16
    assert value.freeze_profiles()['status'] == 'PROFILES_FROZEN_AWAITING_OWNER_REVIEW'
    assert value.freeze_profiles()['replay']['new_api_calls'] == 0
    assert hashes(list(value.directory.rglob('*')), value.run) == before
    assert provider.calls == before_calls
    for p in value.directory.rglob('*'):
        if p.is_file():
            assert b'TEST-KEY-NEVER-LOG' not in p.read_bytes()


@pytest.mark.parametrize('fault,paid', [('upload_hash', 0), ('count', 0), ('http', 1),
    ('connection', 1), ('usage', 1), ('tier', 1), ('audio', 1), ('schema', 1), ('finish', 1)])
def test_operational_failure_stops_without_hidden_retry_or_fake_profile(tmp_path, fault, paid):
    value, provider = runner(tmp_path, fault=fault)
    with pytest.raises((ValueError, KeyError)):
        value.next()
    assert provider.generations == paid
    before_calls = list(provider.calls)
    assert (value.directory / 'STOPPED.json').exists()
    assert not list(value.directory.glob('profiles/*.json'))
    with pytest.raises(RunStopped, match='previous operational failure'):
        value.next()
    assert provider.calls == before_calls
    if paid:
        assert (value.directory / 'attempts/attempt-01.reservation.json').exists()
        assert list(value.directory.glob('transport/*.response.bin'))


def test_interrupted_reservation_is_not_dispatched_again(tmp_path):
    value, provider = runner(tmp_path)
    value.ledger().reserve(counted_input=7000, max_output_tokens=8192, request_sha256='a'*64,
                           manifest_sha256=value.manifest_sha, neutral_id='N001')
    with pytest.raises(RunStopped, match='interrupted'):
        value.next()
    assert not provider.calls


def test_eligible_flag_cannot_override_an_unresolved_source_status(tmp_path):
    run = fixture_run(tmp_path)
    inventory = read(run / 'source_checks/inventory.json')
    inventory['tracks'][13]['source_status'] = 'BLOCKED_CATALOG_PROVIDER_ARTIST_DISCREPANCY'
    path = run / 'source_checks/still_blocked.json'
    freeze_json(path, inventory)
    with pytest.raises(ValueError, match='source identity unresolved: C04'):
        make_manifest(tmp_path, run, path)
    assert not (run / 'execution_manifest.json').exists()


def test_changed_audio_and_changed_cached_classification_fail_before_inference(tmp_path):
    value, provider = runner(tmp_path)
    value.next()
    result = read(value.result_path(1))
    changed = copy.deepcopy(result)
    changed['profile']['vocal_role'] = 'sung_led'
    for path in [value.result_path(1), value.directory / 'profiles' / f'{result["cache_key"]}.json']:
        path.write_text(json.dumps(changed))
    with pytest.raises(RunStopped, match='original provider response'):
        value.replay(require_complete=False)
    (value.run / 'prepared/N002.flac').write_bytes(b'CHANGED')
    with pytest.raises(ValueError, match='integrity mismatch'):
        value.next()
    assert provider.generations == 1


def test_no_upload_or_key_to_unexpected_provider_host(tmp_path):
    transport = GeminiTransport(tmp_path, 'TEST', client=httpx.Client(transport=httpx.MockTransport(
        lambda _: pytest.fail('unexpected external request'))))
    with pytest.raises(TransportStopped, match='unexpected provider host'):
        transport.request('POST', 'https://unrelated.example/upload', label='upload')


def test_live_provider_hex_digest_encoding_is_exact_and_wrong_hashes_still_fail():
    sha = 'ab' * 32
    value = {'state': 'ACTIVE', 'mimeType': 'audio/flac', 'displayName': 'N001', 'sizeBytes': '100',
             'uri': 'https://generativelanguage.googleapis.com/v1beta/files/example',
             'expirationTime': '2030-01-01T00:00:00Z'}
    for encoded in [base64.b64encode(bytes.fromhex(sha)).decode(), base64.b64encode(sha.encode()).decode()]:
        GeminiTransport._verify_file({**value, 'sha256Hash': encoded}, sha, 100, 'N001')
    for encoded in [base64.b64encode(('cd'*32).encode()).decode(), sha, 'not base64!']:
        with pytest.raises(TransportStopped):
            GeminiTransport._verify_file({**value, 'sha256Hash': encoded}, sha, 100, 'N001')
