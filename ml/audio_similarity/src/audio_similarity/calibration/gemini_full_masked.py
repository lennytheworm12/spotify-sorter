"""Owner-approved missing-profile bundle; missing pairs are null, never neutral."""
from pathlib import Path
import numpy as np
from .contracts import require, freeze_json, file_hash, digest
from .gemini_full_inputs import RUN, read
from .gemini_full_features import freeze_array
from .features import FEATURE_IDS


def expand(full_ids, valid_ids, matrices):
    require(len(full_ids) == len(set(full_ids)), 'duplicate full recording IDs')
    require(len(valid_ids) == len(set(valid_ids)) and set(valid_ids) <= set(full_ids), 'invalid valid IDs')
    available = np.array([sid in set(valid_ids) for sid in full_ids], dtype=bool)
    mask = available[:, None] & available[None, :]
    lookup = {sid: i for i, sid in enumerate(full_ids)}
    indices = [lookup[sid] for sid in valid_ids]
    result = {}
    require(set(matrices) == {'Jc', 'Jnr', 'R'}, 'missing genre matrix')
    for key, value in matrices.items():
        value = np.asarray(value, dtype=np.float64)
        require(value.shape == (len(valid_ids), len(valid_ids)), 'genre shape mismatch')
        require(np.isfinite(value).all() and np.array_equal(value, value.T), 'invalid genre values')
        require(((value >= 0) & (value <= 1)).all(), 'genre bounds')
        full = np.full((len(full_ids), len(full_ids)), np.nan)
        full[np.ix_(indices, indices)] = value
        require(np.array_equal(np.isfinite(full), mask), 'missing mask mismatch')
        result[key] = full
    require(np.allclose(result['R'][mask], ((1-result['Jc'])*result['Jnr'])[mask], atol=0, rtol=0), 'residual mismatch')
    return available, mask, result


def build(root):
    root = Path(root).resolve(); run = root / RUN
    out = run / 'masked_bundle_v1'
    audit = read(run/'completed_profile_audit.json')
    audio = read(run/'audio_features/manifest.json')
    ids = read(run/'audio_features/recording_ids.json')
    partial = read(run/'partial_valid_pair_cache/manifest.json')
    require(digest(ids) == audio['recording_ids_sha256'], 'audio order changed')
    require(set(ids)-set(partial['recording_ids']) == set(audit['missing_recording_ids']), 'missing population changed')
    require(len(ids)==1924 and len(audit['missing_recording_ids'])==2, 'approved exception scope changed')
    approval = {'owner_messages':['i already said i approve those 2 missing','and i will fix it later'],
        'missing_recording_ids':audit['missing_recording_ids'], 'corpus_unchanged':True,
        'missing_pair_encoding':'NaN plus explicit validity mask; not zero and not unknown genre',
        'calibration_authorized':False}
    freeze_json(out/'approval.json', approval)
    arrays = {}
    for key, expected in partial['files'].items():
        path=run/'partial_valid_pair_cache'/f'{key}.npy'
        require(file_hash(path)==expected, 'partial cache changed')
        arrays[key]=np.load(path,allow_pickle=False)
    available, mask, expanded = expand(ids,partial['recording_ids'],arrays)
    files = {key:freeze_array(out/f'{key}.npy',value) for key,value in expanded.items()}
    files['genre_pair_valid']=freeze_array(out/'genre_pair_valid.npy',mask)
    freeze_json(out/'recording_ids.json',ids)
    freeze_json(out/'profile_status.json',[
        {'recording_id':sid,'status':'VALID_PROFILE' if valid else 'PROVIDER_BLOCKED_DEFERRED',
         'genre_profile_valid':bool(valid)} for sid,valid in zip(ids,available)])
    links={}
    for key, expected in audio['files'].items():
        path=run/'audio_features'/f'{key}.npy'
        require(file_hash(path)==expected, 'audio matrix changed')
        value=np.load(path,allow_pickle=False)
        require(value.shape==(len(ids),len(ids)) and np.isfinite(value).all() and np.allclose(value,value.T), 'audio contract invalid')
        links[key]={'path':str(path.relative_to(root)),'sha256':expected,'representation_id':FEATURE_IDS[key]}
    manifest={'status':'FEATURE_BUNDLE_READY_WITH_APPROVED_MISSING_PROFILES','tracks':len(ids),
        'valid_profiles':int(available.sum()),'missing_profiles':int((~available).sum()),
        'files':files,'audio_features':links,'genre_representation_ids':{k:FEATURE_IDS[k] for k in expanded},
        'track_order_sha256':digest(ids),'source_order_sha256':audio['source_order_sha256'],
        'approval_sha256':digest(approval),'audit_sha256':file_hash(run/'completed_profile_audit.json'),
        'partial_manifest_sha256':file_hash(run/'partial_valid_pair_cache/manifest.json'),
        'implementation_sha256':file_hash(Path(__file__)), 'numpy_version':np.__version__,
        'missing_semantics':'NaN means unavailable processing evidence; consumers must check mask and fail closed',
        'calibration_ready':False,'api_calls':0}
    freeze_json(out/'manifest.json',manifest)
    return manifest

if __name__ == '__main__':
    print(build(Path.cwd())['status'])
