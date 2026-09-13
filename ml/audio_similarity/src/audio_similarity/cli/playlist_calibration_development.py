"""Explicit personal development run; no lockbox or production activation."""
import argparse
import fcntl
import json
import os
from pathlib import Path

from ..calibration.development_inputs import RUN


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','audio','profiles-prepare','profiles-run','freeze-protocol','build','tune','status'))
    p.add_argument('--limit',type=int)
    args=p.parse_args()
    root=Path.cwd()
    if args.action=='prepare':
        from ..calibration.development_inputs import prepare
        result=prepare(root)
    elif args.action=='audio':
        # HF reads its offline constants at import time, including transitive
        # imports from the historical cache helpers. Set these before import.
        os.environ['HF_HUB_OFFLINE']='1'
        os.environ['TRANSFORMERS_OFFLINE']='1'
        os.environ['CUDA_VISIBLE_DEVICES']=''
        from ..calibration.development_offline import configure
        configure()
        from ..calibration.development_audio import materialize
        from ..calibration.development_validation import dependencies
        dependencies(root)
        (root/RUN).mkdir(parents=True,exist_ok=True)
        with (root/RUN/'.audio.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=materialize(root,limit=args.limit)
    elif args.action=='profiles-prepare':
        from ..calibration.development_profiles import prepare
        result=prepare(root)
    elif args.action=='profiles-run':
        from ..calibration.development_profiles import DevelopmentRunner
        runner=DevelopmentRunner(root)
        count=0
        while args.limit is None or count<args.limit:
            result=runner.next()
            print(json.dumps(result),flush=True)
            if result['status']=='COMPLETE':
                result=runner.freeze_profiles()
                break
            count+=1
    elif args.action=='build':
        from ..calibration.development_bundle import build
        from ..calibration.development_validation import dependencies, frozen_genre_inputs
        dependencies(root)
        frozen_genre_inputs(root)
        result=build(root)
    elif args.action=='freeze-protocol':
        from ..calibration.development_search import freeze_protocol
        frozen=freeze_protocol(root)
        result={'status':frozen['status'],'configurations':len(frozen['models']),'outer_folds':len(frozen['folds'])}
    elif args.action=='tune':
        from ..calibration.development_search import run
        from ..calibration.development_validation import dependencies, frozen_genre_inputs
        dependencies(root)
        frozen_genre_inputs(root)
        result=run(root)
    else:
        run=root/RUN
        result={'audio_tracks':len(list((run/'audio').glob('*.json'))),
            'prepared_audio':len(list((run/'gemini/prepared').glob('*.flac'))),
            'api_settlements':len(list((run/'gemini/execution/attempts').glob('*.settlement.json'))),
            'profiles_frozen':(run/'gemini/profiles_frozen.json').exists(),
            'profiles_stopped':(run/'gemini/execution/STOPPED.json').exists()}
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
