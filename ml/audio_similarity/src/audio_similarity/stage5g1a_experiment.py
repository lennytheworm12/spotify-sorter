"""A single D-controlled scorer diagnostic with grouped development evaluation."""
from itertools import combinations
from pathlib import Path
import numpy as np
from .stage5e3_artifacts import read,freeze,freeze_json,npz_bytes,verify_hashes
from .stage5g1a_data import PRIOR
from .stage5g1a_model import pair_features,fit,agreement,interval


def feature_inputs(root,run):
    pairs=read(root/PRIOR/'human_evidence.json')['pairs']
    with np.load(run/'d_views.npz',allow_pickle=False) as z:views={id:z[id] for id in z.files}
    with np.load(run/'d0_matrix.npz',allow_pickle=False) as z:ids=list(z['ids']);matrix=z['scores']
    features={};baseline={}
    for p in pairs:
        a,b=sorted(p['tracks']);features[a,b]=pair_features(views[a],views[b]);baseline[a,b]=float(matrix[ids.index(a),ids.index(b)])
    freeze(run/'pair_features.npz',npz_bytes({p['pair_id']:features[tuple(sorted(p['tracks']))] for p in pairs}))
    return features,baseline


def train_and_record(run,name,features,baseline,rows,ridge):
    w,trace=fit(features,baseline,rows,ridge)
    freeze(run/f'{name}_weights.npz',npz_bytes({'weights':w}))
    number=len(list(run.glob(f'{name}_execution_*.json')))
    freeze_json(run/f'{name}_execution_{number:03d}.json',trace)
    return w,trace


def evaluate_folds(run,folds,features,baseline,config,prefix):
    results=[]
    for f in folds:
        if not f['eligible']:
            results.append({'fold':f['fold'],'eligible':False,'counts':f['counts'],'reason':'predeclared evidence floor not met'});continue
        # Exclude every validation/heldout track from the optimizer's preferences.
        train_ids=set(f['partitions']['train'])
        if any(not {p['anchor'],p['preferred'],p['other']}<=train_ids for p in f['constraints']['train']):raise ValueError('track leakage')
        w,trace=train_and_record(run,f"{prefix}_fold_{f['fold']}",features,baseline,f['constraints']['train'],config['model']['ridge'])
        predictions={p:baseline[p]+float(features[p]@w) for p in features}
        metrics={part:{'D0':agreement(baseline,rows),'D1':agreement(predictions,rows)} for part,rows in f['constraints'].items()}
        held=metrics['heldout'];deltas=[held['D1']['per_anchor'][a]-held['D0']['per_anchor'][a] for a in sorted(held['D0']['per_anchor'])]
        strong=[p for p in f['constraints']['heldout'] if p['gap']>=2]
        results.append({'fold':f['fold'],'eligible':True,'counts':f['counts'],'metrics':metrics,'paired_anchor_interval':interval(deltas),
                        'strong':{'D0':agreement(baseline,strong),'D1':agreement(predictions,strong)},
                        'training_final_loss':trace['final_preference_loss'],'gradient_max':trace['gradient_max'],
                        'weight_l2':trace['weight_l2'],'training_rows':len(f['constraints']['train'])})
        freeze_json(run/f"{prefix}_fold_{f['fold']}_scores.json",[{'tracks':list(p),'D0':baseline[p],'D1':predictions[p]} for p in sorted(predictions)])
    valid=[r for r in results if r['eligible']];deltas=[r['paired_anchor_interval']['point'] for r in valid]
    rng=np.random.Generator(np.random.PCG64(20260908));samples=[]
    for _ in range(2000):
        means=[]
        for r in valid:
            a=r['metrics']['heldout'];ids=sorted(a['D0']['per_anchor'])
            d=np.array([a['D1']['per_anchor'][id]-a['D0']['per_anchor'][id] for id in ids])
            means.append(float(d[rng.integers(0,len(d),len(d))].mean()))
        if means:samples.append(float(np.mean(means)))
    bounds=np.percentile(samples,[2.5,97.5],method='linear').tolist() if samples else [None,None]
    summary={'folds':results,'eligible_folds':len(valid),'fold_macro_interval':interval(deltas),
             'stratified_anchor_interval':{'low':bounds[0],'high':bounds[1]},
             'positive_folds':sum(d>0 for d in deltas),'stationary_optimization':bool(valid) and all(r['gradient_max']<=config['decision']['stationary_gradient_max'] for r in valid)}
    freeze_json(run/f'{prefix}_results.json',summary)
    return summary


