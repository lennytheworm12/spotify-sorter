"""Frozen Arm-D independent-view CLAP inference on ordered full-song windows."""
import hashlib
import importlib.metadata
import json
import sqlite3
import time
from pathlib import Path
import numpy as np
from .stage5e3_artifacts import digest, freeze_json, freeze, npz_bytes, read, hashes, verify_hashes
from .stage5b1a_models import file_sha256
from .stage5e1_sampling import full_song_chunks, normalized_mean


def normalize(vector):
    a=np.asarray(vector,dtype=np.float64)
    if a.shape!=(512,) or not np.isfinite(a).all() or np.linalg.norm(a)<=1e-12:
        raise ValueError('invalid CLAP vector')
    return (a/np.linalg.norm(a)).astype(np.float32)


def segment(waveform, chunk):
    a=np.asarray(waveform[chunk.start_sample:chunk.end_sample],dtype=np.float32)
    if not len(a) or not np.isfinite(a).all():raise ValueError('invalid audio chunk')
    return a[np.arange(480000)%len(a)]


class SegmentCache:
    def __init__(self,path):
        path.parent.mkdir(parents=True,exist_ok=True);self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS segments_v1 (identity TEXT, idx INTEGER, blob BLOB, sha TEXT, PRIMARY KEY(identity,idx))')
        self.db.commit()
    @staticmethod
    def identity(source_hash,config):return digest({'source_sha256':source_hash,'config':config})
    def get(self,key,index):
        row=self.db.execute('SELECT blob,sha FROM segments_v1 WHERE identity=? AND idx=?',(key,index)).fetchone()
        if row is None:return None
        if hashlib.sha256(row[0]).hexdigest()!=row[1]:raise ValueError('corrupt segment cache')
        a=np.frombuffer(row[0],dtype='<f4').copy()
        if a.shape!=(512,) or not np.isfinite(a).all() or abs(np.linalg.norm(a)-1)>1e-5:raise ValueError('invalid cached vector')
        return a
    def put(self,key,index,a):
        blob=np.asarray(a,dtype='<f4').tobytes()
        with self.db:self.db.execute('INSERT INTO segments_v1 VALUES (?,?,?,?)',(key,index,blob,hashlib.sha256(blob).hexdigest()))
    def close(self):self.db.close()


def extract(waveform,forward,cache,key):
    if np.asarray(waveform).ndim!=1 or not np.isfinite(waveform).all():raise ValueError('invalid waveform')
    plan=full_song_chunks(len(waveform));vectors=[];calls=0
    for c in plan:
        a=cache.get(key,c.index)
        if a is None:
            a=normalize(forward(segment(waveform,c)));calls+=1;cache.put(key,c.index,a)
        vectors.append(a)
    return np.stack(vectors),[c.as_dict()|{'start_seconds':c.start_sample/48000,'end_seconds':c.end_sample/48000} for c in plan],calls


def encoder_identity(root):
    from .stage5e1_contract import inspect_aff_feasibility,FUSION_CHECKPOINT
    feasible=inspect_aff_feasibility(root)
    if feasible['status']!='AFF_READY':raise ValueError('Arm D checkpoint not validated')
    package=Path(importlib.metadata.distribution('laion-clap').locate_file('laion_clap'))
    return {'checkpoint':str(FUSION_CHECKPOINT),'checkpoint_sha256':file_sha256(root/FUSION_CHECKPOINT),
            'feasibility':feasible,'packages':{p:importlib.metadata.version(p) for p in ['torch','torchaudio','torchvision','numpy','laion-clap','transformers']},
            'package_implementation':hashes(package.rglob('*.py'),package),
            'implementation':hashes([Path(__file__),root/'src/audio_similarity/stage5e1_encoders.py',root/'src/audio_similarity/stage5e1_sampling.py'],root)}


def materialize(root,run,replay=False):
    import torch
    from .stage5e1_encoders import NativeFusionClapEncoder,decode_mono
    from laion_clap.training.data import get_mel
    verify_hashes(root,read(run/'input_hashes.json'))
    config=read(run/'representation_config.json')
    if config['encoder']!=encoder_identity(root):raise ValueError('encoder environment changed')
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    torch.manual_seed(20260908);np.random.seed(20260908)
    cache=SegmentCache(root/'artifacts/stage5g1_clap_similarity/segments_v1.sqlite')
    model=None;counts={'forward_passes':0,'cache_hits':0};arrays={};records=[];statuses=[];start=time.perf_counter()
    def forward(audio):
        nonlocal model
        if replay:raise RuntimeError('cache replay would perform inference')
        if model is None:model=NativeFusionClapEncoder(root/config['encoder']['checkpoint'],device=config['device'])
        view=get_mel(model._quantize(audio),model.module.model_cfg['audio_cfg'])
        if tuple(view.shape)!=(1001,64):raise ValueError('Arm D mel geometry changed')
        with torch.no_grad():return model.module.model.get_audio_embedding([model._sample([view]*4,longer=False,waveform=audio)])[0].detach().float().cpu().numpy()
    try:
        for t in read(run/'tracks.json'):
            id=t['spotify_track_id'];path=root/t['retained_source_path']
            try:
                if file_sha256(path)!=t['source_sha256']:raise ValueError('source changed')
                waveform=decode_mono(path,48000);key=cache.identity(t['source_sha256'],config)
                a,plan,calls=extract(waveform,forward,cache,key);arrays[id]=a
                records.extend({'spotify_track_id':id,**c} for c in plan)
                counts['forward_passes']+=calls;counts['cache_hits']+=len(a)-calls
                statuses.append({'spotify_track_id':id,'status':'OK','segments':len(a),'identity':key})
            except Exception as exc:
                statuses.append({'spotify_track_id':id,'status':'FAILED','error':str(exc)})
                raise
    finally:
        cache.close()
        ledger=counts|{'seconds':time.perf_counter()-start,'tracks':statuses,'replay':replay,
                       'frozen_parameter_count':sum(p.numel() for p in model.module.model.parameters()) if model else None}
        number=len(list(run.glob('extraction_ledger_*.json')))
        freeze_json(run/f'extraction_ledger_{number:03d}.json',ledger)
    freeze(run/'segments.npz',npz_bytes(arrays));freeze_json(run/'segment_manifest.json',records)
    freeze_json(run/'track_status.json',statuses)
    pooled=np.stack([normalized_mean(arrays[id]) for id in sorted(arrays)])
    freeze(run/'b1_matrix.npz',npz_bytes({'ids':np.array(sorted(arrays)),'scores':pooled.astype(np.float64)@pooled.astype(np.float64).T}))
    return counts
