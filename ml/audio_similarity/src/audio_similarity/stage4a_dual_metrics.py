"""Frozen dual-encoder Stage 4A human metrics and cheapest-K verdict."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd
PAIR_MAP={('CENTER5_DUAL','UNIFORM3_DUAL_MEAN'):'UNIFORM3_vs_CENTER5',('UNIFORM3_DUAL_MEAN','UNIFORM5_DUAL_MEAN'):'UNIFORM5_vs_UNIFORM3',('CENTER5_DUAL','UNIFORM5_DUAL_MEAN'):'UNIFORM5_vs_CENTER5'}
def bootstrap(values,draws=50000,seed=20260905):
 data=np.asarray([values[k] for k in sorted(values)]);rng=np.random.default_rng(seed);means=data[rng.integers(0,len(data),size=(draws,len(data)))].mean(axis=1);return tuple(float(x) for x in np.quantile(means,[.025,.975]))
def material(x,ci):return x>=.05 and ci[0]>0
def decide(pairs,protocol):
 if protocol:return 'INSUFFICIENT_EVIDENCE_PICK_CHEAPER'
 a,b,c=[pairs[x] for x in ('UNIFORM3_vs_CENTER5','UNIFORM5_vs_UNIFORM3','UNIFORM5_vs_CENTER5')];p3,p53,p5=material(*a),material(*b),material(*c)
 if p3:return 'UNIFORM5_DUAL_WINS' if p53 and p5 else 'UNIFORM3_DUAL_WINS'
 if p5:return 'UNIFORM5_DUAL_WINS' if p53 else 'UNIFORM3_DUAL_WINS'
 return 'CENTER5_DUAL_SUFFICIENT' if max(a[0],c[0])<=0 else 'INSUFFICIENT_EVIDENCE_PICK_CHEAPER'
def summarize(ratings_path,keys_path,draws=50000,seed=20260905,required=240):
 ratings=pd.read_csv(ratings_path,dtype=str).fillna('');keys=json.loads(Path(keys_path).read_text())['trials'];latest=ratings[ratings.reviewer_id.str.casefold()=='lenny'].drop_duplicates('trial_id',keep='last');rows=[]
 for row in latest.itertuples(index=False):
  if row.trial_id not in keys:raise ValueError(f'unknown dual trial {row.trial_id}')
  k=keys[row.trial_id];selected=None if row.choice in ('Tie','Neither') else int(k['candidate_a'] if row.choice=='A' else k['candidate_b']);x=int(k['method_x_candidate']);credit=None if row.choice=='Neither' else .5 if row.choice=='Tie' else 1. if selected==x else 0.;rows.append({'trial':row.trial_id,'query':int(k['query_id']),'x':k['method_x'],'y':k['method_y'],'choice':row.choice,'x_credit':credit})
 frame=pd.DataFrame(rows);complete=len(frame)==required and set(frame.trial)==set(keys) if len(frame) else False;reports={};decision={}
 for (lower,higher),name in PAIR_MAP.items():
  sub=frame[(frame.x==lower)&(frame.y==higher)] if len(frame) else pd.DataFrame(columns=['x_credit','choice','query']);valid=sub[sub.x_credit.notna()].copy();valid['higher']=1-valid.x_credit.astype(float);macro=valid.groupby('query').higher.mean().to_dict();estimate=float(np.mean(list(macro.values()))) if macro else float('nan');ci=bootstrap(macro,draws,seed) if macro else (float('nan'),float('nan'));imp=estimate-.5;ici=(ci[0]-.5,ci[1]-.5);decision[name]=(imp,ici);reports[name]={'lower_method':lower,'higher_method':higher,'trials':len(sub),'preference_denominator':len(valid),'represented_queries':len(macro),'higher_pairwise_preference':float(valid.higher.mean()) if len(valid) else None,'higher_query_macro_preference':estimate,'improvement_over_0_5':imp,'improvement_95_ci':list(ici),'tie_rate':float((sub.choice=='Tie').mean()) if len(sub) else None,'neither_rate':float((sub.choice=='Neither').mean()) if len(sub) else None}
 protocol=not complete or any(x['represented_queries']==0 for x in reports.values());result=decide(decision,protocol)
 return {'schema_version':'stage4a-dual-final-metrics-v1','designated_reviewer':'lenny','primary_denominator':'dual_encoder_bundle_only','superseded_clap_only_ratings_included':False,'append_only_events':len(ratings),'canonical_trials':len(frame),'required_trials':required,'protocol_failure':protocol,'method_pairs':reports,'bootstrap':{'unit':'query','draws':draws,'seed':seed},'verdict':result,'stage4b_triggered':result in ('UNIFORM3_DUAL_WINS','UNIFORM5_DUAL_WINS')}
