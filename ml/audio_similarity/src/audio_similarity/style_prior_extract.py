"""Isolated CPU Discogs inference, create-once content-addressed cache."""
import argparse
import importlib.metadata
import platform
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from .stage5b1a_models import file_sha256
from .stage5e3_artifacts import digest, freeze, freeze_json, hashes, npz_bytes, read, verify_hashes


def validate(values):
    values = np.asarray(values, dtype=np.float32)
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] != 400:
        raise ValueError('expected nonempty patches x 400')
    if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1):
        raise ValueError('invalid sigmoid predictions')
    return values


def cached(cache, identity, infer):
    key = digest(identity)
    path = cache / (key + '.npz')
    receipt = cache / (key + '.json')
    if receipt.exists():
        record = read(receipt)
        if record['identity'] != identity or file_sha256(path) != record['sha256']:
            raise ValueError('cache integrity mismatch')
        with np.load(path, allow_pickle=False) as data:
            return validate(data['patches']), True, key
    values = validate(infer())
    freeze(path, npz_bytes({'patches': values}))
    freeze_json(receipt, {'identity': identity, 'sha256': file_sha256(path)})
    return values, False, key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    run = root / 'reports/style_prior_pilot/v2'
    verify_hashes(root, read(run / 'input_hashes.json'))
    config = read(run / 'protocol.json')
    import essentia
    import essentia.standard as es
    runtime = {'python': platform.python_version(), 'machine': platform.machine(),
               'essentia': importlib.metadata.version('essentia-tensorflow'),
               'numpy': np.__version__, 'essentia_binary': hashes(list(Path(essentia.__file__).parent.glob('*.so')), root / 'artifacts/style_prior_pilot/env')}
    identity = {'runtime': runtime, 'model_sha256': config['model_sha256'],
                'metadata_sha256': config['metadata_sha256'], 'preprocessing': config['preprocessing'],
                'implementation': file_sha256(Path(__file__)), 'ffmpeg_sha256': file_sha256(Path(shutil.which('ffmpeg'))),
                'serialization': file_sha256(root / 'src/audio_similarity/stage5e3_artifacts.py')}
    freeze_json(run / 'extractor_identity.json', identity)
    cache = root / 'artifacts/style_prior_pilot/cache'
    model = None
    rows, arrays = [], {}
    started = time.monotonic()
    for track in read(run / 'tracks.json'):
        tid = track['spotify_track_id']
        source = root / track['retained_source_path']
        if file_sha256(source) != track['source_sha256']:
            raise ValueError('source integrity mismatch')
        def infer():
            nonlocal model
            if args.replay:
                raise ValueError('replay would require new inference')
            if model is None:
                model = es.TensorflowPredictEffnetDiscogs(graphFilename=str(root / 'models/discogs-effnet-bs64-1.pb'), **config['preprocessing']['predictor'])
            with tempfile.TemporaryDirectory(prefix='style-pcm-') as temporary:
                wav = Path(temporary) / 'decoded.wav'
                subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(source), '-map', '0:a:0', '-c:a', 'pcm_f32le', str(wav)], check=True, capture_output=True)
                signal = es.MonoLoader(filename=str(wav), sampleRate=16000, resampleQuality=4)()
            if len(signal) == 0 or not np.isfinite(signal).all() or np.max(np.abs(signal)) == 0:
                raise ValueError('invalid or silent audio')
            return model(signal)
        try:
            values, hit, key = cached(cache, identity | {'source_sha256': track['source_sha256']}, infer)
            arrays[tid] = values.mean(axis=0, dtype=np.float64)
            rows.append({'track_id': tid, 'status': 'OK', 'patches': len(values), 'cache_hit': hit, 'cache_key': key})
        except (ValueError, RuntimeError) as exc:
            rows.append({'track_id': tid, 'status': 'FAILED', 'reason': str(exc)})
        print(f'{len(rows)}/100 {tid} {rows[-1]["status"]}', flush=True)
    freeze(run / 'raw_style_means.npz', npz_bytes(arrays))
    ledger = {'tracks': rows, 'seconds': time.monotonic() - started,
              'inference_tracks': sum(r.get('cache_hit') is False for r in rows),
              'hits': sum(r.get('cache_hit') is True for r in rows),
              'failures': sum(r['status'] != 'OK' for r in rows)}
    # Numbered execution ledgers preserve the original even after interrupted/repeated runs.
    index = len(list(run.glob('extraction_ledger_*.json')))
    freeze_json(run / f'extraction_ledger_{index:03d}.json', ledger)
    if ledger['failures']:
        raise SystemExit('Incomplete extraction: see explicit failures in ledger')


if __name__ == '__main__':
    main()
