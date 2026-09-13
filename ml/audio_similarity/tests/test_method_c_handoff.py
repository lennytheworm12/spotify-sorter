from audio_similarity.calibration.contracts import freeze_json
from audio_similarity.calibration.method_c_handoff import ACQUISITION,evaluate


def test_handoff_requires_terminal_state_process_exit_and_vram(tmp_path):
    p=tmp_path/ACQUISITION
    freeze_json(p/'manifest.json',{'batches':[{'batch_number':1,'tracks':[{'local_recording_id':'a'}]}]})
    assert evaluate(tmp_path,[],8000)['status']=='WAITING_FOR_ACQUISITION_RELEASE'
    freeze_json(p/'batch_0001/state.json',{'status':'FINISHED','tracks':{'a':{'state':'MANUAL_TAIL'}}})
    assert evaluate(tmp_path,[{'pid':42}],8000)['status']=='WAITING_FOR_ACQUISITION_RELEASE'
    assert evaluate(tmp_path,[],1400)['status']=='WAITING_FOR_ACQUISITION_RELEASE'
    result=evaluate(tmp_path,[],8000)
    assert result['status']=='READY_FOR_GPU_PARITY_CHECK'
    assert result['estimated_time_used'] is False


def test_continuation_preserves_cpu_files_and_rejects_tampering(tmp_path):
    import numpy as np
    import pytest
    from audio_similarity.calibration.contracts import file_hash,ContractError
    from audio_similarity.calibration.method_c_full_inputs import CHECKPOINT_SHA,read
    from audio_similarity.calibration.method_c_full_cache import store_feature
    from audio_similarity.calibration.method_c_continuation import prepare,verified_imports
    cpu=tmp_path/'cpu'
    config={'checkpoint_sha256':CHECKPOINT_SHA,'implementation':{},'sample_rate':48000,
            'chunk_samples':480000,'architecture':'HTSAT-base','fusion':False,'tail':'native repeatpad'}
    r={'recording_id':'a','audio_sha256':'a'*64,'errors':[]}
    corpus={'recordings':[r]}
    freeze_json(cpu/'configuration.json',config)
    freeze_json(cpu/'corpus.json',corpus)
    freeze_json(cpu/'companion_features.json',{})
    store_feature(cpu/'features/a.json',r,config,np.eye(512,dtype=np.float32)[0],None,{'kind':'ISOLATED_FIXTURE'})
    before={p:file_hash(p) for p in cpu.rglob('*.json')}
    assert prepare(tmp_path,'cpu','gpu')['imported_completed_features']==1
    assert all(file_hash(p)==sha for p,sha in before.items())
    receipt=read(tmp_path/'gpu/continuation_imports.json')
    assert verified_imports(tmp_path,corpus,receipt)['a']['kind']=='CPU_CONTINUATION'
    (cpu/'features/a.json').write_text('{}')
    with pytest.raises(ContractError,match='input changed'):
        verified_imports(tmp_path,corpus,receipt)


def test_cpu_drain_refuses_visible_gpu(tmp_path,monkeypatch):
    import torch
    import pytest
    from audio_similarity.calibration.contracts import ContractError
    from audio_similarity.calibration.method_c_continuation import resume_original_cpu
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES','0')
    monkeypatch.setattr(torch.cuda,'is_available',lambda:True)
    with pytest.raises(ContractError,match='CPU drain must run'):
        resume_original_cpu(tmp_path)


def test_float32_resume_repool_requires_explicit_hash_authorization(tmp_path):
    import numpy as np
    import pytest
    from audio_similarity.calibration.contracts import digest,file_hash,ContractError
    from audio_similarity.calibration.method_c_full_inputs import CHECKPOINT_SHA,read
    from audio_similarity.calibration.method_c_full_cache import store_feature,identity
    from audio_similarity.calibration.method_c_continuation import prepare,verified_imports
    from audio_similarity.stage5e1_sampling import sampling_plan,normalized_mean
    cpu=tmp_path/'cpu'
    config={'checkpoint_sha256':CHECKPOINT_SHA,'implementation':{},'sample_rate':48000,
            'chunk_samples':480000,'architecture':'HTSAT-base','fusion':False,'tail':'native repeatpad'}
    r={'recording_id':'a','audio_sha256':'a'*64,'errors':[]}
    corpus={'recordings':[r]}
    freeze_json(cpu/'configuration.json',config)
    freeze_json(cpu/'corpus.json',corpus)
    freeze_json(cpu/'companion_features.json',{})
    plan=sampling_plan(484800,'a'*64)
    freeze_json(cpu/'sampling/a.json',plan)
    v=np.arange(1,513,dtype=np.float64);v/=np.linalg.norm(v)
    raw=[v.tolist(),v.tolist()]
    for chunk,vector in zip(plan['full_song_chunks'],raw):
        freeze_json(cpu/'chunks/a'/(str(chunk['index'])+'.json'),
            {'identity':digest({'identity':identity(r,config),'chunk':chunk}),'vector':vector,'vector_sha256':digest(vector)})
    rounded=np.asarray(raw,dtype=np.float32).tolist()
    path=cpu/'features/a.json'
    store_feature(path,r,config,normalized_mean(rounded),rounded,{'status':'NEW_FULL_SONG_C'})
    original=path.read_bytes()
    with pytest.raises(ContractError,match='authorization required'):
        prepare(tmp_path,'cpu','gpu')
    freeze_json(tmp_path/'gpu/cpu_resume_repool_authorization.json',{'features':{'a':{'original_feature_sha256':file_hash(path)}}})
    prepare(tmp_path,'cpu','gpu')
    result=verified_imports(tmp_path,corpus,read(tmp_path/'gpu/continuation_imports.json'))['a']
    assert result['views']==raw
    assert result['pooling_repair']['new_inference_calls']==0
    assert path.read_bytes()==original
