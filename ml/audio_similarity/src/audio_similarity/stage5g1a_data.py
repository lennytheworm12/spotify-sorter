"""Read-only exact D-view reuse and source/artist-grouped development folds."""
from pathlib import Path
from collections import defaultdict
import hashlib
import sqlite3
import numpy as np
from .stage5e3_artifacts import read,freeze,freeze_json,npz_bytes,hashes,verify_hashes
from .stage5e1_cache import representation_identity
from .stage5e1_sampling import normalized_mean
from .stage5e1_encoders import native_view_spans
from .stage5g1_evidence import preferences
from .stage5g1a_model import order

PRIOR=Path('reports/stage5g1_clap_similarity/v1')
E1=Path('reports/stage5e1_four_arm_retrieval')
CACHE=Path('artifacts/stage5e1_four_arm_retrieval/representations.sqlite')


def groups(tracks,artist=False):
    parent={t['spotify_track_id']:t['spotify_track_id'] for t in tracks};seen={}
    def find(id):
        while parent[id]!=id:parent[id]=parent[parent[id]];id=parent[id]
        return id
    for t in tracks:
        id=t['spotify_track_id'];keys=[('source',t['source_sha256']),('video',t['youtube_video_id'])]
        if artist:keys += [('artist',a.casefold().strip()) for a in t['artists'] if a.strip()]
        for key in keys:
            if key in seen:parent[find(id)]=find(seen[key])
            seen[key]=id
    result=defaultdict(list)
    for id in parent:result[find(id)].append(id)
    return sorted((sorted(v) for v in result.values()),key=lambda v:order('group',v[0]))


def folds(tracks,pairs,config,artist=False):
    buckets=[[] for _ in range(5)]
    for group in groups(tracks,artist):buckets[min(range(5),key=lambda i:(len(buckets[i]),i))]+=group
    buckets=[sorted(v) for v in buckets];result=[]
    for k in range(5):
        parts={'heldout':buckets[k],'validation':buckets[(k+1)%5],
               'train':sorted(id for i,ids in enumerate(buckets) if i not in (k,(k+1)%5) for id in ids)}
        constraints={name:preferences(pairs,ids)[0] for name,ids in parts.items()}
        counts={name:{'tracks':len(parts[name]),'preferences':len(rows),'anchors':len({p['anchor'] for p in rows})} for name,rows in constraints.items()}
        c=config['development'];eligible=(counts['train']['preferences']>=c['minimum_training_preferences'] and
            counts['validation']['preferences']>=c['minimum_validation_preferences'] and
            counts['heldout']['preferences']>=c['minimum_heldout_preferences'] and counts['heldout']['anchors']>=c['minimum_heldout_anchors'])
        result.append({'fold':k,'partitions':parts,'constraints':constraints,'counts':counts,'eligible':eligible})
    return result


