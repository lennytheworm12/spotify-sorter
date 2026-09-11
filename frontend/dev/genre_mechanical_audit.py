"""Independent Python reference for the exhaustive genre QA gate and browser checks."""
import argparse
import json
import socket
from pathlib import Path

import numpy as np

from auditGenreForce import audit, digest, overlap, project_residual, read


def reference_pairs(packet):
    songs = {s['id']: s for s in packet['songs']}
    result = {}
    for pair in packet['pairs']:
        a, b = songs[pair['a']], songs[pair['b']]
        ca, cb = a['canonical'], b['canonical']
        keys = sorted(ca.keys() | cb.keys())
        shared = {k: min(ca.get(k, 0), cb.get(k, 0)) for k in keys if min(ca.get(k, 0), cb.get(k, 0)) > 0}
        ra = {k: ca.get(k, 0) - shared.get(k, 0) for k in keys if ca.get(k, 0) > shared.get(k, 0)}
        rb = {k: cb.get(k, 0) - shared.get(k, 0) for k in keys if cb.get(k, 0) > shared.get(k, 0)}
        na, nb = project_residual(ra, packet['concepts']), project_residual(rb, packet['concepts'])
        usable = bool(a['specificStyleIds'] and b['specificStyleIds'])
        result[(pair['a'], pair['b'])] = {
            **pair,
            'union': {k: max(ca.get(k, 0), cb.get(k, 0)) for k in keys},
            'shared': shared,
            'aOnly': {k: ca[k] for k in keys if ca.get(k, 0) > 0 and cb.get(k, 0) == 0},
            'bOnly': {k: cb[k] for k in keys if cb.get(k, 0) > 0 and ca.get(k, 0) == 0},
            'residualA': ra, 'residualB': rb,
            'residualNeighborhoodA': na, 'residualNeighborhoodB': nb,
            'jc': overlap(ca, cb) if usable else 0,
            'jnr': overlap(na, nb), 'jn': overlap(a['neighborhoods'], b['neighborhoods']),
            'canonicalAvailable': usable,
            'neighborhoodAvailable': usable and any(a['neighborhoods'].values()) and any(b['neighborhoods'].values()),
        }
    return result


def reference_score(pair, settings):
    available = pair['neighborhoodAvailable'] if settings['genreMode'] == 'neighborhood_only_diagnostic' else pair['canonicalAvailable']
    if not available:
        genre = force = 0.0
    else:
        genre = {
            'canonical_only': pair['jc'],
            'neighborhood_only_diagnostic': pair['jn'],
            'canonical_plus_residual': pair['jc'] + settings['eta'] * (1 - pair['jc']) * pair['jnr'],
        }[settings['genreMode']]
        force = genre if settings['forceMode'] == 'pull_only' else 2 * genre - 1
    delta = settings['alpha'] * settings['beta'] * force
    return {'genre': genre, 'force': force, 'delta': delta, 'adjusted': pair['audio'] + delta}


def freeze(path, value):
    text = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n'
    if path.exists():
        if path.read_text() != text:
            raise ValueError('QA replay changed: ' + str(path))
    else:
        path.write_text(text)


def verify(run, out):
    initial = audit(run)
    packet = read(run / 'explorer.json')
    contract = read(out / 'contract.json')
    assert digest(run / 'explorer.json') == contract['inputPacketSha256']
    pairs = reference_pairs(packet)
    actual = read(out / 'components.json')
    failures = []
    if len(actual) != len(pairs):
        raise ValueError('Missing exhaustive components')
    for source, current in zip(packet['pairs'], actual, strict=True):
        key = (source['a'], source['b'])
        expected = pairs[key]
        if any(current[k] != source[k] for k in ('a', 'b', 'audio')):
            failures.append({'check': 'pair_identity_audio', 'pair': key, 'expected': source, 'actual': {k: current[k] for k in ('a', 'b', 'audio')}})
        for field, value in current['evidence'].items():
            if value != expected[field]:
                failures.append({'check': 'component_' + field, 'pair': key, 'expected': expected[field], 'actual': value})
    fields = contract['binary']['fields']
    scores = np.fromfile(out / 'scores.f64', dtype='<f8').reshape(len(contract['scenarios']), len(actual), len(fields))
    for scenario, matrix in zip(contract['scenarios'], scores, strict=True):
        for current, row in zip(actual, matrix, strict=True):
            key = (current['a'], current['b'])
            expected = reference_score(pairs[key], scenario['settings'])
            for field, value in zip(fields, row, strict=True):
                if not np.isfinite(value) or float(value) != expected[field]:
                    failures.append({'check': 'score_' + field, 'pair': key, 'scenario': scenario,
                                     'expected': expected[field], 'actual': float(value) if np.isfinite(value) else str(value)})

    # Reuse the unchanged canonicalizer to prove the packet still matches its source
    # pipeline; independently expected alias and exclusion cases are unit-tested.
    from audio_similarity.genre_force_export import canonical_profile, CONFIG
    from audio_similarity.genre_registry_review import mapper
    ml = Path(__file__).resolve().parents[2] / 'ml/audio_similarity'
    engine, force = mapper(ml), read(ml / CONFIG / 'genre-force-explorer-v1.json')
    for song in packet['songs']:
        fresh = canonical_profile(song['raw'], engine, force)
        for field in ('canonical', 'neighborhoods', 'specificStyleIds', 'excluded', 'traces'):
            if song[field] != fresh[field]:
                failures.append({'check': 'source_mapping_' + field, 'track': song['id'], 'expected': fresh[field], 'actual': song[field]})
        if set(song['canonical']) & {e['id'] for e in song['excluded']}:
            failures.append({'check': 'excluded_concept_has_canonical_mass', 'track': song['id']})
    freeze(out / 'failures_python.json', failures)
    report = {
        'status': 'FAIL' if failures else 'PASS', 'failure_count': len(failures),
        'pairs': len(pairs), 'scenarios': len(contract['scenarios']),
        'float64_score_components_compared_exactly': int(scores.size),
        'current_residual_and_canonical_vectors_compared': len(pairs),
        'source_profiles_rematerialized_without_inference': len(packet['songs']),
        'initial_frozen_audit': initial,
        'new_model_calls': 0, 'network_disabled': True,
        'scope': 'Mechanical correctness only; no human labels read or parameter choice made',
    }
    freeze(out / 'python_checks.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    def forbidden_network(*_args, **_kwargs):
        raise AssertionError('Network is forbidden in the independent QA oracle')
    socket.create_connection = forbidden_network
    socket.socket.connect = forbidden_network
    report = verify(args.run.resolve(), args.output.resolve())
    print(json.dumps(report))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)
