"""Offline resumable execution and deterministic scientific export."""
import os
import resource
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from .stage5e3_artifacts import read,freeze,freeze_json,freeze_parquet,npz_bytes,digest,hashes,verify_hashes
from .stage5e3_cache import MuQCache
from .stage5e3_prepare import verify_prepared,model_identity
from .full_song_muq import extract_source,raw_forward,normalize,cosine_matrix
from .stage5e3_inputs import PRIOR
from .stage5e3_retrieval import rank_tracks,build_packets
from .playlist_compatibility_eval import METHODS


def embed(root,run):
    verify_prepared(root,run)
    config=read(run/'full_song_muq_config.json');tracks=read(run/'source_manifest.json')['tracks']
    current_config,_=model_identity(root)
    if current_config!=config: raise ValueError('embedding environment/model identity changed; use matching environment or new run')
    cache=MuQCache(root/'artifacts/stage5e3_full_song_muq/cache_v1.sqlite')
    began=time.perf_counter();started=datetime.now(timezone.utc).isoformat()
    ledger_path=run/'original_execution_ledger.json'
    if ledger_path.exists():
        index=1
        while (run/f'execution_ledger_{index:04d}.json').exists():index+=1
        ledger_path=run/f'execution_ledger_{index:04d}.json'
    adapter=None;records=[];vectors={};chunk_vectors={};chunk_rows=[]
    try:
        for track in tracks:
            identity=cache.identity(track,config);cached=cache.track(identity)
            if cached:
                vector,result=cached;normalize(vector);result=result|{'vector':vector,'forward_passes':0,'chunk_cache_hits':len(result['chunks'])}
                cache_hit=True
            else:
                if adapter is None:
                    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',CUBLAS_WORKSPACE_CONFIG=':4096:8')
                    import torch
                    from .holistic_encoders import MuQMulanEncoder,AdapterSpec
                    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
                    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
                    adapter=MuQMulanEncoder(AdapterSpec('muq_mulan_large',hf_repo=config['model_snapshot_path']),revision=config['model_revision'])
                result=extract_source(track|{'retained_source_path':str(root/track['retained_source_path'])},lambda x:raw_forward(adapter,x),
                                      saved=lambda i:cache.chunk(identity,i),persist=lambda i,v,m:cache.save_chunk(identity,i,v,m))
                if result['status']=='OK':cache.save_track(identity,result)
                cache_hit=False
            tid=track['spotify_track_id']
            records.append({k:v for k,v in result.items() if k not in ('vector','chunks')}|{'spotify_track_id':tid,'track_cache_hit':cache_hit,'identity':identity})
            if result['status']=='OK':vectors[tid]=result['vector']
            for metadata in result['chunks']:
                i=metadata['chunk_index'];vector,saved=cache.chunk(identity,i)
                chunk_vectors[f'{tid}_{i:05d}']=vector.astype('<f4')
                chunk_rows.append(metadata|{'spotify_track_id':tid,'source_sha256':track['source_sha256']})
            print(f"{len(records)}/100 {result['status']} cached={cache_hit} forwards={result['forward_passes']}",flush=True)
    finally:
        ledger={'started_utc':started,'elapsed_seconds':time.perf_counter()-began,
                'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'track_cache_hits':sum(r['track_cache_hit'] for r in records),'forward_passes':sum(r['forward_passes'] for r in records),
                'chunk_cache_hits':sum(r['chunk_cache_hits'] for r in records),'tracks':records}
        if adapter is not None:
            import torch
            ledger['peak_cuda_allocated_bytes']=torch.cuda.max_memory_allocated() if torch.cuda.is_available() else 0
        freeze_json(ledger_path,ledger);cache.close()
    if len(vectors)!=100:
        freeze_json(run/f'failure_status_{ledger_path.stem}.json',{'status_counts':dict(Counter(r['status'] for r in records)),'tracks':records})
        raise ValueError('100/100 OK required; see execution ledger')
    freeze(run/'full_song_muq_track_embeddings.npz',npz_bytes(vectors))
    freeze(run/'full_song_muq_chunk_embeddings.npz',npz_bytes(chunk_vectors))
    freeze_parquet(run/'full_song_muq_chunk_manifest.parquet',chunk_rows,['spotify_track_id','chunk_index'])
    scientific_status=[{k:v for k,v in r.items() if k not in ('track_cache_hit','forward_passes','chunk_cache_hits')} for r in records]
    freeze_json(run/'track_status.json',{'status_counts':{'OK':100},'tracks':scientific_status})
    if ledger_path.name!='original_execution_ledger.json' and ledger['track_cache_hits']==100 and ledger['forward_passes']==0:
        freeze_json(run/'full_song_muq_cache_rerun.json',{'track_cache_hits':100,'forward_passes':0,'unchanged_vectors':100,
                    'scientific_hashes':hashes([run/n for n in ('full_song_muq_track_embeddings.npz','full_song_muq_chunk_embeddings.npz','full_song_muq_chunk_manifest.parquet','track_status.json')],run)})
    return {k:v for k,v in ledger.items() if k!='tracks'}


