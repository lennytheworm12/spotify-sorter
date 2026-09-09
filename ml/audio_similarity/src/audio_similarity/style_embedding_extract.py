"""Content-addressed extraction of the frozen classifier's latent output."""
import argparse
import importlib.metadata
import importlib.util
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
import numpy as np
from .stage5e3_artifacts import read, digest, freeze, freeze_json, hashes, verify_hashes, npz_bytes
from .stage5b1a_models import file_sha256


def pooled(patches):
    x = np.asarray(patches, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 1280 or len(x) == 0 or not np.isfinite(x).all():
        raise ValueError('expected finite nonempty patches x 1280')
    mean = x.mean(axis=0)
    norm = np.linalg.norm(mean)
    if norm <= 1e-12:
        raise ValueError('degenerate pooled embedding')
    return mean, mean / norm


def cached(cache, identity, infer):
    key = digest(identity); path = cache / (key + '.npz'); receipt = cache / (key + '.json')
    if receipt.exists():
        row = read(receipt)
        if row['identity'] != identity or file_sha256(path) != row['sha256']:
            raise ValueError('embedding cache integrity mismatch')
        with np.load(path, allow_pickle=False) as z:
            patches = z['patches']
        pooled(patches)
        return patches, True, key
    patches = np.asarray(infer(), dtype=np.float32)
    pooled(patches)
    freeze(path, npz_bytes({'patches': patches}))
    freeze_json(receipt, {'identity': identity, 'sha256': file_sha256(path)})
    return patches, False, key


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--replay', action='store_true'); args = parser.parse_args()
    root = Path.cwd(); run = root / 'reports/style_embedding_control/v1'; prior = root / 'reports/style_prior_pilot/v2'
    verify_hashes(root, read(run / 'input_hashes.json'))
    config = read(run / 'protocol.json')
    required = {'CUDA_VISIBLE_DEVICES': '-1', 'TF_NUM_INTRAOP_THREADS': '1', 'TF_NUM_INTEROP_THREADS': '1', 'OMP_NUM_THREADS': '1', 'TF_DETERMINISTIC_OPS': '1'}
    if any(os.environ.get(k) != v for k, v in required.items()):
        raise ValueError('use the documented deterministic CPU environment')
    package = Path(importlib.util.find_spec('essentia').origin).parent
    identity = {'source_independent_protocol_sha256': digest(config), 'model_sha256': file_sha256(root / 'models/discogs-effnet-bs64-1.pb'),
                'metadata_sha256': file_sha256(root / 'models/discogs-effnet-bs64-1.json'), 'implementation_sha256': file_sha256(Path(__file__)),
                'serialization_sha256': file_sha256(root / 'src/audio_similarity/stage5e3_artifacts.py'),
                'runtime': {'python': platform.python_version(), 'numpy': np.__version__, 'essentia': importlib.metadata.version('essentia-tensorflow'),
                            'binary': hashes(list(package.glob('*.so')), root / 'artifacts/style_prior_pilot/env'),
                            'ffmpeg': file_sha256(Path(shutil.which('ffmpeg'))), 'environment': required}}
    freeze_json(run / 'extractor_identity.json', identity)
    expected = {t['track_id']: t['patches'] for t in read(prior / 'extraction_ledger_000.json')['tracks']}
    cache = root / 'artifacts/style_embedding_control/cache'
    predictor = None; rows = []; means = {}; vectors = {}; start = time.monotonic()
    for track in read(run / 'tracks.json'):
        tid = track['spotify_track_id']; source = root / track['retained_source_path']
        def infer():
            nonlocal predictor
            if args.replay:
                raise ValueError('cache replay would require inference')
            import essentia
            import essentia.standard as es
            essentia.log.warningActive = False
            with tempfile.TemporaryDirectory(prefix='discogs-latent-') as temporary:
                wav = Path(temporary) / 'source.wav'
                subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(source), '-map', '0:a:0', '-c:a', 'pcm_f32le', str(wav)], check=True, capture_output=True)
                audio = es.MonoLoader(filename=str(wav), sampleRate=16000, resampleQuality=4)()
                if not len(audio) or not np.isfinite(audio).all() or np.max(np.abs(audio)) == 0:
                    raise ValueError('invalid or silent audio')
                if predictor is None:
                    options = config['preprocessing']['predictor'] | {'output': config['output']}
                    predictor = es.TensorflowPredictEffnetDiscogs(graphFilename=str(root / 'models/discogs-effnet-bs64-1.pb'), **options)
                return predictor(audio)
        try:
            if file_sha256(source) != track['source_sha256']:
                raise ValueError('source integrity mismatch')
            patches, hit, key = cached(cache, identity | {'source_sha256': track['source_sha256']}, infer)
            if len(patches) != expected[tid]:
                raise ValueError('classifier and latent patch coverage differ')
            means[tid], vectors[tid] = pooled(patches)
            rows.append({'track_id': tid, 'status': 'OK', 'patches': len(patches), 'cache_hit': hit, 'cache_key': key})
        except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
            rows.append({'track_id': tid, 'status': 'FAILED', 'error': str(error)})
        print(f'{len(rows)}/100 {tid} {rows[-1]["status"]}', flush=True)
    ledger = {'tracks': rows, 'seconds': time.monotonic() - start, 'inference_tracks': sum(r.get('cache_hit') is False for r in rows),
              'cache_hits': sum(r.get('cache_hit') is True for r in rows), 'failures': sum(r['status'] != 'OK' for r in rows)}
    index = len(list(run.glob('execution_*.json')))
    freeze_json(run / f'execution_{index:03d}.json', ledger)
    if ledger['failures']:
        raise SystemExit('explicit extraction failures; no aggregate published')
    freeze(run / 'raw_embedding_means.npz', npz_bytes(means))
    freeze(run / 'embeddings.npz', npz_bytes(vectors))


if __name__ == '__main__':
    main()
