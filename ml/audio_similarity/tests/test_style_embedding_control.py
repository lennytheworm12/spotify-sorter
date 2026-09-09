import numpy as np
import pytest
from audio_similarity.style_embedding_extract import pooled, cached


def test_raw_mean_then_normalization():
    a = np.zeros((2, 1280)); a[0, 0] = 10; a[1, 1] = 1
    mean, unit = pooled(a)
    assert mean[0] == 5 and mean[1] == .5
    assert unit[0] / unit[1] == pytest.approx(10)
    assert np.linalg.norm(unit) == pytest.approx(1)
    matrix = np.stack([unit, unit]) @ np.stack([unit, unit]).T
    np.testing.assert_allclose(matrix, np.ones((2, 2)))


@pytest.mark.parametrize('bad', [np.zeros((0, 1280)), np.zeros((2, 1280)), np.ones((2, 512)), np.full((2, 1280), np.nan)])
def test_reject_invalid_embeddings(bad):
    with pytest.raises(ValueError): pooled(bad)


def test_cache_identity_replay_and_corruption(tmp_path):
    calls = []
    def infer(): calls.append(1); return np.ones((3, 1280), np.float32)
    a, hit, key = cached(tmp_path, {'source': 'a', 'output': 'latent'}, infer)
    assert not hit
    b, hit, _ = cached(tmp_path, {'source': 'a', 'output': 'latent'}, infer)
    assert hit and len(calls) == 1
    np.testing.assert_array_equal(a, b)
    cached(tmp_path, {'source': 'b', 'output': 'latent'}, infer)
    assert len(calls) == 2
    (tmp_path / (key + '.npz')).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='integrity'): cached(tmp_path, {'source': 'a', 'output': 'latent'}, infer)
