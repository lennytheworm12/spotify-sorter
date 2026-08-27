"""Frozen per-encoder pooling and weighted Stage 4A dual retrieval."""
from __future__ import annotations
import hashlib,itertools
import numpy as np
METHOD_CENTERS={'CENTER5_DUAL':(15,),'UNIFORM3_DUAL_MEAN':(5,15,25),'UNIFORM5_DUAL_MEAN':(3,9,15,21,27)}
METHODS=tuple(METHOD_CENTERS);ALPHA_CLAP=0.7172981519;ALPHA_MUQ=0.2827018481
class DualScoringError(ValueError):pass
def normalized_mean(rows):
 x=np.asarray(rows,dtype=np.float64)
 if x.ndim!=2 or len(x)<1 or not np.isfinite(x).all():raise DualScoringError('invalid segment matrix')
 n=np.linalg.norm(x,axis=1,keepdims=True)
 if np.any(n<=0):raise DualScoringError('zero-norm segment')
 v=(x/n).mean(axis=0);z=np.linalg.norm(v)
 if z<=0:raise DualScoringError('zero-norm aggregate')
 return (v/z).astype(np.float32)
def aggregate_encoder(by_center,method):return normalized_mean(np.stack([by_center[c] for c in METHOD_CENTERS[method]]))
def fused_score(clap_q,clap_c,muq_q,muq_c):return ALPHA_CLAP*float(clap_q@clap_c)+ALPHA_MUQ*float(muq_q@muq_c)
def exact_rank(query_id,clap,muq,excluded=None):
 blocked=set(excluded or ())|{query_id};q_c,q_m=clap[query_id],muq[query_id];rows=[]
 for tid in clap:
  if tid in blocked:continue
  cs=float(q_c@clap[tid]);ms=float(q_m@muq[tid]);rows.append((tid,ALPHA_CLAP*cs+ALPHA_MUQ*ms,cs,ms))
 return sorted(rows,key=lambda x:(-x[1],x[0]))
def generate_trials(rankings,seed,initial=20,expansion=50):
 pairs=((METHODS[0],METHODS[1]),(METHODS[1],METHODS[2]),(METHODS[0],METHODS[2]));public=[];keys={}
 for query in sorted(rankings):
  used=set()
  for left,right in pairs:
   choice=None
   for depth in (initial,expansion):
    lr={x[0]:i+1 for i,x in enumerate(rankings[query][left][:depth])};rr={x[0]:i+1 for i,x in enumerate(rankings[query][right][:depth])};ld={x[0]:x for x in rankings[query][left]};rd={x[0]:x for x in rankings[query][right]};options=[]
    for x,y in itertools.combinations(sorted(set(lr)|set(rr)),2):
     lx,ly=lr.get(x,depth+1),lr.get(y,depth+1);rx,ry=rr.get(x,depth+1),rr.get(y,depth+1)
     if (lx-ly)*(rx-ry)>=0 or tuple(sorted((x,y))) in used:continue
     if lx>ly:x,y,lx,ly,rx,ry=y,x,ly,lx,ry,rx
     options.append(((max(lx,ly,rx,ry),lx+ly+rx+ry,-(abs(lx-ly)+abs(rx-ry)),x,y),x,y))
    if options:choice=min(options);break
   if not choice:continue
   _,x,y=choice;used.add(tuple(sorted((x,y))));identity=f'{query}|{left}|{right}|{min(x,y)}|{max(x,y)}';trial='s4d_'+hashlib.sha256(identity.encode()).hexdigest()[:20];swap=hashlib.sha256(f'{seed}|{identity}'.encode()).digest()[0]&1;a,b=(y,x) if swap else (x,y)
   public.append({'trial_id':trial,'question':'Considering the available 30-second recordings overall, which candidate sounds more like the query?'})
   def detail(row):return None if row is None else {'fused':row[1],'clap':row[2],'muq':row[3]}
   keys[trial]={'query_id':query,'candidate_a':a,'candidate_b':b,'method_x':left,'method_y':right,'method_x_candidate':x,'method_y_candidate':y,'ranks_depth':depth,'scores':{left:{str(x):detail(ld.get(x)),str(y):detail(ld.get(y))},right:{str(x):detail(rd.get(x)),str(y):detail(rd.get(y))}}}
 return public,keys
