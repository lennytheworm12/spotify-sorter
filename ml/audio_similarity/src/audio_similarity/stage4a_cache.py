"""SQLite segment cache and resumable CLAP encoder for amended Stage 4A."""
from __future__ import annotations
import hashlib,json,sqlite3,time
from pathlib import Path
import numpy as np,pandas as pd,yaml
from .stage4a_sampling import CENTERS,cache_windows,decode,pcm_sha256

SCHEMA="""CREATE TABLE IF NOT EXISTS segments (
 corpus TEXT NOT NULL, corpus_version TEXT NOT NULL, track_id INTEGER NOT NULL,
 source_sha256 TEXT NOT NULL, canonical_pcm_sha256 TEXT NOT NULL,
 encoder_id TEXT NOT NULL, encoder_checkpoint_sha256 TEXT NOT NULL, encoder_revision TEXT NOT NULL,
 preprocessing_version TEXT NOT NULL, sampling_version TEXT NOT NULL,
 segment_index INTEGER NOT NULL, center_sec INTEGER NOT NULL, start_sample INTEGER NOT NULL, end_sample INTEGER NOT NULL,
 start_sec REAL NOT NULL, end_sec REAL NOT NULL, embedding_dtype TEXT NOT NULL,
 embedding_dimension INTEGER NOT NULL, embedding BLOB, embedding_sha256 TEXT,
 analysis_key TEXT NOT NULL, status TEXT NOT NULL, failure TEXT NOT NULL,
 encode_ms REAL NOT NULL, created_at INTEGER NOT NULL,
 PRIMARY KEY(track_id, analysis_key, center_sec)
)"""
class CacheError(ValueError):pass

def key(fields):
 names=('source_sha256','canonical_pcm_sha256','encoder_id','encoder_checkpoint_sha256','encoder_revision','preprocessing_version','sampling_version','embedding_dtype','embedding_dimension')
 return hashlib.sha256(json.dumps({n:fields[n] for n in names},sort_keys=True,separators=(',',':')).encode()).hexdigest()
def vector_bytes(vector):
 x=np.asarray(vector,dtype='<f4');norm=np.linalg.norm(x)
 if x.shape!=(512,) or not np.isfinite(x).all() or norm<=0:raise CacheError('invalid CLAP vector')
 x=(x/norm).astype('<f4');return x.tobytes(),hashlib.sha256(x.tobytes()).hexdigest()
