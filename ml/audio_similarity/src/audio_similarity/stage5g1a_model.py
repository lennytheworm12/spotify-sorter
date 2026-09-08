"""Full-dimensional, symmetric ridge scorer over exact frozen Arm-D views."""
import hashlib
import time
from collections import defaultdict
import numpy as np
import torch


def pair_features(a, b):
    """Four coordinatewise summaries retain 512-D evidence through comparison."""
    a=np.asarray(a,dtype=np.float64);b=np.asarray(b,dtype=np.float64)
    if a.shape!=(4,512) or b.shape!=(4,512) or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('expected finite four-view 512-D inputs')
    local=a[1:]@b[1:].T
    # Argmax tie-breaking by fixed front/middle/back order; both directions used.
    forward=(a[1:]*b[1:][local.argmax(axis=1)]).mean(axis=0)
    backward=(b[1:]*a[1:][local.argmax(axis=0)]).mean(axis=0)
    features=np.concatenate([a[0]*b[0],(a[1:]*b[1:]).mean(axis=0),
                            (a[0]*b[1:].mean(axis=0)+b[0]*a[1:].mean(axis=0))/2,
                            (forward+backward)/2])*np.sqrt(512)
    return features


def fit(feature_map, baseline, constraints, ridge):
    """Convex objective; no holdout labels are accepted by the optimizer."""
    if not constraints:raise ValueError('empty training preferences')
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);torch.manual_seed(20260908)
    def key(a,b):return tuple(sorted((a,b)))
    x=[];offset=[];anchors=[]
    for p in constraints:
        good=key(p['anchor'],p['preferred']);bad=key(p['anchor'],p['other'])
        x.append(feature_map[good]-feature_map[bad]);offset.append(baseline[good]-baseline[bad]);anchors.append(p['anchor'])
    x=torch.tensor(np.stack(x),dtype=torch.float64);offset=torch.tensor(offset,dtype=torch.float64)
    counts={a:anchors.count(a) for a in set(anchors)}
    weights=torch.tensor([1/(len(counts)*counts[a]) for a in anchors],dtype=torch.float64)
    w=torch.nn.Parameter(torch.zeros(x.shape[1],dtype=torch.float64))
    optimizer=torch.optim.LBFGS([w],lr=1,max_iter=300,history_size=20,tolerance_grad=1e-9,tolerance_change=1e-12,line_search_fn='strong_wolfe')
    history=[];start=time.perf_counter()
    def closure():
        optimizer.zero_grad()
        data=(torch.nn.functional.softplus(-10*(offset+x@w))*weights).sum()
        loss=data+.5*ridge*(w*w).sum();loss.backward()
        history.append({'evaluation':len(history),'preference_loss':float(data.detach()),'objective':float(loss.detach())})
        return loss
    optimizer.step(closure);closure()
    margin=(offset+x@w).detach().numpy()
    agreement=np.where(np.abs(margin)<=1e-6,.5,(margin>0).astype(float))
    per_anchor={a:float(np.mean([v for v,q in zip(agreement,anchors) if q==a])) for a in sorted(counts)}
    return w.detach().numpy().copy(),{'history':history,'runtime_seconds':time.perf_counter()-start,
           'iterations':optimizer.state[w].get('n_iter',0),'gradient_max':float(w.grad.abs().max()),
           'final_preference_loss':history[-1]['preference_loss'],'anchor_macro_agreement':float(np.mean(list(per_anchor.values()))),
           'minimum_margin':float(margin.min()),'weight_l2':float(w.detach().norm()),'trainable_parameters':len(w)}


def agreement(scores, constraints):
    per=defaultdict(list)
    for p in constraints:
        a=p['anchor'];d=scores[tuple(sorted((a,p['preferred'])))]-scores[tuple(sorted((a,p['other'])))]
        per[a].append(.5 if abs(d)<=1e-6 else float(d>0))
    by={a:float(np.mean(v)) for a,v in sorted(per.items())}
    return {'anchors':len(by),'preferences':len(constraints),'per_anchor':by,
            'macro':float(np.mean(list(by.values()))) if by else None,
            'micro':float(np.mean([v for vs in per.values() for v in vs])) if per else None}


def interval(values,seed=20260908):
    if not len(values):return {'point':None,'low':None,'high':None}
    x=np.array(values,dtype=np.float64);rng=np.random.Generator(np.random.PCG64(seed))
    sample=x[rng.integers(0,len(x),(2000,len(x)))].mean(axis=1)
    lo,hi=np.percentile(sample,[2.5,97.5],method='linear')
    return {'point':float(x.mean()),'low':float(lo),'high':float(hi)}


def order(namespace,value):return hashlib.sha256(f'stage5g1a:20260908:{namespace}:{value}'.encode()).hexdigest()
