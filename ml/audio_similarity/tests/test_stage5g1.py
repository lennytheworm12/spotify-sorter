import copy
import numpy as np
import pytest
import torch
from audio_similarity.stage5g1_evidence import preferences,split_tracks
from audio_similarity.stage5g1_segments import extract,segment,normalize,SegmentCache
from audio_similarity.stage5e1_sampling import full_song_chunks
from audio_similarity.stage5g1_learning import SegmentSimilarity,train,setup,bootstrap
from audio_similarity.stage5e3_artifacts import read
from pathlib import Path


def test_segmentation_and_tail():
    for n in [1,479999,480000,480001,960001]:
        plan=full_song_chunks(n)
        assert plan[0].start_sample==0 and plan[-1].end_sample==n
        assert all(a.end_sample==b.start_sample for a,b in zip(plan,plan[1:]))
        wave=np.arange(n,dtype=np.float32);chunk=segment(wave,plan[-1]);assert chunk.shape==(480000,)
        expected=wave[plan[-1].start_sample:]
        np.testing.assert_array_equal(chunk,expected[np.arange(480000)%len(expected)])
    with pytest.raises(ValueError):full_song_chunks(0)


def test_cache_and_replay(tmp_path):
    cache=SegmentCache(tmp_path/'cache.sqlite');calls=[]
    def forward(x):calls.append(1);return np.arange(1,513,dtype=np.float32)
    config={'checkpoint':'x','segment':1,'code':'a','env':'b'};key=cache.identity('a'*64,config)
    a,plan,n=extract(np.ones(480001,dtype=np.float32),forward,cache,key)
    b,other,replay=extract(np.ones(480001,dtype=np.float32),lambda x:pytest.fail('inference on replay'),cache,key)
    assert n==2 and replay==0 and len(calls)==2 and plan==other
    np.testing.assert_array_equal(a,b);np.testing.assert_allclose(np.linalg.norm(a,axis=1),1,atol=1e-6)
    assert key!=cache.identity('b'*64,config)
    for field in config:assert key!=cache.identity('a'*64,config|{field:'changed'})
    cache.db.execute('UPDATE segments_v1 SET blob=?',(b'bad',));cache.db.commit()
    with pytest.raises(ValueError,match='corrupt'):cache.get(key,0)
    cache.close()


@pytest.mark.parametrize('vector',[np.zeros(512),np.full(512,np.nan),np.ones(511)])
def test_invalid_embedding(vector):
    with pytest.raises(ValueError):normalize(vector)


def test_preferences_no_unknown_negatives_or_ties():
    pairs=[{'tracks':['a','b'],'rating':4},{'tracks':['a','c'],'rating':2},{'tracks':['a','d'],'rating':4}]
    rows,ties=preferences(pairs,['a','b','c','d','unrated'])
    assert len(rows)==2 and ties==1
    assert all(r['preferred'] in ['b','d'] and r['other']=='c' for r in rows)
    assert preferences(pairs,['a','b'])[0]==[]


def test_group_disjointness():
    tracks=[{'spotify_track_id':str(i),'source_sha256':str(i//2),'youtube_video_id':str(i),
             'artists':['shared'] if i<5 else [str(i)]} for i in range(30)]
    for artist in [False,True]:
        s=split_tracks(tracks,artist);sets=list(map(set,s.values()))
        assert set.union(*sets)=={str(i) for i in range(30)}
        assert not any(a&b for i,a in enumerate(sets) for b in sets[i+1:])
        for a in tracks:
            for b in tracks:
                if a['source_sha256']==b['source_sha256'] or (artist and set(a['artists'])&set(b['artists'])):
                    assert next(k for k,v in s.items() if a['spotify_track_id'] in v)==next(k for k,v in s.items() if b['spotify_track_id'] in v)


def test_symmetry_and_deterministic_training():
    setup(4);features={str(i):torch.randn(i+1,512) for i in range(6)}
    model=SegmentSimilarity()
    torch.testing.assert_close(model(features['0'],features['4']),model(features['4'],features['0']),atol=1e-6,rtol=0)
    assert sum(p.numel() for p in model.parameters())==8241
    config=copy.deepcopy(read(Path(__file__).parents[1]/'configs/stage5g1_v1.json'));config['M1']['epochs']=3
    tr=[{'anchor':'0','preferred':'1','other':'2','gap':2}];va=[{'anchor':'3','preferred':'4','other':'5','gap':1}]
    a,ha=train(features,tr,va,config);b,hb=train(features,tr,va,config)
    for k,v in a.state_dict().items():torch.testing.assert_close(v,b.state_dict()[k],atol=0,rtol=0)
    assert ha['epochs']==hb['epochs']
    with pytest.raises(ValueError,match='leakage'):train(features,tr,tr,config)
    assert bootstrap({'a':1},{'a':0},3)['delta']==1
