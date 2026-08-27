import numpy as np,pytest
from audio_similarity.stage4a_sampling import cache_windows,method_windows,canonical_waveform,Stage4AError
from audio_similarity.stage4a_scoring import aggregates,generate_trials,verdict

def test_exact_windows_and_union():
 assert [(w.start_sample,w.end_sample) for w in method_windows('CENTER5',720000)]==[(300000,420000)]
 assert [(w.start_sample,w.end_sample) for w in method_windows('UNIFORM3_MEAN',720000)]==[(60000,180000),(300000,420000),(540000,660000)]
 assert [(w.start_sample,w.end_sample) for w in method_windows('UNIFORM5_MEAN',720000)]==[(12000,132000),(156000,276000),(300000,420000),(444000,564000),(588000,708000)]
 assert len(cache_windows(720000))==7

def test_boundary_and_quarantine():
 assert method_windows('UNIFORM5_MEAN',705600)[-1].end_sample==705600
 with pytest.raises(Stage4AError):cache_windows(700000)

def test_aggregates_only_three_methods():
 r=np.random.default_rng(1);d={c:r.normal(size=8) for c in (3,5,9,15,21,25,27)};out=aggregates(d)
 assert set(out)=={'CENTER5','UNIFORM3_MEAN','UNIFORM5_MEAN'}
 assert all(np.linalg.norm(v)==pytest.approx(1) for v in out.values())

def test_trials_deterministic_opaque():
 rankings={'q':{'CENTER5':[('x',.9),('y',.8),('z',.1)],'UNIFORM3_MEAN':[('y',.9),('x',.8),('z',.1)],'UNIFORM5_MEAN':[('z',.9),('x',.8),('y',.1)]}}
 public,keys=generate_trials(rankings,7);assert (public,keys)==generate_trials(rankings,7);assert all(set(x)=={'trial_id','question'} for x in public)

def test_verdicts():
 assert verdict(-.01,(-.1,.1),-.01,(-.1,.1),-.01,(-.1,.1))=='CENTER5_SUFFICIENT'
 assert verdict(.06,(.01,.1),.01,(-.1,.1),.06,(.01,.1))=='UNIFORM3_WINS'
 assert verdict(.06,(.01,.1),.06,(.01,.1),.1,(.01,.2))=='UNIFORM5_WINS'
 assert verdict(.5,(.4,.6),.5,(.4,.6),.5,(.4,.6),True)=='INSUFFICIENT_EVIDENCE_PICK_CHEAPER'
