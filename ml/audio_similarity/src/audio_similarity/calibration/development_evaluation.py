"""Cached-array evaluation with parity to the small reference harness."""
from collections import Counter, defaultdict
from dataclasses import asdict
import io

import numpy as np

from .contracts import Clap, freeze_json, require
from .ranking import distinct_ids
from .search import Evaluation, METRICS, summaries
from .splits import query_masks


def freeze_npy(path, values):
    stream = io.BytesIO()
    np.save(stream, values, allow_pickle=False)
    raw = stream.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == raw, 'cached score/rank replay differs')
    else:
        path.write_bytes(raw)


def bootstrap_weights(rows, *, draws=2000, seed=1701):
    """Linear weights exactly matching curator-cluster resampling in search.py.

    Repeated draws of a cluster create independent copies of its playlists and
    curators. Empty strata disappear from that draw, as in the reference method.
    No metric values or model scores enter the resampling design.
    """
    clusters = sorted({r['cluster_id'] for r in rows})
    if len(clusters) < 2:
        return None
    counts = Counter((r['playlist_id'], r['curator_group_id'], r['stratum']) for r in rows)
    playlists = defaultdict(set)
    cs = defaultdict(set)
    for r in rows:
        playlists[r['curator_group_id'], r['stratum']].add(r['playlist_id'])
        cs[r['cluster_id'], r['stratum']].add(r['curator_group_id'])
    rng = np.random.default_rng(seed)
    weights = []
    for _ in range(draws):
        sampled = Counter(rng.choice(clusters, size=len(clusters), replace=True))
        strata = Counter()
        for (cluster, stratum), curators in cs.items():
            strata[stratum] += sampled[cluster] * len(curators)
        nstrata = sum(v > 0 for v in strata.values())
        weights.append([sampled[r['cluster_id']] / (nstrata * strata[r['stratum']] *
            len(playlists[r['curator_group_id'], r['stratum']]) * counts[r['playlist_id'], r['curator_group_id'], r['stratum']])
            if strata[r['stratum']] else 0 for r in rows])
    return np.asarray(weights, dtype=np.float64)


def complete_matrices(features, models):
    out = []
    for model in models:
        if model.base == 'frozen_m3':
            audio = features.matrices['M3']
        else:
            key = 'C_center30' if model.clap == Clap.CENTERED else 'C_method_c'
            audio = (1-model.rho) * features.matrices[key] + model.rho * features.matrices['M']
        out.append(audio + model.w_c * features.matrices['Jc'] + model.w_n * features.matrices['R'])
    return np.asarray(out)


def evaluate_many(features, models, folds, *, repetitions=8, draws=2000, seed=1701, output=None):
    require(models and folds, 'models/folds required')
    role = folds[0].evaluation_role
    require(all(p.evaluation_role == role for p in folds), 'mixed evaluation role')
    positions = {key: i for i, key in enumerate(features.track_ids)}
    complete = complete_matrices(features, models)
    rows, metrics, reports, catalogs = [], [], [], []
    for fi, partition in enumerate(folds):
        catalog, queries, excluded = query_masks(features.corpus, partition, repetitions=repetitions)
        catalogs.append(catalog.identity)
        query_refs, indices = [], []
        for qi, q in enumerate(queries):
            candidates = distinct_ids(features, catalog.recording_ids, exclude=q.seed_ids)
            seeds = distinct_ids(features, q.seed_ids)
            a, b = [positions[k] for k in candidates], [positions[k] for k in seeds]
            pair = complete[:, a][:, :, b]
            # Sort complete F before choosing support. Largest first matches the
            # reference's summation order; stable ties preserve seed ID order.
            top = np.sort(pair, axis=2)[:, :, ::-1][:, :, :min(3, len(b))]
            scores = sum(top[:, :, i] for i in range(top.shape[2])) / top.shape[2]
            order = np.argsort(-scores, axis=1, kind='stable')
            hidden = {features.records[k].version_group_id for k in q.hidden_ids}
            positive = np.asarray([features.records[k].version_group_id in hidden for k in candidates])
            require(int(positive.sum()) == len(hidden), 'hidden positive lost from common catalog')
            relevance = positive[order]
            discount = 1 / np.log2(np.arange(min(20, len(candidates))) + 2)
            ideal = sum(1 / np.log2(i+2) for i in range(min(20, int(positive.sum()))))
            result = np.column_stack(((relevance[:, :20] * discount).sum(axis=1) / ideal,
                relevance[:, :20].sum(axis=1) / positive.sum(), relevance[:, :10].sum(axis=1) / positive.sum()))
            row = {'query_id': q.query_id, 'playlist_id': q.playlist_id, 'curator_group_id': q.curator_group_id,
                'cluster_id': q.cluster_id, 'stratum': q.stratum, 'layer': q.layer, 'role': role, 'fold_id': partition.split_id}
            indices.append(len(rows))
            rows.append(row)
            metrics.append(result)
            reference = {'query': asdict(q), 'catalog_hash': catalog.identity, 'candidate_ids': candidates,
                'observed_positive_ids': [k for k, p in zip(candidates, positive) if p],
                'other_candidate_status': 'unlabeled'}
            if output is not None:
                stem = f'scores/fold{fi}/query{qi}'
                freeze_npy(output / (stem + '.scores.npy'), scores)
                freeze_npy(output / (stem + '.ranks.npy'), order.astype('<u4'))
                reference.update(scores_file=stem + '.scores.npy', ranks_file=stem + '.ranks.npy')
            query_refs.append(reference)
        reports.append({'fold_id': partition.split_id, 'catalog': asdict(catalog),
            'scores': query_refs, 'excluded_queries': excluded, 'row_indices': indices})
    # [model, query, metric]. One common bootstrap matrix for every configuration.
    values = np.asarray(metrics).transpose(1, 0, 2)
    weights = bootstrap_weights(rows, draws=draws, seed=seed)
    samples = None if weights is None else values[:, :, 0] @ weights.T
    if output is not None:
        freeze_json(output / 'score_index.json', {'model_ids': [m.identity for m in models], 'folds': reports})
    evaluated = {}
    for i, model in enumerate(models):
        mr = [r | dict(zip(METRICS, (float(x) for x in values[i, j]))) for j, r in enumerate(rows)]
        uncertainty = {'status': 'INSUFFICIENT_DATA', 'standard_error': None, 'interval95': None,
            'clusters': len({r['cluster_id'] for r in rows})}
        if samples is not None:
            uncertainty.update(status='READY', standard_error=float(np.std(samples[i], ddof=1)),
                interval95=[float(x) for x in np.quantile(samples[i], [.025, .975])], draws=draws, seed=seed)
        fold_reports = tuple({k: v for k, v in f.items() if k != 'row_indices'} |
            {'metrics': summaries([mr[j] for j in f['row_indices']])} for f in reports)
        evaluated[model.identity] = Evaluation(role, model, features.identity, tuple(catalogs), fold_reports,
            summaries(mr), uncertainty)
    return evaluated
