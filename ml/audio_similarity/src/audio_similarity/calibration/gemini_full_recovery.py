"""Explicit one-failure continuation; original execution evidence stays immutable."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import json

from .contracts import digest, file_hash, freeze_json, require
from .gemini_full_inputs import RUN, HistoricalReader, read
from .gemini_full_runner import FullRunner, load_execution
from .gemini_full_budget import FullLedger, global_lock, spending
from ..gemini_style_pilot.transport import GeminiTransport, configured_key

RECOVERY = RUN / 'recovery_01'


def historical_files(run):
    return {str(p.relative_to(run)): file_hash(p) for p in sorted(run.glob('batch_*/**/*'))
            if p.is_file() and p.suffix in ('.json', '.bin', '.txt')}


def prepare(root):
    root = root.resolve()
    execution, policy, _ = load_execution(root)
    prior = root / RUN
    state = spending(prior)
    expected = 'batch_0001/execution/attempts/attempt-540.reservation.json'
    require(state['generation_attempts'] == 540 and state['settled_attempts'] == 539
            and state['unsettled'] == [expected], 'recovery scope differs')
    failure = read(prior / 'batch_0001/execution/transport/call-2160.response.json')
    require(failure['http_status'] == 503 and failure['response_sha256'] == file_hash(
        prior / 'batch_0001/execution/transport/call-2160.response.bin'), 'expected 503 evidence differs')
    reserve = Decimal(read(prior / expected)['reserved_upper_cost_usd'])
    inherited = Decimal(state['actual_cost_usd']) + reserve
    out = root / RECOVERY
    approval = {'owner_message': 'ok retry until we encounter multiple of these requests',
        'approved': True, 'interpretation': 'One explicit recovery; another failure stops all work.',
        'total_spend_cap_usd': policy['spend_cap_usd'], 'prior_unresolved_reservation': expected,
        'prior_unresolved_upper_cost_usd': str(reserve), 'prior_settled_usd': state['actual_cost_usd'],
        'inherited_accounting_upper_bound_usd': str(inherited), 'original_execution_sha256': digest(execution)}
    freeze_json(out / 'authorization.json', approval)
    new_policy = policy | {'spend_cap_usd': str(Decimal(policy['spend_cap_usd']) - inherited),
        'max_attempts': 1101, 'authorization_sha256': digest(approval)}
    freeze_json(out / 'global_policy.json', new_policy)
    batches = []
    for b in execution['batches']:
        original = root / b['path']
        runner = FullRunner(root, original.parent, policy)
        completed = 0
        while runner.result_path(completed + 1).exists():
            runner.verified_result(completed + 1)
            completed += 1
        directory = out / original.parent.name
        manifest = runner.manifest | {'schedule': runner.manifest['schedule'][completed:],
            'recovery_parent_manifest_sha256': runner.manifest_sha,
            'recovery_authorization_sha256': digest(approval), 'max_attempts': len(runner.manifest['schedule']) - completed}
        for name in ['prompt.txt', 'response_schema.json'] + sorted(set(manifest['response_schemas'].values())):
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            data = (original.parent / name).read_bytes()
            if path.exists():
                require(path.read_bytes() == data, 'recovery schema/prompt changed')
            else:
                path.write_bytes(data)
        freeze_json(directory / 'execution_manifest.json', manifest)
        batches.append({'path': str(directory.relative_to(root)), 'sha256': digest(manifest),
                        'original_completed': completed})
    require(sum(len(read(root / b['path'] / 'execution_manifest.json')['schedule']) for b in batches) == 1101,
            'remaining population differs')
    receipt = {'schema': 'gemini-full-recovery-v1', 'batches': batches,
        'policy_sha256': digest(new_policy), 'authorization_sha256': digest(approval),
        'implementation_sha256': file_hash(Path(__file__)), 'original_files': historical_files(prior)}
    freeze_json(out / 'manifest.json', receipt)
    return {'status': 'RECOVERY_FROZEN', 'remaining': 1101, 'additional_503_allowance': 0,
            'remaining_budget_usd': new_policy['spend_cap_usd']}


def load(root):
    load_execution(root)
    out = root / RECOVERY
    m, p, a = (read(out / name) for name in ('manifest.json', 'global_policy.json', 'authorization.json'))
    require(file_hash(Path(__file__)) == m['implementation_sha256'], 'recovery implementation changed')
    require(digest(p) == m['policy_sha256'] and digest(a) == m['authorization_sha256'], 'recovery policy changed')
    require(historical_files(root / RUN) == m['original_files'], 'original execution changed')
    for b in m['batches']:
        require(file_hash(root / b['path'] / 'execution_manifest.json') == b['sha256'], 'recovery batch changed')
    return m, p, a


class RecoveryRunner(FullRunner):
    def __init__(self, root, batch, policy):
        original = root / RUN / Path(batch['path']).name
        super().__init__(root, original, policy)
        self.run = root / batch['path']
        self.directory = self.run / 'execution'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.manifest = read(self.run / 'execution_manifest.json')
        self.manifest_sha = file_hash(self.run / 'execution_manifest.json')

    def ledger(self):
        return FullLedger(self.directory / 'attempts', self.root / RECOVERY,
                          self.policy, len(self.manifest['schedule']))

    def execute_remaining(self):
        require(not list((self.root / RECOVERY).glob('batch_*/execution/STOPPED.json')), 'recovery already stopped')
        require(date.today() <= date.fromisoformat(self.policy['rates']['valid_through']), 'rates expired')
        index = 1
        while self.result_path(index).exists():
            self.verified_result(index)
            index += 1
        require(len(list((self.directory / 'attempts').glob('*.reservation.json'))) == index - 1,
                'unresolved recovery attempt; stop')
        transport = None
        try:
            for slot in range(index, len(self.manifest['schedule']) + 1):
                t = self.tracks[self.manifest['schedule'][slot - 1]['pilot_id']]
                require(file_hash(self.root / t['source_path']) == t['source_sha256'], 'source changed')
                require(file_hash(self.root / self.manifest['prepared_root'] / t['prepared']['prepared_filename'])
                        == t['prepared']['prepared_sha256'], 'prepared audio changed')
                self.ledger().check_global()
                if transport is None:
                    transport = GeminiTransport(self.directory / 'transport', configured_key(self.root / '.env'))
                self._attempt(slot, transport)
                print(json.dumps({'recovery_batch': self.manifest['batch'], 'validated': slot,
                                  **spending(self.root / RECOVERY)}), flush=True)
        except Exception as exc:
            freeze_json(self.directory / 'STOPPED.json', {'exception_type': type(exc).__name__,
                'reason': 'Another failure after explicit recovery; stop without automatic retry.'})
            raise
        finally:
            if transport:
                transport.close()


def run(root):
    root = root.resolve()
    with global_lock(root / RUN, '.full-worker.lock'):
        m, policy, _ = load(root)
        for batch in m['batches']:
            RecoveryRunner(root, batch, policy).execute_remaining()
    return {'status': 'RECOVERY_GENERATIONS_COMPLETE', **spending(root / RECOVERY)}


if __name__ == '__main__':
    import sys
    action = {'prepare': prepare, 'run': run}[sys.argv[1]]
    print(json.dumps(action(Path.cwd()), indent=2))


def freeze_profiles(root):
    """Merge verified original and recovery results without rewriting either ledger."""
    root = root.resolve()
    if not (root / RECOVERY / 'manifest.json').exists():
        from .gemini_full_runner import freeze_profiles as original_freeze
        return original_freeze(root)
    import math
    m, policy, approval = load(root)
    execution, original_policy, preflight = load_execution(root)
    require(not list((root / RECOVERY).glob('batch_*/execution/STOPPED.json')), 'recovery failure prevents freeze')
    state = spending(root / RECOVERY)
    require(not state['unsettled'] and state['generation_attempts'] == 1101, 'recovery incomplete')
    profiles, provenance, transport_hashes = {}, {}, {}
    for t in preflight['recordings']:
        require(file_hash(root / t['source_path']) == t['audio_sha256'], 'source changed')
        if t['profile'] is not None:
            for origin in t['reuse_origins']:
                profile, reference = HistoricalReader(root, Path(origin['run'])).profile(origin['pilot_id'])
                require(reference == origin and profile == t['profile'], 'historical profile changed')
            require(file_hash(Path(t['prepared']['conversion_command'][-1])) == t['prepared']['prepared_sha256'],
                    'reused prepared audio changed')
            profiles[t['recording_id']] = t['profile']
            provenance[t['recording_id']] = {'status': 'REUSED_VALIDATED', 'origins': t['reuse_origins'],
                'source_sha256': t['audio_sha256'], 'prepared_sha256': t['prepared']['prepared_sha256']}
    for batch, old_batch in zip(m['batches'], execution['batches']):
        original = FullRunner(root, (root / old_batch['path']).parent, original_policy)
        resumed = RecoveryRunner(root, batch, policy)
        from .gemini_full_manifest import verify_prepared
        verify_prepared(root, original.run, original.manifest, audio=True)
        for runner, count in ((original, batch['original_completed']), (resumed, len(resumed.manifest['schedule']))):
            for p in sorted((runner.directory/'transport').glob('call-*.response.json')):
                metadata = read(p)
                require(file_hash(p.with_suffix('.bin')) == metadata['response_sha256'], 'response changed')
                require(math.isfinite(metadata['latency_seconds']) and metadata['latency_seconds'] >= 0,
                        'invalid latency')
            for p in sorted((runner.directory/'transport').glob('*')):
                if p.is_file(): transport_hashes[str(p.relative_to(root))] = file_hash(p)
            for i in range(1,count+1):
                result=runner.verified_result(i)
                track=runner.tracks[result['pilot_id']]
                sid=track['recording_id']
                require(sid not in profiles,'duplicate completed profile')
                profiles[sid]=result['profile']
                provenance[sid]={'status':'NEW_VALIDATED','source_sha256':track['source_sha256'],
                    'prepared_sha256':track['prepared']['prepared_sha256'],'cache_key':result['cache_key'],
                    'response_id':result['response_id'],'model_version':result['model_version'],
                    'result_path':str(runner.result_path(i).relative_to(root)),
                    'result_sha256':file_hash(runner.result_path(i)),'manifest_sha256':runner.manifest_sha}
    require(set(profiles)=={t['recording_id'] for t in preflight['recordings']},'full population required')
    settled=Decimal(approval['prior_settled_usd'])+Decimal(state['actual_cost_usd'])
    usage={'generation_attempts':540+state['generation_attempts'],'settled_cost_usd':str(settled),
        'unresolved_historical_charge_upper_bound_usd':approval['prior_unresolved_upper_cost_usd'],
        'total_accounting_upper_bound_usd':str(settled+Decimal(approval['prior_unresolved_upper_cost_usd'])),
        'failed_attempts_preserved':1,'new_unsettled_attempts':0}
    require(Decimal(usage['total_accounting_upper_bound_usd'])<=Decimal(approval['total_spend_cap_usd']), 'cap exceeded')
    value={'schema':'gemini-full-profiles-frozen-v1','execution_manifest_sha256':digest(execution),
        'recovery_manifest_sha256':digest(m),'preflight_sha256':original_policy['preflight_sha256'],
        'profiles':profiles,'provenance':provenance,'replay_new_api_calls':0,'replayed_new_profiles':1640,
        'usage':usage,'transport_hashes':transport_hashes}
    freeze_json(root/RUN/'profiles_frozen.json',value)
    return value
