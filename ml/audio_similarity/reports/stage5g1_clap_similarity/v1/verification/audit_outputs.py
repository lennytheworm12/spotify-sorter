"""Read-only data, isolation, cache, and prediction audit. Run from audio project."""
from pathlib import Path
from collections import Counter
from itertools import combinations
import hashlib
import numpy as np
from audio_similarity.stage5e3_artifacts import read,verify_hashes,freeze_json
from audio_similarity.stage5g1_evidence import preferences
from audio_similarity.stage5g1_learning import metric,bootstrap

root=Path.cwd();run=root/'reports/stage5g1_clap_similarity/v1'
verify_hashes(root,read(run/'input_hashes.json'))
tracks=read(run/'tracks.json');pairs=read(run/'human_evidence.json')['pairs'];split=read(run/'split.json')
parts=split['partitions'];assert set.union(*(set(v) for v in parts.values()))=={t['spotify_track_id'] for t in tracks}
for x,y in combinations(parts,2):assert not set(parts[x])&set(parts[y])
for name,ids in parts.items():
    expected,ties=preferences(pairs,ids);assert expected==split['constraints'][name]
    assert all({p['anchor'],p['preferred'],p['other']}<=set(ids) for p in expected)
artists={name:{a.casefold().strip() for t in tracks if t['spotify_track_id'] in ids for a in t['artists']} for name,ids in parts.items()}
artist_overlap={f'{a}__{b}':sorted(artists[a]&artists[b]) for a,b in combinations(parts,2)}
with np.load(run/'segments.npz',allow_pickle=False) as z:
    assert set(z.files)=={t['spotify_track_id'] for t in tracks}
    for id in z.files:
        a=z[id];assert a.ndim==2 and a.shape[1]==512 and np.isfinite(a).all()
        np.testing.assert_allclose(np.linalg.norm(a,axis=1),1,atol=1e-6,rtol=0)
    segments=sum(len(z[k]) for k in z.files)
manifest=read(run/'segment_manifest.json');assert len(manifest)==segments
for t in tracks:
    chunks=[r for r in manifest if r['spotify_track_id']==t['spotify_track_id']]
    assert chunks[0]['start_sample']==0 and [r['index'] for r in chunks]==list(range(len(chunks)))
    assert all(a['end_sample']==b['start_sample'] for a,b in zip(chunks,chunks[1:]))
    assert all(r['end_sample']-r['start_sample']+r['padded_samples']==480000 for r in chunks)
    assert all(r['start_seconds']==r['start_sample']/48000 and r['end_seconds']==r['end_sample']/48000 for r in chunks)
ledgers=[read(p) for p in sorted(run.glob('extraction_ledger_*.json'))];replays=[r for r in ledgers if r['replay']]
assert replays and all(r['forward_passes']==0 and r['cache_hits']==segments for r in replays)
results=read(run/'comparison.json');extra={};matrices={}
for method,file in [('B0','b0_matrix.npz'),('B1','b1_matrix.npz'),('M1','m1_matrix.npz')]:
    with np.load(run/file,allow_pickle=False) as z:ids=list(z['ids']);scores=z['scores'].copy()
    matrices[method]=(ids,scores)
    assert np.isfinite(scores).all();np.testing.assert_allclose(scores,scores.T,atol=1e-6,rtol=0)
    for part in parts:assert metric(scores,ids,split['constraints'][part])==results['metrics'][part][method]
    strong=[r for r in split['constraints']['test'] if r['gap']>=2]
    m=metric(scores,ids,strong);zero={k:0 for k in m['per_anchor']}
    extra[method]={'strong_test':m,'strong_test_macro_interval':bootstrap(m['per_anchor'],zero,20260908),
                   'test_macro_interval':bootstrap(results['metrics']['test'][method]['per_anchor'],{k:0 for k in results['metrics']['test'][method]['per_anchor']},20260908)}
# Only observed compatible human pairs; known examples have no invented labels.
known={'Wet Dreamz','boys dont cry','Shoota (feat. Lil Uzi Vert)'};by={t['spotify_track_id']:t for t in tracks};diagnostics=[]
for p in pairs:
    a,b=p['tracks']
    if not ({by[a]['title'],by[b]['title']}&known):continue
    diagnostics.append(p|{'titles':[by[a]['title'],by[b]['title']],'partition':[next(k for k,v in parts.items() if id in v) for id in [a,b]],
                         'scores':{m:float(s[ids.index(a),ids.index(b)]) for m,(ids,s) in matrices.items()},
                         'untouched_generalization_evidence':False})
output={'status':'PASS','tracks':len(tracks),'segments':segments,'artist_overlap':artist_overlap,'strong_and_absolute_uncertainty':extra,
        'known_case_diagnostics':diagnostics,'test_label_selection':'No test labels used for fraction/epoch/model selection',
        'historical_hash_count':len(read(run/'input_hashes.json')),'all_historical_hashes_unchanged':True,'cache_replay_forwards':0}
freeze_json(run/'supplemental_audit.json',output)
print('PASS: isolation, human-only constraints, segments, replay, metrics, historical hashes')
