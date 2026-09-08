"""Small symmetric latent-segment scorer; human preferences are the only targets."""
import hashlib
import time
from itertools import combinations
import numpy as np
import torch
from .stage5e3_artifacts import read,freeze_json,freeze,npz_bytes


class SegmentSimilarity(torch.nn.Module):
    def __init__(self):
        super().__init__();self.projection=torch.nn.Linear(512,16);self.head=torch.nn.Linear(32,1)
    def projected_logit(self,a,b):
        # All section relationships; symmetric by construction, no metadata inputs.
        delta=(a[:,None,:]-b[None,:,:]).abs().mean(dim=(0,1))
        product=(a[:,None,:]*b[None,:,:]).mean(dim=(0,1))
        return self.head(torch.cat([delta,product])).squeeze()
    def forward(self,a,b):
        return torch.sigmoid(self.projected_logit(torch.tanh(self.projection(a)),torch.tanh(self.projection(b))))


def setup(seed):
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);torch.manual_seed(seed);np.random.seed(seed)


def preference_loss(model,features,constraints):
    if not constraints:raise ValueError('no human preferences')
    ids=sorted({p[k] for p in constraints for k in ['anchor','preferred','other']})
    projected={id:torch.tanh(model.projection(features[id])) for id in ids}
    scores={};by_anchor={}
    for p in constraints:
        keys=[tuple(sorted((p['anchor'],p[k]))) for k in ['preferred','other']]
        for key in keys:
            if key not in scores:scores[key]=model.projected_logit(projected[key[0]],projected[key[1]])
        by_anchor.setdefault(p['anchor'],[]).append(torch.nn.functional.softplus(-(scores[keys[0]]-scores[keys[1]])))
    return torch.stack([torch.stack(losses).mean() for losses in by_anchor.values()]).mean()


def train(features,train_rows,validation_rows,config):
    if {p[k] for p in train_rows for k in ['anchor','preferred','other']} & {p[k] for p in validation_rows for k in ['anchor','preferred','other']}:
        raise ValueError('training/validation track leakage')
    setup(config['seed']);model=SegmentSimilarity();c=config['M1']
    optimizer=torch.optim.AdamW(model.parameters(),lr=c['learning_rate'],weight_decay=c['weight_decay'])
    history=[];best=float('inf');state=None;stale=0;began=time.perf_counter()
    for epoch in range(c['epochs']):
        model.train();optimizer.zero_grad();loss=preference_loss(model,features,train_rows)
        if not torch.isfinite(loss):raise ValueError('nonfinite training loss')
        loss.backward();optimizer.step();model.eval()
        with torch.no_grad():validation=float(preference_loss(model,features,validation_rows))
        history.append({'epoch':epoch+1,'train_loss_before_step':float(loss.detach()),'validation_loss':validation})
        if validation<best-c['minimum_validation_improvement']:
            best=validation;state={k:v.detach().clone() for k,v in model.state_dict().items()};stale=0;selected=epoch+1
        else:stale+=1
        if stale>=c['patience']:break
    model.load_state_dict(state);model.eval()
    return model,{'epochs':history,'selected_epoch':selected,'best_validation_loss':best,'runtime_seconds':time.perf_counter()-began}


def score_matrix(model,features,ids):
    began=time.perf_counter();matrix=np.zeros((len(ids),len(ids)),dtype=np.float64)
    with torch.no_grad():
        for i,a in enumerate(ids):
            for j in range(i,len(ids)):
                value=float(model(features[a],features[ids[j]]));matrix[i,j]=matrix[j,i]=value
    return matrix,time.perf_counter()-began


def metric(scores,ids,constraints):
    positions={id:i for i,id in enumerate(ids)};by={};strong={}
    for p in constraints:
        delta=scores[positions[p['anchor']],positions[p['preferred']]]-scores[positions[p['anchor']],positions[p['other']]]
        value=.5 if abs(delta)<=1e-6 else float(delta>0)
        by.setdefault(p['anchor'],[]).append(value)
        if p['gap']>=2:strong.setdefault(p['anchor'],[]).append(value)
    macro={k:float(np.mean(v)) for k,v in sorted(by.items())}
    return {'anchor_macro':float(np.mean(list(macro.values()))) if macro else None,'per_anchor':macro,
            'preference_micro':float(np.mean([v for a in by.values() for v in a])) if by else None,
            'constraints':len(constraints),'anchors':len(by),'strong_constraints':sum(len(v) for v in strong.values()),
            'strong_anchor_macro':float(np.mean([np.mean(v) for v in strong.values()])) if strong else None}


