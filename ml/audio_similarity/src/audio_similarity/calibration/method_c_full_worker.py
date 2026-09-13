"""Offline Method C only worker; every completed chunk survives interruption."""
import os
import time
import uuid
from importlib.metadata import version
from pathlib import Path

from .contracts import digest, file_hash, freeze_json, require
from .method_c_full_inputs import RUN, CHECKPOINT, CHECKPOINT_SHA, read
from .method_c_full_cache import identity, load_feature, store_feature
from .development_audio import vector_ok


def configuration(root):
    paths = ['holistic_encoders.py', 'stage5e1_encoders.py', 'stage5e1_sampling.py',
             'calibration/method_c_full_worker.py', 'calibration/method_c_full_cache.py']
    require(file_hash(root/CHECKPOINT) == CHECKPOINT_SHA, 'checkpoint changed')
    return {'representation': 'method_c_full_song', 'checkpoint_path': CHECKPOINT,
        'checkpoint_sha256': CHECKPOINT_SHA, 'architecture': 'HTSAT-base', 'fusion': False,
        'sample_rate': 48000, 'chunk_samples': 480000, 'tail': 'native repeatpad',
        'pooling': 'equal normalized chunk mean then L2; float32 output',
        'implementation': {p: file_hash(root/'src/audio_similarity'/p) for p in paths},
        'packages': {p: version(p) for p in ('torch','torchaudio','numpy','laion-clap','librosa','transformers')},
        'device': os.environ.get('METHOD_C_DEVICE', 'cpu'), 'threads': 2,
        'precision': 'fp32', 'cuda_matmul_allow_tf32': False, 'cudnn_allow_tf32': False}


def run(root, *, replay=False, limit=None):
    device = os.environ.get('METHOD_C_DEVICE', 'cpu')
    require(device in ('cpu','cuda:0'), 'unsupported extraction device')
    if device == 'cpu':
        os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from .development_offline import configure
    configure()
    import fcntl
    import numpy as np
    from ..stage5e1_sampling import sampling_plan, normalized_mean
    directory = root/RUN
    lock = (directory/'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    corpus = read(directory/'corpus.json')
    reuse = read(directory/'reuse_manifest.json')
    config = configuration(root)
    freeze_json(directory/'configuration.json', config)
    if device != 'cpu':
        parity = read(directory/'gpu_parity.json')
        require(parity['status'] == 'PASS' and parity['configuration_sha256'] == digest(config), 'GPU parity gate not satisfied')
    invocation = uuid.uuid4().hex
    ledger = directory/'invocations'/invocation
    freeze_json(ledger/'start.json', {'replay': replay, 'configuration_sha256': digest(config),
        'corpus_sha256': file_hash(directory/'corpus.json'), 'reuse_sha256': file_hash(directory/'reuse_manifest.json')})
    counts = {'cached': 0, 'imported': 0, 'computed': 0, 'inference_calls': 0, 'blocked': 0, 'failed': 0}
    encoder = None
    try:
        for recording in corpus['recordings']:
            sid = recording['recording_id']
            if recording['errors']:
                counts['blocked'] += 1
                continue
            target = directory/'features'/(sid+'.json')
            require(file_hash(root/recording['source_path']) == recording['audio_sha256'], 'source changed')
            require(file_hash(root/recording['provenance_path']) == recording['provenance_sha256'], 'source provenance changed')
            if target.exists():
                load_feature(target, recording, config)
                counts['cached'] += 1
                continue
            require(not replay, 'replay encountered missing feature')
            if sid in reuse:
                entry = reuse[sid]
                if 'path' in entry:
                    require(file_hash(root/entry['path']) == entry['sha256'], 'reuse source changed')
                store_feature(target, recording, config, entry['vector'], entry['views'], entry)
                counts['imported'] += 1
                continue
            if limit is not None and counts['computed'] + counts['failed'] >= limit:
                continue
            began = time.monotonic()
            try:
                from ..stage5e1_encoders import decode_mono
                wav = decode_mono(root/recording['source_path'], 48000)
                plan = sampling_plan(len(wav), recording['audio_sha256'])
                freeze_json(directory/'sampling'/(sid+'.json'), plan)
                vectors = []
                for chunk in plan['full_song_chunks']:
                    chunk_id = digest({'identity': identity(recording, config), 'chunk': chunk})
                    cache = directory/'chunks'/sid/(str(chunk['index'])+'.json')
                    if cache.exists():
                        item = read(cache)
                        require(item['identity'] == chunk_id and vector_ok(item['vector']) and digest(item['vector']) == item['vector_sha256'], 'chunk cache mismatch')
                        vector = np.asarray(item['vector'], dtype=np.float64)
                    else:
                        if encoder is None:
                            import torch
                            require(device == 'cpu' or torch.cuda.is_available(), 'GPU unavailable')
                            torch.backends.cuda.matmul.allow_tf32 = False
                            torch.backends.cudnn.allow_tf32 = False
                            torch.set_num_threads(2)
                            torch.set_num_interop_threads(2)
                            from ..holistic_encoders import LaionClapEncoder
                            encoder = LaionClapEncoder(checkpoint_path=str(root/CHECKPOINT))
                        attempt = ledger/'calls'/f'{sid}_{chunk["index"]}.json'
                        freeze_json(attempt, {'recording_id': sid, 'chunk_identity': chunk_id, 'status': 'ATTEMPT_RESERVED'})
                        counts['inference_calls'] += 1
                        vector = encoder.encode_segment(wav[chunk['start_sample']:chunk['end_sample']],48000).embedding
                        require(vector_ok(vector), 'invalid inferred chunk')
                        freeze_json(cache, {'identity': chunk_id, 'vector': vector.tolist(), 'vector_sha256': digest(vector.tolist())})
                    vectors.append(vector)
                store_feature(target, recording, config, normalized_mean(vectors), [v.tolist() for v in vectors],
                    {'status': 'NEW_FULL_SONG_C', 'sampling_plan_sha256': plan['sampling_plan_sha256']})
                counts['computed'] += 1
                freeze_json(ledger/'tracks'/(sid+'.json'), {'status': 'COMPLETE', 'elapsed_seconds': time.monotonic()-began})
            except Exception as exc:
                counts['failed'] += 1
                freeze_json(ledger/'tracks'/(sid+'.json'), {'status': 'FAILED', 'error_type': type(exc).__name__, 'detail': str(exc)})
            print({'recording_id': sid, **counts}, flush=True)
        freeze_json(ledger/'result.json', counts)
        return counts
    finally:
        lock.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    print(run(Path.cwd(), replay=args.replay, limit=args.limit))
