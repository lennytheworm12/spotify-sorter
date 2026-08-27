import json,pandas as pd
from audio_similarity.stage4a_dual_metrics import summarize
def fixture(tmp,choices):
 pairs=[('CENTER5_DUAL','UNIFORM3_DUAL_MEAN'),('UNIFORM3_DUAL_MEAN','UNIFORM5_DUAL_MEAN'),('CENTER5_DUAL','UNIFORM5_DUAL_MEAN')];keys={};rows=[]
 for q in range(2):
  for i,(x,y) in enumerate(pairs):
   t=f'd{q}{i}';keys[t]={'query_id':q,'candidate_a':10,'candidate_b':11,'method_x':x,'method_y':y,'method_x_candidate':10,'method_y_candidate':11};rows.append({'event_id':t,'trial_id':t,'reviewer_id':'lenny','choice':choices[i],'submitted_at':'1','supersedes_event_id':''})
 kp=tmp/'k.json';kp.write_text(json.dumps({'trials':keys}));rp=tmp/'r.csv';pd.DataFrame(rows).to_csv(rp,index=False);return rp,kp
def test_dual_metrics_never_include_superseded_denominator(tmp_path):
 rp,kp=fixture(tmp_path,['Tie','Neither','A']);x=summarize(rp,kp,100,7,6);assert not x['superseded_clap_only_ratings_included'];assert x['method_pairs']['UNIFORM3_vs_CENTER5']['higher_pairwise_preference']==.5;assert x['method_pairs']['UNIFORM5_vs_UNIFORM3']['preference_denominator']==0
def test_dual_higher_k_path(tmp_path):
 rp,kp=fixture(tmp_path,['B','B','B']);x=summarize(rp,kp,100,7,6);assert x['verdict']=='UNIFORM5_DUAL_WINS' and x['stage4b_triggered']
