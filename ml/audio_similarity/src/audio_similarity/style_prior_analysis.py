"""Predeclared style distance evaluation; historical development data only."""
from collections import defaultdict
from itertools import combinations
from pathlib import Path
import numpy as np
from .stage5e3_artifacts import read, freeze, freeze_json, hashes, verify_hashes, npz_bytes
from .stage5g1b_data import E3
from .style_prior import RUN, distributions, distances


def interval(values):
    x = np.asarray(values, dtype=np.float64)
    if not len(x):
        return {'point': None, 'low': None, 'high': None}
    rng = np.random.default_rng(5101)
    means = x[rng.integers(0, len(x), (5000, len(x)))].mean(axis=1)
    lo, hi = np.quantile(means, [.025, .975])
    return {'point': float(x.mean()), 'low': float(lo), 'high': float(hi)}


def win(delta):
    return .5 if abs(delta) <= 1e-6 else float(delta > 0)


def discrimination(pairs, distance, scores, caliper=None):
    by = defaultdict(lambda: {'good': [], 'bad': []})
    for p in pairs:
        if p['rating'] == 3:
            continue
        a, b = p['tracks']
        bucket = 'good' if p['rating'] >= 4 else 'bad'
        key = tuple(sorted((a, b)))
        for anchor in (a, b):
            by[anchor][bucket].append((distance[key], scores[key]))
    per = {}
    comparisons = 0
    for anchor, rows in sorted(by.items()):
        values = [win(bad[0] - good[0]) for good in rows['good'] for bad in rows['bad']
                  if caliper is None or abs(good[1] - bad[1]) <= caliper]
        if values:
            per[anchor] = float(np.mean(values))
            comparisons += len(values)
    return {'anchors': len(per), 'comparisons': comparisons, 'macro_auc': interval(list(per.values())), 'per_anchor': per,
            'bad_mean_distance': _mean([distance[tuple(sorted(p['tracks']))] for p in pairs if p['rating'] <= 2]),
            'good_mean_distance': _mean([distance[tuple(sorted(p['tracks']))] for p in pairs if p['rating'] >= 4])}


def _mean(values):
    return float(np.mean(values)) if values else None


def agreement(scores, constraints):
    per = defaultdict(list)
    for p in constraints:
        a = p['anchor']
        per[a].append(win(scores[tuple(sorted((a, p['preferred'])))] - scores[tuple(sorted((a, p['other'])))]))
    values = {a: float(np.mean(v)) for a, v in sorted(per.items())}
    return {'preferences': len(constraints), 'anchors': len(values), 'macro': _mean(list(values.values())), 'per_anchor': values}


def signal_passes(result, gate):
    overall, high, caliper = result['all'], result['high_D_top10'], result['cosine_caliper']
    def above(value, threshold):
        return value is not None and value > threshold
    return (overall['anchors'] >= gate['minimum_anchors']
            and above(overall['macro_auc']['low'], gate['macro_auc_lower_bound_above'])
            and above(high['macro_auc']['point'], gate['high_neighbor_macro_auc_above'])
            and above(caliper['macro_auc']['point'], gate['caliper_macro_auc_above']))


def penalty_cv(scores, distance, folds, config):
    results = []
    deltas = {}
    for fold in folds:
        heldout = fold['heldout_preferences']
        if len(heldout) < config['minimum_fold_preferences'] or len({p['anchor'] for p in heldout}) < config['minimum_fold_anchors']:
            return {'status': 'INSUFFICIENT_GROUPED_EVIDENCE'}
        train_ids, test_ids = set(fold['train']), set(fold['heldout'])
        if train_ids & test_ids:
            raise ValueError('track leakage')
        for name, allowed in [('train_preferences', train_ids), ('heldout_preferences', test_ids)]:
            if any(not {p['anchor'], p['preferred'], p['other']} <= allowed for p in fold[name]):
                raise ValueError('preference leakage')
        candidates = []
        for lam in config['conditional_penalty']['lambdas']:
            adjusted = {key: value - lam * distance[key] for key, value in scores.items()}
            train = agreement(adjusted, fold['train_preferences'])
            candidates.append((lam, adjusted, train))
        best = max(row[2]['macro'] for row in candidates)
        lam, adjusted, train = next(row for row in candidates if row[2]['macro'] >= best - 1e-12)
        baseline = agreement(scores, heldout)
        corrected = agreement(adjusted, heldout)
        for anchor, value in corrected['per_anchor'].items():
            deltas[anchor] = value - baseline['per_anchor'][anchor]
        strong = [p for p in heldout if p['gap'] >= 2]
        results.append({'fold': fold['fold'], 'lambda': lam, 'training': train, 'baseline': baseline, 'penalty': corrected,
                        'training_grid': [{'lambda': row[0], 'macro': row[2]['macro']} for row in candidates],
                        'strong_baseline': agreement(scores, strong), 'strong_penalty': agreement(adjusted, strong)})
    return {'status': 'DEVELOPMENT_ONLY', 'folds': results, 'paired_anchor_delta': interval(list(deltas.values())), 'per_anchor_delta': deltas}


