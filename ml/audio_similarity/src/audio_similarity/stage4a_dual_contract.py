"""Immutable pre-outcome dual-encoder Stage 4A contract."""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path
import yaml
from .stage4_corpus import sha256_file
from .stage4a_dual_scoring import ALPHA_CLAP,ALPHA_MUQ,METHODS
class DualContractError(ValueError):pass
FILES=['src/audio_similarity/stage4a_sampling.py','src/audio_similarity/stage4a_dual_scoring.py','src/audio_similarity/stage4a_dual_contract.py','src/audio_similarity/holistic_encoders.py']
def atomic(path,value):path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+f'.{os.getpid()}.tmp');tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');tmp.replace(path)
def chash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def load(path):
 c=yaml.safe_load(Path(path).read_text())
 if c.get('experiment_id')!='holistic_stage4a_fma30_dual_encoder_coverage':raise DualContractError('wrong experiment')
 if tuple(c['sampling']['representations'])!=METHODS:raise DualContractError('dual methods changed')
 w=c['ranking']['normalized_weights']
 if abs(w['clap']-ALPHA_CLAP)>1e-12 or abs(w['muq']-ALPHA_MUQ)>1e-12 or abs(sum(w.values())-1)>1e-9:raise DualContractError('ranking weights changed')
 coef=c['ranking']['stage2b_coefficients'];scale=c['ranking']['stage2b_feature_scales'];raw=np.array([coef['clap']/scale['clap'],coef['muq']/scale['muq']]);derived=raw/raw.sum()
 if not np.allclose(derived,[ALPHA_CLAP,ALPHA_MUQ],atol=5e-11):raise DualContractError('weights do not derive from Stage 2B values')
 if c['scientific_history']['stage2b_verdict']!='SINGLE_ENCODER_WINS' or c['scientific_history']['fusion_won_stage2b']:raise DualContractError('Stage 2B history rewritten')
 if any(c['non_goals'].values()):raise DualContractError('downstream work authorized unexpectedly')
 return c
import numpy as np
def build(root,config_path):
 root=Path(root);config_path=Path(config_path);c=load(config_path)
 checks=[(c['corpus']['candidate_manifest'],c['corpus']['candidate_manifest_sha256']),(c['corpus']['query_manifest'],c['corpus']['query_manifest_sha256']),(c['encoders']['clap']['checkpoint'],c['encoders']['clap']['checkpoint_sha256']),(c['encoders']['clap']['center_artifact'],c['encoders']['clap']['center_artifact_sha256']),(c['encoders']['muq']['center_artifact'],c['encoders']['muq']['center_artifact_sha256'])]
 for rel,expected in checks:
  if sha256_file(root/rel)!=expected:raise DualContractError(f'hash mismatch {rel}')
 snapshot=Path.home()/'.cache/huggingface/hub/models--OpenMuQ--MuQ-MuLan-large/snapshots'/c['encoders']['muq']['revision']
 for name,expected in [('pytorch_model.bin',c['encoders']['muq']['weights_sha256']),('config.json',c['encoders']['muq']['config_sha256'])]:
  if sha256_file(snapshot/name)!=expected:raise DualContractError(f'MuQ {name} mismatch')
 superseded=root/'reports/holistic_stage4a/superseded_clap_only/supersession_manifest.json';s=json.loads(superseded.read_text())
 payload={'schema_version':'stage4a-dual-contract-v1','config_sha256':sha256_file(config_path),'candidate_manifest_sha256':c['corpus']['candidate_manifest_sha256'],'query_manifest_sha256':c['corpus']['query_manifest_sha256'],'candidate_count':c['corpus']['candidate_count'],'query_count':c['corpus']['query_count'],'encoders':{'clap':c['encoders']['clap'],'muq':c['encoders']['muq']},'ranking':c['ranking'],'sampling':c['sampling'],'implementation_sha256':{x:sha256_file(root/x) for x in FILES},'superseded_clap_only_manifest_sha256':s['manifest_sha256'],'superseded_clap_only_rating_rows':s['rating_rows_at_supersession'],'stage2b_verdict':'SINGLE_ENCODER_WINS','stage2b_rerun':False,'new_fusion_fit':False}
 payload['contract_sha256']=chash(payload);return c,payload
def freeze(root,config):
 root=Path(root);c,p=build(root,config);atomic(root/c['paths']['report_dir']/'experiment_contract.json',p);return p
def validate(root,config):
 root=Path(root);c,p=build(root,config);saved=json.loads((root/c['paths']['report_dir']/'experiment_contract.json').read_text())
 if p!=saved:raise DualContractError('contract mismatch')
 return p
