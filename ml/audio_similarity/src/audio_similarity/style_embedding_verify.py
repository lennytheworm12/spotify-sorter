"""Reconstruct and verify the completed latent control without inference."""
from pathlib import Path
import numpy as np
from .stage5e3_artifacts import read, verify_hashes, npz_bytes
from .stage5b1a_models import file_sha256
from .style_embedding_extract import pooled


def verify(root):
    run = root / 'reports/style_embedding_control/v1'
    verify_hashes(root, read(run / 'input_hashes.json'))
    executions = [read(p) for p in sorted(run.glob('execution_*.json'))]
    assert len(executions) >= 2
    assert executions[-1]['inference_tracks'] == 0 and executions[-1]['cache_hits'] == 100
    assert all(e['failures'] == 0 for e in executions)
    vectors, means = {}, {}
    cache = root / 'artifacts/style_embedding_control/cache'
    for row in executions[-1]['tracks']:
        path = cache / (row['cache_key'] + '.npz')
        receipt = read(cache / (row['cache_key'] + '.json'))
        assert file_sha256(path) == receipt['sha256']
        with np.load(path, allow_pickle=False) as z:
            patches = z['patches']
        assert len(patches) == row['patches']
        means[row['track_id']], vectors[row['track_id']] = pooled(patches)
    assert len(vectors) == 100
    assert (run / 'embeddings.npz').read_bytes() == npz_bytes(vectors)
    assert (run / 'raw_embedding_means.npz').read_bytes() == npz_bytes(means)
    with np.load(run / 'similarity_matrices.npz', allow_pickle=False) as z:
        for name in ('latent', 'labels', 'D', 'C'):
            matrix = z[name]
            assert matrix.shape == (100, 100) and np.isfinite(matrix).all()
            np.testing.assert_allclose(matrix, matrix.T, atol=1e-12)
            np.testing.assert_allclose(matrix.diagonal(), 1, atol=1e-6)
    for fold in read(run / 'folds.json'):
        assert not set(fold['train']) & set(fold['heldout'])
    for previous in ('reports/style_prior_pilot/v2', 'reports/style_source_audit/v1'):
        p = root / previous
        verify_hashes(p, read(p / 'artifact_manifest.json'))
        verify_hashes(root, read(p / 'input_hashes.json'))
    if (run / 'artifact_manifest.json').exists():
        verify_hashes(run, read(run / 'artifact_manifest.json'))
    return {'tracks': 100, 'patches': sum(r['patches'] for r in executions[-1]['tracks']),
            'initial_inference_tracks': executions[0]['inference_tracks'], 'replay_inference_tracks': 0,
            'replay_hits': 100, 'exact_aggregate_reconstruction': True, 'symmetric_finite_self_one': True,
            'historical_inputs_unchanged': True, 'extraction_seconds': executions[0]['seconds'], 'replay_seconds': executions[-1]['seconds']}


if __name__ == '__main__':
    print(verify(Path.cwd()))
