"""Read-only acquisition/GPU gate; elapsed-time estimates never authorize handoff."""
from pathlib import Path
import json
import subprocess

from .method_c_full_inputs import read

ACQUISITION = '.research_audio/example_playlist_batches_v2'


def acquisition_processes(proc=Path('/proc')):
    matches=[]
    for directory in proc.iterdir():
        if not directory.name.isdigit():
            continue
        try:
            args=(directory/'cmdline').read_bytes().decode().split('\0')
            if 'audio_similarity.cli.reference_batches' not in args:
                continue
            if '--run-dir' not in args or args[args.index('--run-dir')+1] != ACQUISITION:
                continue
            stat=(directory/'stat').read_text().rsplit(')',1)[1].split()
            if stat[0] != 'Z':
                matches.append({'pid':int(directory.name),'start_ticks':stat[19]})
        except (FileNotFoundError,PermissionError,ProcessLookupError,IndexError):
            continue
    return sorted(matches,key=lambda p:p['pid'])


def evaluate(root, processes, free_mib):
    directory=root/ACQUISITION
    manifest=read(directory/'manifest.json')
    waiting=[]
    terminal={'COMPLETE','MANUAL_TAIL','ACQUISITION_FAILED'}
    for batch in manifest['batches']:
        path=directory/f"batch_{batch['batch_number']:04d}/state.json"
        if not path.exists():
            waiting.append({'batch':batch['batch_number'],'reason':'NOT_STARTED'})
            continue
        state=read(path)
        expected={t['local_recording_id'] for t in batch['tracks']}
        if set(state['tracks']) != expected or state['status'] != 'FINISHED' or any(t['state'] not in terminal for t in state['tracks'].values()):
            waiting.append({'batch':batch['batch_number'],'reason':'NOT_TERMINAL'})
    ready=not waiting and not processes and free_mib >= 5000
    return {'status':'READY_FOR_GPU_PARITY_CHECK' if ready else 'WAITING_FOR_ACQUISITION_RELEASE',
            'unfinished_batches':waiting,'live_acquisition_processes':processes,
            'gpu_free_mib':free_mib,'minimum_free_mib':5000,'estimated_time_used':False,
            'production_changes':False}


if __name__=='__main__':
    output=subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True)
    values=[int(v.strip()) for v in output.splitlines() if v.strip()]
    if len(values)!=1:
        raise RuntimeError('Explicit GPU selection required for multiple devices')
    print(json.dumps(evaluate(Path.cwd(),acquisition_processes(),values[0]),indent=2))
