"""Read-only verification of pilot features, provenance and extraction replay."""
from pathlib import Path
import numpy as np
from .stage5b1a_models import file_sha256
from .stage5e3_artifacts import read, verify_hashes, npz_bytes
from .style_prior import RUN, distributions, distances


def verify(root):
    run = root / RUN
    verify_hashes(root, read(run / 'input_hashes.json'))
    for filename in ('analysis_identity.json', 'engineering_identity.json', 'input_response_identity.json', 'report_identity.json'):
        verify_hashes(root, read(run / filename))
    tracks = read(run / 'tracks.json')
    ids = [t['spotify_track_id'] for t in tracks]
    assert len(ids) == len(set(ids)) == 100
    ledgers = [read(p) for p in sorted(run.glob('extraction_ledger_*.json'))]
    assert len(ledgers) >= 2, 'extraction and replay ledgers required'
    assert ledgers[-1]['inference_tracks'] == 0 and ledgers[-1]['hits'] == 100
    assert all(ledger['failures'] == 0 for ledger in ledgers)
    means = {}
    cache = root / 'artifacts/style_prior_pilot/cache'
    for row in ledgers[-1]['tracks']:
        path = cache / (row['cache_key'] + '.npz')
        receipt = read(cache / (row['cache_key'] + '.json'))
        assert file_sha256(path) == receipt['sha256']
        with np.load(path, allow_pickle=False) as data:
            values = data['patches']
            assert values.shape == (row['patches'], 400) and np.isfinite(values).all()
            means[row['track_id']] = values.mean(axis=0, dtype=np.float64)
    assert (run / 'raw_style_means.npz').read_bytes() == npz_bytes(means)
    profiles = distributions(np.stack([means[tid] for tid in ids]))
    matrix = distances(profiles)
    assert np.isfinite(matrix).all() and np.all(matrix >= 0) and np.all(matrix <= 1)
    np.testing.assert_allclose(matrix, matrix.T, rtol=0, atol=1e-15)
    np.testing.assert_array_equal(matrix.diagonal(), 0)
    assert (run / 'style_distributions.npz').read_bytes() == npz_bytes({'ids': np.array(ids), 'profiles': profiles, 'distances': matrix})
    by = {t['spotify_track_id']: t for t in tracks}
    for fold in read(run / 'folds.json'):
        assert not set(fold['train']) & set(fold['heldout'])
        def groups(ids):
            return {('artist', a.casefold().strip()) for tid in ids for a in by[tid]['artists']} | {('source', by[tid]['source_sha256']) for tid in ids} | {('video', by[tid]['youtube_video_id']) for tid in ids}
        assert not groups(fold['train']) & groups(fold['heldout'])
    historical = {}
    for stage in ('stage5g1_clap_similarity', 'stage5g1a_scorer_diagnostic', 'stage5g1b_identity_probes'):
        prior = root / 'reports' / stage / 'v1'
        verify_hashes(root, read(prior / 'input_hashes.json'))
        verify_hashes(prior, read(prior / 'artifact_manifest.json'))
        historical[stage] = True
    if (run / 'artifact_manifest.json').exists():
        verify_hashes(run, read(run / 'artifact_manifest.json'))
    return {'valid_tracks': len(ids), 'first_inference_tracks': ledgers[0]['inference_tracks'], 'replay_inference_tracks': ledgers[-1]['inference_tracks'],
            'replay_cache_hits': ledgers[-1]['hits'], 'total_real_patches': sum(row['patches'] for row in ledgers[-1]['tracks']),
            'aggregate_bytes_reconstructed_exactly': True, 'distance_symmetric_and_self_zero': True, 'artist_source_track_folds_disjoint': True,
            'historical_integrity': historical, 'extraction_seconds': ledgers[0]['seconds'], 'replay_seconds': ledgers[-1]['seconds']}


if __name__ == '__main__':
    import json
    print(json.dumps(verify(Path.cwd()), sort_keys=True, indent=2))
