"""Fail-closed, create-once request reservations for the isolated paid pilot."""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from audio_similarity.stage5e3_artifacts import freeze_json, read


class BudgetStopped(ValueError):
    pass


def nonnegative_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BudgetStopped('missing or invalid integer token accounting')
    return value


class AttemptLedger:
    """Unsettled/failed requests retain their full reservation and stop continuation.

    CountTokens can differ from billed prompt tokens. Reserve the documented
    entire model input limit, not an empirical token-count safety multiplier.
    Release the unused reservation only after complete provider accounting.
    """

    def __init__(self, directory: Path, *, input_limit: int, input_usd_per_million: str,
                 output_usd_per_million: str, spend_cap_usd: str = '2', max_attempts: int = 20):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.input_limit = nonnegative_int(input_limit)
        self.input_rate = Decimal(input_usd_per_million) / 1_000_000
        self.output_rate = Decimal(output_usd_per_million) / 1_000_000
        self.cap = Decimal(spend_cap_usd)
        self.max_attempts = nonnegative_int(max_attempts)
        if not all(x.is_finite() and x > 0 for x in [self.input_rate, self.output_rate, self.cap]):
            raise BudgetStopped('invalid rates or spend cap')
        if self.cap > 2 or self.max_attempts > 20 or not self.input_limit or not self.max_attempts:
            raise BudgetStopped('pilot hard limits exceeded')
        freeze_json(self.directory / 'policy.json', {
            'input_limit': self.input_limit, 'input_rate': str(self.input_rate),
            'output_rate': str(self.output_rate), 'cap_usd': str(self.cap),
            'max_attempts': self.max_attempts,
        })

    @contextmanager
    def locked(self):
        with (self.directory / '.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def cost(self, prompt_tokens: int, output_including_thinking: int) -> Decimal:
        return (nonnegative_int(prompt_tokens) * self.input_rate
                + nonnegative_int(output_including_thinking) * self.output_rate)

    def reserve(self, *, counted_input: int, max_output_tokens: int, request_sha256: str,
                manifest_sha256: str, neutral_id: str, repeat: bool = False) -> dict:
        count, output = nonnegative_int(counted_input), nonnegative_int(max_output_tokens)
        if not count or count > self.input_limit or not output or output > 65536:
            raise BudgetStopped('request token bounds are not established')
        with self.locked():
            previous = sorted(self.directory.glob('attempt-*.reservation.json'))
            if len(previous) >= self.max_attempts:
                raise BudgetStopped('generation attempt allowance exhausted')
            spent = Decimal(0)
            for path in previous:
                result_path = path.with_name(path.name.replace('.reservation.', '.settlement.'))
                if not result_path.exists():
                    raise BudgetStopped('an attempt has unresolved token accounting; do not retry silently')
                spent += Decimal(read(result_path)['actual_cost_usd'])
            upper = self.cost(self.input_limit, output)
            if spent + upper > self.cap:
                raise BudgetStopped('cannot reserve the conservative upper cost bound')
            attempt = len(previous) + 1
            record = {
                'attempt': attempt, 'neutral_id': neutral_id, 'repeat': repeat,
                'counted_input_tokens': count, 'reserved_input_upper_tokens': self.input_limit,
                'max_output_including_thinking_tokens': output,
                'reserved_upper_cost_usd': str(upper), 'settled_cost_before_usd': str(spent),
                'request_sha256': request_sha256, 'manifest_sha256': manifest_sha256,
            }
            freeze_json(self.directory / f'attempt-{attempt:02d}.reservation.json', record)
            return record

    def settle(self, attempt: int, usage: dict) -> dict:
        with self.locked():
            reservation = read(self.directory / f'attempt-{attempt:02d}.reservation.json')
            prompt = nonnegative_int(usage.get('promptTokenCount'))
            output = nonnegative_int(usage.get('candidatesTokenCount'))
            # REST protobuf omits default zero values; total must reconcile exactly.
            thoughts = nonnegative_int(usage.get('thoughtsTokenCount', 0))
            total = nonnegative_int(usage.get('totalTokenCount'))
            tools = nonnegative_int(usage.get('toolUsePromptTokenCount', 0))
            if usage.get('serviceTier', 'standard') not in ('standard', 'unspecified'):
                raise BudgetStopped('provider used an unexpected service tier; pricing is not established')
            if tools or total != prompt + output + thoughts:
                raise BudgetStopped('usage is incomplete, inconsistent, or includes prohibited tool use')
            if prompt > self.input_limit or output + thoughts > reservation['max_output_including_thinking_tokens']:
                raise BudgetStopped('provider usage exceeded frozen token bounds')
            cost = self.cost(prompt, output + thoughts)
            record = {'attempt': attempt, 'usage': usage, 'actual_cost_usd': str(cost)}
            freeze_json(self.directory / f'attempt-{attempt:02d}.settlement.json', record)
            return record
