"""Frozen Stage 4A normalized means, retrieval, trials, bootstrap, and verdict."""
from __future__ import annotations
import hashlib,itertools
import numpy as np
from .stage4a_sampling import METHOD_CENTERS
METHODS=("CENTER5","UNIFORM3_MEAN","UNIFORM5_MEAN")
class ScoringError(ValueError): pass

def normalized_mean(rows:np.ndarray)->np.ndarray:
    x=np.asarray(rows,dtype=np.float64)
    if x.ndim!=2 or len(x)<1 or not np.isfinite(x).all(): raise ScoringError("invalid segment matrix")
    norms=np.linalg.norm(x,axis=1,keepdims=True)
    if np.any(norms<=0): raise ScoringError("zero-norm segment")
    vector=(x/norms).mean(axis=0); norm=np.linalg.norm(vector)
    if norm<=0: raise ScoringError("zero-norm aggregate")
    return (vector/norm).astype(np.float32)

def aggregates(by_center:dict[int,np.ndarray])->dict[str,np.ndarray]:
    return {method:normalized_mean(np.stack([by_center[c] for c in METHOD_CENTERS[method]])) for method in METHODS}

def exact_rank(query_id:int,vectors:dict[int,np.ndarray],excluded:set[int]|None=None)->list[tuple[int,float]]:
    blocked=set(excluded or ())|{query_id}; q=vectors[query_id]
    return sorted(((tid,float(q@v)) for tid,v in vectors.items() if tid not in blocked),key=lambda x:(-x[1],x[0]))

def all_rankings(query_ids:list[int],vectors:dict[str,dict[int,np.ndarray]],exclusions:dict[int,set[int]])->dict:
    return {q:{m:exact_rank(q,vectors[m],exclusions.get(q)) for m in METHODS} for q in query_ids}

def generate_trials(rankings:dict,seed:int,initial_depth:int=20,expansion_depth:int=50)->tuple[list[dict],dict]:
    pairs=((METHODS[0],METHODS[1]),(METHODS[1],METHODS[2]),(METHODS[0],METHODS[2])); public=[]; keys={}
    for query in sorted(rankings):
        used=set()
        for left,right in pairs:
            chosen=None
            for depth in (initial_depth,expansion_depth):
                lr={t:i+1 for i,(t,_) in enumerate(rankings[query][left][:depth])}; rr={t:i+1 for i,(t,_) in enumerate(rankings[query][right][:depth])}
                ls=dict(rankings[query][left]); rs=dict(rankings[query][right]); options=[]
                for x,y in itertools.combinations(sorted(set(lr)|set(rr)),2):
                    lx,ly=lr.get(x,depth+1),lr.get(y,depth+1); rx,ry=rr.get(x,depth+1),rr.get(y,depth+1)
                    if (lx-ly)*(rx-ry)>=0 or tuple(sorted((x,y))) in used: continue
                    if lx>ly: x,y,lx,ly,rx,ry=y,x,ly,lx,ry,rx
                    options.append(((max(lx,ly,rx,ry),lx+ly+rx+ry,-(abs(lx-ly)+abs(rx-ry)),x,y),x,y))
                if options: chosen=min(options); break
            if not chosen: continue
            _,x,y=chosen; used.add(tuple(sorted((x,y)))); identity=f"{query}|{left}|{right}|{min(x,y)}|{max(x,y)}"; trial_id='s4a_'+hashlib.sha256(identity.encode()).hexdigest()[:20]
            swap=hashlib.sha256(f"{seed}|{identity}".encode()).digest()[0]&1; a,b=(y,x) if swap else (x,y)
            public.append({"trial_id":trial_id,"question":"Considering the available 30-second recordings overall, which candidate sounds more like the query?"})
            keys[trial_id]={"query_id":query,"candidate_a":a,"candidate_b":b,"method_x":left,"method_y":right,"method_x_candidate":x,"method_y_candidate":y,"ranks_depth":depth,"scores":{left:{str(x):ls.get(x),str(y):ls.get(y)},right:{str(x):rs.get(x),str(y):rs.get(y)}}}
    return public,keys

def bootstrap(values:dict[int,float],draws:int=50000,seed:int=20260905)->tuple[float,float]:
    data=np.asarray([values[k] for k in sorted(values)]); rng=np.random.default_rng(seed); means=data[rng.integers(0,len(data),size=(draws,len(data)))].mean(axis=1)
    return tuple(float(x) for x in np.quantile(means,[.025,.975]))
def material(estimate,ci): return estimate>=.05 and ci[0]>0
def verdict(three_center,ci3,five_three,ci53,five_center,ci5,protocol_failure=False):
    if protocol_failure:return "INSUFFICIENT_EVIDENCE_PICK_CHEAPER"
    p3,p53,p5=material(three_center,ci3),material(five_three,ci53),material(five_center,ci5)
    if p3:return "UNIFORM5_WINS" if p53 and p5 else "UNIFORM3_WINS"
    if p5:return "UNIFORM5_WINS" if p53 else "UNIFORM3_WINS"
    return "CENTER5_SUFFICIENT" if max(three_center,five_center)<=0 else "INSUFFICIENT_EVIDENCE_PICK_CHEAPER"
