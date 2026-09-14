"""Coverage, accounting and immutable deterministic replay; no model inference."""
from pathlib import Path

from .contracts import digest, file_hash, freeze_json, require
from .gemini_full_inputs import RUN, PUBLIC, read, historical_receipt
from .gemini_full_budget import spending


def status(root):
    run = root / RUN
    if not (run / 'preflight.json').exists():
        return {'status': 'PREFLIGHT_REQUIRED', 'new_api_calls': 0}
    preflight = read(run / 'preflight.json')
    n = preflight['counts']['frozen_recordings']
    valid = list(run.glob('batch_*/execution/attempts/attempt-*.result.json'))
    failures = list(run.glob('batch_*/execution/STOPPED.json'))
    reused = preflight['counts']['reused_profiles']
    result = {'status': 'WAITING_FOR_PROFILES', **preflight['counts'], **spending(run),
        'new_validated_profiles': len(valid), 'remaining_profiles': n - reused - len(valid),
        'stopped_batches': len(failures),
        'prepared_recordings': len(list(run.glob('batch_*/prepared/N*.json'))),
        'execution_frozen': (run / 'execution_manifest.json').exists(),
        'calibration_status': 'NOT_AUTHORIZED_EVALUATION_PROTOCOL_NOT_FROZEN'}
    result['missing_profiles_at_preflight'] = preflight['counts']['missing_profiles']
    result['missing_profiles'] = result['remaining_profiles']
    result['failed_or_unresolved_generation_attempts'] = result['generation_attempts'] - len(valid)
    if failures:
        result['status'] = 'STOPPED_REVIEW_REQUIRED'
    elif not result['execution_frozen']:
        result['status'] = ('PREPARED_AWAITING_APPROVED_CAP' if (run / 'prepared.json').exists()
                            else 'PREPARING_AWAITING_APPROVED_CAP')
    if (run / 'recovery_01/manifest.json').exists():
        from decimal import Decimal
        recovered = spending(run / 'recovery_01')
        successes = len(list((run / 'recovery_01').glob('batch_*/execution/attempts/attempt-*.result.json')))
        approval = read(run / 'recovery_01/authorization.json')
        result['new_validated_profiles'] += successes
        result['remaining_profiles'] -= successes
        result['missing_profiles'] = result['remaining_profiles']
        result['generation_attempts'] += recovered['generation_attempts']
        result['actual_cost_usd'] = str(Decimal(result['actual_cost_usd']) + Decimal(recovered['actual_cost_usd']))
        result['unresolved_historical_charge_upper_bound_usd'] = approval['prior_unresolved_upper_cost_usd']
        result['total_accounting_upper_bound_usd'] = str(Decimal(result['actual_cost_usd']) + Decimal(approval['prior_unresolved_upper_cost_usd']))
        result['recovery_unsettled'] = recovered['unsettled']
        result['historical_failed_attempts_preserved'] = 1
        result['failed_or_unresolved_generation_attempts'] = result['generation_attempts'] - result['new_validated_profiles']
        result['recovery_stopped_batches'] = len(list((run / 'recovery_01').glob('batch_*/execution/STOPPED.json')))
        result['status'] = 'STOPPED_REVIEW_REQUIRED' if result['recovery_stopped_batches'] else 'RECOVERY_IN_PROGRESS'
    if (run / 'bundle_report.json').exists():
        result.update(read(run / 'bundle_report.json'))
    return result


def verify(root):
    from .gemini_full_features import build
    from .gemini_full_recovery import freeze_profiles
    from .features import PairFeatures
    from .development_validation import integrity, historical_payloads
    root = root.resolve()
    run = root / RUN
    require((run / 'bundle_report.json').exists(), 'complete feature bundle required')
    before = {str(p.relative_to(run)): file_hash(p) for p in sorted(run.rglob('*')) if p.is_file()
              and p.suffix in ('.json', '.bin', '.npy')
              and p.name not in ('verification.json', 'artifact_manifest.json', 'original_execution_receipt.json')}
    freeze_json(run / 'original_execution_receipt.json', before)
    replay = freeze_profiles(root)
    require(replay['replay_new_api_calls'] == 0, 'completed replay performed inference')
    result = build(root, recompute=True)
    bundle = PairFeatures.load(run / 'features')
    require(bundle.identity == result['bundle_id'], 'bundle loader identity mismatch')
    for name, expected in before.items():
        require(file_hash(run / name) == expected, 'replay modified original evidence: ' + name)
    histories = historical_receipt(root)
    require(histories == read(run / 'preflight.json')['historical_manifest_hashes'], 'historical manifest replaced')
    source_checks = integrity(root)
    published = historical_payloads(root)
    value = {'status': 'PASS', 'bundle_id': bundle.identity, 'tracks': len(bundle.track_ids),
        'cache_replay_new_generation_calls': 0, 'deterministic_full_genre_recompute': True,
        'unchanged_execution_artifacts': len(before), 'source_integrity': source_checks,
        'historical_payloads': published, 'historical_manifest_hashes': histories,
        'feature_bundle_report_sha256': file_hash(run / 'bundle_report.json')}
    freeze_json(run / 'verification.json', value)
    files = {str(p.relative_to(run)): file_hash(p) for p in sorted(run.rglob('*')) if p.is_file()
             and p.suffix in ('.json', '.bin', '.npy', '.txt') and p.name != 'artifact_manifest.json'}
    freeze_json(run / 'artifact_manifest.json', {'files': files,
        'audio_policy': 'Source/prepared bytes are separately hash-linked in the frozen manifests; not republished.'})
    return value


