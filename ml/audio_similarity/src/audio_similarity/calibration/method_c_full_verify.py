"""Completion audit: immutable history, exact views, matrix and zero-call replay."""
from collections import Counter
from pathlib import Path
import json

from .contracts import digest, file_hash, freeze_json, require
from .method_c_full_inputs import RUN, DEVELOPMENT, read, reusable
from .method_c_full_readiness import report,companion_features
from .method_c_full_worker import run
from .development_validation import integrity, historical_payloads



def verify_view_contracts(root, corpus):
    from ..stage5e1_sampling import sampling_plan
    from .method_c_full_cache import identity
    directory=root/RUN
    config=read(directory/'configuration.json')
    count=0
    for recording in corpus['recordings']:
        path=directory/'features'/(recording['recording_id']+'.json')
        if not path.exists():
            require(bool(recording['errors']),'eligible feature missing')
            continue
        feature=read(path)
        origin=feature['origin']
        if origin.get('status')!='NEW_FULL_SONG_C':
            continue  # Independently verified original-cache proofs are checked by reusable().
        plan=read(directory/'sampling'/(recording['recording_id']+'.json'))
        chunks=plan['full_song_chunks']
        expected=sampling_plan(chunks[-1]['end_sample'],recording['audio_sha256'])
        require(plan==expected and origin['sampling_plan_sha256']==plan['sampling_plan_sha256'],'sampling plan changed')
        require(len(feature['views'])==len(chunks),'missing full-song chunk')
        for chunk,vector in zip(chunks,feature['views']):
            cached=read(directory/'chunks'/recording['recording_id']/(str(chunk['index'])+'.json'))
            require(cached['identity']==digest({'identity':identity(recording,config),'chunk':chunk}),'chunk identity mismatch')
            require(cached['vector']==vector and cached['vector_sha256']==digest(vector),'chunk feature linkage mismatch')
            count+=1
    return count


def verify(root):
    directory=root/RUN
    corpus=read(directory/'corpus.json')
    if (directory/'artifact_manifest.json').exists():
        for name,sha in read(directory/'artifact_manifest.json')['files'].items():
            require(file_hash(directory/name)==sha,'completed run artifact changed: '+name)
        integrity(root)
        historical_payloads(root)
        report(root,finalize=True)
        return read(directory/'verification.json')
    # Re-read original C proofs, not merely the imported pooled copies.
    reusable(root,corpus)
    companion_features(root,corpus)
    first=report(root,finalize=True)
    checked_views=verify_view_contracts(root,corpus)
    for name,sha in corpus['protected_files'].items():
        require(file_hash(root/name)==sha,'protected source provenance changed')
    source_checks=integrity(root)
    historical=historical_payloads(root)
    development=read(root/DEVELOPMENT/'artifact_manifest.private.json')['files']
    for name,sha in development.items():
        require(file_hash(root/DEVELOPMENT/name)==sha,'historical development artifact changed: '+name)
    receipt=directory/'original_execution_receipt.json'
    previous=(read(receipt) if receipt.exists() else
        {str(p.relative_to(directory)):file_hash(p) for p in sorted(directory.rglob('*.json'))
         if p.name not in ('artifact_manifest.json','verification.json')})
    freeze_json(receipt,previous)
    replay=run(root,replay=True)
    require(replay['inference_calls']==0 and replay['computed']==0 and replay['imported']==0 and replay['failed']==0,
            'unexpected replay inference or materialization')
    require(replay['cached']==first['counts']['method_c_complete'],'replay population differs')
    for name,sha in previous.items():
        require(file_hash(directory/name)==sha,'original artifact/ledger changed during replay')
    require(report(root,finalize=True)==first,'matrix/readiness replay differs')
    track_events=[read(p) for p in directory.glob('invocations/*/tracks/*.json')]
    attempts=list(directory.glob('invocations/*/calls/*.json'))
    cpu_calls=0
    cpu_views=0
    if (directory/'continuation_imports.json').exists():
        imports=read(directory/'continuation_imports.json')
        cpu_calls=sum('/invocations/' in p and '/calls/' in p for p in imports['files'])
        for item in imports['features'].values():
            feature=read(root/item['path'])
            if feature['origin'].get('status')=='NEW_FULL_SONG_C':
                cpu_views+=len(feature['views'])
    require(len(attempts)+cpu_calls>=checked_views+cpu_views, 'missing inference ledger entries')
    value={'status':'VERIFIED','readiness_status':first['status'],'counts':first['counts'],
        'replay':replay,'original_json_artifacts_unchanged':len(previous),
        'historical_sources':source_checks,'historical_reports':historical,
        'historical_development_files_unchanged':len(development),
        'verified_new_chunk_views':checked_views+cpu_views,
        'attempts_without_unique_committed_chunk':len(attempts)+cpu_calls-checked_views-cpu_views,'attempted_clap_chunk_calls':len(attempts)+cpu_calls,'cpu_continuation_attempts':cpu_calls,
        'gpu_parity_engineering_attempts':len(list(directory.glob('gpu_parity_attempts/*.json'))),'muq_inference_calls':0,'centered30_inference_calls':0,
        'track_execution_events':dict(Counter(e['status'] for e in track_events)),
        'matrix':first['matrix'],'configuration_sha256':file_hash(directory/'configuration.json'),
        'corpus_sha256':file_hash(directory/'corpus.json')}
    freeze_json(directory/'verification.json',value)
    payload={str(p.relative_to(directory)):file_hash(p) for p in sorted(directory.rglob('*'))
             if p.is_file() and p.name not in ('artifact_manifest.json','worker.lock') and p.suffix not in ('.log',)}
    freeze_json(directory/'artifact_manifest.json',{'files':payload})
    return value


if __name__=='__main__':
    print(json.dumps(verify(Path.cwd()),indent=2))
