"""Frozen single-reviewer Stage 4A metrics and quality-cost verdict."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd
from .stage4a_scoring import bootstrap,verdict
class MetricsError(ValueError):pass
PAIR_MAP={('CENTER5','UNIFORM3_MEAN'):'UNIFORM3_vs_CENTER5',('UNIFORM3_MEAN','UNIFORM5_MEAN'):'UNIFORM5_vs_UNIFORM3',('CENTER5','UNIFORM5_MEAN'):'UNIFORM5_vs_CENTER5'}
def canonical_rows(ratings:pd.DataFrame,keys:dict,reviewer='lenny'):
 rows=ratings[ratings.reviewer_id.astype(str).str.casefold()==reviewer.casefold()].drop_duplicates('trial_id',keep='last');output=[]
 for row in rows.itertuples(index=False):
  if row.trial_id not in keys:raise MetricsError(f'unknown trial {row.trial_id}')
  key=keys[row.trial_id];choice=str(row.choice);selected=None if choice in ('Tie','Neither') else int(key['candidate_a'] if choice=='A' else key['candidate_b'])
  x=int(key['method_x_candidate']);credit=None if choice=='Neither' else .5 if choice=='Tie' else 1.0 if selected==x else 0.0
  output.append({'trial_id':row.trial_id,'query_id':int(key['query_id']),'method_x':key['method_x'],'method_y':key['method_y'],'choice':choice,'x_credit':credit})
 return pd.DataFrame(output)
def summarize(ratings_path,keys_path,draws=50000,seed=20260905,required=240):
 ratings=pd.read_csv(ratings_path,dtype=str).fillna('');keys=json.loads(Path(keys_path).read_text())['trials'];rows=canonical_rows(ratings,keys);complete=len(rows)==required and set(rows.trial_id)==set(keys)
 pairs={};decision={}
 for (lower,higher),name in PAIR_MAP.items():
  subset=rows[(rows.method_x==lower)&(rows.method_y==higher)]
  # Generator method_x is lower. Convert x-credit to higher-method credit.
  valid=subset[subset.x_credit.notna()].copy();valid['higher_credit']=1-valid.x_credit.astype(float);macro=valid.groupby('query_id').higher_credit.mean().to_dict();estimate=float(np.mean(list(macro.values()))) if macro else float('nan');ci=bootstrap(macro,draws,seed) if macro else (float('nan'),float('nan'));improvement=estimate-.5;improvement_ci=(ci[0]-.5,ci[1]-.5)
  pairs[name]={'lower_method':lower,'higher_method':higher,'trials':len(subset),'preference_denominator':len(valid),'represented_queries':len(macro),'higher_pairwise_preference':float(valid.higher_credit.mean()) if len(valid) else None,'higher_query_macro_preference':estimate,'improvement_over_0_5':improvement,'improvement_95_ci':list(improvement_ci),'tie_rate':float((subset.choice=='Tie').mean()) if len(subset) else None,'neither_rate':float((subset.choice=='Neither').mean()) if len(subset) else None,'coverage':len(subset)/80}
  decision[name]=(improvement,improvement_ci)
 protocol_failure=not complete or any(value['represented_queries']==0 for value in pairs.values());result=verdict(*decision['UNIFORM3_vs_CENTER5'],*decision['UNIFORM5_vs_UNIFORM3'],*decision['UNIFORM5_vs_CENTER5'],protocol_failure)
 return {'schema_version':'stage4a-final-metrics-v1','designated_reviewer':'lenny','claim_boundary':'personal perceptual alignment on frozen FMA 30-second excerpts','append_only_events':len(ratings),'canonical_trials':len(rows),'required_trials':required,'protocol_failure':protocol_failure,'method_pairs':pairs,'bootstrap':{'unit':'query_id','draws':draws,'seed':seed,'confidence':.95},'verdict':result,'stage4b_triggered':result in ('UNIFORM3_WINS','UNIFORM5_WINS')}