def publish(root):
    """Publication requires actual completion; an unfinished run is never shrunk."""
    run, public = root / RUN, root / PUBLIC
    require((run / 'verification.json').exists(), 'verified complete run required for closeout')
    tests_name = 'recovery_tests.json' if (run / 'recovery_01/manifest.json').exists() else 'tests.json'
    tests = read(run / tests_name)
    require(tests['status'] == 'PASS' and {'focused', 'nonheavy'} <= set(tests['suites']),
            'focused and non-heavy test evidence required')
    for suite in tests['suites'].values():
        require(suite['exit_code'] == 0 and file_hash(root / suite['log_path']) == suite['log_sha256'],
                'test execution evidence differs')
    from .features import PairFeatures
    features = PairFeatures.load(run / 'features')
    report = read(run / 'bundle_report.json')
    verification = read(run / 'verification.json')
    require(features.identity == report['bundle_id'] == verification['bundle_id'], 'closeout bundle mismatch')
    state = status(root)
    preflight = read(run / 'preflight.json')
    rows = []
    profiles = read(run / 'profiles_frozen.json')
    mapped = read(run / 'mapped_profiles.json')
    for sid in features.track_ids:
        rows.append({'recording_id': sid, 'profile': profiles['profiles'][sid], 'mapping': mapped[sid],
                     'provenance': profiles['provenance'][sid]})
    freeze_json(public / 'mapped_profiles.json', rows)
    for name in ('bundle_report.json', 'verification.json', 'bundle_inputs.json', 'global_policy.json', tests_name):
        freeze_json(public / name, read(run / name))
    freeze_json(public / 'feature_manifest.json', read(run / 'features/bundle.json'))
    freeze_json(public / 'closeout_counts.json', state)
    text = f'''# Full-corpus Gemini and genre feature preparation

**FEATURE_BUNDLE_READY. Calibration execution remains separately gated.**

The unchanged frozen corpus contains {state['frozen_recordings']} retained recordings
from {state['original_requests']} requests. {state['source_unavailable_requests']} original
requests remain source attrition. No extensions or model-based exclusions were added.

Profiles: {state['reused_profiles']} reused; {state['new_validated_profiles']} newly validated;
{state['remaining_profiles']} missing; {state['failed_or_unresolved_generation_attempts']} failed/unresolved generation attempts.
This run made {state['generation_attempts']} generation
attempts and spent ${state['actual_cost_usd']}. All required responses and source/prepared
audio identities validate. Any preserved unresolved historical charge is reported separately
in closeout_counts.json with its conservative upper bound; settled spending is not a
claim that the failed call was free. The original total cap remains $15. Raw responses, usage, provider IDs/version, transport latency,
reservations and settlements remain in the private execution directories.

The unchanged 138-concept / 29-neighborhood mapper yields
{report['usable_specific_style']} profiles with usable specific-style evidence and
{report['valid_but_noninformative']} valid but score-neutral profiles. The latter remain
in the full population. Missing or invalid profiles were never substituted with unknown.
Raw labels and complete per-track mapping traces accompany the numerical pair features.

All six matrices (centered30 CLAP, Method C, MuQ, Jc, Jnr, R) share explicit IDs and
source ordering. The exact Method C matrix bytes were reused. Genre computation uses
the existing canonical weighted Jaccard and unmatched canonical-mass neighborhood
scorer, with R=(1-Jc)*Jnr. Bounded upper-triangle shards avoid per-pair text traces.

Replay verified zero new generation calls, deterministic full genre recomputation,
symmetry/bounds/finiteness and unchanged execution evidence. Original source and
historical experiment integrity checks passed. Test logs accompany this report.

Private run: `{RUN}` (relative to `ml/audio_similarity`).
Feature bundle: `{RUN}/features/bundle.json`.
Bundle identity: `{features.identity}`.
Frozen corpus SHA-256: `{preflight['corpus_sha256']}`.
Exact matrix/file hashes and representation identities: `feature_manifest.json`.

This is a feature catalog, not an evaluation split. Original source-playlist records
remain in the linked corpus manifest. Broader recording/version purges, final curator
groups/splits and candidate catalogs, and source-use documentation still need the
separately authorized evaluation stage. No weight search, output calibration,
suitability labels, thresholds, representation selection or production changes ran.
'''
    path = public / 'REPORT.md'
    if path.exists():
        require(path.read_text() == text, 'closeout report differs')
    else:
        path.write_text(text)
    manifest = {str(p.relative_to(public)): file_hash(p) for p in sorted(public.rglob('*'))
                if p.is_file() and p.name != 'artifact_manifest.json'}
    freeze_json(public / 'artifact_manifest.json', {'files': manifest})
    return state
