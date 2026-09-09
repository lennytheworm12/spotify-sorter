"""Synthetic latent-output shape, determinism and input-response check."""
from pathlib import Path
import numpy as np
import essentia.standard as es
from audio_similarity.stage5e3_artifacts import read, freeze_json, hashes
from audio_similarity.style_embedding_extract import pooled

if __name__ == '__main__':
    root = Path.cwd(); run = root / 'reports/style_embedding_control/v1'
    config = read(run / 'protocol.json')
    model = es.TensorflowPredictEffnetDiscogs(graphFilename='models/discogs-effnet-bs64-1.pb', **(config['preprocessing']['predictor'] | {'output': config['output']}))
    sine = (.05 * np.sin(2 * np.pi * 440 * np.arange(170001) / 16000)).astype(np.float32)
    noise = np.random.default_rng(5101).normal(0, .05, 170001).astype(np.float32)
    first, changed, replay = model(sine), model(noise), model(sine)
    assert first.shape == (10, 1280)
    error = float(np.max(np.abs(first - replay)))
    difference = float(np.max(np.abs(first - changed)))
    assert error <= 1e-6 and difference > 1e-4
    _, unit = pooled(first)
    freeze_json(run / 'synthetic_golden.json', {'samples': 170001, 'shape': list(first.shape), 'repeat_error': error, 'input_response_max_difference': difference, 'unit_norm': float(np.linalg.norm(unit)), 'passes': True, 'real_tracks_recomputed': 0, 'implementation': hashes([Path(__file__)], root)})