class Cache:
 def __init__(self,path):
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.db=sqlite3.connect(self.path);self.db.execute(SCHEMA);self.db.commit()
 def centers(self,track_id,analysis_key):return {r[0] for r in self.db.execute("SELECT center_sec FROM segments WHERE track_id=? AND analysis_key=? AND status='ok'",(track_id,analysis_key))}
 def insert(self,row):
  names=[x[1] for x in self.db.execute('PRAGMA table_info(segments)')];self.db.execute(f"INSERT OR REPLACE INTO segments ({','.join(names)}) VALUES ({','.join('?'*len(names))})",[row[n] for n in names]);self.db.commit()
 def vectors(self):
  out={}
  for tid,center,blob,status in self.db.execute("SELECT track_id,center_sec,embedding,status FROM segments"):
   if status=='ok':out.setdefault(int(tid),{})[int(center)]=np.frombuffer(blob,dtype='<f4').copy()
  return out
 def manifest(self):
  total,ok,failed,tracks=self.db.execute("SELECT count(*),sum(status='ok'),sum(status!='ok'),count(DISTINCT track_id) FROM segments").fetchone()
  complete=self.db.execute("SELECT count(*) FROM (SELECT track_id FROM segments WHERE status='ok' GROUP BY track_id HAVING count(DISTINCT center_sec)=7)").fetchone()[0]
  return {'schema_version':'stage4a-segment-cache-sqlite-v1','path':str(self.path),'rows':total,'ok_rows':ok or 0,'failure_rows':failed or 0,'tracks_with_rows':tracks,'complete_tracks':complete,'expected_centers':list(CENTERS),'sqlite_sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}

def base_row(config,track,identity):
 row={'corpus':'fma_small','corpus_version':'fma_small_2017','track_id':int(track.track_id),'source_sha256':str(track.audio_sha256),'canonical_pcm_sha256':identity['canonical_pcm_sha256'],'encoder_id':'laion_clap','encoder_checkpoint_sha256':config['encoder']['checkpoint_sha256'],'encoder_revision':config['encoder']['revision'],'preprocessing_version':config['canonical_audio']['preprocessing_version'],'sampling_version':config['sampling']['cache_version'],'embedding_dtype':'float32','embedding_dimension':512}
 row['analysis_key']=key(row);return row

def migrate_center5(cache,config,candidates,identities,legacy_path):
 legacy=pd.read_parquet(legacy_path);success=legacy[legacy.status=='SUCCESS'].set_index('track_id');count=0
 for track in candidates.itertuples(index=False):
  if int(track.track_id) not in success.index:continue
  identity=identities[str(track.audio_sha256)];base=base_row(config,track,identity)
  if 15 in cache.centers(int(track.track_id),base['analysis_key']):continue
  raw,digest=vector_bytes(success.loc[int(track.track_id)].embedding);bounds=identity['window_bounds'];start,end=bounds['15'] if '15' in bounds else bounds['15.0']
  cache.insert(base|{'segment_index':CENTERS.index(15),'center_sec':15,'start_sample':start,'end_sample':end,'start_sec':start/24000,'end_sec':end/24000,'embedding':raw,'embedding_sha256':digest,'status':'ok','failure':'','encode_ms':float(success.loc[int(track.track_id)].encode_ms),'created_at':int(time.time())});count+=1
 return count

def encode(config_path,limit=None,track_ids=None):
 config_path=Path(config_path);root=config_path.parent.parent;config=yaml.safe_load(config_path.read_text());candidates=pd.read_parquet(root/config['corpus']['candidate_manifest']);identities=json.loads((root/config['paths']['pcm_cache']).read_text());cache=Cache(root/config['paths']['artifacts']/ 'segments.sqlite')
 migrated=migrate_center5(cache,config,candidates,identities,root/'artifacts/holistic_stage1a/laion_clap.parquet')
 if track_ids:candidates=candidates[candidates.track_id.isin(track_ids)]
 if limit:candidates=candidates.head(limit)
 from .holistic_encoders import LaionClapEncoder
 encoder=LaionClapEncoder(checkpoint_path=str(root/config['encoder']['checkpoint']))
 attempted=succeeded=failed=0;started=time.time()
 for track in candidates.itertuples(index=False):
  identity=identities[str(track.audio_sha256)];base=base_row(config,track,identity);done=cache.centers(int(track.track_id),base['analysis_key']);missing=[c for c in CENTERS if c not in done]
  if not missing:continue
  try:waveform=decode(root/config['corpus']['audio_root']/track.relative_audio_path);windows={w.center_sec:w for w in cache_windows(len(waveform))}
  except Exception as exc:
   for center in missing:
    w=identity['window_bounds'].get(str(center),identity['window_bounds'].get(f'{center}.0'));cache.insert(base|{'segment_index':CENTERS.index(center),'center_sec':center,'start_sample':w[0],'end_sample':w[1],'start_sec':w[0]/24000,'end_sec':w[1]/24000,'embedding':None,'embedding_sha256':'','status':'failed','failure':f'{type(exc).__name__}: {exc}'[:500],'encode_ms':0,'created_at':int(time.time())});failed+=1
   continue
  for center in missing:
   w=windows[center];t=time.perf_counter();attempted+=1
   try:
    result=encoder.encode_segment(np.asarray(waveform[w.start_sample:w.end_sample]),24000);raw,digest=vector_bytes(result.embedding);status='ok';failure='';succeeded+=1
   except Exception as exc:raw=None;digest='';status='failed';failure=f'{type(exc).__name__}: {exc}'[:500];failed+=1
   cache.insert(base|{'segment_index':CENTERS.index(center),'center_sec':center,'start_sample':w.start_sample,'end_sample':w.end_sample,'start_sec':w.start_sample/24000,'end_sec':w.end_sample/24000,'embedding':raw,'embedding_sha256':digest,'status':status,'failure':failure,'encode_ms':(time.perf_counter()-t)*1000,'created_at':int(time.time())})
 return cache.manifest()|{'migrated_center5_rows':migrated,'attempted_inference':attempted,'succeeded_inference':succeeded,'failed_inference':failed,'wall_sec':time.time()-started}
