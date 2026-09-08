import numpy as np
import pytest
from audio_similarity.stage5g1a_model import pair_features, fit, agreement, interval
from audio_similarity.stage5g1a_data import groups, folds
from audio_similarity.stage5g1a_experiment import diagnose
from audio_similarity.stage5e3_artifacts import freeze, npz_bytes


def test_symmetry_and_full_dimension():
    rng=np.random.default_rng(7)
    a=rng.normal(size=(4,512));b=rng.normal(size=(4,512))
    a/=np.linalg.norm(a,axis=1,keepdims=True);b/=np.linalg.norm(b,axis=1,keepdims=True)
    x=pair_features(a,b)
    assert x.shape==(2048,)
    np.testing.assert_array_equal(x,pair_features(b,a))
    assert .37+x@np.zeros(2048)==.37
    with pytest.raises(ValueError):pair_features(a[:3],b)
    with pytest.raises(ValueError):pair_features(a*np.nan,b)


def test_fit_deterministic_only_rated_pairs():
    features={('a','b'):np.array([1.,0.]),('a','c'):np.array([0.,1.])}
    baseline={p:0. for p in features}
    rows=[{'anchor':'a','preferred':'b','other':'c','gap':2}]
    w,t=fit(features,baseline,rows,0);v,u=fit(features,baseline,rows,0)
    np.testing.assert_array_equal(w,v)
    assert t['history']==u['history']
    assert t['anchor_macro_agreement']==1 and t['final_preference_loss']<.05
    with pytest.raises(KeyError):fit(features,baseline,[dict(rows[0],other='unknown')],1)
    with pytest.raises(ValueError):fit(features,baseline,[],1)


def test_groups_and_disjointness():
    tracks=[{'spotify_track_id':str(i),'source_sha256':str(i),'youtube_video_id':str(i),'artists':[str(i)]} for i in range(30)]
    tracks[1]['source_sha256']='0';tracks[2]['artists']=['0']
    assert any({'0','1'}<=set(g) for g in groups(tracks))
    assert any({'0','1','2'}<=set(g) for g in groups(tracks,True))
    pairs=[{'tracks':[str(i),str(j)],'rating':1+(j%5),'pair_id':f'{i}-{j}'} for i in range(30) for j in range(i+1,30)]
    cfg={'development':{f'minimum_{k}':0 for k in ['training_preferences','validation_preferences','heldout_preferences','heldout_anchors']}}
    fs=folds(tracks,pairs,cfg)
    assert fs==folds(list(reversed(tracks)),pairs,cfg)
    for f in fs:
        p={k:set(v) for k,v in f['partitions'].items()}
        assert not p['train']&p['validation'] and not p['train']&p['heldout'] and not p['validation']&p['heldout']
        for k,rows in f['constraints'].items():assert all({r['anchor'],r['preferred'],r['other']}<=p[k] for r in rows)


def test_artifact_replay(tmp_path):
    p=tmp_path/'views.npz';content=npz_bytes({'x':np.eye(4)})
    freeze(p,content);freeze(p,npz_bytes({'x':np.eye(4)}))
    assert p.read_bytes()==content
    with pytest.raises((ValueError,RuntimeError)):freeze(p,b'changed')


def test_metrics():
    assert agreement({('a','b'):0,('a','c'):0},[{'anchor':'a','preferred':'b','other':'c'}])['macro']==.5
    assert interval([.1,.2])==interval([.1,.2])
    assert agreement({},[])['macro'] is None


def test_diagnoses():
    cfg={'decision':{'material_gain':.05}}
    assert diagnose({'passes':False},None,None,cfg)=='MODEL_CAPACITY_OR_IMPLEMENTATION_FAILURE'
    p={'eligible_folds':5,'fold_macro_interval':{'point':.1,'low':.01,'high':.2},'positive_folds':4,'stationary_optimization':True}
    o={'delta_interval':{'point':0,'low':-.1,'high':.1}}
    assert diagnose({'passes':True},p,o,cfg)=='SCORER_OR_AGGREGATION_BOTTLENECK'
    p['fold_macro_interval']={'point':0,'low':-.1,'high':.1}
    assert diagnose({'passes':True},p,o,cfg)=='SUPERVISION_LIMITED'
    p['fold_macro_interval']['high']=.04;o['delta_interval']['high']=.04
    assert diagnose({'passes':True},p,o,cfg)=='COMPLEMENTARY_REPRESENTATION_JUSTIFIED'
