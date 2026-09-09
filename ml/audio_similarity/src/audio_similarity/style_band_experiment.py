"""Freeze, execute and replay a small cached-output-only CLAP C prior study."""
from pathlib import Path
import argparse
import platform
import numpy as np

from .stage5e3_artifacts import read, freeze, freeze_json, hashes, verify_hashes, npz_bytes
from .stage5g1b_data import E3
from .style_prior_analysis import agreement, discrimination, interval
from .style_prior_verify import verify as verify_prior_cache
from .style_band_math import aggregate, mapping, adjust
from .style_band_metrics import (key, validate_folds, select, crossings, correction_summary,
                                 top_changes, cluster_interval, breakdown, verdict)

RUN = Path('reports/style_band_prior/v1')
PRIOR = Path('reports/style_prior_pilot/v2')


def prepare(root):
    run, prior = root / RUN, root / PRIOR
    if (run / 'input_hashes.json').exists():
        verify_hashes(root, read(run / 'input_hashes.json'))
        return
    cache = verify_prior_cache(root)
    config = read(root / 'configs/style_band_prior_v1.json')
    classes = read(prior / 'model_metadata.json')['classes']
    bands, weights, records = mapping(classes, config)
    if len(classes) != 400:
        raise ValueError('exact Discogs 400-style metadata required')
    freeze_json(run / 'protocol.json', config)
    freeze_json(run / 'mapping.json', {'classes': records, 'bands_with_unknown': bands,
                                      'effective_style_counts': dict(zip(bands, weights.sum(axis=0).tolist())),
                                      'parents': config['parents']})
    for name in ('tracks.json', 'evidence.json', 'folds.json', 'inventory.json'):
        freeze(run / name, (prior / name).read_bytes())
    freeze_json(run / 'cache_reuse.json', {'source': str(PRIOR), 'validated_cached_tracks': cache['valid_tracks'],
                                         'validated_cached_patches': cache['total_real_patches'],
                                         'new_audio_inference_calls': 0, 'aggregate_reconstruction_exact': True})
    freeze_json(run / 'environment.json', {'python': platform.python_version(), 'numpy': np.__version__})
    paths = list((root / 'src/audio_similarity').glob('style_band_*.py'))
    paths += [root / 'tests/test_style_band_prior.py', root / 'configs/style_band_prior_v1.json', root / 'docs/style_band_prior.md']
    paths += list(prior.iterdir()) + list((root / 'reports/style_embedding_control/v1').iterdir())
    paths += list(run.glob('*.json'))
    protected = read(prior / 'input_hashes.json') | hashes(paths, root)
    freeze_json(run / 'input_hashes.json', protected)
    verify_hashes(root, protected)


def _load(root):
    run, prior = root / RUN, root / PRIOR
    verify_hashes(root, read(run / 'input_hashes.json'))
    config = read(run / 'protocol.json')
    tracks = read(run / 'tracks.json')
    pairs = read(run / 'evidence.json')['playlist']
    folds = read(run / 'folds.json')
    validate_folds(tracks, pairs, folds)
    ids = [t['spotify_track_id'] for t in tracks]
    if ids != sorted(set(ids)) or len(ids) != 100:
        raise ValueError('exact ordered frozen 100 required')
    with np.load(prior / 'raw_style_means.npz', allow_pickle=False) as data:
        if set(data.files) != set(ids):
            raise ValueError('missing cached track')
        raw = np.stack([data[tid] for tid in ids])
    classes = read(prior / 'model_metadata.json')['classes']
    features = aggregate(raw, classes, config)
    with np.load(root / E3 / 'historical_reference_matrices.npz', allow_pickle=False) as data:
        old = list(data['spotify_ids'])
        if set(old) != set(ids) or len(old) != len(ids):
            raise ValueError('C identity mismatch')
        ix = [old.index(tid) for tid in ids]
        c = data['c_clap'][np.ix_(ix, ix)]
    with np.load(prior / 'style_distributions.npz', allow_pickle=False) as data:
        old = list(data['ids'])
        ix = [old.index(tid) for tid in ids]
        raw_distance = data['distances'][np.ix_(ix, ix)]
    np.testing.assert_allclose(c, c.T, atol=1e-12, rtol=0)
    np.testing.assert_allclose(c.diagonal(), 1, atol=1e-6, rtol=0)
    def lookup(matrix):
        return {(a, b): float(matrix[i, j]) for i, a in enumerate(ids) for j, b in enumerate(ids) if a < b}
    return config, tracks, pairs, folds, features, c, lookup(c), lookup(features['distance']), lookup(raw_distance)


