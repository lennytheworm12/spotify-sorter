"""Predeclared CPU/GPU numerical check using already frozen chunk evidence."""
from pathlib import Path
import os
import time
import numpy as np
from .contracts import digest,file_hash,freeze_json,require
from .method_c_full_inputs import RUN,CHECKPOINT,read
from .method_c_full_worker import configuration


def check(root):
    require(os.environ.get('METHOD_C_DEVICE')=='cuda:0','explicit GPU execution required')
    from .development_offline import configure
    configure()
    import torch
    require(torch.cuda.is_available(),'GPU unavailable')
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    torch.set_num_threads(2)
    from ..holistic_encoders import LaionClapEncoder
    from ..stage5e1_encoders import decode_mono
    from ..stage5e1_sampling import sampling_plan
    from .method_c_handoff import acquisition_processes,evaluate
    import subprocess
    free=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).strip())
    require(evaluate(root,acquisition_processes(),free)['status']=='READY_FOR_GPU_PARITY_CHECK', 'acquisition/GPU release gate failed')
    directory=root/RUN
    config=configuration(root)
    freeze_json(directory/'configuration.json',config)
    receipt=read(directory/'continuation_imports.json')
    tracks={r['recording_id']:r for r in read(directory/'corpus.json')['recordings']}
    selected=[]
    for sid,entry in sorted(receipt['features'].items()):
        feature=read(root/entry['path'])
        if feature['origin'].get('status')=='NEW_FULL_SONG_C':
            selected.append(sid)
        if len(selected)==3:
            break
    require(len(selected)==3,'three completed CPU tracks required')
    plan={'recording_ids':selected,'chunks':'first/middle/last unique indices per track',
          'max_abs_error':1e-4,'minimum_cosine':.999999,'configuration_sha256':digest(config),
          'selection':'first three sorted CPU-computed IDs; no ratings or scores inspected',
          'implementation_sha256':file_hash(Path(__file__))}
    freeze_json(directory/'gpu_parity_plan.json',plan)
    encoder=None
    results=[]
    new_calls=0
    for sid in selected:
        r=tracks[sid]
        require(file_hash(root/r['source_path'])==r['audio_sha256'],'parity source changed')
        require(file_hash(root/receipt['features'][sid]['path'])==receipt['features'][sid]['sha256'], 'CPU parity reference changed')
        original=read(root/receipt['features'][sid]['path'])
        wav=decode_mono(root/r['source_path'],48000)
        chunks=sampling_plan(len(wav),r['audio_sha256'])['full_song_chunks']
        for index in sorted({0,len(chunks)//2,len(chunks)-1}):
            path=directory/'gpu_parity_chunks'/f'{sid}_{index}.json'
            if path.exists():
                item=read(path)
                require(item['plan_sha256']==digest(plan),'parity cache changed')
                gpu=np.asarray(item['vector'],dtype=np.float64)
            else:
                encoder=encoder or LaionClapEncoder(checkpoint_path=str(root/CHECKPOINT))
                require(not (directory/'gpu_parity_attempts'/f'{sid}_{index}.json').exists(), 'unresolved prior parity attempt; investigate before retry')
                freeze_json(directory/'gpu_parity_attempts'/f'{sid}_{index}.json',
                    {'status':'ATTEMPT_RESERVED','plan_sha256':digest(plan)})
                c=chunks[index];start=time.monotonic()
                gpu=encoder.encode_segment(wav[c['start_sample']:c['end_sample']],48000).embedding
                new_calls+=1
                freeze_json(path,{'plan_sha256':digest(plan),'vector':gpu.tolist(),'elapsed_seconds':time.monotonic()-start})
            cpu=np.asarray(original['views'][index],dtype=np.float64)
            maximum=float(np.max(np.abs(cpu-gpu)))
            cosine=float(np.dot(cpu,gpu)/(np.linalg.norm(cpu)*np.linalg.norm(gpu)))
            results.append({'recording_id':sid,'chunk_index':index,'max_abs_error':maximum,'cosine':cosine})
    passed=all(r['max_abs_error']<=plan['max_abs_error'] and r['cosine']>=plan['minimum_cosine'] for r in results)
    output={'status':'PASS' if passed else 'FAIL','configuration_sha256':digest(config),
            'plan_sha256':digest(plan),'comparisons':results,'expected_engineering_calls':len(results),
            'gpu_name':torch.cuda.get_device_name(0),'cuda':torch.version.cuda}
    freeze_json(directory/'gpu_parity.json',output)
    require(passed,'CPU/GPU numerical parity failed')
    return output|{'new_calls_this_invocation':new_calls}


if __name__=='__main__':
    import json
    print(json.dumps(check(Path.cwd()),indent=2))
