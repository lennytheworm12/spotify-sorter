"""Resumable full-corpus requests through the unchanged free-genre transport."""
from datetime import date
from pathlib import Path
import json
import math

from .contracts import digest, file_hash, freeze_json, require
from .gemini_full_inputs import RUN, HistoricalReader, read
from .gemini_full_budget import FullLedger, global_lock, spending
from .gemini_full_manifest import validate_approval, verify_prepared, producer_hashes
from ..gemini_free_genre_runner import FreeGenreRunner
from ..gemini_style_pilot.transport import GeminiTransport, configured_key


def load_execution(root):
    run = root / RUN
    execution = read(run / 'execution_manifest.json')
    policy = read(run / 'global_policy.json')
    preflight = read(run / 'preflight.json')
    require(digest(policy) == execution['policy_sha256'], 'global policy changed')
    require(file_hash(run / 'preflight.json') == policy['preflight_sha256'], 'preflight changed')
    approval = read(run / 'upload_authorization.json')
    require(digest(approval) == policy['authorization_sha256'], 'upload authorization changed')
    cap = validate_approval(approval, preflight, policy['preflight_sha256'])
    require(str(cap) == policy['spend_cap_usd'], 'approved cap differs')
    require(policy['implementation_hashes'] == producer_hashes(root), 'execution implementation changed')
    require(file_hash(root / preflight['corpus_path']) == preflight['corpus_sha256'], 'frozen corpus changed')
    observed = []
    for batch in execution['batches']:
        require(file_hash(root / batch['path']) == batch['sha256'], 'batch execution changed')
        m = read(root / batch['path'])
        require(m['global_policy_sha256'] == digest(policy), 'batch uses different global policy')
        require(m['schedule'] == [{'pilot_id': t['pilot_id'], 'repeat': False} for t in m['tracks']],
                'batch schedule changed')
        observed.extend(t['recording_id'] for t in m['tracks'])
    require(observed == [t['recording_id'] for t in preflight['recordings'] if t['profile'] is None],
            'execution population differs from frozen missing profiles')
    return execution, policy, preflight


class FullRunner(FreeGenreRunner):
    def __init__(self, root, batch_path, policy, *, transport_factory=None):
        self.root, self.run = root.resolve(), batch_path.resolve()
        self.manifest = read(self.run / 'execution_manifest.json')
        self.manifest_sha = file_hash(self.run / 'execution_manifest.json')
        self.directory = self.run / 'execution'
        self.tracks = {t['pilot_id']: t for t in self.manifest['tracks']}
        self.prompt = (self.run / 'prompt.txt').read_text()
        self.policy = policy
        self.transport_factory = transport_factory
        verify_prepared(root, self.run, self.manifest, audio=False)

    def ledger(self):
        return FullLedger(self.directory / 'attempts', self.root / RUN,
                          self.policy, len(self.manifest['schedule']))

    def execute_remaining(self):
        """Caller holds the all-batches worker lock. Validate once, never retry."""
        require(not list((self.root / RUN).glob('batch_*/execution/STOPPED.json')),
                'prior failure requires explicit reviewed recovery')
        require(date.today() <= date.fromisoformat(self.policy['rates']['valid_through']), 'rates expired')
        index = 1
        while index <= len(self.manifest['schedule']) and self.result_path(index).exists():
            self.verified_result(index)
            index += 1
        require(len(list((self.directory / 'attempts').glob('*.reservation.json'))) == index - 1,
                'interrupted/unaccounted request; no automatic retry')
        require(len(list((self.directory / 'attempts').glob('*.result.json'))) == index - 1,
                'noncontiguous primary results')
        # Completed replay must not even initialize a transport or access a key.
        if index > len(self.manifest['schedule']):
            return 0
        transport = None
        calls = 0
        try:
            for slot in range(index, len(self.manifest['schedule']) + 1):
                if slot > 2:
                    require(read(self.directory / 'smoke_gate.json') == self.smoke_record(), 'smoke gate differs')
                t = self.tracks[self.manifest['schedule'][slot - 1]['pilot_id']]
                require(file_hash(self.root / t['source_path']) == t['source_sha256'], 'source changed before upload')
                require(file_hash(self.root / self.manifest['prepared_root'] / t['prepared']['prepared_filename'])
                        == t['prepared']['prepared_sha256'], 'prepared audio changed before upload')
                self.ledger().check_global()  # Do not upload when the next generation cannot be funded.
                if transport is None:
                    transport = (self.transport_factory() if self.transport_factory else
                        GeminiTransport(self.directory / 'transport', configured_key(self.root / '.env')))
                self._attempt(slot, transport)
                calls += 1
                if slot == 2:
                    freeze_json(self.directory / 'smoke_gate.json', self.smoke_record())
                print(json.dumps({'batch': self.manifest['batch'], 'validated': slot,
                    'batch_total': len(self.manifest['schedule']), **spending(self.root / RUN)}), flush=True)
        except Exception as exc:
            freeze_json(self.directory / 'STOPPED.json', {'exception_type': type(exc).__name__,
                'manifest_sha256': self.manifest_sha,
                'reason': 'Preserved operational/accounting/schema failure; no automatic retry or classification repair.'})
            raise
        finally:
            if transport:
                transport.close()
        return calls