def evaluate(root):
    run = root / RUN
    config, tracks, pairs, folds, features, c, scores, distance, raw_distance = _load(root)
    ids = [t['spotify_track_id'] for t in tracks]
    ratings = {key(*p['tracks']): p['rating'] for p in pairs}
    track_bands = {}
    for i, tid in enumerate(ids):
        band = str(features['bands'][int(np.argmax(features['band_profiles'][i]))])
        parent = str(features['parents'][int(np.argmax(features['parent_profiles'][i]))])
        track_bands[tid] = {'band': band if features['known_fraction'][i] > 0 else 'unknown',
                            'parent': parent if features['known_fraction'][i] > 0 else 'unknown',
                            'known_fraction': float(features['known_fraction'][i])}
    excluded_artists = set(read(run / 'inventory.json')['diagnostic_artist_exclusions'])
    excluded = {t['spotify_track_id'] for t in tracks if any(a.casefold().strip() in excluded_artists for a in t['artists'])}
    fold_results, events, top_grouped, top_full = [], [], [], []
    per = {name: {} for name in ('C', 'band', 'raw_style_control')}
    excluded_per, strong_per = {}, {}
    for fold in folds:
        heldout = fold['heldout_preferences']
        if len(heldout) < config['minimum_fold_preferences'] or len({p['anchor'] for p in heldout}) < config['minimum_fold_anchors']:
            raise ValueError('insufficient frozen grouped evidence; do not weaken split')
        strength, grid = select(scores, distance, fold['train_preferences'], config['conditional_penalty']['lambdas'])
        adjusted = adjust(scores, distance, strength)
        raw_strength, raw_grid = select(scores, raw_distance, fold['train_preferences'], config['conditional_penalty']['lambdas'])
        variants = {'C': scores, 'band': adjusted, 'raw_style_control': adjust(scores, raw_distance, raw_strength)}
        metrics = {name: agreement(values, heldout) for name, values in variants.items()}
        for name in per:
            per[name].update(metrics[name]['per_anchor'])
        sensitivities = {}
        for name, subset, destination in [
            ('exclude_diagnostic_artists', [p for p in heldout if not {p['anchor'], p['preferred'], p['other']} & excluded], excluded_per),
            ('strong', [p for p in heldout if p['gap'] >= 2], strong_per),
        ]:
            base, modified = agreement(scores, subset), agreement(adjusted, subset)
            destination.update({a: modified['per_anchor'][a] - v for a, v in base['per_anchor'].items()})
            sensitivities[name] = {'C': base, 'band': modified}
        changes = [r | {'fold': fold['fold']} for r in crossings(scores, adjusted, heldout, ratings)]
        events.extend(changes)
        grouped = top_changes(scores, adjusted, fold['heldout'], fold['heldout'], ratings, config['top_k'])
        full = top_changes(scores, adjusted, fold['heldout'], ids, ratings, config['top_k'])
        top_grouped.extend(r | {'fold': fold['fold']} for r in grouped['rows'])
        top_full.extend(r | {'fold': fold['fold']} for r in full['rows'])
        fold_results.append({'fold': fold['fold'], 'lambda': strength, 'training_grid': grid,
                             'raw_control_lambda': raw_strength, 'raw_control_training_grid': raw_grid,
                             'metrics': metrics, 'sensitivities': sensitivities, 'corrections': correction_summary(changes),
                             'top5_grouped': grouped['counts'], 'top5_all_candidates_diagnostic': full['counts']})
    deltas = {a: per['band'][a] - value for a, value in per['C'].items()}
    parent_breakdown = breakdown(deltas, track_bands, 'parent')
    corrections = correction_summary(events)
    delta, clustered = interval(list(deltas.values())), cluster_interval(deltas, tracks)
    decision = verdict(delta, clustered, corrections, parent_breakdown, interval(list(excluded_per.values())), config)
    top5 = {a: set(sorted((b for b in ids if b != a), key=lambda b: (-scores[key(a, b)], b))[:5]) for a in ids}
    high = [p for p in pairs if p['tracks'][0] in top5[p['tracks'][1]] or p['tracks'][1] in top5[p['tracks'][0]]]
    diagnostics = {name: {'all': discrimination(pairs, values, scores),
                           'C_caliper': discrimination(pairs, values, scores, config['cosine_caliper']),
                           'either_direction_C_top5': discrimination(high, values, scores)}
                   for name, values in [('band_distance', distance), ('raw_style_distance', raw_distance),
                                        ('C_distance', {k: 1-v for k, v in scores.items()})]}
    results = {'folds': fold_results, 'performance': {name: interval(list(values.values())) for name, values in per.items()},
               'paired_delta': delta, 'clustered_paired_delta': clustered, 'anchors': len(deltas),
               'preferences': len(events), 'per_anchor_delta': deltas, 'corrections': corrections,
               'strong_delta': interval(list(strong_per.values())), 'exclude_diagnostic_artists_delta': interval(list(excluded_per.values())),
               'parent_breakdown': parent_breakdown, 'band_breakdown': breakdown(deltas, track_bands, 'band'),
               'distance_diagnostics_all_development': diagnostics, 'decision': decision}
    pair_rows = []
    for p in pairs:
        a, b = p['tracks']
        fold = next((f for f in fold_results if set((a, b)) <= set(folds[f['fold']]['heldout'])), None)
        pair_rows.append(p | {'C': scores[key(a, b)], 'band_distance': distance[key(a, b)],
                             'raw_style_distance': raw_distance[key(a, b)], 'bands': [track_bands[a], track_bands[b]],
                             'fold': fold['fold'] if fold else None,
                             'adjusted_C': scores[key(a, b)] - fold['lambda'] * distance[key(a, b)] if fold else None,
                             'status': 'GROUPED_EVALUATION' if fold else 'CROSS_GROUP_NOT_PRIMARY'})
    freeze(run / 'band_features.npz', npz_bytes({'ids': np.array(ids), 'C': c, **features}))
    for name, value in [('results', results), ('track_bands', track_bands), ('pair_results', pair_rows),
                        ('preference_changes', events), ('top5_grouped', top_grouped), ('top5_all_candidates_diagnostic', top_full)]:
        freeze_json(run / (name + '.json'), value)
    return results


def replay(root):
    run = root / RUN
    names = ['band_features.npz', 'results.json', 'track_bands.json', 'pair_results.json',
             'preference_changes.json', 'top5_grouped.json', 'top5_all_candidates_diagnostic.json']
    before = hashes([run / name for name in names], run)
    if len(before) != len(names):
        raise ValueError('initial run required before replay')
    evaluate(root)
    verify_hashes(run, before)
    verify_hashes(root, read(run / 'input_hashes.json'))
    freeze_json(run / 'replay.json', {'exact_artifact_hashes': before, 'byte_identical': True,
                                     'new_audio_inference_calls': 0, 'cached_track_outputs_reused': 100,
                                     'historical_inputs_unchanged': True})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'evaluate', 'replay'])
    args = parser.parse_args()
    value = {'prepare': prepare, 'evaluate': evaluate, 'replay': replay}[args.command](Path.cwd())
    if value:
        print(value['decision'])
