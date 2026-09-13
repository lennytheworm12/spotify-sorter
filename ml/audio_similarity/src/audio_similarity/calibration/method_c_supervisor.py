"""Monitor real acquisition termination and execute the authorized GPU handoff."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .contracts import freeze_json,require
from .method_c_handoff import acquisition_processes,evaluate
from .method_c_continuation import prepare

CPU='.research_audio/playlist_calibration_method_c_full_v1'
GPU='.research_audio/playlist_calibration_method_c_gpu_v1'
MONITOR='.research_audio/playlist_calibration_method_c_handoff_v1'


def process_identity(pid):
    path=Path('/proc')/str(pid)
    try:
        fields=(path/'stat').read_text().rsplit(')',1)[1].split()
        if fields[0]=='Z':
            return None
        return {'pid':pid,'start_ticks':fields[19],
                'args':(path/'cmdline').read_bytes().decode().split('\0')}
    except FileNotFoundError:
        return None


def supervise(root,cpu_pid):
    directory=root/MONITOR
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'supervisor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        original=process_identity(cpu_pid)
        require(original and 'audio_similarity.calibration.method_c_full_worker' in original['args'],
                'specified PID is not the live Method C worker')
        freeze_json(directory/'cpu_process.json',original)
        base_env=os.environ.copy()
        base_env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='2')
        gpu_env=base_env|{'METHOD_C_RUN_DIRECTORY':GPU,'METHOD_C_DEVICE':'cuda:0'}
        python=str(root/'.venv/bin/python')

        def child(name,args,env):
            freeze_json(directory/(name+'.start.json'),{'command':args,'runtime':'GPU' if env.get('METHOD_C_DEVICE')=='cuda:0' else 'CPU'})
            with (directory/(name+'.log')).open('x') as log:
                process=subprocess.Popen(args,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
                freeze_json(directory/(name+'.pid.json'),{'pid':process.pid})
                code=process.wait()
            freeze_json(directory/(name+'.result.json'),{'exit_code':code})
            require(code==0,name+' failed; inspect preserved log')
            print(json.dumps({'phase':name,'status':'COMPLETE'}),flush=True)

        last=None
        while True:
            output=subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True)
            gate=evaluate(root,acquisition_processes(),int(output.strip()))
            key=(gate['status'],len(gate['unfinished_batches']),len(gate['live_acquisition_processes']))
            if key!=last:
                print(json.dumps(gate),flush=True);last=key
            if gate['status']=='READY_FOR_GPU_PARITY_CHECK':
                freeze_json(directory/'acquisition_released.json',gate)
                break
            time.sleep(30)
        current=process_identity(cpu_pid)
        if current is not None:
            require(current==original,'CPU PID identity changed; refusing signal')
            freeze_json(directory/'cpu_stop_requested.json',{'pid':cpu_pid,'signal':'SIGINT',
                'reason':'verified acquisition process exit and GPU release; preserve partial chunks'})
            os.kill(cpu_pid,signal.SIGINT)
            while process_identity(cpu_pid) is not None:
                time.sleep(1)
        # Finish the interrupted song with the original CPU implementation.
        # A new invocation ledger records any retried in-flight chunk explicitly.
        child('cpu_drain',[python,'-c',
            'from pathlib import Path; from audio_similarity.calibration.method_c_continuation import resume_original_cpu; r=resume_original_cpu(Path.cwd(),limit=1); print(r); raise SystemExit(bool(r["failed"]))'],base_env)
        summary=prepare(root,CPU,GPU)
        freeze_json(directory/'continuation_prepared.json',summary)
        child('reuse_preflight',[python,'-c',
            'from pathlib import Path; from audio_similarity.calibration.method_c_full_inputs import RUN,read,reusable; p=Path.cwd(); print(len(reusable(p,read(p/RUN/"corpus.json"))))'],gpu_env)
        child('gpu_parity',[python,'-m','audio_similarity.calibration.method_c_gpu_parity'],gpu_env)
        child('gpu_extraction',[python,'-m','audio_similarity.calibration.method_c_full_worker'],gpu_env)
        child('verification',[python,'-m','audio_similarity.calibration.method_c_full_verify'],gpu_env)
        child('nonheavy_tests',[python,'-m','pytest','-q'],base_env|{'OMP_NUM_THREADS':'1'})
        freeze_json(directory/'complete.json',{'status':'MATERIALIZATION_AND_VERIFICATION_COMPLETE',
            'run_directory':GPU,'calibration_started':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--cpu-pid',type=int,required=True)
    arguments=parser.parse_args()
    supervise(Path.cwd(),arguments.cpu_pid)
