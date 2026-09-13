"""Read-only common-population audit and deterministic Method C matrices."""
from pathlib import Path
import io
import numpy as np

from .contracts import digest, file_hash, freeze_json, require
from .method_c_full_inputs import RUN, DEVELOPMENT, read
from .method_c_full_cache import load_feature
from .development_audio import cached_vector, vector_ok
from .audit_capture import read_db


def companion_features(root, corpus):
    """Freeze verified pre-existing MuQ/centered30 and genre evidence, no inference."""
    dev = root/DEVELOPMENT
    expected = read(dev/'artifact_manifest.private.json')['files']
    names = ['plan.private.json','audio_config.json','gemini/profiles_frozen.json',
             'gemini/execution_manifest.json','mapped_profiles.json','genre_input_receipt.json']
    for name in names:
        require(file_hash(dev/name) == expected[name], 'development input changed: '+name)
    plan = read(dev/'plan.private.json')
    config = read(dev/'audio_config.json')
    profiles = read(dev/'gemini/profiles_frozen.json')
    gm = read(dev/'gemini/execution_manifest.json')
    require(profiles['manifest_sha256'] == digest(gm), 'Gemini manifest linkage changed')
    mapped = read(dev/'mapped_profiles.json')
    for name, sha in read(dev/'genre_input_receipt.json').items():
        require(file_hash(root/name) == sha, 'mapper changed')
    dev_tracks = {}
    for t in plan['tracks']:
        name = 'audio/'+t['request_id']+'.json'
        require(file_hash(dev/name) == expected[name], 'development audio changed')
        row = read(dev/name)
        require(row['source_sha256'] == t['source_sha256'] and row['configuration_sha256'] == digest(config), 'development source linkage changed')
        dev_tracks[t['stable_track_id'],t['source_sha256']] = (t,row)
    gm_tracks = {t['request_id']:t for t in gm['tracks']}
    rows = []
    for r in corpus['recordings']:
        sid = r['recording_id']
        value = {'recording_id':sid,'audio_sha256':r['audio_sha256'], 'C_center30':None,'M':None,
                 'gemini':None,'genre_available':False,'issues':[]}
        key = sid,r['audio_sha256']
        if key in dev_tracks:
            t, audio = dev_tracks[key]
            for name in ('C_center30','M'):
                require(vector_ok(audio[name]), 'invalid historical companion feature')
                value[name] = {'origin':'DEVELOPMENT_SOURCE_LINKED_CACHE','vector_sha256':digest(audio[name]),
                    'path':str((dev/'audio'/(t['request_id']+'.json')).relative_to(root))}
            rid = t['request_id']
            if rid in profiles['profiles']:
                gt = gm_tracks[rid]
                require(gt['source_sha256'] == r['audio_sha256'] and gt['stable_track_id'] == sid, 'profile source mismatch')
                prepared = gt['prepared']
                require(prepared['source_sha256'] == r['audio_sha256'] and prepared['full_recording_preserved'], 'profile lacks full-source evidence')
                require(file_hash(Path(prepared['conversion_command'][-1])) == prepared['prepared_sha256'], 'prepared Gemini audio changed')
                value['gemini'] = {'profile_sha256':digest(profiles['profiles'][rid]),
                    'manifest_sha256':digest(gm),'request_id':rid,'model_id':gm['model_id']}
                value['genre_available'] = bool(mapped[rid]['specificStyleIds'])
        else:
            db = read_db(root/r['prior_representation']['cache_path'])
            try:
                for name,encoder in [('C_center30','laion_clap'),('M','muq_mulan_large')]:
                    v, origin = cached_vector(db,'pooled',
                        "stable_track_id=? AND source_audio_sha256=? AND encoder_id=? AND status='SUCCESS'",
                        (sid,r['audio_sha256'],encoder))
                    if v is not None:
                        require(origin['vector_contract_sha256'] == config['contract_sha256'], 'companion representation contract mismatch')
                        value[name] = {'origin':origin,'vector_sha256':digest(v.tolist()),'path':r['prior_representation']['cache_path']}
                    else:
                        value['issues'].append('MISSING_EXACT_SOURCE_'+name)
            finally:
                db.close()
        rows.append(value)
    result = {'recordings':rows,'development_manifest_sha256':file_hash(dev/'artifact_manifest.private.json'),
              'source_corpus_sha256':digest(corpus),'no_inference':True}
    freeze_json(root/RUN/'companion_features.json',result)
    return result


def cosine_matrix(vectors):
    a = np.asarray(vectors,dtype=np.float64)
    require(a.ndim == 2 and a.shape[1] == 512 and np.isfinite(a).all(), 'invalid matrix input')
    norms = np.linalg.norm(a,axis=1,keepdims=True)
    require(np.all(norms > 0),'zero input vector')
    a = a/norms
    result = np.clip(a@a.T,-1,1)
    require(np.array_equal(result,result.T),'asymmetric cosine matrix')
    require(np.allclose(np.diag(result),1,atol=1e-12,rtol=0),'invalid self similarity')
    return result