def build_similarities(root,run):
    verify_prepared(root,run)
    tracks=read(run/'source_manifest.json')['tracks'];ids=[t['spotify_track_id'] for t in tracks]
    if read(run/'track_status.json')['status_counts']!={'OK':100}:raise ValueError('full100 required')
    with np.load(root/PRIOR/'similarity_matrices.npz',allow_pickle=False) as z:
        all_ids=list(z['spotify_ids']);index=[all_ids.index(t) for t in ids]
        if len(set(all_ids))!=len(all_ids):raise ValueError('duplicate matrix identity')
        baseline={k:z[k][np.ix_(index,index)].astype(np.float64) for k in ('c_clap','muq','a_clap','a_combined','d_clap','d_combined')}
    for m in baseline.values():
        if not np.isfinite(m).all() or not np.allclose(m,m.T,atol=1e-6,rtol=0) or not np.allclose(np.diag(m),1,atol=1e-6,rtol=0):raise ValueError('invalid baseline matrix')
    with np.load(run/'full_song_muq_track_embeddings.npz',allow_pickle=False) as z:
        if set(z.files)!=set(ids):raise ValueError('vector corpus mismatch')
        full=cosine_matrix([z[t] for t in ids])
    c=baseline['c_clap'];fixed=baseline['muq']
    matrices=dict(zip(METHODS,(c,full,.7172981519*c+.2827018481*fixed,.7172981519*c+.2827018481*full)))
    freeze(run/'similarity_matrices.npz',npz_bytes(matrices|{'spotify_ids':np.array(ids)}))
    freeze(run/'historical_reference_matrices.npz',npz_bytes(baseline|{'spotify_ids':np.array(ids)}))
    rows=rank_tracks(tracks,matrices)
    if len(rows)!=2000:raise ValueError('expected 2000 natural slots')
    freeze_parquet(run/'retrieval_top5.parquet',rows,['method_id','query','rank'])
    return {'methods':4,'slots':len(rows)}


def build_review(root,run):
    import pyarrow.parquet as pq
    verify_prepared(root,run)
    tracks=read(run/'source_manifest.json')['tracks'];rows=pq.read_table(run/'retrieval_top5.parquet').to_pylist()
    payload,probes,assignment,counts=build_packets(tracks,rows,read(run/'pre_review_rating_snapshot.json'))
    freeze_json(run/'review_blind_payload.json',payload)
    freeze_parquet(run/'probe_manifest.parquet',probes,['query','pair_id'])
    union={ (r['query'],r['candidate']):{'query':r['query'],'candidate':r['candidate'],'pair_id':r['pair_id']} for r in rows}
    freeze_parquet(run/'candidate_union.parquet',list(union.values()),['query','candidate'])
    freeze_json(run/'review_manifest.json',{'counts':counts,'assignments':assignment,'payload_hash':digest(payload),
                'scientific_hashes':hashes([run/n for n in ('review_blind_payload.json','probe_manifest.parquet','candidate_union.parquet','retrieval_top5.parquet','similarity_matrices.npz','pre_review_rating_snapshot.json')],run)})
    return counts
