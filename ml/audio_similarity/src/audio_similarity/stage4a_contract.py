"""Pre-score freeze and hash verification for amended FMA Stage 4A."""
from __future__ import annotations
import hashlib,json,os,re,unicodedata
from pathlib import Path
import pandas as pd, yaml
from .stage4_corpus import sha256_file
from .stage4a_sampling import cache_windows,decode,pcm_sha256

class ContractError(ValueError):pass
FILES=["src/audio_similarity/holistic_encoders.py","src/audio_similarity/stage4a_sampling.py","src/audio_similarity/stage4a_scoring.py","src/audio_similarity/stage4a_contract.py"]
def atomic_json(path:Path,value):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+f'.{os.getpid()}.tmp'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); tmp.replace(path)
def canonical_hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def norm(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value or '')).casefold()).strip()
def load(path):
    c=yaml.safe_load(Path(path).read_text())
    if c.get('experiment_id')!='holistic_stage4a_fma30_representation_benchmark' or c['rollback_commit']!='a14e9e8':raise ContractError('wrong amendment lineage')
    if list(c['sampling']['representations'])!=['CENTER5','UNIFORM3_MEAN','UNIFORM5_MEAN']:raise ContractError('representation set changed')
    if c['stage4b']['automatic'] or c['fma_large']['bulk_encoding_authorized']:raise ContractError('downstream work is not authorized')
    return c

def _identities(root:Path,c,eligible,compute:bool):
    path=root/c['paths']['pcm_cache']
    try: cache=json.loads(path.read_text())
    except (FileNotFoundError,json.JSONDecodeError):cache={}
    for index,row in enumerate(eligible.itertuples(index=False),1):
        key=str(row.audio_sha256)
        if key in cache:continue
        if not compute:raise ContractError(f'missing PCM identity for {row.track_id}')
        wav=decode(root/c['corpus']['audio_root']/row.relative_audio_path); windows=cache_windows(len(wav))
        cache[key]={"canonical_pcm_sha256":pcm_sha256(wav),"canonical_samples":len(wav),"window_bounds":{str(w.center_sec):[w.start_sample,w.end_sample] for w in windows},"window_pcm_sha256":{str(w.center_sec):pcm_sha256(wav[w.start_sample:w.end_sample]) for w in windows}}
        if index%100==0:atomic_json(path,cache)
    if compute:atomic_json(path,cache)
    return path,cache

def _queries(eligible,existing,seed,cap):
    ids=[int(x) for x in existing['query_ids']]; indexed=eligible.set_index('track_id'); artist_counts={}
    for tid in ids:artist_counts[norm(indexed.loc[tid].artist)]=artist_counts.get(norm(indexed.loc[tid].artist),0)+1
    selected=[]
    for genre in sorted(eligible.top_genre.unique()):
        rows=eligible[(eligible.top_genre==genre)&~eligible.track_id.isin(ids)].copy(); rows['order']=rows.track_id.map(lambda t:hashlib.sha256(f'{seed}|{int(t)}'.encode()).hexdigest()); rows=rows.sort_values(['order','track_id'])
        for enforce in (True,False):
            for row in rows.itertuples():
                if len([x for x in selected if x.top_genre==genre])>=5:break
                if any(x.track_id==row.track_id for x in selected):continue
                artist=norm(row.artist)
                if enforce and artist_counts.get(artist,0)>=cap:continue
                selected.append(row);artist_counts[artist]=artist_counts.get(artist,0)+1
    if len(selected)!=40:raise ContractError(f'expected 40 additional queries, got {len(selected)}')
    all_ids=ids+[int(x.track_id) for x in sorted(selected,key=lambda x:x.order)]
    return {"schema_version":"stage4a-fma-queries-v1","seed":seed,"uses_retrieval_scores":False,"count":80,"queries":[{"query_id":tid,"source":"STAGE2B_EXISTING" if i<40 else "STAGE4A_ADDITIONAL","order":i,"top_genre":str(indexed.loc[tid].top_genre),"artist":str(indexed.loc[tid].artist),"source_sha256":str(indexed.loc[tid].audio_sha256)} for i,tid in enumerate(all_ids)]}

def build(root:Path,config_path:Path,compute=False,write_outputs=True):
    c=load(config_path)
    for rel,expected in [(c['corpus']['manifest'],c['corpus']['manifest_sha256']),(c['encoder']['checkpoint'],c['encoder']['checkpoint_sha256']),(c['encoder']['adapter'],c['encoder']['adapter_sha256']),(c['queries']['existing_manifest'],c['queries']['existing_sha256'])]:
        if sha256_file(root/rel)!=expected:raise ContractError(f'hash mismatch: {rel}')
    manifest=pd.read_parquet(root/c['corpus']['manifest']); eligible=manifest[(manifest.decode_status=='SUCCESS')&(manifest.duration_sec>=c['corpus']['minimum_duration_sec'])].sort_values('track_id').reset_index(drop=True).copy()
    if len(eligible)!=c['corpus']['expected_eligible']:raise ContractError(f'eligible count {len(eligible)}')
    cache_path,cache=_identities(root,c,eligible,compute)
    eligible['canonical_pcm_sha256']=eligible.audio_sha256.map(lambda x:cache[str(x)]['canonical_pcm_sha256']);eligible['canonical_samples']=eligible.audio_sha256.map(lambda x:cache[str(x)]['canonical_samples'])
    candidates=root/c['corpus']['candidate_manifest'];query_path=root/c['queries']['output']
    existing=json.loads((root/c['queries']['existing_manifest']).read_text());queries=_queries(eligible,existing,c['seed'],c['queries']['artist_cap'])
    if write_outputs:
        candidates.parent.mkdir(parents=True,exist_ok=True);eligible.to_parquet(candidates,index=False);atomic_json(query_path,queries)
    else:
        saved_candidates=pd.read_parquet(candidates)
        if not saved_candidates.equals(eligible):raise ContractError('candidate manifest content mismatch')
        if json.loads(query_path.read_text())!=queries:raise ContractError('query manifest content mismatch')
    duplicate_rows=int(eligible.canonical_pcm_sha256.duplicated(keep=False).sum())
    payload={"experiment_id":c['experiment_id'],"config_sha256":sha256_file(config_path),"candidate_manifest_sha256":sha256_file(candidates),"candidate_count":len(eligible),"query_manifest_sha256":sha256_file(query_path),"query_count":80,"pcm_cache_sha256":sha256_file(cache_path),"pcm_duplicate_rows":duplicate_rows,"implementation_sha256":{f:sha256_file(root/f) for f in FILES},"claim_boundary":c['claim_boundary'],"stage4b_automatic":False,"fma_large_bulk_authorized":False};payload['contract_sha256']=canonical_hash(payload)
    return c,payload

def freeze(root,config):
    root=Path(root);c,p=build(root,Path(config),True,True);atomic_json(root/c['paths']['report_dir']/ 'experiment_contract.json',p);return p
def validate(root,config):
    root=Path(root);c,p=build(root,Path(config),False,False);saved=json.loads((root/c['paths']['report_dir']/ 'experiment_contract.json').read_text())
    if p!=saved:raise ContractError('contract mismatch')
    return p
