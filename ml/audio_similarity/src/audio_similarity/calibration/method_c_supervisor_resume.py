"""Continue a verified, prepared handoff after a diagnosed pre-inference stop."""
import fcntl
import os
from pathlib import Path
import subprocess

from .contracts import freeze_json,file_hash,require
from .method_c_full_inputs import read
from .method_c_supervisor import GPU,MONITOR,process_identity


def resume(root):
    directory=root/MONITOR
    with (directory/'supervisor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(read(directory/'cpu_drain.result.json')['exit_code']==0,'CPU drain incomplete')
        require(process_identity(read(directory/'cpu_process.json')['pid']) is None,'old CPU worker still alive')
        require((root/GPU/'continuation_imports.json').exists(),'continuation not prepared')
        freeze_json(directory/'resume_after_repool.json',{'reason':'diagnosed float32 resume cast; exact original chunks preserved',
            'authorization_sha256':file_hash(root/GPU/'cpu_resume_repool_authorization.json')})
        env=os.environ.copy()
        env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='2')
        gpu_env=env|{'METHOD_C_RUN_DIRECTORY':GPU,'METHOD_C_DEVICE':'cuda:0'}
        python=str(root/'.venv/bin/python')
        commands=[('reuse_preflight',[python,'-c',
            'from pathlib import Path; from audio_similarity.calibration.method_c_full_inputs import RUN,read,reusable; p=Path.cwd(); print(len(reusable(p,read(p/RUN/"corpus.json"))))'],gpu_env),
            ('gpu_parity',[python,'-m','audio_similarity.calibration.method_c_gpu_parity'],gpu_env),
            ('gpu_extraction',[python,'-m','audio_similarity.calibration.method_c_full_worker'],gpu_env),
            ('verification',[python,'-m','audio_similarity.calibration.method_c_full_verify'],gpu_env),
            ('nonheavy_tests',[python,'-m','pytest','-q'],env|{'OMP_NUM_THREADS':'1'})]
        for name,args,environment in commands:
            freeze_json(directory/(name+'.start.json'),{'command':args,'runtime':'GPU' if environment.get('METHOD_C_DEVICE')=='cuda:0' else 'CPU'})
            with (directory/(name+'.log')).open('x') as log:
                process=subprocess.Popen(args,cwd=root,env=environment,stdout=log,stderr=subprocess.STDOUT)
                freeze_json(directory/(name+'.pid.json'),{'pid':process.pid})
                code=process.wait()
            freeze_json(directory/(name+'.result.json'),{'exit_code':code})
            require(code==0,name+' failed; inspect preserved log')
            print({'phase':name,'status':'COMPLETE'},flush=True)
        freeze_json(directory/'complete.json',{'status':'MATERIALIZATION_AND_VERIFICATION_COMPLETE',
            'run_directory':GPU,'calibration_started':False})


if __name__=='__main__':
    resume(Path.cwd())
