import json,pandas as pd
from audio_similarity.stage4a_metrics import summarize

def fixture(tmp_path,choices):
 pairs=[('CENTER5','UNIFORM3_MEAN'),('UNIFORM3_MEAN','UNIFORM5_MEAN'),('CENTER5','UNIFORM5_MEAN')];keys={};ratings=[]
 for q in range(2):
  for i,(x,y) in enumerate(pairs):
   trial=f't{q}{i}';keys[trial]={'query_id':q,'candidate_a':10,'candidate_b':11,'method_x':x,'method_y':y,'method_x_candidate':10,'method_y_candidate':11};ratings.append({'event_id':trial,'trial_id':trial,'reviewer_id':'lenny','choice':choices[i],'submitted_at':'1','supersedes_event_id':''})
 kp=tmp_path/'keys.json';kp.write_text(json.dumps({'trials':keys}));rp=tmp_path/'ratings.csv';pd.DataFrame(ratings).to_csv(rp,index=False);return rp,kp

def test_tie_half_neither_excluded_and_incomplete_is_protocol_failure(tmp_path):
 rp,kp=fixture(tmp_path,['Tie','Neither','A']);result=summarize(rp,kp,100,7,required=6)
 assert result['method_pairs']['UNIFORM3_vs_CENTER5']['higher_pairwise_preference']==.5
 assert result['method_pairs']['UNIFORM5_vs_UNIFORM3']['preference_denominator']==0
 assert result['protocol_failure'] and result['verdict']=='INSUFFICIENT_EVIDENCE_PICK_CHEAPER'

def test_higher_method_wins_all_three_pairs(tmp_path):
 rp,kp=fixture(tmp_path,['B','B','B']);result=summarize(rp,kp,100,7,required=6)
 assert all(x['higher_query_macro_preference']==1 for x in result['method_pairs'].values())
 assert result['verdict']=='UNIFORM5_WINS' and result['stage4b_triggered']
