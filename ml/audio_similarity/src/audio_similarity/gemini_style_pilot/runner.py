"""One immutable generation attempt at a time, behind the frozen source gate."""
from __future__ import annotations

import fcntl
from datetime import date
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import digest, freeze_json, hashes, read, verify_hashes
from .budget import AttemptLedger, BudgetStopped
from .inputs import ModelInput, profile_cache_key, request_body
from .manifest import load_manifest
from .responses import ResponseStopped, validate_response
from .transport import GeminiTransport, TransportStopped, configured_key
from .validation import InvalidProfile


class RunStopped(ValueError):
    pass


class PilotRunner:
    def __init__(self, root: Path, run: Path, *, transport_factory=None):
        self.root, self.run = root.resolve(), run.resolve()
        self.manifest = load_manifest(self.root, self.run)
        self.manifest_sha = file_sha256(self.run / 'execution_manifest.json')
        self.directory = self.run / 'execution'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.transport_factory = transport_factory
        self.tracks = {t['pilot_id']: t for t in self.manifest['tracks']}
        self.schema = read(self.run / 'contract/model/response_schema.json')
        self.allowed = read(self.run / 'contract/style_allowed_families.json')
        self.prompt = (self.run / 'contract/model/prompt.txt').read_text()
        self.ontology = (self.run / 'contract/model/ontology.md').read_text()

    def track_input(self, pilot_id: str) -> ModelInput:
        t = self.tracks[pilot_id]
        return ModelInput(t['neutral_id'], t['prepared']['duration_seconds'], t['prepared']['prepared_sha256'])

    def key(self, pilot_id: str) -> str:
        model = self.run / 'contract/model'
        return profile_cache_key(self.track_input(pilot_id), model_id=self.manifest['model_id'],
            generation_config=self.manifest['generation_config'],
            prompt_sha256=file_sha256(model / 'prompt.txt'), ontology_sha256=file_sha256(model / 'ontology.md'),
            schema_sha256=file_sha256(self.schema_path(pilot_id)),
            implementation_sha256=self.manifest['implementation_sha256'])

    def schema_path(self, pilot_id: str) -> Path:
        return self.run / self.manifest.get('response_schemas', {}).get(pilot_id, 'contract/model/response_schema.json')

    def schema_for(self, pilot_id: str) -> dict:
        return read(self.schema_path(pilot_id))

    def ledger(self) -> AttemptLedger:
        m = self.manifest
        return AttemptLedger(self.directory / 'attempts', input_limit=m['input_token_limit'],
            input_usd_per_million=m['rates']['input'], output_usd_per_million=m['rates']['output_including_thinking'],
            spend_cap_usd=m['spend_cap_usd'], max_attempts=m['max_attempts'])

    def result_path(self, index: int) -> Path:
        return self.directory / 'attempts' / f'attempt-{index:02d}.result.json'

    def verified_result(self, index: int) -> dict:
        result = read(self.result_path(index))
        slot = self.manifest['schedule'][index - 1]
        if (result['attempt'] != index or result['pilot_id'] != slot['pilot_id']
                or result['repeat'] != slot['repeat'] or result['manifest_sha256'] != self.manifest_sha
                or result['cache_key'] != self.key(slot['pilot_id'])):
            raise RunStopped('attempt result has incompatible provenance')
        verify_hashes(self.run, result['evidence_hashes'])
        if result['response_file'] not in result['evidence_hashes']:
            raise RunStopped('raw response missing from integrity evidence')
        parsed = validate_response(read(self.run / result['response_file']), schema=self.schema_for(slot['pilot_id']), allowed=self.allowed,
                                   duration=self.track_input(slot['pilot_id']).duration_seconds)
        if any(result[k] != v for k, v in parsed.items()):
            raise RunStopped('cached profile differs from original provider response')
        if not slot['repeat']:
            cached = read(self.directory / 'profiles' / f'{result["cache_key"]}.json')
            if cached != result:
                raise RunStopped('primary profile cache differs from original attempt')
        return result

    def next(self) -> dict:
        with (self.directory / '.runner.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Validate again after taking the run-wide lock, before any provider I/O.
            load_manifest(self.root, self.run)
            if (self.directory / 'STOPPED.json').exists():
                raise RunStopped('a previous operational failure requires inspection; no automatic retry')
            index = 1
            while index <= len(self.manifest['schedule']) and self.result_path(index).exists():
                self.verified_result(index)
                index += 1
            if index > len(self.manifest['schedule']):
                return {'status': 'ALL_ATTEMPTS_COMPLETE', 'new_generation_calls': 0}
            reservations = list((self.directory / 'attempts').glob('attempt-*.reservation.json'))
            if len(reservations) != index - 1:
                raise RunStopped('interrupted or unaccounted generation; inspect original ledger')
            if index > 2:
                gate = read(self.directory / 'smoke_gate.json')
                if gate != self.smoke_record():
                    raise RunStopped('engineering smoke gate does not verify')
            if date.today() > date.fromisoformat(self.manifest['rates']['valid_through']):
                raise RunStopped('verified prices expired; do not request generation')
            transport = None
            try:
                if self.transport_factory:
                    transport = self.transport_factory()
                else:
                    key = configured_key(self.root / '.env')
                    transport = GeminiTransport(self.directory / 'transport', key)
                result = self._attempt(index, transport)
                if index == 2:
                    freeze_json(self.directory / 'smoke_gate.json', self.smoke_record())
                return {'status': 'ATTEMPT_VALIDATED', 'attempt': index,
                        'neutral_id': result['neutral_id'], 'repeat': result['repeat'],
                        'new_generation_calls': 1, 'cost_usd': result['actual_cost_usd']}
            except Exception as exc:
                freeze_json(self.directory / 'STOPPED.json', {
                    'attempt_slot': index, 'exception_type': type(exc).__name__,
                    'reason': str(exc) if isinstance(exc, (RunStopped, BudgetStopped, InvalidProfile, TransportStopped, ResponseStopped)) else 'unexpected execution error; inspect preserved evidence',
                    'manifest_sha256': self.manifest_sha,
                })
                raise
            finally:
                if transport:
                    transport.close()

    def smoke_record(self) -> dict:
        results = [self.verified_result(i) for i in (1, 2)]
        return {'status': 'ENGINEERING_SMOKES_PASSED', 'attempts': [1, 2],
                'result_hashes': hashes([self.result_path(i) for i in (1, 2)], self.run),
                'checks': ['uploaded audio hash', 'positive input AUDIO tokens', 'response ID/model version',
                           'STOP finish', 'complete usage accounting', 'schema and semantic validation'],
                'semantic_agreement_checked': False,
                'model_versions': [r['model_version'] for r in results]}

    def _attempt(self, index: int, transport) -> dict:
        slot = self.manifest['schedule'][index - 1]
        pid, track = slot['pilot_id'], self.track_input(slot['pilot_id'])
        prepared_path = self.run / 'prepared' / self.tracks[pid]['prepared']['prepared_filename']
        uploaded = transport.upload(prepared_path, neutral_id=track.neutral_id,
                                    expected_sha256=track.prepared_sha256)
        body = request_body(track, file_uri=uploaded['uri'], prompt=self.prompt, ontology=self.ontology,
                            schema=self.schema_for(pid), generation_config=self.manifest['generation_config'])
        count, count_stem = transport.count_tokens(self.manifest['model_id'], body)
        ledger = self.ledger()
        reservation = ledger.reserve(counted_input=count.get('totalTokens'),
            max_output_tokens=self.manifest['generation_config']['maxOutputTokens'],
            request_sha256=digest(body), manifest_sha256=self.manifest_sha,
            neutral_id=track.neutral_id, repeat=slot['repeat'])
        if reservation['attempt'] != index:
            raise RunStopped('attempt sequence diverged')
        attempts = self.directory / 'attempts'
        request_path = attempts / f'attempt-{index:02d}.request.json'
        freeze_json(request_path, body)
        response, response_stem = transport.generate(self.manifest['model_id'], body)
        # Raw bytes are already durable in the transport ledger, including HTTP errors.
        if not response.is_success:
            raise RunStopped('generation HTTP failure; reservation remains unresolved')
        value = response.json()
        settlement = ledger.settle(index, value.get('usageMetadata', {}))
        parsed = validate_response(value, schema=self.schema_for(pid), allowed=self.allowed, duration=track.duration_seconds)
        evidence = [request_path, count_stem.with_suffix('.response.bin'), response_stem.with_suffix('.response.bin'),
                    response_stem.with_suffix('.response.json'), attempts / f'attempt-{index:02d}.reservation.json',
                    attempts / f'attempt-{index:02d}.settlement.json']
        result = {
            'attempt': index, 'pilot_id': pid, 'neutral_id': track.neutral_id, 'repeat': slot['repeat'],
            'cache_key': self.key(pid), 'manifest_sha256': self.manifest_sha,
            **parsed, 'actual_cost_usd': settlement['actual_cost_usd'],
            'response_file': str(response_stem.with_suffix('.response.bin').relative_to(self.run)),
            'evidence_hashes': hashes(evidence, self.run),
        }
        freeze_json(self.result_path(index), result)
        if not slot['repeat']:
            freeze_json(self.directory / 'profiles' / f'{result["cache_key"]}.json', result)
        return result

    def replay(self, *, require_complete=True) -> dict:
        """Read/validate only. Never constructs a transport client or touches the key."""
        expected = len(self.manifest['schedule'])
        results = [self.verified_result(i) for i in range(1, expected + 1) if self.result_path(i).exists()]
        if require_complete and len(results) != expected:
            raise RunStopped('full replay requires the complete frozen primary and repeat schedule')
        if (self.run / 'profiles_frozen.json').exists():
            verify_hashes(self.run, read(self.run / 'profiles_frozen.json')['files'])
        return {'status': 'CACHE_REPLAY_VERIFIED', 'validated_attempts': len(results),
                'unique_profiles': sum(not r['repeat'] for r in results), 'new_api_calls': 0}

    def freeze_profiles(self) -> dict:
        replay = self.replay()
        if (self.directory / 'STOPPED.json').exists():
            raise RunStopped('cannot freeze a successful run after an operational failure')
        result = {'status': 'PROFILES_FROZEN_AWAITING_OWNER_REVIEW', 'manifest_sha256': self.manifest_sha,
                  'replay': replay, 'files': hashes([p for p in self.directory.rglob('*') if p.is_file()
                                                   and p.name != '.runner.lock'], self.run)}
        freeze_json(self.run / 'profiles_frozen.json', result)
        return result
