"""Derive dual-encoder aggregates, exact fused retrieval, and blinded trials."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yaml
from .stage4a_cache import Cache
from .stage4a_dual_scoring import METHODS,aggregate_encoder,exact_rank,generate_trials,ALPHA_CLAP,ALPHA_MUQ
class DualAnalysisError(ValueError):pass
def atomic(path,value):path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');tmp.replace(path)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def top_overlap(a,b,k=20):return len(set(x[0] for x in a[:k])&set(x[0] for x in b[:k]))/k
def run(config_path,validate_only=False):
 config_path=Path(config_path);root=config_path.parent.parent;c=yaml.safe_load(config_path.read_text());report=root/c['paths']['report_dir'];artifact=root/c['paths']['artifacts'];report.mkdir(parents=True,exist_ok=True);artifact.mkdir(parents=True,exist_ok=True)
 clap_cache=Cache(root/c['paths']['clap_cache']);muq_cache=Cache(root/c['paths']['muq_cache']);cm,mm=clap_cache.manifest(),muq_cache.manifest()
 for name,m in [('clap',cm),('muq',mm)]:
  if m['complete_tracks']!=c['corpus']['candidate_count'] or m['failure_rows']!=0:raise DualAnalysisError(f'{name} cache incomplete')
 if validate_only:
  saved=json.loads((report/'retrieval_diagnostics.json').read_text());
  if saved['cache_sha256']!={'clap':cm['sqlite_sha256'],'muq':mm['sqlite_sha256']}:raise DualAnalysisError('cache hash mismatch')
  for name in ('aggregate_manifest.json','trial_balance.json','trial_keys.json','dual_trials.csv'): 
   if not (report/name).is_file():raise DualAnalysisError(f'missing {name}')
  return saved
 clap_segments,muq_segments=clap_cache.vectors(),muq_cache.vectors();candidate=pd.read_parquet(root/c['corpus']['candidate_manifest']);query=json.loads((root/c['corpus']['query_manifest']).read_text());query_ids=[int(x['query_id']) for x in query['queries']]
 clap={m:{} for m in METHODS};muq={m:{} for m in METHODS};rows=[]
 for tid in sorted(clap_segments):
  if tid not in muq_segments:raise DualAnalysisError(f'MuQ missing {tid}')
  for method in METHODS:
   cv=aggregate_encoder(clap_segments[tid],method);mv=aggregate_encoder(muq_segments[tid],method);clap[method][tid]=cv;muq[method][tid]=mv;rows.append({'track_id':tid,'representation':method,'K':c['sampling']['representations'][method]['K'],'clap_embedding':cv.tolist(),'muq_embedding':mv.tolist(),'clap_sha256':hashlib.sha256(np.asarray(cv,dtype='<f4').tobytes()).hexdigest(),'muq_sha256':hashlib.sha256(np.asarray(mv,dtype='<f4').tobytes()).hexdigest()})
 aggregate_path=artifact/'dual_aggregates.parquet';pd.DataFrame(rows).to_parquet(aggregate_path,index=False)
 indexed=candidate.set_index('track_id');groups={h:set(int(x) for x in g.track_id) for h,g in candidate.groupby('canonical_pcm_sha256')};exclusions={q:groups[indexed.loc[q].canonical_pcm_sha256] for q in query_ids};rankings={q:{m:exact_rank(q,clap[m],muq[m],exclusions[q]) for m in METHODS} for q in query_ids};public,keys=generate_trials(rankings,c['seed'],c['trials']['initial_depth'],c['trials']['expansion_depth']);pd.DataFrame(public).to_csv(report/'dual_trials.csv',index=False);atomic(report/'trial_keys.json',{'schema_version':'stage4a-dual-trial-keys-v1','trials':keys})
 pairs=c['trials']['method_pairs'];counts={f'{a}__{b}':sum(1 for x in keys.values() if x['method_x']==a and x['method_y']==b) for a,b in pairs};balance={'trial_count':len(public),'maximum':c['trials']['maximum_total'],'query_count':len(set(x['query_id'] for x in keys.values())),'method_pair_counts':counts,'primary_denominator':'dual_encoder_bundle_only','superseded_clap_only_ratings_included':False};atomic(report/'trial_balance.json',balance)
 component={};variation={}
 for method in METHODS:
  c_ag=[];m_ag=[]
  for q in query_ids:
   fused=rankings[q][method];cr=sorted(((tid,float(clap[method][q]@v)) for tid,v in clap[method].items() if tid not in exclusions[q]),key=lambda x:(-x[1],x[0]));mr=sorted(((tid,float(muq[method][q]@v)) for tid,v in muq[method].items() if tid not in exclusions[q]),key=lambda x:(-x[1],x[0]));c_ag.append(top_overlap(fused,cr));m_ag.append(top_overlap(fused,mr))
  component[method]={'fused_clap_top20_overlap':float(np.mean(c_ag)),'fused_muq_top20_overlap':float(np.mean(m_ag))}
 for a,b in pairs:variation[f'{a}__{b}']=float(np.mean([1-top_overlap(rankings[q][a],rankings[q][b]) for q in query_ids]))
 clap_ms=sum(x[0] for x in clap_cache.db.execute("SELECT encode_ms FROM segments WHERE center_sec!=15 AND status='ok'"));muq_ms=sum(x[0] for x in muq_cache.db.execute("SELECT encode_ms FROM segments WHERE center_sec!=15 AND status='ok'"));forwards={'CENTER5_DUAL':2,'UNIFORM3_DUAL_MEAN':6,'UNIFORM5_DUAL_MEAN':10}
 diagnostics={'candidate_count':len(candidate),'query_count':len(query_ids),'weights':{'clap':ALPHA_CLAP,'muq':ALPHA_MUQ},'cache_sha256':{'clap':cm['sqlite_sha256'],'muq':mm['sqlite_sha256']},'aggregate_artifact_sha256':sha(aggregate_path),'component_retrieval_agreement':component,'dual_method_rank_variation':variation,'engineering_cost':{m:{'K':c['sampling']['representations'][m]['K'],'clap_segments_per_track':c['sampling']['representations'][m]['K'],'muq_segments_per_track':c['sampling']['representations'][m]['K'],'total_forwards_per_track':forwards[m],'raw_segment_vector_bytes_per_track':forwards[m]*2048} for m in METHODS}|{'measured_clap_segment_hours':clap_ms/3_600_000,'measured_muq_segment_hours':muq_ms/3_600_000,'fma_large_projection_formula':'eligible_tracks * total_forwards_per_track'}};atomic(report/'retrieval_diagnostics.json',diagnostics);atomic(report/'cache_manifest.json',{'clap':cm,'muq':mm,'shared_source_interval_version':c['sampling']['version']});atomic(report/'aggregate_manifest.json',{'path':'artifacts/holistic_stage4a_dual/dual_aggregates.parquet','sha256':sha(aggregate_path),'rows':len(rows),'tracks':len(candidate),'representations':list(METHODS),'per_encoder_pooling':True,'fusion_weights':diagnostics['weights']})
 return diagnostics|balance
