"""Fresh-process reference reproduction of cached classifier predictions."""
import argparse
import subprocess
import tempfile
import time
from pathlib import Path
import numpy as np
from .stage5e3_artifacts import read, freeze_json, verify_hashes, hashes


def prediction_error(reference, cached):
    if reference.shape != cached.shape or reference.ndim != 2 or reference.shape[1] != 400:
        raise ValueError('reference patch shape mismatch')
    if not np.isfinite(reference).all() or not np.isfinite(cached).all():
        raise ValueError('nonfinite predictions')
    return float(np.max(np.abs(reference.astype(np.float64) - cached.astype(np.float64))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--track', required=True)
    args = parser.parse_args()
    root = Path.cwd()
    run = root / 'reports/style_source_audit/v1'
    prior = root / 'reports/style_prior_pilot/v2'
    verify_hashes(root, read(run / 'input_hashes.json'))
    protocol = read(run / 'reference_protocol.json')
    if args.track not in protocol['tracks']:
        raise ValueError('track outside frozen reference audit')
    track = next(t for t in read(prior / 'tracks.json') if t['spotify_track_id'] == args.track)
    config = read(prior / 'protocol.json')
    ledger = next(t for t in read(prior / 'extraction_ledger_000.json')['tracks'] if t['track_id'] == args.track)
    with np.load(root / 'artifacts/style_prior_pilot/cache' / (ledger['cache_key'] + '.npz'), allow_pickle=False) as z:
        cached = z['patches']
    import essentia.standard as es
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='style-reference-') as temp:
        wav = Path(temp) / 'source.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(root / track['retained_source_path']), '-map', '0:a:0', '-c:a', 'pcm_f32le', str(wav)], check=True, capture_output=True)
        audio = es.MonoLoader(filename=str(wav), sampleRate=16000, resampleQuality=4)()
        predictor = es.TensorflowPredictEffnetDiscogs(graphFilename=str(root / 'models/discogs-effnet-bs64-1.pb'), **config['preprocessing']['predictor'])
        reference = predictor(audio)
    error = prediction_error(reference, cached)
    result = {'track_id': args.track, 'title': track['title'], 'patches': len(reference), 'max_absolute_error': error,
              'passes': error <= protocol['tolerance'], 'fresh_process': True, 'inference_tracks': 1,
              'seconds': time.monotonic() - started, 'implementation': hashes([Path(__file__)], root)}
    freeze_json(run / ('reference_' + args.track + '.json'), result)
    print(result, flush=True)
    if not result['passes']:
        raise SystemExit('reference reproduction failed')


if __name__ == '__main__':
    main()
