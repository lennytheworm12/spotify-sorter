"""Freeze the expanded execution only after explicit corpus/upload/cap approval."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from .contracts import digest, file_hash, freeze_json, require
from .gemini_full_inputs import DEV, METHOD_C, RUN, read
from ..gemini_style_pilot.manifest import CONFIG, MODEL, environment


def producer_hashes(root):
    names = ['gemini_free_genre.py', 'gemini_free_genre_runner.py',
        'gemini_style_pilot/budget.py', 'gemini_style_pilot/prepare.py',
        'gemini_style_pilot/inputs.py', 'gemini_style_pilot/transport.py',
        'gemini_style_pilot/validation.py', 'gemini_style_pilot/runner.py',
        'stage5e3_artifacts.py', 'stage5b1a_models.py',
        'calibration/contracts.py', 'calibration/gemini_full_budget.py',
        'calibration/gemini_full_manifest.py', 'calibration/gemini_full_runner.py',
        'calibration/gemini_full_inputs.py', 'calibration/gemini_full_prepare.py']
    return {f'src/audio_similarity/{name}': file_hash(root / 'src/audio_similarity' / name) for name in names}


def validate_approval(approval, preflight, preflight_sha):
    missing = [t['recording_id'] for t in preflight['recordings'] if t['profile'] is None]
    require(approval.get('schema') == 'gemini-full-upload-authorization-v1'
            and approval.get('approved') is True, 'expanded upload approval required')
    require(approval.get('destination') == 'Google Gemini API'
            and approval.get('corpus_sha256') == preflight['corpus_sha256']
            and approval.get('preflight_sha256') == preflight_sha
            and approval.get('recording_ids_sha256') == digest(missing)
            and approval.get('max_new_generations') == len(missing), 'approval does not cover this batch')
    require(isinstance(approval.get('owner_message'), str) and approval['owner_message'].strip(),
            'preserved explicit owner approval required')
    cap = Decimal(approval.get('spend_cap_usd', 'NaN'))
    require(cap.is_finite() and cap > 0, 'explicit numeric spending cap required')
    return cap


def verify_prepared(root, directory, plan, *, audio=True):
    require(plan['model_id'] == MODEL and plan['generation_config'] == CONFIG
            and plan['environment'] == environment(), 'original generation contract changed')
    old = root / DEV / 'gemini'
    for name, field in [('prompt.txt', 'prompt_sha256'), ('response_schema.json', 'base_schema_sha256')]:
        require(file_hash(directory / name) == plan[field] == file_hash(old / name),
                'prompt/schema differs from frozen development contract')
    ids = set()
    for i, t in enumerate(plan['tracks'], 1):
        require(t['pilot_id'] == f'T{i:03d}' and t['neutral_id'] == f'N{i:03d}'
                and i <= 900 and t['recording_id'] not in ids, 'batch identity/order invalid')
        ids.add(t['recording_id'])
        prepared = t['prepared']
        require(prepared['source_sha256'] == t['source_sha256']
                and prepared['full_recording_preserved'] and prepared['identity_metadata_removed'],
                'source/prepared linkage incomplete')
        path = root / plan['prepared_root'] / prepared['prepared_filename']
        require(path.resolve() == (directory / 'prepared' / (t['neutral_id'] + '.flac')).resolve(),
                'prepared path or neutral filename differs')
        require(read(path.with_suffix('.json')) == prepared, 'prepared receipt changed')
        if audio:
            require(file_hash(path) == prepared['prepared_sha256'], 'prepared audio changed')
            require(file_hash(root / t['source_path']) == t['source_sha256'], 'source audio changed')
        schema = read(directory / t['response_schema'])
        expected = read(directory / 'response_schema.json')
        expected['properties']['audio_evidence']['items']['properties']['at_seconds']['maximum'] = prepared['duration_seconds']
        require(schema == expected and digest(schema) == t['response_schema_sha256'], 'duration schema changed')


def freeze_execution(root, approval_path):
    root = root.resolve()
    run = root / RUN
    preflight = read(run / 'preflight.json')
    prepared = read(run / 'prepared.json')
    psha = file_hash(run / 'preflight.json')
    approval = read(approval_path)
    cap = validate_approval(approval, preflight, psha)
    require(prepared['preflight_sha256'] == psha, 'prepared population changed')
    require(file_hash(root / METHOD_C / 'corpus.json') == preflight['corpus_sha256'], 'corpus changed')
    price = read(run / 'pricing_verification.json')
    require(price['model_id'] == MODEL and price['tier'] == 'standard'
            and price['input'] == '0.75'
            and price['output_including_thinking'] == '3.75'
            and date.today() <= date.fromisoformat(price['valid_through']), 'verified rates unavailable/expired')
    hashes = producer_hashes(root)
    freeze_json(run / 'upload_authorization.json', approval)
    policy = {'schema': 'gemini-full-global-policy-v1', 'spend_cap_usd': str(cap),
        'max_attempts': preflight['counts']['missing_profiles'], 'input_token_limit': 1048576,
        'authorization_sha256': digest(approval), 'preflight_sha256': psha,
        'rates': price, 'automatic_retries': 0, 'implementation_hashes': hashes}
    batches, observed = [], []
    for row in prepared['batches']:
        path = root / row['path']
        require(file_hash(path) == row['sha256'], 'prepared plan changed')
        plan = read(path)
        verify_prepared(root, path.parent, plan)
        observed.extend(t['recording_id'] for t in plan['tracks'])
        manifest = plan | {'schema': 'gemini-full-execution-batch-v1',
            'global_policy_sha256': digest(policy), 'max_attempts': len(plan['tracks']),
            'input_token_limit': 1048576, 'spend_cap_usd': str(cap), 'rates': price,
            'implementation_sha256': digest(hashes), 'implementation_hashes': hashes,
            'response_schemas': {t['pilot_id']: t['response_schema'] for t in plan['tracks']},
            'schedule': [{'pilot_id': t['pilot_id'], 'repeat': False} for t in plan['tracks']],
            'automatic_retries': 0, 'ontology': None,
            'metadata_to_provider': 'neutral identifier and full duration only',
            'failure_policy': 'Stop all batches on operational/schema/accounting failure; preserve every attempt; no silent retry.'}
        freeze_json(path.parent / 'execution_manifest.json', manifest)
        batches.append({'path': str((path.parent / 'execution_manifest.json').relative_to(root)),
                        'sha256': digest(manifest), 'tracks': len(plan['tracks'])})
    expected = [t['recording_id'] for t in preflight['recordings'] if t['profile'] is None]
    require(observed == expected, 'execution omits/reorders/substitutes missing corpus members')
    freeze_json(run / 'global_policy.json', policy)
    result = {'schema': 'gemini-full-execution-v1', 'policy_sha256': digest(policy),
              'batches': batches, 'new_generations_planned': len(expected), 'corpus_sha256': preflight['corpus_sha256']}
    freeze_json(run / 'execution_manifest.json', result)
    return result
