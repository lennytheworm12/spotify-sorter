"""Independent arithmetic and provenance audit of a frozen genre explorer packet.

Run with the ML virtualenv; this reads existing evidence and performs no inference.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def overlap(a, b):
    keys = sorted(a.keys() | b.keys())
    denominator = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return sum(min(a.get(k, 0), b.get(k, 0)) for k in keys) / denominator if denominator else 0


def project_residual(vector, concepts):
    result = {}
    for key, value in vector.items():
        concept = concepts[key]
        if concept['kind'] not in ('style', 'style_umbrella'):
            continue
        for neighborhood, strength in concept['neighborhoods'].items():
            result[neighborhood] = max(result.get(neighborhood, 0), value * strength)
    return result


def audit(run):
    repo = Path(__file__).resolve().parents[2]
    ml = repo / 'ml/audio_similarity'
    packet = read(run / 'explorer.json')
    manifest = read(run / 'artifact_manifest.json')
    for name, expected in manifest['files'].items():
        assert digest(run / name) == expected, name
    for name, expected in packet['provenance']['input_hashes'].items():
        assert digest(ml / name) == expected, name
    for name, expected in packet['provenance']['frontendImplementationHashes'].items():
        assert digest(repo / 'frontend' / name) == expected, name

    source = ml / 'reports/gemini_style_pilot/frozen100_free_genre_v1'
    matrix_path = ml / 'reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/similarity_matrices.npz'
    with np.load(matrix_path, allow_pickle=False) as matrices:
        ids = list(map(str, matrices['spotify_ids']))
        matrix = matrices[packet['provenance']['audio_matrix_key']].copy()
    songs = {s['id']: s for s in packet['songs']}
    assert len(ids) == len(songs) == 100 and set(ids) == songs.keys()
    lookup = {key: i for i, key in enumerate(ids)}
    assert np.array_equal(matrix, matrix.T) and np.isfinite(matrix).all()
    for song in songs.values():
        profile = read(source / 'profiles' / (song['pilotId'] + '.json'))
        assert profile['spotify_track_id'] == song['id']
        assert profile['profile'] == song['raw'], 'Raw Gemini fields changed'

    evidence = read(run / 'pair_genre_evidence.json')
    rankings = read(run / 'baseline_rankings.json')
    assert len(evidence) == len(packet['pairs']) == 4950
    assert set(rankings) == songs.keys()
    assert [(p['a'], p['b']) for p in evidence] == sorted((p['a'], p['b']) for p in evidence)
    assert len({(p['a'], p['b']) for p in evidence}) == 4950
    assert all(p['a'] < p['b'] for p in evidence)
    checked_noop = 0
    for original, pair in zip(packet['pairs'], evidence, strict=True):
        assert original == {k: pair[k] for k in ('a', 'b', 'audio')}
        a, b = songs[pair['a']], songs[pair['b']]
        assert pair['audio'] == float(matrix[lookup[a['id']], lookup[b['id']]])
        ca, cb = a['canonical'], b['canonical']
        keys = ca.keys() | cb.keys()
        ra = {k: max(0, ca.get(k, 0) - cb.get(k, 0)) for k in keys}
        rb = {k: max(0, cb.get(k, 0) - ca.get(k, 0)) for k in keys}
        usable = bool(a['specificStyleIds'] and b['specificStyleIds'])
        assert pair['available'] == usable
        expected = {
            'jc': overlap(ca, cb) if usable else 0,
            'jnr': overlap(project_residual(ra, packet['concepts']), project_residual(rb, packet['concepts'])),
            'jn': overlap(a['neighborhoods'], b['neighborhoods']),
        }
        for key, value in expected.items():
            assert math.isclose(pair[key], value, rel_tol=0, abs_tol=1e-15), (a['id'], b['id'], key)
        checked_noop += not usable

    for key in songs:
        eligible = sorted((other for other in ids if other != key),
                          key=lambda other: (-float(matrix[lookup[key], lookup[other]]), other))
        assert rankings[key] == [
            {'id': other, 'rank': rank, 'audio': float(matrix[lookup[key], lookup[other]])}
            for rank, other in enumerate(eligible, 1)
        ], key
    return {
        'status': 'PASS',
        'tracks': 100,
        'unordered_pairs': 4950,
        'directed_baseline_ranks_exact': 9900,
        'arithmetic_oracle': 'independent Python weighted Jaccard / mass subtraction / max projection',
        'arithmetic_tolerance': 1e-15,
        'audio_matrix_key': packet['provenance']['audio_matrix_key'],
        'matrix_sha256': digest(matrix_path),
        'raw_gemini_profiles_unchanged': 100,
        'source_identity_matches': sum(c['same_source'] for c in packet['provenance']['source_checks']),
        'pairs_with_insufficient_specific_style': checked_noop,
        'input_hashes_verified': len(packet['provenance']['input_hashes']),
        'frontend_implementation_hashes_verified': len(packet['provenance']['frontendImplementationHashes']),
        'run_manifest_sha256': digest(run / 'artifact_manifest.json'),
        'new_model_calls': 0,
        'human_outcome_evaluation': 'not performed; development explorer only',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = json.dumps(audit(args.run.resolve()), indent=2, sort_keys=True) + '\n'
    if args.output.exists():
        assert args.output.read_text() == result, 'Audit differs from frozen result'
    else:
        args.output.write_text(result)
    print(result)
