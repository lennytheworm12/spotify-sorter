import numpy as np
import pytest
from audio_similarity.full_song_muq import chunk_plan, padded_chunk, extract_waveform, normalize, cosine_matrix, InvalidVector
from audio_similarity.stage5e3_cache import MuQCache
from audio_similarity.stage5e3_artifacts import freeze, npz_bytes, freeze_json, freeze_parquet

@pytest.mark.parametrize('n',[1,2400,239976,239999,240000,240001,240024,479976,480000,480001,480024])
def test_full_coverage(n):
    x=np.arange(n,dtype=np.float32)
    plan=chunk_plan(n)
    assert sum(b-a for a,b in plan)==n
    assert all(a==i*240000 for i,(a,b) in enumerate(plan))
    a,b=plan[-1]; padded=padded_chunk(x,a,b)
    assert len(padded)==240000
    assert np.array_equal(padded,x[a:b][np.arange(240000)%(b-a)])

@pytest.mark.parametrize('v,status',[(np.zeros(512),'ZERO_NORM'),(np.full(512,np.nan),'INVALID_EMBEDDING'),(np.ones(511),'INVALID_EMBEDDING'),(np.ones((1,512)),'INVALID_EMBEDDING'),(np.ones(512)*1e-15,'ZERO_NORM')])
def test_bad_embeddings(v,status):
    with pytest.raises(InvalidVector) as e: normalize(v)
    assert e.value.status==status


def test_empty_nonfinite_mid_failure():
    assert extract_waveform([],lambda _:None)['status']=='EMPTY_AUDIO'
    assert extract_waveform([np.nan],lambda _:None)['status']=='NONFINITE_AUDIO'
    calls=[]
    def forward(x):
        calls.append(1)
        if len(calls)==2: raise RuntimeError('mid-song')
        return np.ones(512)
    r=extract_waveform(np.ones(480001),forward)
    assert r['status']=='INFERENCE_FAILED' and r['vector'] is None
    assert r['failing_chunk_index']==1 and len(r['chunks'])==1


def test_pool_and_resume(tmp_path):
    cache=MuQCache(tmp_path/'cache.sqlite'); calls=[]
    def forward(x):
        calls.append(1); v=np.zeros(512); v[len(calls)-1]=1; return v
    r=extract_waveform(np.ones(240001),forward,persist=lambda i,v,m:cache.save_chunk('x',i,v,m))
    assert r['status']=='OK'; assert r['vector'][:2]==pytest.approx([2**-.5]*2)
    replay=extract_waveform(np.ones(240001),lambda _:pytest.fail('new forward'),saved=lambda i:cache.chunk('x',i))
    assert np.array_equal(r['vector'],replay['vector']); assert replay['forward_passes']==0
    cache.save_track('x',r); assert np.array_equal(cache.track('x')[0],r['vector'])
    matrix=cosine_matrix([r['vector'],replay['vector']]); assert np.allclose(matrix,1)
    cache.close()


def test_serialization_create_once(tmp_path):
    data=npz_bytes({'z':np.ones(5),'a':np.zeros(3)})
    assert data==npz_bytes({'a':np.zeros(3),'z':np.ones(5)})
    p=tmp_path/'a'; freeze(p,data); before=p.stat().st_mtime_ns; freeze(p,data)
    assert p.stat().st_mtime_ns==before
    with pytest.raises(ValueError):freeze(p,b'changed')
    with pytest.raises(ValueError):freeze_json(tmp_path/'bad',{'x':float('nan')})
    rows=[{'i':2,'v':'b'},{'i':1,'v':'a'}]
    freeze_parquet(tmp_path/'x.parquet',rows,['i']);freeze_parquet(tmp_path/'x.parquet',rows[::-1],['i'])


def test_parquet_column_order_survives_json_cache(tmp_path):
    import json
    rows=[{"z":3.5,"a":"x","middle":2}]
    freeze_parquet(tmp_path/"manifest.parquet",rows,["a"])
    cached=json.loads(json.dumps(rows,sort_keys=True))
    freeze_parquet(tmp_path/"manifest.parquet",cached,["a"])
