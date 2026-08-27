import json,pandas as pd,pytest
from audio_similarity.stage4a_store import Store,StoreError

def make(tmp_path):
 report=tmp_path/'reports';report.mkdir();json.dump({'trials':{'opaque1':{'query_id':1,'candidate_a':2,'candidate_b':3,'method_x':'CENTER5','method_y':'UNIFORM3_MEAN','scores':{'secret':1}}}},open(report/'trial_keys.json','w'));manifest=tmp_path/'manifest.parquet';pd.DataFrame([{'track_id':i,'relative_audio_path':f'{i}.mp3','canonical_pcm_sha256':str(i)} for i in (1,2,3)]).to_parquet(manifest,index=False);return Store(report,tmp_path,manifest,' Reviewer One ')

def test_session_is_blinded_and_reviewer_locked(tmp_path):
 store=make(tmp_path);session=store.session('reviewer one');text=json.dumps(session).casefold()
 assert 'center5' not in text and 'method' not in text and 'score' not in text and 'candidate_a' not in text
 assert session['choices']==['A','B','Tie','Neither']
 with pytest.raises(StoreError):store.session('other')

def test_append_only_self_correction_and_resume(tmp_path):
 store=make(tmp_path);first=store.submit('opaque1','reviewer one','A',1);second=store.submit('opaque1','reviewer one','Tie',2);rows=pd.read_csv(store.ratings,dtype=str).fillna('')
 assert len(rows)==2 and rows.iloc[1].supersedes_event_id==first['event_id']
 session=store.session('reviewer one');assert session['trials'][0]['current_reviewer']['choice']=='Tie' and session['progress']['rated']==1

def test_tie_and_neither_are_not_coerced(tmp_path):
 store=make(tmp_path);store.submit('opaque1','reviewer one','Neither',1);assert store.session('reviewer one')['trials'][0]['current_reviewer']['choice']=='Neither'
