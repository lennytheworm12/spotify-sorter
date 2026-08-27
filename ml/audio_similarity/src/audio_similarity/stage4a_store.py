"""Blinded single-reviewer append-only evaluator for Stage 4A."""
from __future__ import annotations
import csv,hashlib,io,json,re,threading,time,unicodedata,wave
from pathlib import Path
import numpy as np,pandas as pd
from .stage4a_sampling import decode,pcm_sha256
CHOICES=('A','B','Tie','Neither');COLUMNS=['event_id','trial_id','reviewer_id','choice','submitted_at','supersedes_event_id']
class StoreError(ValueError):pass
def normalize(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value or '')).casefold()).strip()[:80]
class Store:
 def __init__(self,report_dir,audio_root,candidate_manifest,reviewer_id):
  self.report=Path(report_dir);self.audio_root=Path(audio_root);self.reviewer=normalize(reviewer_id)
  if not self.reviewer:raise StoreError('non-empty designated reviewer ID required')
  self.keys=json.loads((self.report/'trial_keys.json').read_text())['trials'];self.candidates=pd.read_parquet(candidate_manifest).set_index('track_id');self.ratings=self.report/'human_ratings.csv';self.lock=threading.RLock();self.audio_cache={};self._write(self._read())
 def _read(self):
  if not self.ratings.exists() or not self.ratings.stat().st_size:return pd.DataFrame(columns=COLUMNS)
  frame=pd.read_csv(self.ratings,dtype=str).fillna('');
  if set(COLUMNS)-set(frame):raise StoreError('invalid ratings columns')
  return frame[COLUMNS]
 def _write(self,frame):
  self.ratings.parent.mkdir(parents=True,exist_ok=True);tmp=self.ratings.with_suffix('.tmp');frame.to_csv(tmp,index=False,columns=COLUMNS,quoting=csv.QUOTE_MINIMAL);tmp.replace(self.ratings)
 def latest(self,frame=None):
  frame=self._read() if frame is None else frame;return {str(row.trial_id):row for row in frame.itertuples(index=False)}
 def session(self,reviewer):
  if normalize(reviewer)!=self.reviewer:raise StoreError('reviewer ID does not match designated reviewer')
  latest=self.latest();trials=[]
  for trial_id in sorted(self.keys):
   own=latest.get(trial_id);trials.append({'trial_id':trial_id,'question':'Considering the available 30-second recordings overall, which candidate sounds more like the query?','query_audio':f'/trial/{trial_id}/query','a_audio':f'/trial/{trial_id}/a','b_audio':f'/trial/{trial_id}/b','current_reviewer':{'choice':own.choice if own else ''},'aggregate_count':1 if own else 0})
  return {'reviewer_id':self.reviewer,'choices':list(CHOICES),'trials':trials,'progress':{'rated':len(latest),'total':len(trials)}}
 def submit(self,trial_id,reviewer,choice,submitted_at=None):
  if normalize(reviewer)!=self.reviewer:raise StoreError('reviewer ID does not match designated reviewer')
  choice=str(choice).strip().capitalize()
  if choice not in CHOICES:raise StoreError('invalid choice')
  if trial_id not in self.keys:raise KeyError(trial_id)
  with self.lock:
   frame=self._read();prior=self.latest(frame).get(trial_id);stamp=int(time.time()) if submitted_at is None else int(submitted_at);event='s4vote_'+hashlib.sha256(f'{trial_id}|{self.reviewer}|{choice}|{stamp}|{len(frame)}'.encode()).hexdigest()[:24];row={'event_id':event,'trial_id':trial_id,'reviewer_id':self.reviewer,'choice':choice,'submitted_at':str(stamp),'supersedes_event_id':prior.event_id if prior else ''};frame=pd.concat([frame,pd.DataFrame([row])],ignore_index=True);self._write(frame)
  return {'ok':True,'event_id':event,'aggregate_count':1}
 def import_rows(self,rows):
  for row in rows:self.submit(row.get('trial_id'),row.get('reviewer_id'),row.get('choice'),row.get('submitted_at'))
  return {'applied':len(rows)}
 def export_bytes(self):return self.ratings.read_bytes()
 def audio(self,trial_id,role):
  if trial_id not in self.keys or role not in ('query','a','b'):raise KeyError('audio role')
  cache_key=(trial_id,role)
  if cache_key in self.audio_cache:return self.audio_cache[cache_key]
  key=self.keys[trial_id];track_id=int({'query':key['query_id'],'a':key['candidate_a'],'b':key['candidate_b']}[role]);row=self.candidates.loc[track_id];samples=decode(self.audio_root/row.relative_audio_path);digest=pcm_sha256(samples)
  if digest!=row.canonical_pcm_sha256:raise StoreError('canonical PCM hash mismatch')
  pcm=np.clip(np.asarray(samples),-1,1);pcm=(pcm*32767).astype('<i2');buffer=io.BytesIO()
  with wave.open(buffer,'wb') as output:output.setnchannels(1);output.setsampwidth(2);output.setframerate(24000);output.writeframes(pcm.tobytes())
  result=(buffer.getvalue(),digest);self.audio_cache[cache_key]=result;return result
