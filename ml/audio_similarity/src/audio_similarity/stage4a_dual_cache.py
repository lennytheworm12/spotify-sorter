"""Resumable MuQ segment cache sharing the frozen CLAP source intervals."""
from __future__ import annotations
import json,time
from pathlib import Path
import numpy as np,pandas as pd,yaml
from .stage4a_cache import Cache,key,vector_bytes
from .stage4a_sampling import CENTERS,cache_windows,decode

def base(config,track,identity):
 muq=config['encoders']['muq'];row={'corpus':'fma_small','corpus_version':'fma_small_2017','track_id':int(track.track_id),'source_sha256':str(track.audio_sha256),'canonical_pcm_sha256':identity['canonical_pcm_sha256'],'encoder_id':muq['id'],'encoder_checkpoint_sha256':muq['weights_sha256'],'encoder_revision':muq['revision'],'preprocessing_version':config['canonical_audio']['preprocessing_version'],'sampling_version':config['sampling']['version'],'embedding_dtype':'float32','embedding_dimension':512};row['analysis_key']=key(row);return row
def bounds(identity,center):
 values=identity['window_bounds'];return values[str(center)] if str(center) in values else values[f'{center}.0']
def migrate(cache,config,candidates,identities,legacy):
 data=pd.read_parquet(legacy);data=data[data.status=='SUCCESS'].set_index('track_id');count=0
 for track in candidates.itertuples(index=False):
  tid=int(track.track_id)
  if tid not in data.index:continue
  identity=identities[str(track.audio_sha256)];row=base(config,track,identity)
  if 15 in cache.centers(tid,row['analysis_key']):continue
  raw,digest=vector_bytes(data.loc[tid].embedding);start,end=bounds(identity,15);cache.insert(row|{'segment_index':CENTERS.index(15),'center_sec':15,'start_sample':start,'end_sample':end,'start_sec':start/24000,'end_sec':end/24000,'embedding':raw,'embedding_sha256':digest,'status':'ok','failure':'','encode_ms':float(data.loc[tid].encode_ms),'created_at':int(time.time())});count+=1
 return count
def encode(config_path,limit=None,track_ids=None):
 config_path=Path(config_path);root=config_path.parent.parent;config=yaml.safe_load(config_path.read_text());candidates=pd.read_parquet(root/config['corpus']['candidate_manifest']);identities=json.loads((root/'data/holistic_stage4/pcm_identities.json').read_text());cache=Cache(root/config['paths']['muq_cache']);migrated=migrate(cache,config,candidates,identities,root/config['encoders']['muq']['center_artifact'])
 if track_ids:candidates=candidates[candidates.track_id.isin(track_ids)]
 if limit:candidates=candidates.head(limit)
 from .holistic_encoders import MuQMulanEncoder
 encoder=MuQMulanEncoder(revision=config['encoders']['muq']['revision']);attempted=success=failed=0;started=time.time()
 for track in candidates.itertuples(index=False):
  identity=identities[str(track.audio_sha256)];row=base(config,track,identity);done=cache.centers(int(track.track_id),row['analysis_key']);missing=[x for x in CENTERS if x not in done]
  if not missing:continue
  try:waveform=decode(root/config['corpus']['audio_root']/track.relative_audio_path);windows={w.center_sec:w for w in cache_windows(len(waveform))}
  except Exception as exc:
   for center in missing:
    start,end=bounds(identity,center);cache.insert(row|{'segment_index':CENTERS.index(center),'center_sec':center,'start_sample':start,'end_sample':end,'start_sec':start/24000,'end_sec':end/24000,'embedding':None,'embedding_sha256':'','status':'failed','failure':f'{type(exc).__name__}: {exc}'[:500],'encode_ms':0,'created_at':int(time.time())});failed+=1
   continue
  for center in missing:
   w=windows[center];expected=bounds(identity,center)
   if [w.start_sample,w.end_sample]!=expected:raise RuntimeError('shared source interval identity mismatch')
   t=time.perf_counter();attempted+=1
   try:result=encoder.encode_segment(np.asarray(waveform[w.start_sample:w.end_sample]),24000);raw,digest=vector_bytes(result.embedding);status='ok';failure='';success+=1
   except Exception as exc:raw=None;digest='';status='failed';failure=f'{type(exc).__name__}: {exc}'[:500];failed+=1
   cache.insert(row|{'segment_index':CENTERS.index(center),'center_sec':center,'start_sample':w.start_sample,'end_sample':w.end_sample,'start_sec':w.start_sample/24000,'end_sec':w.end_sample/24000,'embedding':raw,'embedding_sha256':digest,'status':status,'failure':failure,'encode_ms':(time.perf_counter()-t)*1000,'created_at':int(time.time())})
 return cache.manifest()|{'migrated_center5_rows':migrated,'attempted_inference':attempted,'succeeded_inference':success,'failed_inference':failed,'wall_sec':time.time()-started,'encoder':'muq_mulan_large'}
