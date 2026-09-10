"""Explicit duration-only continuation after the two original engineering smokes.

This is deliberately bounded to the observed two-attempt predecessor. It cannot
create another independent 20-call allowance or silently reuse an old profile.
"""
from __future__ import annotations

import copy
import math
from decimal import Decimal
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import freeze_json, read, verify_hashes
from .budget import nonnegative_int


def bounded_schema(schema: dict, duration: float) -> dict:
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('invalid recording duration')
    revised = copy.deepcopy(schema)
    fields = revised['properties']['audio_evidence']['items']['properties']
    for field in ('start_seconds', 'end_seconds'):
        fields[field]['maximum'] = duration
    return revised


def continuation_fields(root: Path, run: Path, revision_path: Path, tracks: list) -> tuple[dict, list]:
    approval = read(revision_path)
    if approval.get('schema_policy') != 'duration-maximum-v1' or not approval.get('owner_message'):
        raise ValueError('explicit duration revision record required')
    prior = (root / approval['prior_run']).resolve()
    if prior == run.resolve() or not (prior / 'execution/STOPPED.json').exists():
        raise ValueError('preserve the stopped predecessor in a separate directory')
    manifest = read(prior / 'execution_manifest.json')
    if manifest.get('continuation') or manifest['max_attempts'] != 20 or manifest['spend_cap_usd'] != '2':
        raise ValueError('this bounded revision requires the original pilot allowance')
    verify_hashes(root, manifest['input_hashes'])
    verify_hashes(root, manifest['protected_hashes'])
    identity = lambda t: (t['pilot_id'], t['spotify_track_id'], t['neutral_id'],
                          t['prepared']['prepared_sha256'], t['prepared']['duration_seconds'])
    if [identity(t) for t in tracks] != [identity(t) for t in manifest['tracks']]:
        raise ValueError('duration revision cannot change the original recordings')
    for name in ('prompt.txt', 'ontology.md', 'response_schema.json'):
        if (run / 'contract/model' / name).read_bytes() != (prior / 'contract/model' / name).read_bytes():
            raise ValueError('the base classification contract must remain unchanged')
    attempts = prior / 'execution/attempts'
    reservations = sorted(attempts.glob('attempt-*.reservation.json'))
    calls = [p for p in sorted((prior / 'execution/transport').glob('call-*.request.json'))
             if read(p)['label'] == 'generateContent']
    if len(reservations) != 2 or len(calls) != 2 or len(list(attempts.glob('*.settlement.json'))) != 2:
        raise ValueError('expected exactly two accounted predecessor generations')
    spent = Decimal(0)
    for index, (reservation_path, call) in enumerate(zip(reservations, calls), 1):
        reservation = read(reservation_path)
        settlement = read(attempts / f'attempt-{index:02d}.settlement.json')
        response = read(call.with_name(call.name.replace('.request.json', '.response.bin')))
        usage = response['usageMetadata']
        if (reservation['attempt'] != index or settlement['attempt'] != index
                or reservation['manifest_sha256'] != file_sha256(prior / 'execution_manifest.json')
                or settlement['usage'] != usage):
            raise ValueError('predecessor accounting does not match the original response')
        prompt = nonnegative_int(usage.get('promptTokenCount'))
        output = nonnegative_int(usage.get('candidatesTokenCount')) + nonnegative_int(usage.get('thoughtsTokenCount', 0))
        if (nonnegative_int(usage.get('totalTokenCount')) != prompt + output
                or nonnegative_int(usage.get('toolUsePromptTokenCount', 0))
                or prompt > manifest['input_token_limit']
                or output > reservation['max_output_including_thinking_tokens']
                or usage.get('serviceTier', 'standard') not in ('standard', 'unspecified')):
            raise ValueError('predecessor token bounds are not established')
        cost = (prompt * Decimal(manifest['rates']['input'])
                + output * Decimal(manifest['rates']['output_including_thinking'])) / 1_000_000
        if cost != Decimal(settlement['actual_cost_usd']):
            raise ValueError('predecessor settled cost does not reconcile')
        spent += cost
    if spent >= 2:
        raise ValueError('global spend allowance exhausted')
    files = [revision_path, prior / 'execution_manifest.json']
    files += [p for p in (prior / 'execution').rglob('*') if p.is_file() and p.name not in ('.lock', '.runner.lock')]
    schemas = {}
    for track in tracks:
        path = run / 'revision/schemas' / f'{track["neutral_id"]}.json'
        freeze_json(path, bounded_schema(read(run / 'contract/model/response_schema.json'),
                                        track['prepared']['duration_seconds']))
        schemas[track['pilot_id']] = str(path.relative_to(run))
        files.append(path)
    return {
        'schema_version': 'gemini-style-execution-duration-v3',
        'response_schemas': schemas, 'spend_cap_usd': str(Decimal(2) - spent), 'max_attempts': 18,
        'continuation': {'prior_manifest_sha256': file_sha256(prior / 'execution_manifest.json'),
                         'prior_run': str(prior.relative_to(root)), 'prior_generation_attempts': 2,
                         'prior_settled_usd': str(spent), 'global_attempt_cap': 20, 'global_spend_cap_usd': '2',
                         'repeat_policy': 'Keep the first two IDs in original repeat order: A01, A03. A08/C05 omitted because prior smokes consumed the allowance.'},
    }, files
