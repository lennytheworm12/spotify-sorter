"""Derive frozen Stage 4A aggregates, exact retrieval, and blinded trials."""
from __future__ import annotations
import hashlib,json,time
from pathlib import Path
import numpy as np,pandas as pd,yaml
from .stage4a_cache import Cache
from .stage4a_scoring import METHODS,aggregates,all_rankings,generate_trials

class AnalysisError(ValueError):pass
def atomic_json(path,value):path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');tmp.replace(path)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(config_path,validate_only=False):
 config_path=Path(config_path);root=config_path.parent.parent;c=yaml.safe_load(config_path.read_text());report=root/c['paths']['report_dir'];artifact=root/c['paths']['artifacts'];artifact.mkdir(parents=True,exist_ok=True)
 cache=Cache(artifact/'segments.sqlite');manifest=cache.manifest()
 if manifest['complete_tracks']!=c['corpus']['expected_eligible'] or manifest['failure_rows']!=0:raise AnalysisError(f'incomplete segment cache: {manifest}')
 if validate_only:
  saved=json.loads((report/'retrieval_diagnostics.json').read_text());
  for name in ('segment_cache_manifest.json','aggregate_manifest.json','trial_balance.json','trial_keys.json'):
   if not (report/name).is_file():raise AnalysisError(f'missing {name}')
  if saved['segment_cache_sqlite_sha256']!=manifest['sqlite_sha256']:raise AnalysisError('segment cache hash mismatch')
  return saved
 segments=cache.vectors();candidate=pd.read_parquet(root/c['corpus']['candidate_manifest']);query=json.loads((root/c['queries']['output']).read_text());query_ids=[int(x['query_id']) for x in query['queries']]
 vectors={method:{} for method in METHODS};aggregate_rows=[]
 for track_id,by_center in sorted(segments.items()):
  out=aggregates(by_center)
  for method,vector in out.items():vectors[method][track_id]=vector;aggregate_rows.append({'track_id':track_id,'aggregation_version':method,'K':len(c['sampling']['representations'][method]['centers_sec']),'embedding':vector.tolist(),'embedding_sha256':hashlib.sha256(np.asarray(vector,dtype='<f4').tobytes()).hexdigest()})
 aggregate_path=artifact/'aggregates.parquet';pd.DataFrame(aggregate_rows).to_parquet(aggregate_path,index=False)
 indexed=candidate.set_index('track_id');hash_groups={h:set(int(x) for x in g.track_id) for h,g in candidate.groupby('canonical_pcm_sha256')};exclusions={q:hash_groups[str(indexed.loc[q].canonical_pcm_sha256)] for q in query_ids}
 rankings=all_rankings(query_ids,vectors,exclusions);public,keys=generate_trials(rankings,int(c['seed']),int(c['trials']['initial_depth']),int(c['trials']['expansion_depth']))
 pd.DataFrame(public,columns=['trial_id','question']).to_csv(report/'fma30_trials.csv',index=False);atomic_json(report/'trial_keys.json',{'schema_version':'stage4a-trial-keys-v1','trials':keys})
 pair_counts={f'{a}__{b}':sum(1 for x in keys.values() if x['method_x']==a and x['method_y']==b) for a,b in c['trials']['method_pairs']}
 trial_balance={'trial_count':len(public),'maximum':c['trials']['maximum_total'],'query_count':len(set(x['query_id'] for x in keys.values())),'method_pair_counts':pair_counts,'opaque_public_columns':['trial_id','question'],'identity_exclusion_rules':c['retrieval']['duplicate_rules']};atomic_json(report/'trial_balance.json',trial_balance)
 # Rank variation and same-artist-excluded top-10 sensitivity are diagnostics only.
 variation={};same_artist={};artist={int(r.track_id):str(r.artist).casefold().strip() for r in candidate.itertuples()}
 for left,right in c['trials']['method_pairs']:
  variation[f'{left}__{right}']=float(np.mean([len(set(x for x,_ in rankings[q][left][:20])^set(x for x,_ in rankings[q][right][:20]))/40 for q in query_ids]))
 for method in METHODS:
  overlaps=[]
  for q in query_ids:
   primary=[x for x,_ in rankings[q][method][:10]];filtered=[x for x,_ in rankings[q][method] if artist[x]!=artist[q]][:10];overlaps.append(len(set(primary)&set(filtered))/10)
  same_artist[method]={'mean_top10_overlap_after_exclusion':float(np.mean(overlaps))}
 db=cache.db;timings=[x[0] for x in db.execute("SELECT encode_ms FROM segments WHERE status='ok' AND center_sec!=15")];total_ms=sum(timings)
 diagnostics={'candidate_count':len(candidate),'query_count':len(query_ids),'segment_cache_sqlite_sha256':manifest['sqlite_sha256'],'aggregate_artifact_sha256':sha(aggregate_path),'method_rank_variation':variation,'same_artist_excluded_sensitivity':same_artist,'engineering_cost':{'CENTER5':{'segments_per_track':1,'raw_vector_bytes_per_track':2048},'UNIFORM3_MEAN':{'segments_per_track':3,'raw_vector_bytes_per_track':6144},'UNIFORM5_MEAN':{'segments_per_track':5,'raw_vector_bytes_per_track':10240},'measured_new_segment_inferences':len(timings),'measured_segment_encode_hours':total_ms/3_600_000,'observed_segments_per_hour':len(timings)/(total_ms/3_600_000),'fma_large_projection_formula':'eligible_track_count * selected_K'}};atomic_json(report/'retrieval_diagnostics.json',diagnostics)
 atomic_json(report/'segment_cache_manifest.json',manifest);atomic_json(report/'aggregate_manifest.json',{'artifact_path':'artifacts/holistic_stage4a/aggregates.parquet','artifact_sha256':sha(aggregate_path),'rows':len(aggregate_rows),'tracks':len(candidate),'representations':list(METHODS),'exact_regeneration_from_segment_cache':True})
 return diagnostics|trial_balance