def run_all(root):
    root = root.resolve()
    with global_lock(root / RUN, '.full-worker.lock'):
        execution, policy, _ = load_execution(root)
        calls = 0
        for batch in execution['batches']:
            runner = FullRunner(root, (root / batch['path']).parent, policy)
            calls += runner.execute_remaining()
        return {'status': 'ALL_GENERATIONS_COMPLETE', 'new_generation_calls_this_invocation': calls,
                **spending(root / RUN)}


def freeze_profiles(root):
    """Every raw response revalidates; missing/invalid is never an unknown genre."""
    root = root.resolve()
    execution, policy, preflight = load_execution(root)
    require(not list((root / RUN).glob('batch_*/execution/STOPPED.json')), 'operational failure prevents completion')
    state = spending(root / RUN)
    require(not state['unsettled'] and state['generation_attempts'] == execution['new_generations_planned'],
            'missing/unsettled generation attempts')
    profiles, provenance = {}, {}
    for t in preflight['recordings']:
        require(file_hash(root / t['source_path']) == t['audio_sha256'], 'retained source changed')
        if t['profile'] is None:
            continue
        for origin in t['reuse_origins']:
            old = HistoricalReader(root, Path(origin['run']))
            profile, reference = old.profile(origin['pilot_id'])
            require(reference == origin and profile == t['profile'], 'reused profile no longer verifies')
        receipt = t['prepared']
        require(file_hash(Path(receipt['conversion_command'][-1])) == receipt['prepared_sha256'],
                'reused prepared audio changed')
        profiles[t['recording_id']] = t['profile']
        provenance[t['recording_id']] = {'status': 'REUSED_VALIDATED', 'origins': t['reuse_origins'],
            'source_sha256': t['audio_sha256'], 'prepared_sha256': receipt['prepared_sha256']}
    replayed = 0
    transport_hashes = {}
    for batch in execution['batches']:
        runner = FullRunner(root, (root / batch['path']).parent, policy)
        verify_prepared(root, runner.run, runner.manifest, audio=True)
        for metadata_path in sorted((runner.directory / 'transport').glob('call-*.response.json')):
            metadata = read(metadata_path)
            raw_path = metadata_path.with_suffix('.bin')
            require(file_hash(raw_path) == metadata['response_sha256'], 'transport response bytes changed')
            require(math.isfinite(metadata['latency_seconds']) and metadata['latency_seconds'] >= 0,
                    'invalid transport latency receipt')
        for path in sorted((runner.directory / 'transport').glob('*')):
            if path.is_file():
                transport_hashes[str(path.relative_to(root))] = file_hash(path)
        for i, slot in enumerate(runner.manifest['schedule'], 1):
            result = runner.verified_result(i)
            track = runner.tracks[slot['pilot_id']]
            sid = track['recording_id']
            require(sid not in profiles, 'profile overlap or duplicate execution')
            profiles[sid] = result['profile']
            provenance[sid] = {'status': 'NEW_VALIDATED', 'source_sha256': track['source_sha256'],
                'prepared_sha256': track['prepared']['prepared_sha256'], 'cache_key': result['cache_key'],
                'response_id': result['response_id'], 'model_version': result['model_version'],
                'result_path': str(runner.result_path(i).relative_to(root)),
                'result_sha256': file_hash(runner.result_path(i)), 'manifest_sha256': runner.manifest_sha}
            replayed += 1
    require(set(profiles) == {t['recording_id'] for t in preflight['recordings']}, 'full corpus profile coverage required')
    value = {'schema': 'gemini-full-profiles-frozen-v1', 'execution_manifest_sha256': digest(execution),
        'preflight_sha256': policy['preflight_sha256'], 'profiles': profiles, 'provenance': provenance,
        'replay_new_api_calls': 0, 'replayed_new_profiles': replayed, 'usage': state,
        'transport_hashes': transport_hashes}
    freeze_json(root / RUN / 'profiles_frozen.json', value)
    return value
