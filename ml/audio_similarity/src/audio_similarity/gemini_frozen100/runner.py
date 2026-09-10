"""Bounded corpus continuation; exact prior profiles retain their producer identity."""
from __future__ import annotations

import fcntl
from datetime import date
from decimal import Decimal
from pathlib import Path

from audio_similarity.gemini_free_genre_runner import FreeGenreRunner, parse_response
from audio_similarity.gemini_style_pilot.budget import AttemptLedger, BudgetStopped, nonnegative_int
from audio_similarity.gemini_style_pilot.manifest import CONFIG, MODEL, environment
from audio_similarity.gemini_style_pilot.runner import RunStopped
from audio_similarity.gemini_style_pilot.transport import GeminiTransport, configured_key
from audio_similarity.gemini_style_pilot.validation import InvalidProfile
from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import digest, freeze_json, hashes, read, verify_hashes


class CorpusLedger(AttemptLedger):
    """Same audited reservation/settlement operations, separately frozen 84-call policy."""

    def __init__(self, directory, *, prior_spend, spend_cap, max_attempts=84):
        self.directory = Path(directory)
        self.input_limit = 1048576
        self.input_rate = Decimal('.75') / 1_000_000
        self.output_rate = Decimal('3.75') / 1_000_000
        self.cap = Decimal(spend_cap)
        prior = Decimal(prior_spend)
        self.max_attempts = nonnegative_int(max_attempts)
        if (not all(v.is_finite() for v in (self.cap, prior)) or prior < 0 or self.cap <= 0
                or self.cap + prior != 2 or not 1 <= self.max_attempts <= 84):
            raise BudgetStopped('invalid frozen-100 allowance or combined spend cap')
        freeze_json(self.directory / 'policy.json', {
            'input_limit': self.input_limit, 'input_rate': str(self.input_rate),
            'output_rate': str(self.output_rate), 'cap_usd': str(self.cap),
            'prior_settled_usd': str(prior), 'combined_cap_usd': '2',
            'max_attempts': self.max_attempts})


