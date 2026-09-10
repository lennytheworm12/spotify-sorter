"""Documented engineering continuation: point timestamps, unchanged free genres."""
import copy
from decimal import Decimal

from .stage5b1a_models import file_sha256
from .stage5e3_artifacts import hashes, read, verify_hashes
from .gemini_free_genre import PROMPT
from .gemini_style_pilot.budget import nonnegative_int

POINT_PROMPT = PROMPT.replace('approximate start/end times within the supplied duration',
                             'one approximate at_seconds timestamp per cue within the supplied duration')


def point_schema(base):
    schema = copy.deepcopy(base)
    item = schema['properties']['audio_evidence']['items']
    item['properties'] = {'at_seconds': {'type': 'number', 'minimum': 0},
                          'observation': item['properties']['observation']}
    item['required'] = ['at_seconds', 'observation']
    return schema


def extend_manifest(root, run, manifest, stopped):
    if stopped == run or not (stopped / 'execution/STOPPED.json').exists():
        raise ValueError('preserve the stopped interval arm in a separate directory')
    old = read(stopped / 'execution_manifest.json')
    if old['schema_version'] != 'gemini-free-genre-v1' or old['max_attempts'] != 18 or old['prior_attempts'] != 20:
        raise ValueError('point continuation requires the original bounded free-genre arm')
    if old['tracks'] != manifest['tracks'] or old['prior_settled_usd'] != manifest['prior_settled_usd']:
        raise ValueError('prior source or spending mismatch')
    verify_hashes(root, old['input_hashes'])
    verify_hashes(root, old['protected_hashes'])
    snapshots = read(stopped / 'implementation_snapshot.json')
    if set(snapshots) != set(old['implementation_hashes']):
        raise ValueError('missing exact predecessor implementation snapshot')
    for name, row in snapshots.items():
        if row['sha256'] != old['implementation_hashes'][name]:
            raise ValueError('predecessor implementation identity mismatch')
        verify_hashes(root, {row['snapshot_path']: row['sha256']})
    attempts = stopped / 'execution/attempts'
    calls = [p for p in sorted((stopped / 'execution/transport').glob('call-*.request.json'))
             if read(p)['label'] == 'generateContent']
    if len(calls) != 2 or len(list(attempts.glob('*.reservation.json'))) != 2 or len(list(attempts.glob('*.settlement.json'))) != 2:
        raise ValueError('expected exactly two fully accounted predecessor generations')
    added = Decimal(0)
    for index, call in enumerate(calls, 1):
        usage = read(call.with_name(call.name.replace('.request.json', '.response.bin')))['usageMetadata']
        settlement = read(attempts / f'attempt-{index:02d}.settlement.json')
        reservation = read(attempts / f'attempt-{index:02d}.reservation.json')
        prompt = nonnegative_int(usage.get('promptTokenCount'))
        output = nonnegative_int(usage.get('candidatesTokenCount')) + nonnegative_int(usage.get('thoughtsTokenCount', 0))
        if (usage != settlement['usage'] or nonnegative_int(usage.get('totalTokenCount')) != prompt + output
            or usage.get('toolUsePromptTokenCount', 0) or prompt > old['input_token_limit']
            or output > reservation['max_output_including_thinking_tokens']
            or reservation['manifest_sha256'] != file_sha256(stopped / 'execution_manifest.json')):
            raise ValueError('incomplete predecessor accounting')
        cost = (prompt * Decimal(old['rates']['input']) + output * Decimal(old['rates']['output_including_thinking'])) / 1_000_000
        if cost != Decimal(settlement['actual_cost_usd']):
            raise ValueError('predecessor cost does not match raw usage')
        added += cost
    manifest.update(schema_version='gemini-free-genre-point-v1', prior_attempts=22, max_attempts=16,
                    prior_settled_usd=str(Decimal(old['prior_settled_usd']) + added),
                    spend_cap_usd=str(Decimal(old['spend_cap_usd']) - added),
                    schedule=[s for s in old['schedule'] if not s['repeat']],
                    point_revision={'prior_run': str(stopped.relative_to(root)),
                        'prior_manifest_sha256': file_sha256(stopped / 'execution_manifest.json'),
                        'prior_code_commit': 'b322790', 'prior_new_attempts': 2,
                        'prior_new_spend_usd': str(added),
                        'failure': 'Second engineering smoke returned a reversed 31-to-30-second evidence interval.',
                        'change': 'One bounded point timestamp per cue; genre/facet instructions unchanged.',
                        'repeat_policy': 'Both planned repeats consumed by the stopped smokes; no additional repeat allowance.'})
    files = [p for p in stopped.rglob('*') if p.is_file() and p.name not in ('.lock', '.runner.lock')]
    manifest['input_hashes'].update(hashes(files, root))
    return manifest
