"""Explicit development-only nested comparison; no lockbox or policy selection."""
from dataclasses import asdict
import json
from pathlib import Path

from .contracts import Role, digest, file_hash, freeze_json, require
from .development_inputs import RUN, load
from .development_bundle import corpus_from_plan
from .development_evaluation import evaluate_many
from .features import PairFeatures
from .ranking import ablations
from .search import select_inner, summaries, cluster_uncertainty
from .splits import NestedFold, grouped_folds


def development_plan(plan):
    require(plan['formal_confirmation'] is False and plan['production_activation'] is False and plan['lockbox'] is None,
            'this entrypoint is development-only')
    require(plan['owner_authorization'] and plan['development_exception'], 'explicit development authorization required')
    corpus = corpus_from_plan(plan)
    ids = [p.playlist_id for p in corpus.playlists]
    seed = plan['split_seed']
    outer = grouped_folds(corpus, ids, plan['outer_folds'], Role.OUTER, seed)
    nested = tuple(NestedFold(p, grouped_folds(corpus, p.fit_playlists, plan['inner_folds'], Role.INNER,
        f'{seed}/{i}/inner', p.fit_recordings)) for i, p in enumerate(outer))
    return corpus, nested


def freeze_protocol(root):
    """Can run before inference finishes: source membership and splits only."""
    plan, run = load(root), root / RUN
    corpus, nested = development_plan(plan)
    registry = ablations()
    models = {m.identity: m for values in registry.values() for m in values}
    paths = [p for p in Path(__file__).parent.glob('*.py') if p.name in {
        'contracts.py', 'features.py', 'ranking.py', 'splits.py', 'search.py',
        'development_search.py', 'development_evaluation.py', 'development_bundle.py'}]
    result = {'schema': 'personal-development-nested-execution-v1', 'status': 'PROTOCOL_FROZEN_FEATURES_PENDING',
        'plan_sha256': digest(plan), 'corpus_sha256': corpus.identity,
        'implementation_hashes': {str(p.relative_to(root)): file_hash(p) for p in sorted(paths)},
        'source_use_status': 'PENDING_OWNER_REPORTS_NO_LICENSE', 'formal_confirmation': False,
        'models': {k: m.definition for k, m in sorted(models.items())},
        'arms': {k: [m.identity for m in v] for k, v in registry.items()},
        'folds': [asdict(f) for f in nested], 'mask_repetitions': plan['mask_repetitions'],
        'bootstrap_draws': plan['bootstrap_draws'], 'bootstrap_seed': plan['bootstrap_seed'],
        'selection': plan['selection'], 'recall_comparator': plan['recall_comparator'],
        'candidate_catalog': 'all evaluation recordings in the fold, excluding seed/duplicate versions; identical across configurations',
        'outer_use': 'estimate each predeclared selection procedure; never select a model family from outer results',
        'lockbox': None, 'production_activation': False}
    freeze_json(run / 'search_protocol.json', result)
    return result


def run(root):
    plan, run = load(root), root / RUN
    protocol = json.loads((run / 'search_protocol.json').read_text())
    require(protocol['plan_sha256'] == digest(plan), 'search plan changed')
    for name, expected in protocol['implementation_hashes'].items():
        require(file_hash(root / name) == expected, 'frozen search implementation changed')
    features = PairFeatures.load(run / 'features')
    require(features.corpus.identity == protocol['corpus_sha256'], 'feature population differs from frozen sample')
    # Verify the producer caches and profiles linked by the completed bundle.
    for name, expected in json.loads((run / 'bundle_inputs.json').read_text()).items():
        require(file_hash(root / name) == expected, 'completed feature input changed')
    _, folds = development_plan(plan)
    registry = ablations()
    configs = {m.identity: m for values in registry.values() for m in values}
    models = [configs[k] for k in sorted(configs)]
    require(len(models) == 792, 'frozen grid/control count changed')
    estimates, outer_rows = [], {arm: [] for arm in registry}
    settings = {'repetitions': plan['mask_repetitions'], 'draws': plan['bootstrap_draws'], 'seed': plan['bootstrap_seed']}
    freeze_json(run / 'search/feature_freeze.json', {'bundle_id': features.identity,
        'search_protocol_sha256': file_hash(run / 'search_protocol.json'), 'status': 'DEVELOPMENT_FEATURES_FROZEN'})
    for i, fold in enumerate(folds):
        directory = run / f'search/outer_{i}'
        evaluated = evaluate_many(features, models, fold.inner, output=directory / 'inner', **settings)
        choices = {arm: select_inner([evaluated[m.identity] for m in candidates], evaluated)
            for arm, candidates in registry.items()}
        ledger = [{'model_id': key, 'configuration': e.model.definition,
            'summary': e.summary, 'uncertainty': e.uncertainty,
            'per_fold': [{'fold_id': f['fold_id'], 'metrics': f['metrics']} for f in e.fold_reports],
            'arm_decisions': {arm: c['reasons'][key] for arm, c in choices.items() if key in c['reasons']}}
            for key, e in sorted(evaluated.items())]
        freeze_json(directory / 'inner/search_ledger.json', {'role': Role.INNER, 'feature_bundle_id': features.identity,
            'configurations': ledger, 'arm_selection': choices})
        selected = sorted({c['selected_model_id'] for c in choices.values() if c['selected_model_id'] is not None})
        outer = evaluate_many(features, [configs[k] for k in selected], (fold.outer,), output=directory / 'outer', **settings)
        arm_estimates = {}
        for arm, choice in choices.items():
            key = choice['selected_model_id']
            if key is None:
                arm_estimates[arm] = {'status': 'INSUFFICIENT_DATA'}
                continue
            e = outer[key]
            arm_estimates[arm] = {'model': e.model.definition, 'model_id': key, 'summary': e.summary, 'uncertainty': e.uncertainty}
            outer_rows[arm].extend(e.summary['per_query'])
        estimate = {'outer_split': asdict(fold.outer), 'inner_choices': choices, 'outer_estimates': arm_estimates}
        freeze_json(directory / 'outer/estimates.json', estimate)
        estimates.append(estimate)
        print(json.dumps({'nested_outer_completed': i+1, 'of': len(folds), 'inner_configurations': len(evaluated)}), flush=True)
    result = {'schema': 'personal-development-nested-results-v1', 'status': 'DEVELOPMENT_COMPARISON_COMPLETE',
        'feature_bundle_id': features.identity, 'folds': estimates,
        'arm_summaries': {arm: {'summary': summaries(rows),
            'uncertainty': cluster_uncertainty(rows, draws=plan['bootstrap_draws'], seed=plan['bootstrap_seed'])}
            for arm, rows in outer_rows.items() if rows},
        'limitations': ['Small selected development corpus; no untouched lockbox.',
            'Source-use documentation remains pending under owner-authorized personal-development exception.',
            'Observed membership is positive evidence; all other candidates remain unlabeled.',
            'Outer results do not select a model family or authorize production settings.'],
        'production_activation': False, 'suitability_status': 'LABELS_REQUIRED', 'strictness_status': 'NOT_CALIBRATED'}
    freeze_json(run / 'search/results.json', result)
    return {'status': result['status'], 'outer_folds': len(folds), 'configurations_per_inner_search': len(models),
        'artifact': str((run / 'search/results.json').relative_to(root))}
