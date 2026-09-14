"""One approved spending ceiling shared by the neutral-ID batches."""
from contextlib import contextmanager
from decimal import Decimal
import fcntl
from pathlib import Path

from .contracts import freeze_json, require
from .gemini_full_inputs import read
from ..gemini_style_pilot.budget import AttemptLedger, BudgetStopped, nonnegative_int


@contextmanager
def global_lock(run, name):
    run.mkdir(parents=True, exist_ok=True)
    with (run / name).open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def spending(run):
    spent, unsettled, reservations = Decimal(0), [], []
    for directory in sorted(run.glob('batch_*/execution/attempts')):
        reserved = set(directory.glob('attempt-*.reservation.json'))
        settlements = set(directory.glob('attempt-*.settlement.json'))
        require(all(p.with_name(p.name.replace('.settlement.', '.reservation.')) in reserved
                    for p in settlements), 'settlement without original reservation')
        for path in sorted(reserved):
            reservations.append(str(path.relative_to(run)))
            settlement = path.with_name(path.name.replace('.reservation.', '.settlement.'))
            if not settlement.exists():
                unsettled.append(str(path.relative_to(run)))
                continue
            value = Decimal(read(settlement)['actual_cost_usd'])
            require(value.is_finite() and value >= 0, 'invalid settled cost')
            spent += value
    return {'actual_cost_usd': str(spent), 'generation_attempts': len(reservations),
            'unsettled': unsettled, 'settled_attempts': len(reservations) - len(unsettled)}


class FullLedger(AttemptLedger):
    """Reuse exact reservation/settlement arithmetic; expand only explicit run limits.

    Each batch keeps the original local attempt numbering. The extra lock/check
    prevents separate batches from each spending the entire approved allowance.
    """

    def __init__(self, directory, run, policy, max_attempts):
        self.directory, self.run = Path(directory), Path(run)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.input_limit = nonnegative_int(policy['input_token_limit'])
        self.input_rate = Decimal(policy['rates']['input']) / 1000000
        self.output_rate = Decimal(policy['rates']['output_including_thinking']) / 1000000
        self.cap = Decimal(policy['spend_cap_usd'])
        self.max_attempts = nonnegative_int(max_attempts)
        self.total_attempts = nonnegative_int(policy['max_attempts'])
        require(self.input_limit == 1048576 and 0 < self.max_attempts <= 900,
                'unsupported input or batch limit')
        require(self.cap.is_finite() and self.cap > 0, 'numeric approved spending cap required')
        require(self.input_rate == Decimal('.75') / 1000000
                and self.output_rate == Decimal('3.75') / 1000000, 'frozen rates changed')
        freeze_json(self.directory / 'policy.json', {
            'input_limit': self.input_limit, 'input_rate': str(self.input_rate),
            'output_rate': str(self.output_rate), 'cap_usd': str(self.cap),
            'max_attempts': self.max_attempts, 'global_max_attempts': self.total_attempts,
            'authorization_sha256': policy['authorization_sha256'], 'cap_scope': 'ALL_BATCHES_COMBINED'})

    def check_global(self, max_output_tokens=8192):
        state = spending(self.run)
        if state['unsettled']:
            raise BudgetStopped('unresolved global token accounting; no retry')
        if state['generation_attempts'] >= self.total_attempts:
            raise BudgetStopped('global generation attempt allowance exhausted')
        if Decimal(state['actual_cost_usd']) + self.cost(self.input_limit, max_output_tokens) > self.cap:
            raise BudgetStopped('cannot reserve upper cost bound within approved global cap')

    def reserve(self, **kwargs):
        with global_lock(self.run, '.global-budget.lock'):
            self.check_global(kwargs['max_output_tokens'])
            return super().reserve(**kwargs)