def bootstrap(x,y,seed):
    ids=sorted(set(x)&set(y));delta=np.array([x[id]-y[id] for id in ids])
    if not len(delta):return {'delta':None,'low':None,'high':None,'reason':'no eligible anchors'}
    rng=np.random.Generator(np.random.PCG64(seed));sample=delta[rng.integers(0,len(delta),(2000,len(delta)))].mean(axis=1)
    lo,hi=np.percentile(sample,[2.5,97.5],method='linear')
    return {'delta':float(delta.mean()),'low':float(lo),'high':float(hi),'eligible_ids':ids,'reason':None}


def run_learning(root,run):
    config=read(run/'protocol.json');split=read(run/'split.json')
    if not split['counts']['passes']:return {'status':'DATA_INSUFFICIENT','trained':False}
    with np.load(run/'segments.npz',allow_pickle=False) as z:features={k:torch.from_numpy(z[k].copy()) for k in z.files}
    ids=sorted(features);baselines={}
    for name,path in [('B0','b0_matrix.npz'),('B1','b1_matrix.npz')]:
        with np.load(run/path,allow_pickle=False) as z:
            order=list(z['ids']);pos=[order.index(id) for id in ids];baselines[name]=z['scores'][np.ix_(pos,pos)]
    curves=[];full=None
    # This loop never receives test judgments. Curves expose train/validation only.
    ordered=sorted(split['constraints']['train'],key=lambda p:hashlib.sha256(f"{config['seed']}:{p['anchor']}:{p['preferred']}:{p['other']}".encode()).hexdigest())
    for fraction in config['M1']['learning_curve_fractions']:
        subset=ordered[:max(1,int(len(ordered)*fraction))]
        model,history=train(features,subset,split['constraints']['validation'],config)
        scores,cost=score_matrix(model,features,ids)
        checkpoint=npz_bytes({k:v.detach().numpy() for k,v in model.state_dict().items()})
        freeze(run/f'model_{fraction}.npz',checkpoint)
        curves.append({'fraction':fraction,'training_constraints':len(subset),'train':metric(scores,ids,subset),
                       'validation':metric(scores,ids,split['constraints']['validation']),
                       'selected_epoch':history['selected_epoch'],'checkpoint_sha256':hashlib.sha256(checkpoint).hexdigest()})
        # Wall-clock timings belong to a single immutable execution ledger.
        number=len(list(run.glob(f'training_ledger_{fraction}_*.json')))
        freeze_json(run/f'training_ledger_{fraction}_{number:03d}.json',history|{'inference_matrix_seconds':cost,'matrix_pairs':len(ids)*(len(ids)+1)//2})
        if fraction==1.0:full=scores;final=model
    freeze_json(run/'learning_curves.json',curves)
    freeze(run/'m1_matrix.npz',npz_bytes({'ids':np.array(ids),'scores':full}))
    methods=baselines|{'M1':full};results={}
    for part in ['train','validation','test']:
        results[part]={name:metric(scores,ids,split['constraints'][part]) for name,scores in methods.items()}
    comparisons={f'{x}_vs_{y}':bootstrap(results['test'][x]['per_anchor'],results['test'][y]['per_anchor'],config['seed']) for x,y in [('B1','B0'),('M1','B1'),('M1','B0')]}
    def improves(key):
        c=comparisons[key];return c['delta'] is not None and c['delta']>=config['evaluation']['material_gain'] and c['low']>0
    outcome='SUPPORTED' if improves('M1_vs_B1') else 'COVERAGE_ONLY' if improves('B1_vs_B0') else 'REPRESENTATION_LIMITED'
    output={'outcome':outcome,'metrics':results,'comparisons':comparisons,'trainable_parameters':sum(p.numel() for p in final.parameters()),
            'artist_sensitivity':'DATA_INSUFFICIENT' if not read(run/'artist_split.json')['counts']['passes'] else 'REQUIRES_SEPARATE_TRAINING',
            'production_activation':False}
    freeze_json(run/'comparison.json',output)
    return output
