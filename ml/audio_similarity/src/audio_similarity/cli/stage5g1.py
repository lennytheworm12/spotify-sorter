"""Controlled CLAP-only learned similarity experiment; never activates production."""
import argparse
from pathlib import Path
import numpy as np
from audio_similarity.stage5e3_artifacts import read,freeze,freeze_json,npz_bytes,hashes,verify_hashes
from audio_similarity.stage5g1_evidence import inventory
from audio_similarity.stage5g1_segments import encoder_identity,materialize
from audio_similarity.stage5g1_learning import run_learning

ROOT=Path(__file__).resolve().parents[3]
RUN=ROOT/'reports/stage5g1_clap_similarity/v1'


def prepare(root=ROOT,run=RUN):
    config=read(root/'configs/stage5g1_v1.json');freeze_json(run/'protocol.json',config)
    stats=inventory(root,run,config)
    paths=[]
    for prefix in ['stage5e','stage5f1','holistic_stage2b','stage5c2_representative_100_amended_v2']:
        for directory in (root/'reports').glob(prefix+'*'):
            paths.extend(p for p in directory.rglob('*') if p.is_file())
    paths.extend(root/e['source'] for e in read(run/'human_evidence.json')['evidence'])
    paths.extend((root/'src/audio_similarity').glob('stage5g1*.py'))
    paths.extend([Path(__file__),root/'configs/stage5g1_v1.json',root/'uv.lock',root/'tests/test_stage5g1.py'])
    reference=hashes(set(paths),root)
    for t in read(run/'tracks.json'):reference[t['retained_source_path']]=t['source_sha256']
    freeze_json(run/'input_hashes.json',reference);verify_hashes(root,reference)
    identity=encoder_identity(root)
    # Reuse the exact old checkpoint and package validation, not a new model.
    freeze_json(run/'representation_config.json',{'encoder':identity,'segmentation':config['segmentation'],'device':'cuda',
                                                'determinism':'seed 20260908, one CPU thread, deterministic torch, TF32 disabled'})
    with np.load(root/'reports/stage5e1_four_arm_retrieval/similarity_matrices.npz',allow_pickle=False) as z:
        ids=sorted(t['spotify_track_id'] for t in read(run/'tracks.json'));old=list(z['spotify_ids'].astype(str));pos=[old.index(id) for id in ids]
        scores=z['d_clap'][np.ix_(pos,pos)]
        if not np.isfinite(scores).all() or not np.allclose(scores,scores.T,atol=1e-6):raise ValueError('invalid frozen Arm D matrix')
        freeze(run/'b0_matrix.npz',npz_bytes({'ids':np.array(ids),'scores':scores}))
    return {'status':'PREPARED','training_gate':stats['gate_passes'],'tracks':stats['compatible_tracks']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['prepare','extract','replay','train','verify'])
    args=parser.parse_args()
    if args.command=='prepare':result=prepare()
    else:
        verify_hashes(ROOT,read(RUN/'input_hashes.json'))
        if args.command in ['extract','replay']:result=materialize(ROOT,RUN,args.command=='replay')
        elif args.command=='train':result=run_learning(ROOT,RUN)
        else:result={'status':'INPUTS_UNCHANGED'}
    import json
    print(json.dumps(result,sort_keys=True,allow_nan=False))

if __name__=='__main__':main()
