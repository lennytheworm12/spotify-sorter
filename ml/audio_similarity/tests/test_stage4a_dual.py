import json
from pathlib import Path
import numpy as np,pytest,yaml
from audio_similarity.stage4a_dual_contract import load
from audio_similarity.stage4a_dual_scoring import ALPHA_CLAP,ALPHA_MUQ,METHODS,aggregate_encoder,fused_score
from audio_similarity.stage4a_sampling import method_windows
ROOT=Path(__file__).resolve().parents[1]
def test_frozen_weights_derive_from_stage2b_and_history_remains_closed():
 c=load(ROOT/'configs/holistic_stage4a_dual.yaml');coef=c['ranking']['stage2b_coefficients'];scale=c['ranking']['stage2b_feature_scales'];raw=np.array([coef['clap']/scale['clap'],coef['muq']/scale['muq']]);weights=raw/raw.sum()
 assert np.allclose(weights,[ALPHA_CLAP,ALPHA_MUQ],atol=5e-11)
 assert c['scientific_history']['stage2b_verdict']=='SINGLE_ENCODER_WINS' and not c['scientific_history']['fusion_won_stage2b']
def test_exact_three_dual_schedules_share_source_intervals():
 assert METHODS==('CENTER5_DUAL','UNIFORM3_DUAL_MEAN','UNIFORM5_DUAL_MEAN')
 c=yaml.safe_load((ROOT/'configs/holistic_stage4a_dual.yaml').read_text());assert c['sampling']['shared_source_intervals']
 assert c['sampling']['representations']['CENTER5_DUAL']['centers_sec']==[15]
 assert c['sampling']['representations']['UNIFORM3_DUAL_MEAN']['centers_sec']==[5,15,25]
 assert c['sampling']['representations']['UNIFORM5_DUAL_MEAN']['centers_sec']==[3,9,15,21,27]
def test_pooling_is_independent_and_fusion_is_weighted_cosines():
 r=np.random.default_rng(2);clap={x:r.normal(size=8) for x in (3,5,9,15,21,25,27)};muq={x:r.normal(size=8) for x in (3,5,9,15,21,25,27)}
 cg=aggregate_encoder(clap,'UNIFORM3_DUAL_MEAN');mg=aggregate_encoder(muq,'UNIFORM3_DUAL_MEAN');muq[5]*=999
 assert np.array_equal(cg,aggregate_encoder(clap,'UNIFORM3_DUAL_MEAN'))
 assert fused_score(cg,cg,mg,mg)==pytest.approx(1)
def test_clap_only_bundle_preserved_with_historical_only_ratings():
 p=json.loads((ROOT/'reports/holistic_stage4a/superseded_clap_only/supersession_manifest.json').read_text());assert p['rating_rows_at_supersession']==3;assert 'never_dual_primary_denominator' in p['ratings_policy']
