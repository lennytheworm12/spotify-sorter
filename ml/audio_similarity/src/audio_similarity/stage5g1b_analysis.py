"""Descriptive, anchor-macro evaluation of frozen zero-shot mismatch signals."""
from collections import defaultdict
from pathlib import Path
import argparse
import json
import numpy as np
from .stage5e3_artifacts import read, freeze, freeze_json, npz_bytes, verify_hashes
from .stage5g1b_data import G1, G1A, prepare
from .stage5g1b_probes import profiles, compare, materialize_text


def summarize(rows, field='distance', confidence=.9875):
    """Only explicitly rated good/bad pairs; score ties receive half credit."""
    anchors = defaultdict(lambda: {'good': [], 'bad': []})
    bad, good = [], []
    for row in rows:
        kind = 'bad' if row['rating'] <= 2 else 'good' if row['rating'] >= 4 else None
        if kind is None:
            continue
        (bad if kind == 'bad' else good).append(row)
        for anchor in row['tracks']:
            anchors[anchor][kind].append(row[field])
    auc = {}
    for anchor, data in sorted(anchors.items()):
        if data['bad'] and data['good']:
            difference = np.array(data['bad'])[:, None] - np.array(data['good'])[None, :]
            auc[anchor] = float(np.mean(np.where(np.abs(difference) <= 1e-12, .5, difference > 0)))
    values = np.array(list(auc.values()))
    if len(values):
        rng = np.random.default_rng(20260909)
        samples = values[rng.integers(0, len(values), (2000, len(values)))].mean(axis=1)
        alpha = (1 - confidence) / 2
        bounds = np.quantile(samples, [alpha, 1 - alpha]).tolist()
    else:
        bounds = [None, None]
    def rates(items):
        return {'pairs': len(items), 'flag_rate': sum(r['flag'] is True for r in items) / len(items) if items else None,
                'abstention_rate': sum(r['flag'] is None for r in items) / len(items) if items else None}
    return {'anchors': len(auc), 'macro_auc': float(values.mean()) if len(values) else None,
            'interval': bounds, 'per_anchor': auc, 'bad': rates(bad), 'good': rates(good)}


def axis_gate(main, variants, sensitivity, neighbors, excluded, leave_artist, config):
    gate = config['gate']
    def credible(result):
        return (result['anchors'] >= gate['minimum_anchors'] and result['macro_auc'] >= gate['minimum_macro_auc']
                and result['interval'][0] > .5 and result['bad']['flag_rate'] >= gate['minimum_bad_flag_rate']
                and result['good']['flag_rate'] <= gate['maximum_good_flag_rate'])
    return bool(all(credible(r) for r in [main, *variants, sensitivity])
                and neighbors['anchors'] >= gate['minimum_neighbor_anchors'] and neighbors['macro_auc'] > .5
                and excluded['anchors'] >= gate['minimum_neighbor_anchors'] and excluded['macro_auc'] > .5
                and leave_artist and min(leave_artist.values()) >= gate['minimum_leave_artist_out_auc'])


def run_analysis(root, run):
    verify_hashes(root, read(run / 'input_hashes.json'))
    config = read(run / 'protocol.json')
    tracks = read(run / 'tracks.json')
    artists = {t['spotify_track_id']: {a.casefold().strip() for a in t['artists']} for t in tracks}
    with np.load(run / 'text_vectors.npz', allow_pickle=False) as z:
        text = z['vectors']
    track_profiles = {}
    for name, path in [('segments', root / G1 / 'segments.npz'), ('D', root / G1A / 'd_views.npz')]:
        with np.load(path, allow_pickle=False) as z:
            track_profiles[name] = {id: profiles(z[id], text, config) for id in sorted(z.files)}
    freeze_json(run / 'track_profiles.json', track_profiles)
    with np.load(root / G1 / 'b0_matrix.npz', allow_pickle=False) as z:
        ids, matrix = list(z['ids']), z['scores']
    top = {id: {ids[j] for j in sorted((j for j in range(len(ids)) if ids[j] != id),
                                     key=lambda j: (-matrix[i, j], ids[j]))[:10]} for i, id in enumerate(ids)}
    diagnostic_artists = set(read(run / 'inventory.json')['diagnostic_artist_exclusions'])
    excluded_ids = {id for id, credits in artists.items() if credits & diagnostic_artists}
    all_rows, results = [], {}
    for rubric, pairs in read(run / 'evidence.json').items():
        axis_rows = {}
        for axis in sorted(config['axes']):
            rows, d_rows = [], []
            for pair in pairs:
                a, b = pair['tracks']
                record = pair | compare(track_profiles['segments'][a][axis], track_profiles['segments'][b][axis])
                record['neighbor'] = b in top[a] or a in top[b]
                record['variant0'], record['variant1'] = record.pop('variant_distances')
                rows.append(record)
                d_rows.append(pair | compare(track_profiles['D'][a][axis], track_profiles['D'][b][axis]))
                all_rows.append(record | {'rubric': rubric, 'axis': axis})
            axis_rows[axis] = rows
            main = summarize(rows)
            variants = [summarize(rows, f'variant{v}') for v in range(2)]
            sensitivity = summarize(d_rows)
            neighbors = summarize([r for r in rows if r['neighbor']])
            excluded = summarize([r for r in rows if not set(r['tracks']) & excluded_ids])
            leave_artist = {}
            for artist in sorted(set.union(*artists.values())):
                remaining = [r for r in rows if all(artist not in artists[id] for id in r['tracks'])]
                estimate = summarize(remaining)
                if estimate['anchors'] >= config['gate']['minimum_anchors']:
                    leave_artist[artist] = estimate['macro_auc']
            results.setdefault(rubric, {})[axis] = {
                'primary': main, 'paraphrases': variants, 'D_sensitivity': sensitivity,
                'high_D_neighbors': neighbors, 'exclude_diagnostic_artists': excluded,
                'leave_one_artist_out_auc': leave_artist,
                'passes': axis_gate(main, variants, sensitivity, neighbors, excluded, leave_artist, config)}
        union = []
        for i, pair in enumerate(pairs):
            rs = [axis_rows[a][i] for a in sorted(axis_rows)]
            flags = [r['flag'] for r in rs]
            union.append(pair | {'distance': max(r['distance'] for r in rs),
                                 'flag': True if True in flags else None if None in flags else False})
        results[rubric]['any_axis_descriptive'] = summarize(union, confidence=.95)
    freeze_json(run / 'pair_probes.json', all_rows)
    freeze_json(run / 'results.json', results)
    passing = [axis for axis in config['axes'] if results['playlist'][axis]['passes']]
    diagnosis = {'outcome': 'PROMISING_ZERO_SHOT_SIGNAL' if passing else 'ZERO_SHOT_NOT_ESTABLISHED',
                 'passing_axes': sorted(passing), 'causal_taxonomy_validated': False,
                 'fresh_confirmatory_evidence': False, 'production_activation': False}
    freeze_json(run / 'diagnosis.json', diagnosis)
    return diagnosis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'extract', 'replay', 'analyze', 'verify'])
    command = parser.parse_args().command
    root = Path(__file__).resolve().parents[2]
    run = root / 'reports/stage5g1b_identity_probes/v1'
    if command == 'prepare':
        result = prepare(root, run)
    else:
        verify_hashes(root, read(run / 'input_hashes.json'))
        if command in ('extract', 'replay'):
            result = materialize_text(root, run, replay=command == 'replay')
        elif command == 'analyze':
            result = run_analysis(root, run)
        else:
            result = {'historical_hashes': 'PASS'}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