def optional_correspondence(root,run):
    """One fixed, training-free diagnostic on already-revealed historical TEST."""
    with np.load(root/PRIOR/'segments.npz',allow_pickle=False) as z:segments={id:z[id].astype(np.float64) for id in z.files}
    constraints=read(root/PRIOR/'split.json')['constraints']['test']
    needed={tuple(sorted((p['anchor'],p[k]))) for p in constraints for k in ['preferred','other']}
    scores={}
    for a,b in sorted(needed):
        cross=segments[a]@segments[b].T;scores[a,b]=float((cross.max(axis=1).mean()+cross.max(axis=0).mean())/2)
    with np.load(root/PRIOR/'m1_matrix.npz',allow_pickle=False) as z:
        ids=list(z['ids']);m=z['scores'];old={p:float(m[ids.index(p[0]),ids.index(p[1])]) for p in needed}
    new=agreement(scores,constraints);historical=agreement(old,constraints)
    deltas=[new['per_anchor'][a]-historical['per_anchor'][a] for a in sorted(new['per_anchor'])]
    result={'new_correspondence':new,'historical_G1':historical,'delta_interval':interval(deltas),'new_fit':False,
            'fresh_confirmation':False,'population':'previously revealed Stage5G1 TEST, diagnostic only',
            'scores':[{'tracks':list(p),'correspondence':scores[p],'historical_G1':old[p]} for p in sorted(needed)]}
    freeze_json(run/'optional_correspondence.json',result);return result


def diagnose(smoke,primary,optional,config):
    if not smoke['passes']:return 'MODEL_CAPACITY_OR_IMPLEMENTATION_FAILURE'
    margin=config['decision']['material_gain'];a=primary['fold_macro_interval'];b=optional['delta_interval']
    primary_gain=primary['eligible_folds']==5 and a['point']>=margin and a['low']>0 and primary['positive_folds']>=4
    optional_gain=b['point'] is not None and b['point']>=margin and b['low']>0
    if primary_gain or optional_gain:return 'SCORER_OR_AGGREGATION_BOTTLENECK'
    if (primary['eligible_folds']==5 and primary['stationary_optimization'] and a['high']<margin and b['high'] is not None and b['high']<margin):
        return 'COMPLEMENTARY_REPRESENTATION_JUSTIFIED'
    return 'SUPERVISION_LIMITED'


def run_experiment(root,run):
    verify_hashes(root,read(run/'input_hashes.json'));config=read(run/'protocol.json');features,baseline=feature_inputs(root,run)
    smoke_rows=read(run/'smoke_preferences.json');_,trace=train_and_record(run,'smoke',features,baseline,smoke_rows,0)
    smoke={k:v for k,v in trace.items() if k not in ('runtime_seconds','history')}
    smoke['passes']=smoke['anchor_macro_agreement']>=config['smoke']['pass_agreement'] and smoke['final_preference_loss']<=config['smoke']['pass_loss']
    freeze_json(run/'smoke_result.json',smoke)
    if not smoke['passes']:
        primary=optional=None
    else:
        primary=evaluate_folds(run,read(run/'development_folds.json'),features,baseline,config,'primary')
        evaluate_folds(run,read(run/'artist_folds.json'),features,baseline,config,'artist')
        optional=optional_correspondence(root,run)
    outcome=diagnose(smoke,primary,optional,config)
    freeze_json(run/'diagnosis.json',{'outcome':outcome,'development_only':True,'production_activation':False})
    return {'outcome':outcome,'smoke':smoke,'primary':primary['fold_macro_interval'] if primary else None}

if __name__=='__main__':
    import argparse,json
    from .stage5g1a_data import prepare
    root=Path(__file__).resolve().parents[2];run=root/'reports/stage5g1a_scorer_diagnostic/v1'
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['prepare','run','verify'])
    command=parser.parse_args().command
    result=prepare(root,run) if command=='prepare' else run_experiment(root,run) if command=='run' else verify_hashes(root,read(run/'input_hashes.json'))
    print(json.dumps(result,sort_keys=True))