def read_views(root,tracks):
    """Never instantiate the writable historical cache class or an encoder."""
    plans=read(root/E1/'sampling_plans.json');plan_by={t['spotify_track_id']:t['plan'] for t in plans['tracks']}
    checkpoint=read(root/E1/'experiment_config.json')['arms']['D']['checkpoint_sha256']
    result={};provenance=[]
    with sqlite3.connect(f'file:{root/CACHE}?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        for t in tracks:
            id=t['spotify_track_id'];plan=plan_by[id]
            fields={'spotify_track_id':id,'arm':'D','source_sha256':t['source_sha256'],
                    'config_sha256':plans['experiment_config_sha256'],'sampling_plan_sha256':plan['sampling_plan_sha256'],
                    'checkpoint_sha256':checkpoint}
            identity=representation_identity(**fields)
            row=db.execute('SELECT * FROM vectors WHERE representation_identity=?',(identity,)).fetchone()
            if row is None or row['status']!='SUCCESS' or row['view_count']!=4:raise ValueError('missing exact cached D vector')
            records=db.execute('SELECT * FROM views WHERE representation_identity=? ORDER BY view_index',(identity,)).fetchall()
            expected=native_view_spans(plan['native_fusion'])
            if len(records)!=4:raise ValueError('incomplete D views')
            vectors=[]
            for i,(record,span) in enumerate(zip(records,expected)):
                if (record['view_index'],record['view_kind'],record['start_unit'],record['end_unit'])!=(i,*span):raise ValueError('D view plan mismatch')
                blob=bytes(record['embedding'])
                if hashlib.sha256(blob).hexdigest()!=record['embedding_sha256']:raise ValueError('D view checksum mismatch')
                vector=np.frombuffer(blob,dtype='<f4').copy()
                if vector.shape!=(512,) or not np.isfinite(vector).all() or abs(np.linalg.norm(vector)-1)>1e-5:raise ValueError('invalid cached D embedding')
                vectors.append(vector)
                provenance.append(fields|{'representation_identity':identity,'view_index':i,'view_kind':span[0],
                                         'start_mel_frame':span[1],'end_mel_frame':span[2],'embedding_sha256':record['embedding_sha256']})
            pooled=np.frombuffer(row['embedding'],dtype='<f4').copy()
            if hashlib.sha256(row['embedding']).hexdigest()!=row['embedding_sha256']:raise ValueError('D pooled hash mismatch')
            np.testing.assert_allclose(normalized_mean(vectors),pooled,atol=1e-6,rtol=0)
            result[id]=np.stack(vectors)
    return result,provenance


def prepare(root,run):
    if (run/'input_hashes.json').exists():verify_hashes(root,read(run/'input_hashes.json'))
    verify_hashes(root,read(root/PRIOR/'input_hashes.json'));verify_hashes(root/PRIOR,read(root/PRIOR/'artifact_manifest.json'))
    config=read(root/'configs/stage5g1a_v1.json');freeze_json(run/'protocol.json',config)
    tracks=read(root/PRIOR/'tracks.json');pairs=read(root/PRIOR/'human_evidence.json')['pairs']
    freeze_json(run/'development_folds.json',folds(tracks,pairs,config));freeze_json(run/'artist_folds.json',folds(tracks,pairs,config,True))
    train=read(root/PRIOR/'split.json')['constraints']['train'];by=defaultdict(list)
    for p in train:by[p['anchor']].append(p)
    anchors=sorted((a for a,ps in by.items() if len(ps)>=4),key=lambda a:order('smoke-anchor',a))[:4]
    smoke=[p for a in anchors for p in sorted(by[a],key=lambda p:order('smoke-preference',f"{p['anchor']}:{p['preferred']}:{p['other']}"))[:4]]
    if len(smoke)!=16:raise ValueError('insufficient predeclared TRAIN smoke subset')
    freeze_json(run/'smoke_preferences.json',smoke)
    views,provenance=read_views(root,tracks);ids=sorted(views)
    reconstructed=np.stack([normalized_mean(views[id]) for id in ids]).astype(np.float64)
    with np.load(root/PRIOR/'b0_matrix.npz',allow_pickle=False) as z:
        old=list(z['ids']);positions=[old.index(id) for id in ids];baseline=z['scores'][np.ix_(positions,positions)]
    error=float(np.max(np.abs(reconstructed@reconstructed.T-baseline)))
    if error>1e-6:raise ValueError('exact D score reconstruction failed')
    freeze(run/'d_views.npz',npz_bytes(views));freeze_json(run/'view_provenance.json',provenance)
    freeze(run/'d0_matrix.npz',npz_bytes({'ids':np.array(ids),'scores':baseline}))
    freeze_json(run/'cache_reuse.json',{'tracks':len(views),'view_cache_hits':len(provenance),'clap_forward_passes':0,'max_d0_reconstruction_error':error})
    paths=list((root/PRIOR).rglob('*'))+[root/CACHE,root/E1/'sampling_plans.json',root/E1/'experiment_config.json',root/'configs/stage5g1a_v1.json']
    paths+=list((root/'src/audio_similarity').glob('stage5g1a*.py'))+[root/'tests/test_stage5g1a.py']
    paths+=[run/'design.md',run/'protocol.json',run/'development_folds.json',run/'artist_folds.json',run/'smoke_preferences.json',run/'d_views.npz',run/'d0_matrix.npz']
    protected=read(root/PRIOR/'input_hashes.json')|hashes([p for p in paths if p.is_file()],root)
    freeze_json(run/'input_hashes.json',protected);verify_hashes(root,protected)
    return {'status':'PREPARED','views':400,'max_reconstruction_error':error,'primary_eligible_folds':sum(f['eligible'] for f in read(run/'development_folds.json'))}
