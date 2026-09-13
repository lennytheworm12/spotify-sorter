"""Verified import of a stopped CPU run into an isolated GPU continuation."""
from pathlib import Path
import fcntl
from .contracts import digest,file_hash,freeze_json,require
from .method_c_full_inputs import read,CHECKPOINT_SHA
from .method_c_full_cache import load_feature,identity
from ..stage5e1_sampling import sampling_plan,normalized_mean
import numpy as np


def verified_imports(root,corpus,receipt):
    config=receipt['configuration']
    require(read(root/receipt['cpu_run']/'configuration.json')==config, 'CPU configuration source changed')
    require(config['sample_rate']==48000 and config['chunk_samples']==480000 and config['architecture']=='HTSAT-base' and config['fusion'] is False and config['tail']=='native repeatpad', 'incompatible CPU Method C contract')
    require(digest(config)==receipt['configuration_sha256'] and config['checkpoint_sha256']==CHECKPOINT_SHA,
            'CPU configuration mismatch')
    for name,sha in receipt['files'].items():
        require(file_hash(root/name)==sha,'CPU continuation input changed: '+name)
    for name,sha in config['implementation'].items():
        require(file_hash(root/receipt['cpu_run']/'implementation_snapshot'/name)==sha,'CPU implementation snapshot changed')
    out={}
    recordings={r['recording_id']:r for r in corpus['recordings']}
    for sid,entry in receipt['features'].items():
        r=recordings[sid]
        feature=load_feature(root/entry['path'],r,config)
        repaired=None
        if feature['origin'].get('status')=='NEW_FULL_SONG_C':
            plan=read(root/receipt['cpu_run']/'sampling'/(sid+'.json'))
            require(plan==sampling_plan(plan['full_song_chunks'][-1]['end_sample'],r['audio_sha256']), 'CPU sampling contract mismatch')
            require(len(plan['full_song_chunks'])==len(feature['views']), 'incomplete CPU views')
            authoritative=[]
            for chunk,vector in zip(plan['full_song_chunks'],feature['views']):
                cached=read(root/receipt['cpu_run']/'chunks'/sid/(str(chunk['index'])+'.json'))
                require(cached['identity']==digest({'identity':identity(r,config),'chunk':chunk}), 'CPU chunk identity changed')
                require(cached['vector_sha256']==digest(cached['vector']), 'CPU chunk payload changed')
                authoritative.append(cached['vector'])
            if authoritative != feature['views']:
                authorization=receipt.get('repool_authorizations',{}).get('features',{}).get(sid)
                require(authorization and authorization['original_feature_sha256']==entry['sha256'], 'CPU chunk linkage changed; reviewed repool authorization required')
                require(all(a==b or np.array_equal(np.asarray(a,dtype=np.float32).astype(np.float64),b) for a,b in zip(authoritative,feature['views'])), 'mismatch is not the diagnosed float32 resume cast')
                repaired={'reason':'remove diagnosed float32 resume cast; pool original float64 chunk evidence',
                          'original_feature_sha256':entry['sha256'],'new_inference_calls':0,
                          'implementation_sha256':file_hash(Path(__file__))}
                feature=feature|{'views':authoritative,'vector':normalized_mean(authoritative).tolist()}
        out[sid]={'kind':'CPU_CONTINUATION','path':entry['path'],'sha256':entry['sha256'],
                  'vector':feature['vector'],'views':feature['views'],'origin':feature['origin'],
                  'cpu_configuration_sha256':digest(config),'pooling_repair':repaired}
    return out


def prepare(root,cpu_run,gpu_run):
    cpu=root/cpu_run
    destination=root/gpu_run
    require(cpu!=destination,'continuation must be isolated')
    with (cpu/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        corpus=read(cpu/'corpus.json')
        config=read(cpu/'configuration.json')
        features={p.stem:{'path':str(p.relative_to(root)),'sha256':file_hash(p)} for p in sorted((cpu/'features').glob('*.json'))}
        files={str(p.relative_to(root)):file_hash(p) for p in sorted(cpu.rglob('*'))
               if p.is_file() and p.suffix in ('.json','.py')}
        receipt={'cpu_run':cpu_run,'configuration':config,'configuration_sha256':digest(config),
                 'features':features,'files':files,
                 'repool_authorizations':read(destination/'cpu_resume_repool_authorization.json') if (destination/'cpu_resume_repool_authorization.json').exists() else {},'reason':'owner requested GPU continuation after acquisition exits'}
        verified_imports(root,corpus,receipt)
        freeze_json(destination/'corpus.json',corpus)
        freeze_json(destination/'companion_features.json',read(cpu/'companion_features.json'))
        freeze_json(destination/'continuation_imports.json',receipt)
        return {'imported_completed_features':len(features),'cpu_run':cpu_run,'gpu_run':gpu_run}


def resume_original_cpu(root, *, limit=1):
    """Finish the interrupted track using the archived exact original worker."""
    import importlib.util
    import os
    os.environ['CUDA_VISIBLE_DEVICES']=''
    import torch
    require(not torch.cuda.is_available(), 'CPU drain must run without a visible CUDA device')
    cpu=root/'.research_audio/playlist_calibration_method_c_full_v1'
    config=read(cpu/'configuration.json')
    require(file_hash(root/config['checkpoint_path'])==config['checkpoint_sha256'], 'CPU checkpoint changed')
    for name,sha in config['implementation'].items():
        require(file_hash(cpu/'implementation_snapshot'/name)==sha,'original implementation changed')
        if name!='calibration/method_c_full_worker.py':
            require(file_hash(root/'src/audio_similarity'/name)==sha,'original CPU dependency changed')
    path=cpu/'implementation_snapshot/calibration/method_c_full_worker.py'
    spec=importlib.util.spec_from_file_location('audio_similarity.calibration._frozen_cpu_worker',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RUN=str(cpu.relative_to(root))
    module.configuration=lambda _:config
    return module.run(root,limit=limit)
