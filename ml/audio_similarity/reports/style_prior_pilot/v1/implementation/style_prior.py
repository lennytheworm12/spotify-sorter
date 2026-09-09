"""Frozen dedicated-style pilot: preparation and label-free distance primitives."""
from pathlib import Path
import hashlib
import numpy as np
from .stage5e3_artifacts import read, freeze_json, hashes, verify_hashes
from .stage5g1b_data import evidence, G1A, E3
from .stage5g1a_data import groups
from .stage5g1_evidence import preferences

RUN = Path('reports/style_prior_pilot/v1')


def distributions(raw, epsilon=1e-8):
    raw = np.asarray(raw, dtype=np.float64)
    if raw.ndim != 2 or not np.isfinite(raw).all() or np.any(raw < 0):
        raise ValueError('invalid raw profiles')
    smoothed = raw + epsilon
    return smoothed / smoothed.sum(axis=1, keepdims=True)


def distances(profiles):
    p = np.asarray(profiles, dtype=np.float64)
    if p.ndim != 2 or np.any(p <= 0) or not np.isfinite(p).all() or not np.allclose(p.sum(axis=1), 1):
        raise ValueError('expected positive normalized profiles')
    result = np.zeros((len(p), len(p)))
    for i in range(len(p)):
        m = (p[i] + p) / 2
        result[i] = ((p[i] * np.log(p[i] / m)).sum(axis=1) + (p * np.log(p / m)).sum(axis=1)) / (2 * np.log(2))
    return np.clip(result, 0, 1)


def make_folds(tracks, pairs):
    buckets = [[] for _ in range(3)]
    ordered = sorted(groups(tracks, True), key=lambda g: (-len(g), hashlib.sha256(('style-prior-v1:' + min(g)).encode()).hexdigest()))
    for group in ordered:
        buckets[min(range(3), key=lambda i: (len(buckets[i]), i))].extend(group)
    result = []
    for i in range(3):
        test = sorted(buckets[i])
        train = sorted(t for j, bucket in enumerate(buckets) if j != i for t in bucket)
        result.append({'fold': i, 'train': train, 'heldout': test,
                       'train_preferences': preferences(pairs, train)[0],
                       'heldout_preferences': preferences(pairs, test)[0]})
    return result


def prepare(root):
    run = root / RUN
    if (run / 'input_hashes.json').exists():
        verify_hashes(root, read(run / 'input_hashes.json'))
        return
    config = read(root / 'configs/style_prior_v1.json')
    verify_hashes(root, read(root / G1A / 'input_hashes.json'))
    verify_hashes(root / G1A, read(root / G1A / 'artifact_manifest.json'))
    tracks, labels, notes, inventory = evidence(root)
    freeze_json(run / 'protocol.json', config)
    freeze_json(run / 'tracks.json', sorted(tracks, key=lambda t: t['spotify_track_id']))
    freeze_json(run / 'evidence.json', labels)
    freeze_json(run / 'inventory.json', inventory)
    freeze_json(run / 'folds.json', make_folds(tracks, labels['playlist']))
    freeze_json(run / 'model_metadata.json', read(root / 'models/discogs-effnet-bs64-1.json'))
    for name, expected in [('pb', config['model_sha256']), ('json', config['metadata_sha256'])]:
        verify_hashes(root, {f'models/discogs-effnet-bs64-1.{name}': expected})
    sources = [root / 'src/audio_similarity' / f for f in ['style_prior.py', 'style_prior_extract.py', 'stage5e3_artifacts.py', 'stage5g1b_data.py', 'stage5g1a_data.py', 'stage5g1_evidence.py']]
    paths = sources + [root / 'configs/style_prior_v1.json', root / E3 / 'historical_reference_matrices.npz', root / E3 / 'post_review_rating_snapshot.json', root / 'models/discogs-effnet-bs64-1.pb', root / 'models/discogs-effnet-bs64-1.json']
    paths += list(run.glob('*.json'))
    protected = read(root / G1A / 'input_hashes.json') | hashes(paths, root)
    freeze_json(run / 'input_hashes.json', protected)
    verify_hashes(root, protected)


if __name__ == '__main__':
    prepare(Path.cwd())