def main(root):
    run = root / RUN
    verify_hashes(root, read(run / 'input_hashes.json'))
    # Freeze analysis implementation before loading classifier outputs.
    freeze_json(run / 'analysis_identity.json', hashes([Path(__file__), root / 'tests/test_style_prior.py'], root))
    config = read(run / 'protocol.json')
    tracks = read(run / 'tracks.json')
    ids = [t['spotify_track_id'] for t in tracks]
    with np.load(run / 'raw_style_means.npz', allow_pickle=False) as data:
        if set(data.files) != set(ids):
            raise ValueError('full 100-track extraction required')
        raw = np.stack([data[t] for t in ids])
    profiles = distributions(raw, config['epsilon'])
    matrix = distances(profiles)
    freeze(run / 'style_distributions.npz', npz_bytes({'ids': np.array(ids), 'profiles': profiles, 'distances': matrix}))
    positions = {tid: i for i, tid in enumerate(ids)}
    distance = {(a, b): float(matrix[positions[a], positions[b]]) for a, b in combinations(ids, 2)}
    with np.load(root / E3 / 'historical_reference_matrices.npz', allow_pickle=False) as data:
        old = list(data['spotify_ids'])
        ix = [old.index(tid) for tid in ids]
        baselines = {name: data[field][np.ix_(ix, ix)] for name, field in [('D', 'd_clap'), ('C', 'c_clap')]}
    scores = {name: {(a, b): float(mat[positions[a], positions[b]]) for a, b in combinations(ids, 2)} for name, mat in baselines.items()}
    top10 = {a: set(sorted((b for b in ids if b != a), key=lambda b: (-scores['D'][tuple(sorted((a, b)))], b))[:10]) for a in ids}
    excluded = set(read(run / 'inventory.json')['diagnostic_artist_exclusions'])
    eligible = {t['spotify_track_id'] for t in tracks if not any(a.casefold().strip() in excluded for a in t['artists'])}
    evidence = read(run / 'evidence.json')
    results = {}
    pair_rows = []
    for rubric, pairs in evidence.items():
        high = [p for p in pairs if p['tracks'][0] in top10[p['tracks'][1]] or p['tracks'][1] in top10[p['tracks'][0]]]
        results[rubric] = {'all': discrimination(pairs, distance, scores['D']),
                           'high_D_top10': discrimination(high, distance, scores['D']),
                           'cosine_caliper': discrimination(pairs, distance, scores['D'], config['cosine_caliper']),
                           'exclude_diagnostic_artists': discrimination([p for p in pairs if set(p['tracks']) <= eligible], distance, scores['D']),
                           'C_cosine_caliper': discrimination(pairs, distance, scores['C'], config['cosine_caliper'])}
        for pair in pairs:
            key = tuple(sorted(pair['tracks']))
            pair_rows.append(pair | {'rubric': rubric, 'style_distance': distance[key], 'D_cosine': scores['D'][key], 'C_cosine': scores['C'][key], 'high_D_top10': pair in high})
    passed = signal_passes(results['playlist'], config['signal_gate'])
    results['signal_gate_passes'] = passed
    results['penalty'] = {name: penalty_cv(score, distance, read(run / 'folds.json'), config) for name, score in scores.items()} if passed else {'status': 'NOT_RUN_SIGNAL_GATE_FAILED'}
    metadata = read(run / 'model_metadata.json')
    classes = metadata['classes']
    descriptions = []
    for i, track in enumerate(tracks):
        best = sorted(range(400), key=lambda j: (-raw[i, j], j))[:10]
        descriptions.append({'track_id': ids[i], 'title': track['title'], 'artist': track['artist_credit'],
                             'raw_sigmoid_sum': float(raw[i].sum()),
                             'top_styles': [{'style': classes[j], 'raw_score': float(raw[i, j]), 'normalized_mass': float(profiles[i, j])} for j in best]})
    freeze_json(run / 'track_styles.json', descriptions)
    freeze_json(run / 'pair_results.json', sorted(pair_rows, key=lambda p: (p['rubric'], p['pair_id'])))
    freeze_json(run / 'results.json', results)
    print({k: results['playlist'][k]['macro_auc'] for k in ('all', 'high_D_top10', 'cosine_caliper', 'exclude_diagnostic_artists')})
    print('signal_gate_passes', passed)


if __name__ == '__main__':
    main(Path.cwd())
