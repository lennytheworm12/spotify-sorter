"""Full-song C and two source-link repairs, cached outside all historical stores."""
import os
import time
import json
from pathlib import Path

import numpy as np

from .audit_capture import read_db, vector_valid
from .contracts import digest, file_hash, freeze_json, require
from .development_inputs import RUN, load


def cached_vector(db, table, clauses, args):
    rows = db.execute(f'SELECT * FROM {table} WHERE {clauses}', args).fetchall()
    require(len(rows) <= 1, 'ambiguous cached representation')
    if not rows:
        return None, None
    row = rows[0]
    require(vector_valid(row), 'cached vector hash/shape/normalization failed')
    return np.frombuffer(row['embedding'], dtype='<f4').copy(), {
        k: row[k] for k in row.keys() if k not in ('embedding', 'failure_detail')}


def materialize(root, *, limit=None):
    # This process is CPU-only so it cannot evict the active acquisition worker.
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    import torch
    from ..stage5a_contract import load_contract
    from ..stage5c1_pipeline import verify_model_files
    from ..holistic_encoders import LaionClapEncoder, MuQMulanEncoder
    from ..stage5e1_encoders import decode_mono
    from ..stage5e1_sampling import sampling_plan, normalized_mean
    from ..stage4a_sampling import cache_windows
    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    plan = load(root)
    run = root / RUN
    contract = load_contract(root / 'reports/holistic_stage4a_dual/audio_representation_v1.json')
    verified_models = verify_model_files(root, contract)
    config = {'plan_sha256': digest(plan), 'contract_sha256': contract.vector_contract_sha256,
        'models': verified_models, 'implementation_sha256': file_hash(Path(__file__)),
        'torch': torch.__version__, 'numpy': np.__version__, 'device': 'cpu', 'threads': 2}
    freeze_json(run / 'audio_config.json', config)
    identity = digest(config)
    clap = muq = None
    e1 = read_db(root / 'artifacts/stage5e1_four_arm_retrieval/representations.sqlite')
    reused, computed = 0, 0
    try:
        for t in plan['tracks']:
            target = run / 'audio' / (t['request_id'] + '.json')
            if target.exists():
                old = json.loads(target.read_text())
                require(old['source_sha256'] == t['source_sha256'] and old['configuration_sha256'] == identity, 'audio cache identity changed')
                require(all(vector_ok(old[k]) for k in ('C_center30','C_method_c','M')), 'invalid cached pooled vectors')
                reused += 1
                continue
            if limit is not None and computed >= limit:
                break
            require(file_hash(root / t['source_path']) == t['source_sha256'], 'retained source changed')
            began = time.monotonic()
            values, origins = {}, {}
            previous = read_db(root / t['prior_representation']['cache_path'])
            try:
                for name, encoder in [('C_center30','laion_clap'),('M','muq_mulan_large')]:
                    value, origin = cached_vector(previous, 'pooled',
                        "stable_track_id=? AND source_audio_sha256=? AND encoder_id=? AND status='SUCCESS'",
                        (t['stable_track_id'],t['source_sha256'],encoder))
                    if value is not None:
                        require(origin['vector_contract_sha256'] == contract.vector_contract_sha256, 'historical contract mismatch')
                        values[name], origins[name] = value, origin
            finally:
                previous.close()
            for name, arm in [('C_center30','A'),('C_method_c','C'),('M','MUQ')]:
                if name not in values:
                    value, origin = cached_vector(e1, 'vectors',
                        "spotify_track_id=? AND source_sha256=? AND arm=? AND status='SUCCESS'",
                        (t['stable_track_id'],t['source_sha256'],arm))
                    if value is not None:
                        values[name], origins[name] = value, origin
            calls = {'clap': 0, 'muq': 0}
            views = {}
            if 'C_center30' not in values or 'M' not in values:
                wav = decode_mono(root / t['source_path'], 24000)
                windows = [w for w in cache_windows(len(wav)) if w.center_sec in (5,15,25)]
                for name in ('C_center30', 'M'):
                    if name in values:
                        continue
                    if name == 'C_center30':
                        clap = clap or LaionClapEncoder(checkpoint_path=verified_models['clap']['path'])
                        encoder = clap
                    else:
                        muq = muq or MuQMulanEncoder(device='cpu', revision=contract.encoder('muq_mulan_large').provenance['revision'])
                        encoder = muq
                    vectors = [encoder.encode_segment(wav[w.start_sample:w.end_sample],24000).embedding for w in windows]
                    values[name] = normalized_mean(vectors)
                    views[name] = [v.tolist() for v in vectors]
                    calls['clap' if name == 'C_center30' else 'muq'] += len(vectors)
                    origins[name] = {'status': 'NEW_EXACT_SOURCE_REPAIR', 'centers': [5,15,25]}
            if 'C_method_c' not in values:
                wav = decode_mono(root / t['source_path'],48000)
                sampling = sampling_plan(len(wav),t['source_sha256'])
                freeze_json(run/'sampling'/(t['request_id']+'.json'),sampling)
                clap = clap or LaionClapEncoder(checkpoint_path=verified_models['clap']['path'])
                vectors = [clap.encode_segment(wav[w['start_sample']:w['end_sample']],48000).embedding
                           for w in sampling['full_song_chunks']]
                values['C_method_c'] = normalized_mean(vectors)
                views['C_method_c'] = [v.tolist() for v in vectors]
                calls['clap'] += len(vectors)
                origins['C_method_c'] = {'status':'NEW_FULL_SONG_C','sampling_plan_sha256':sampling['sampling_plan_sha256']}
            payload = {'request_id':t['request_id'],'stable_track_id':t['stable_track_id'],
                'source_sha256':t['source_sha256'],'configuration_sha256':identity,
                **{k:v.tolist() for k,v in values.items()}, 'views':views, 'origins':origins}
            freeze_json(target,payload)
            freeze_json(run/'audio_ledger'/(t['request_id']+'.json'),{'inference_calls':calls,'elapsed_seconds':time.monotonic()-began})
            computed += 1
            print(json.dumps({'audio_completed':reused+computed,'total':len(plan['tracks']),
                              'seconds':round(time.monotonic()-began,2),'new_calls':calls}),flush=True)
    finally:
        e1.close()
    return {'reused_tracks':reused,'new_tracks':computed}


def vector_ok(values):
    a = np.asarray(values)
    return a.shape == (512,) and np.isfinite(a).all() and np.isclose(np.linalg.norm(a),1,atol=1e-5)