class Frozen100Runner(FreeGenreRunner):
    def __init__(self, root, run, *, transport_factory=None):
        self.root, self.run = Path(root).resolve(), Path(run).resolve()
        self.manifest = read(self.run / 'execution_manifest.json')
        self.manifest_sha = file_sha256(self.run / 'execution_manifest.json')
        self.directory = self.run / 'execution'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.tracks = {t['pilot_id']: t for t in self.manifest['tracks']}
        self.transport_factory = transport_factory
        self.prompt = (self.run / 'prompt.txt').read_text()
        self.verify_contract(full=True)
        self.cached = self.verify_prior_cache()

    def verify_contract(self, *, full=False):
        m = self.manifest
        new = [t['pilot_id'] for t in m['tracks'] if not t['cached_profile']]
        cached = {t['pilot_id']: t['cached_profile'] for t in m['tracks'] if t['cached_profile']}
        if (m['schema_version'] != 'gemini-frozen100-v1' or len(self.tracks) != 100
                or len({t['spotify_track_id'] for t in m['tracks']}) != 100
                or len({t['neutral_id'] for t in m['tracks']}) != 100
                or len(new) != 84 or len(cached) != 16 or m['cached_profiles'] != cached
                or m['schedule'] != [{'pilot_id': p, 'repeat': False} for p in new]
                or m['model_id'] != MODEL or m['generation_config'] != CONFIG
                or m['max_attempts'] != 84 or m['prior_attempts'] != 38 or m['combined_attempt_cap'] != 122
                or Decimal(m['spend_cap_usd']) + Decimal(m['prior_settled_usd']) != 2
                or m['rates']['input'] != '0.75' or m['rates']['output_including_thinking'] != '3.75'
                or m['input_token_limit'] != 1048576 or m['environment'] != environment()
                or m['implementation_sha256'] != digest(m['implementation_hashes'])
                or m['ontology'] is not None or m['genre_examples'] is not None or m['genre_definitions'] is not None
                or any(not t['eligible'] for t in m['tracks'])):
            raise RunStopped('incompatible frozen-100 execution contract')
        if file_sha256(self.run / 'execution_manifest.json') != self.manifest_sha:
            raise RunStopped('execution manifest changed')
        verify_hashes(self.root, m['implementation_hashes'])
        verify_hashes(self.root, m['input_hashes'] if full else m['critical_input_hashes'])
        if full:
            verify_hashes(self.root, m['protected_hashes'])

    def verify_prior_cache(self):
        producers, results = {}, {}
        for pid, ref in self.manifest['cached_profiles'].items():
            if ref['source_run'] not in producers:
                producers[ref['source_run']] = FreeGenreRunner(self.root, self.root / ref['source_run'])
            producer = producers[ref['source_run']]
            old = producer.tracks[ref['source_pilot_id']]
            track = self.tracks[pid]
            result = producer.verified_result(ref['source_attempt'])
            if (producer.manifest_sha != ref['source_manifest_sha256']
                    or file_sha256(producer.result_path(ref['source_attempt'])) != ref['result_sha256']
                    or result['cache_key'] != ref['cache_key'] or result['pilot_id'] != ref['source_pilot_id']
                    or old['spotify_track_id'] != track['spotify_track_id']
                    or old['prepared']['source_sha256'] != track['source_sha256']
                    or producer.track_input(ref['source_pilot_id']) != self.track_input(pid)
                    or producer.prompt != self.prompt or producer.schema_for(ref['source_pilot_id']) != self.schema_for(pid)
                    or any(producer.manifest[k] != self.manifest[k] for k in ('model_id', 'generation_config', 'environment'))):
                raise RunStopped('prior cached request is not exactly compatible')
            results[pid] = result
        return results

    def ledger(self):
        return CorpusLedger(self.directory / 'attempts', prior_spend=self.manifest['prior_settled_usd'],
                            spend_cap=self.manifest['spend_cap_usd'], max_attempts=self.manifest['max_attempts'])

    def failure_path(self, index):
        return self.result_path(index).with_name(f'attempt-{index:02d}.failure.json')

    def record_profile_failure(self, index, exc):
        """Only an accounted response with a valid provider envelope may be skipped."""
        settlement = read(self.directory / 'attempts' / f'attempt-{index:02d}.settlement.json')
        requests = sorted(p for p in (self.directory / 'transport').glob('call-*.request.json')
                          if read(p)['label'] == 'generateContent')
        stem = requests[-1].with_name(requests[-1].name.removesuffix('.request.json'))
        response = stem.with_suffix('.response.bin')
        slot = self.manifest['schedule'][index - 1]
        # Reproduce the exact validation failure without editing its classification.
        try:
            parse_response(read(response), self.schema_for(slot['pilot_id']), self.track_input(slot['pilot_id']).duration_seconds)
        except InvalidProfile:
            pass
        else:
            raise RunStopped('schema failure did not reproduce')
        files = list((self.directory / 'attempts').glob(f'attempt-{index:02d}.*')) + list(stem.parent.glob(stem.name + '.*'))
        value = {'status': 'INVALID_PROFILE', 'attempt': index, 'pilot_id': slot['pilot_id'],
                 'manifest_sha256': self.manifest_sha, 'profile': None, 'exception_type': type(exc).__name__,
                 'reason': str(exc), 'actual_cost_usd': settlement['actual_cost_usd'],
                 'response_file': str(response.relative_to(self.run)), 'evidence_hashes': hashes(files, self.run)}
        freeze_json(self.failure_path(index), value)
        return value

    def verified_failure(self, index):
        value = read(self.failure_path(index))
        pid = self.manifest['schedule'][index - 1]['pilot_id']
        if (value['attempt'] != index or value['pilot_id'] != pid or value['profile'] is not None
                or value['manifest_sha256'] != self.manifest_sha or value['status'] != 'INVALID_PROFILE'):
            raise RunStopped('incompatible failure record')
        verify_hashes(self.run, value['evidence_hashes'])
        if value['response_file'] not in value['evidence_hashes']:
            raise RunStopped('failure missing raw evidence')
        try:
            parse_response(read(self.run / value['response_file']), self.schema_for(pid), self.track_input(pid).duration_seconds)
        except InvalidProfile:
            return value
        raise RunStopped('cached failure differs from provider response')

    def next(self):
        with (self.directory / '.runner.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.verify_contract()
            if (self.directory / 'STOPPED.json').exists():
                raise RunStopped('previous operational failure; no automatic retry')
            index = 1
            while index <= 84:
                if self.result_path(index).exists():
                    self.verified_result(index)
                elif self.failure_path(index).exists():
                    self.verified_failure(index)
                else:
                    break
                index += 1
            if index > 84:
                return {'status': 'ALL_ATTEMPTS_COMPLETE', 'new_generation_calls': 0}
            if len(list((self.directory / 'attempts').glob('*.reservation.json'))) != index - 1:
                raise RunStopped('interrupted or unaccounted generation')
            if index > 2 and read(self.directory / 'smoke_gate.json') != self.smoke_record():
                raise RunStopped('engineering smokes do not verify')
            if date.today() > date.fromisoformat(self.manifest['rates']['valid_through']):
                raise RunStopped('verified rates expired')
            transport = None
            try:
                transport = self.transport_factory() if self.transport_factory else GeminiTransport(
                    self.directory / 'transport', configured_key(self.root / '.env'))
                try:
                    result = self._attempt(index, transport)
                    if index == 2:
                        freeze_json(self.directory / 'smoke_gate.json', self.smoke_record())
                    status = 'ATTEMPT_VALIDATED'
                except InvalidProfile as exc:
                    result = self.record_profile_failure(index, exc)
                    if index <= 2:
                        raise RunStopped('engineering smoke profile failed') from exc
                    status = 'INVALID_PROFILE_NO_RETRY'
                return {'status': status, 'attempt': index, 'new_generation_calls': 1,
                        'neutral_id': self.tracks[result['pilot_id']]['neutral_id'], 'cost_usd': result['actual_cost_usd']}
            except Exception as exc:
                freeze_json(self.directory / 'STOPPED.json', {'attempt_slot': index,
                    'exception_type': type(exc).__name__, 'manifest_sha256': self.manifest_sha,
                    'reason': 'Operational failure; inspect preserved evidence. No automatic retry.'})
                raise
            finally:
                if transport:
                    transport.close()

    def replay(self, *, require_complete=True):
        self.verify_contract(full=True)
        self.cached = self.verify_prior_cache()
        valid, invalid = [], []
        for i in range(1, 85):
            if self.result_path(i).exists() and self.failure_path(i).exists():
                raise RunStopped('conflicting attempt outcomes')
            if self.result_path(i).exists():
                valid.append(self.verified_result(i))
            elif self.failure_path(i).exists():
                invalid.append(self.verified_failure(i))
        if require_complete and len(valid) + len(invalid) != 84:
            raise RunStopped('full replay requires all 84 scheduled attempts')
        for result in valid + invalid:
            i = result['attempt']
            usage = read(self.directory / 'attempts' / f'attempt-{i:02d}.settlement.json')['usage']
            settled = self.ledger().settle(i, usage)
            if settled['actual_cost_usd'] != result['actual_cost_usd']:
                raise RunStopped('cost does not reconcile')
        if (self.run / 'profiles_frozen.json').exists():
            verify_hashes(self.run, read(self.run / 'profiles_frozen.json')['files'])
        return {'status': 'CACHE_REPLAY_VERIFIED', 'cached_prior_profiles': len(self.cached),
                'new_validated_profiles': len(valid), 'invalid_profiles': len(invalid),
                'unique_profiles': len(self.cached) + len(valid), 'new_api_calls': 0}

    def freeze_profiles(self):
        replay = self.replay()
        if (self.directory / 'STOPPED.json').exists():
            raise RunStopped('run stopped; cannot claim completed profile collection')
        result = {'status': 'PROFILES_FROZEN_AWAITING_OWNER_REVIEW', 'manifest_sha256': self.manifest_sha,
                  'replay': replay, 'files': hashes([p for p in self.directory.rglob('*') if p.is_file()
                                                   and p.name not in ('.runner.lock', '.lock')], self.run)}
        freeze_json(self.run / 'profiles_frozen.json', result)
        return result
