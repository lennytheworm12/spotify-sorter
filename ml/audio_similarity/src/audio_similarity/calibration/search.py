"""Nested selection on synthetic cached evidence; lockbox results never enter selection."""
from collections import defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np

from .contracts import Layer, Role, digest, freeze_json, require
from .ranking import M3_RHO, Model, ablations, rank_query, reconstruction_metrics
from .splits import query_masks

METRICS = ('ndcg20', 'recall20', 'recall10')


def mean_metrics(rows):
    require(bool(rows), 'INSUFFICIENT_DATA: empty metric group')
    return {key: sum(row[key] for row in rows) / len(rows) for key in METRICS}


def grouped_metrics(rows, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    return [{**dict(zip(keys, group)), **mean_metrics(values)} for group, values in sorted(groups.items())]


def summaries(rows):
    require(bool(rows) and len({r['query_id'] for r in rows}) == len(rows), 'empty or duplicate query ledger')
    playlists = grouped_metrics(rows, ('playlist_id', 'curator_group_id', 'cluster_id', 'stratum'))
    curators = grouped_metrics(playlists, ('curator_group_id', 'cluster_id', 'stratum'))
    strata = grouped_metrics(curators, ('stratum',))
    return {'per_query': rows, 'per_playlist': playlists, 'per_curator_stratum': curators,
            'per_curator': grouped_metrics(playlists, ('curator_group_id',)),
            'per_stratum': strata, 'macro': mean_metrics(strata), 'playlist_macro': mean_metrics(playlists)}


def cluster_uncertainty(rows, *, draws=128, seed=1701):
    require(draws >= 2, 'bootstrap needs at least two draws')
    clusters = sorted({r['cluster_id'] for r in rows})
    if len(clusters) < 2:
        return {'status': 'INSUFFICIENT_DATA', 'standard_error': None, 'interval95': None, 'clusters': len(clusters)}
    rng = np.random.default_rng(seed)
    by_cluster = {key: [r for r in rows if r['cluster_id'] == key] for key in clusters}
    values = []
    for _ in range(draws):
        sampled = []
        for i, key in enumerate(rng.choice(clusters, size=len(clusters), replace=True)):
            for row in by_cluster[key]:
                # Each resampled cluster is a separate draw; keep masks together.
                sampled.append({**row, 'query_id': f"{i}/{row['query_id']}",
                                'playlist_id': f"{i}/{row['playlist_id']}",
                                'curator_group_id': f"{i}/{row['curator_group_id']}"})
        values.append(summaries(sampled)['macro']['ndcg20'])
    return {'status': 'READY', 'standard_error': float(np.std(values, ddof=1)),
            'interval95': [float(x) for x in np.quantile(values, [.025, .975])],
            'clusters': len(clusters), 'draws': draws, 'seed': seed}


@dataclass(frozen=True)
class Evaluation:
    role: Role
    model: Model
    feature_bundle_id: str
    catalog_hashes: tuple[str, ...]
    fold_reports: tuple[dict, ...]
    summary: dict
    uncertainty: dict

    def __post_init__(self):
        require(isinstance(self.role, Role), 'evaluation role required')
        for row in self.summary['per_query']:
            require(row['role'] == self.role, 'mixed evaluation roles')

    @property
    def identity(self):
        return digest(asdict(self))


def evaluate(features, model, folds, *, repetitions=1, bootstrap_draws=128):
    require(bool(folds), 'evaluation folds required')
    role = folds[0].evaluation_role
    require(all(p.evaluation_role == role for p in folds), 'mixed evaluation roles')
    rows, reports, catalogs = [], [], []
    for partition in folds:
        catalog, queries, excluded = query_masks(features.corpus, partition, repetitions=repetitions)
        catalogs.append(catalog.identity)
        fold_rows, scores = [], []
        for q in queries:
            ranks = rank_query(features, model, q, catalog)
            metrics = reconstruction_metrics([r['candidate_recording_id'] for r in ranks],
                        [r['candidate_recording_id'] for r in ranks if r['observed_membership'] == 'observed_positive'])
            row = {'query_id': q.query_id, 'playlist_id': q.playlist_id, 'curator_group_id': q.curator_group_id,
                   'cluster_id': q.cluster_id, 'stratum': q.stratum, 'layer': q.layer, 'role': role,
                   'fold_id': partition.split_id, **{k: metrics[k] for k in METRICS}}
            fold_rows.append(row)
            scores.append({'query': asdict(q), 'catalog_hash': catalog.identity, 'rows': ranks})
        rows.extend(fold_rows)
        reports.append({'fold_id': partition.split_id, 'catalog': asdict(catalog),
                        'metrics': summaries(fold_rows), 'scores': scores, 'excluded_queries': excluded})
    return Evaluation(role, model, features.identity, tuple(catalogs), tuple(reports), summaries(rows),
                      cluster_uncertainty(rows, draws=bootstrap_draws))


def audio_comparator(model):
    return Model(model.clap, model.rho, 0., 0., model.base)


def simplicity(model):
    signals = int(model.rho < 1) + int(model.rho > 0) + int(model.w_c > 0) + int(model.w_n > 0)
    return (signals, model.w_c, model.w_n, abs(model.rho - M3_RHO),
            model.rho, model.eta, model.clap.value, model.base)


def select_inner(evaluations, comparator_evaluations):
    require(evaluations, 'no candidate configurations')
    all_rows = list(evaluations) + list(comparator_evaluations.values())
    require(all(isinstance(e, Evaluation) and e.role == Role.INNER for e in all_rows),
            'selection accepts only inner-validation evidence; outer/lockbox/final prohibited')
    require(all(r['layer'] == Layer.ORIGINAL for e in all_rows for r in e.summary['per_query']), 'Layer B/C cannot select v1')
    require(len({(e.feature_bundle_id, e.catalog_hashes) for e in all_rows}) == 1,
            'candidate population or feature bundle differs across configurations')
    populations = {digest([{'fold_id': fold['fold_id'], 'queries': [score['query'] for score in fold['scores']]}
                           for fold in e.fold_reports]) for e in all_rows}
    require(len(populations) == 1, 'query masks differ across configurations')
    eligible, reasons = [], {}
    for e in evaluations:
        comparator_id = audio_comparator(e.model).identity
        require(comparator_id in comparator_evaluations, 'corresponding audio comparator missing')
        comparator = comparator_evaluations[comparator_id]
        if e.summary['macro']['recall20'] < comparator.summary['macro']['recall20'] - .02 - 1e-12:
            reasons[e.model.identity] = 'RECALL_GUARDRAIL'
        elif e.uncertainty['standard_error'] is None:
            reasons[e.model.identity] = 'INSUFFICIENT_INDEPENDENT_CLUSTERS'
        else:
            eligible.append(e)
    if not eligible:
        return {'status': 'INSUFFICIENT_DATA', 'selected_model_id': None, 'reasons': reasons}
    best = min(eligible, key=lambda e: (-e.summary['macro']['ndcg20'], simplicity(e.model)))
    floor = best.summary['macro']['ndcg20'] - best.uncertainty['standard_error']
    within = [e for e in eligible if e.summary['macro']['ndcg20'] >= floor - 1e-12]
    selected = min(within, key=lambda e: simplicity(e.model))
    for e in eligible:
        reasons[e.model.identity] = ('SELECTED_SIMPLICITY_WITHIN_ONE_SE' if e is selected else
                                    'SIMPLICITY_TIEBREAK' if e in within else 'OUTSIDE_ONE_SE')
    return {'status': 'READY', 'selected_model_id': selected.model.identity, 'reasons': reasons,
            'one_se_floor': floor, 'best_model_id': best.model.identity,
            'boundary_limited': selected.model.w_c == .1,
            'comparator_protocol': 'same representation/rho/audio base with genre coefficients zero'}


def load_selection_evaluation(path: Path):
    value = json.loads(path.read_text())
    require(value.get('schema') == 'inner-evaluation-v1' and value.get('role') == Role.INNER.value,
            'not an inner-validation selection artifact; lockbox/outer/final results prohibited')
    require(set(value) == {'schema', 'role', 'evaluation', 'sha256'}, 'selection envelope mismatch')
    require(digest(value['evaluation']) == value['sha256'], 'evaluation envelope hash mismatch')
    raw = value['evaluation']
    require(raw['role'] == Role.INNER.value, 'nested role mismatch')
    from .contracts import Clap, strict_fields
    model = strict_fields(Model, dict(raw['model'], clap=Clap(raw['model']['clap'])))
    return Evaluation(Role.INNER, model, raw['feature_bundle_id'], tuple(raw['catalog_hashes']),
                      tuple(raw['fold_reports']), raw['summary'], raw['uncertainty'])


def exhaustive_synthetic(features, inner_folds, *, output=None, bootstrap_draws=128):
    require(features.corpus.evidence_kind == 'SYNTHETIC', 'real parameter selection is not enabled in this scaffolding stage')
    require(all(p.evaluation_role == Role.INNER for p in inner_folds), 'search accepts inner folds only')
    registry = ablations()
    configs = {m.identity: m for models in registry.values() for m in models}
    for m in tuple(configs.values()):
        comparator = audio_comparator(m)
        configs[comparator.identity] = comparator
    evaluated = {key: evaluate(features, configs[key], inner_folds, bootstrap_draws=bootstrap_draws)
                 for key in sorted(configs)}
    selected = {arm: select_inner([evaluated[m.identity] for m in models], evaluated)
                for arm, models in registry.items()}
    ledger = []
    for key, e in evaluated.items():
        row = {'model_id': key, 'configuration': e.model.definition,
               'feature_bundle_id': features.identity, 'role': Role.INNER,
               'per_fold': [{'fold_id': f['fold_id'], 'metrics': f['metrics']} for f in e.fold_reports],
               'summary': e.summary, 'uncertainty': e.uncertainty,
               'arm_decisions': {arm: choice['reasons'][key] for arm, choice in selected.items() if key in choice['reasons']}}
        ledger.append(row)
        if output is not None:
            freeze_json(output / 'evaluations' / f'{key}.json', {'schema': 'inner-evaluation-v1',
                        'role': Role.INNER, 'evaluation': asdict(e), 'sha256': e.identity})
    result = {'schema': 'synthetic-search-v1', 'evidence_kind': 'SYNTHETIC',
              'ledger': ledger, 'arm_selection': selected, 'configuration_count_with_controls': len(evaluated)}
    if output is not None:
        freeze_json(output / 'search_ledger.json', result)
    return result, evaluated


def nested_synthetic(features, plan, *, output=None, bootstrap_draws=128):
    results = []
    for i, fold in enumerate(plan):
        inner, evaluated = exhaustive_synthetic(features, fold.inner,
                            output=output / f'outer_{i}' if output else None, bootstrap_draws=bootstrap_draws)
        outer_results = {}
        for arm, choice in inner['arm_selection'].items():
            if choice['selected_model_id'] is None:
                outer_results[arm] = {'status': 'INSUFFICIENT_DATA'}
                continue
            model = evaluated[choice['selected_model_id']].model
            outer_results[arm] = asdict(evaluate(features, model, (fold.outer,), bootstrap_draws=bootstrap_draws))
        results.append({'outer_split': asdict(fold.outer), 'inner_selection': inner['arm_selection'],
                        'outer_estimates': outer_results})
    result = {'schema': 'synthetic-nested-v1', 'role': Role.OUTER, 'folds': results,
              'warning': 'Synthetic mechanics only; outer results cannot select a model family.'}
    if output is not None:
        freeze_json(output / 'nested_estimates.json', result)
    return result