def freeze_matrix(path, vectors):
    result = cosine_matrix(vectors)
    data = io.BytesIO()
    np.save(data,result,allow_pickle=False)
    raw = data.getvalue()
    require(not path.exists() or path.read_bytes() == raw,'matrix deterministic replay differs')
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:
            f.write(raw)
    return {'path':str(path),'sha256':file_hash(path),'shape':list(result.shape),
            'symmetric':True,'diagonal_max_error':float(np.max(np.abs(np.diag(result)-1)))}


def report(root, *, finalize=False):
    run = root/RUN
    corpus,config = read(run/'corpus.json'),read(run/'configuration.json')
    companions = read(run/'companion_features.json')
    require(companions['source_corpus_sha256'] == digest(corpus),'companion population mismatch')
    other = {r['recording_id']:r for r in companions['recordings']}
    rows, vectors, ids, common = [],[],[],[]
    for r in corpus['recordings']:
        sid = r['recording_id']
        path = run/'features'/(sid+'.json')
        row = {'recording_id':sid,'audio_sha256':r['audio_sha256'], 'source_errors':r['errors'],
               'method_c':'WAITING_FOR_FEATURES','feature_sha256':None,**{k:other[sid][k] is not None for k in ('M','C_center30','gemini')},
               'genre_available':other[sid]['genre_available']}
        if path.exists():
            value = load_feature(path,r,config)
            row.update(method_c='COMPLETE',feature_sha256=file_hash(path),
                       execution='NEW' if (value['origin'].get('status') == 'NEW_FULL_SONG_C' or
                           (value['origin'].get('kind') == 'CPU_CONTINUATION' and value['origin']['origin'].get('status') == 'NEW_FULL_SONG_C')) else 'REUSED')
            row['pooling_repair'] = value['origin'].get('pooling_repair')
            row['runtime'] = ('historical_cache' if row['execution']=='REUSED' else
                'cpu' if value['origin'].get('kind') == 'CPU_CONTINUATION' else config.get('device','fixture'))
            ids.append(sid);vectors.append(value['vector'])
            if row['M'] and row['C_center30'] and row['gemini']:
                common.append(sid)
        rows.append(row)
    complete = len(ids)
    eligible = sum(not r['errors'] for r in corpus['recordings'])
    counts = {'frozen_requests':len(corpus['requests']),'distinct_retained_recordings':len(rows),
        'source_unavailable_requests':sum(r['status']=='SOURCE_UNAVAILABLE' for r in corpus['requests']),
        'source_blocked_recordings':len(rows)-eligible,'method_c_complete':complete,
        'method_c_missing':eligible-complete,'method_c_reused':sum(r.get('execution')=='REUSED' for r in rows),
        'method_c_new':sum(r.get('execution')=='NEW' for r in rows),
        'method_c_cpu_new':sum(r.get('execution')=='NEW' and r.get('runtime')=='cpu' for r in rows),
        'method_c_gpu_new':sum(r.get('execution')=='NEW' and r.get('runtime')=='cuda:0' for r in rows),
        'pooling_repairs_without_inference':sum(bool(r.get('pooling_repair')) for r in rows),
        **{k+'_complete':sum(r[k] for r in rows) for k in ('M','C_center30','gemini','genre_available')},
        'common_audio_genre_profile_population':len(common)}
    result = {'schema':'full-corpus-method-c-readiness-v1','counts':counts,
        'status':'READY_FOR_WEIGHT_CALIBRATION' if complete==eligible==len(common) and eligible else 'WAITING_FOR_FEATURES',
        'method_c_status':'COMPLETE' if complete==eligible else 'WAITING_FOR_FEATURES',
        'corpus_sha256':digest(corpus),'configuration_sha256':digest(config),
        'common_population_recording_ids':common,'recordings':rows,
        'genre_missing_policy':'No new profiles; unknown genre evidence is not silently fabricated.',
        'evaluation_status':'Development only; this materialization does not freeze splits or select weights.',
        'extension_included':False,'matrix':None}
    if finalize:
        require(complete==eligible and eligible>0,'Method C materialization incomplete')
        require(ids==sorted(set(ids)), 'matrix recording order must be sorted and unique')
        result['matrix'] = freeze_matrix(run/'matrices/method_c.npy',vectors)
        freeze_json(run/'matrices/recording_ids.json',ids)
        result['matrix']['recording_ids_sha256']=digest(ids)
        sources={r['recording_id']:r['audio_sha256'] for r in corpus['recordings']}
        result['matrix']['ordered_source_hashes_sha256']=digest([sources[sid] for sid in ids])
        indices = [ids.index(k) for k in common]
        if indices:
            result['common_matrix'] = freeze_matrix(run/'matrices/common_method_c.npy',[vectors[i] for i in indices])
            freeze_json(run/'matrices/common_recording_ids.json',common)
            result['common_matrix']['recording_ids_sha256']=digest(common)
            result['common_matrix']['ordered_source_hashes_sha256']=digest([sources[sid] for sid in common])
        freeze_json(run/'readiness.json',result)
    else:
        freeze_json(run/'readiness_snapshots'/(digest(result)+'.json'),result)
    return result


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--companions',action='store_true')
    parser.add_argument('--finalize',action='store_true')
    args=parser.parse_args()
    root=Path.cwd()
    if args.companions:
        companion_features(root,read(root/RUN/'corpus.json'))
    print(report(root,finalize=args.finalize)['counts'])
