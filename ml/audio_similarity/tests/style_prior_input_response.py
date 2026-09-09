"""Real runtime check that predictor reuse responds to changed audio and resets."""
from pathlib import Path
import numpy as np
import essentia.standard as es
from audio_similarity.stage5e3_artifacts import read, freeze_json

if __name__ == '__main__':
    run = Path('reports/style_prior_pilot/v2')
    config = read(run / 'protocol.json')
    model = es.TensorflowPredictEffnetDiscogs(graphFilename='models/discogs-effnet-bs64-1.pb', **config['preprocessing']['predictor'])
    a = (.05 * np.sin(2 * np.pi * 440 * np.arange(160000) / 16000)).astype('float32')
    b = np.random.default_rng(5101).normal(0, .05, 160000).astype('float32')
    first, changed, replay = model(a), model(b), model(a)
    change = float(np.max(np.abs(first - changed)))
    repeat = float(np.max(np.abs(first - replay)))
    assert change > 1e-4 and repeat <= 1e-6
    freeze_json(run / 'input_response.json', {'sine_vs_noise_max_change': change, 'sine_after_noise_repeat_error': repeat, 'passes': True})
