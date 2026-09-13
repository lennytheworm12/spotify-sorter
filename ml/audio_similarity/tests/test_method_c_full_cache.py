import numpy as np
import pytest
from audio_similarity.calibration.contracts import ContractError
from audio_similarity.calibration.method_c_full_cache import store_feature, load_feature
from audio_similarity.stage5e1_sampling import normalized_mean, full_song_chunks


def test_chunk_coverage_and_native_tail():
    chunks = full_song_chunks(960001)
    assert [(c.start_sample,c.end_sample,c.padded_samples) for c in chunks] == [(0,480000,0),(480000,960000,0),(960000,960001,479999)]


def test_cache_exact_replay_and_fail_closed(tmp_path):
    r = {'recording_id':'a','audio_sha256':'a'*64}
    config = {'checkpoint':'frozen','implementation':'v1'}
    v = np.eye(512,dtype=np.float32)[:2]
    path = tmp_path/'feature.json'
    store_feature(path,r,config,normalized_mean(v),v.tolist(),{'status':'TEST'})
    original = path.read_bytes()
    assert load_feature(path,r,config)['representation'] == 'method_c_full_song'
    assert path.read_bytes() == original
    for changed_r, changed_c in [(dict(r,audio_sha256='b'*64),config),(r,dict(config,implementation='v2'))]:
        with pytest.raises(ContractError):
            load_feature(path,changed_r,changed_c)


def test_reject_invalid_pooling(tmp_path):
    v = np.eye(512,dtype=np.float32)[:2]
    with pytest.raises(ContractError,match='pooling mismatch'):
        store_feature(tmp_path/'bad.json',{'recording_id':'a','audio_sha256':'a'*64},{},v[0],v.tolist(),{})


def test_matrix_order_symmetry_and_byte_replay(tmp_path):
    from audio_similarity.calibration.method_c_full_readiness import cosine_matrix, freeze_matrix
    v = np.eye(512,dtype=np.float32)[:3]
    v[2] = normalized_mean(v[:2])
    matrix = cosine_matrix(v)
    assert np.array_equal(matrix,matrix.T)
    assert np.allclose(np.diag(matrix),1,atol=1e-12)
    assert matrix[0,1] == 0
    assert matrix[0,2] == pytest.approx(2**-.5)
    path=tmp_path/'matrix.npy'
    first=freeze_matrix(path,v)
    assert freeze_matrix(path,v) == first
    with pytest.raises(ContractError,match='replay differs'):
        freeze_matrix(path,v[[2,1,0]])


def test_worker_replay_zero_encoder_construction_and_original_ledger(tmp_path, monkeypatch):
    from audio_similarity.calibration import method_c_full_worker as worker
    from audio_similarity.calibration.contracts import freeze_json, file_hash
    from audio_similarity.calibration.method_c_full_inputs import RUN
    import audio_similarity.holistic_encoders as encoders
    source=tmp_path/'audio'; source.write_bytes(b'fixture')
    provenance=tmp_path/'provenance'; provenance.write_text('{}')
    r={'recording_id':'a','audio_sha256':file_hash(source),'source_path':'audio',
       'provenance_path':'provenance','provenance_sha256':file_hash(provenance),'errors':[]}
    directory=tmp_path/RUN
    freeze_json(directory/'corpus.json',{'recordings':[r]})
    v=np.eye(512,dtype=np.float32)[0].tolist()
    freeze_json(directory/'reuse_manifest.json',{'a':{'kind':'ISOLATED_FIXTURE','vector':v,'views':None}})
    monkeypatch.setattr(worker,'configuration',lambda root:{'fixture':True})
    def forbidden(*args,**kwargs):
        raise AssertionError('cache replay attempted encoder construction')
    monkeypatch.setattr(encoders,'LaionClapEncoder',forbidden)
    assert worker.run(tmp_path)['imported'] == 1
    before={p:p.read_bytes() for p in directory.rglob('*.json')}
    result=worker.run(tmp_path,replay=True)
    assert result['cached'] == 1 and result['inference_calls'] == 0
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_readiness_separates_full_c_from_missing_genre(tmp_path):
    from audio_similarity.calibration.contracts import freeze_json,digest
    from audio_similarity.calibration.method_c_full_inputs import RUN
    from audio_similarity.calibration.method_c_full_readiness import report
    directory=tmp_path/RUN
    r={'recording_id':'a','audio_sha256':'a'*64,'errors':[]}
    corpus={'recordings':[r],'requests':[{'status':'ELIGIBLE'}]}
    config={'fixture':True}
    freeze_json(directory/'corpus.json',corpus)
    freeze_json(directory/'configuration.json',config)
    freeze_json(directory/'companion_features.json',{'source_corpus_sha256':digest(corpus),
        'recordings':[{'recording_id':'a','M':{},'C_center30':{},'gemini':None,'genre_available':False}]})
    v=np.eye(512,dtype=np.float32)[0]
    store_feature(directory/'features/a.json',r,config,v,None,{'kind':'FIXTURE'})
    result=report(tmp_path,finalize=True)
    assert result['method_c_status']=='COMPLETE'
    assert result['status']=='WAITING_FOR_FEATURES'
    assert result['counts']['method_c_complete']==1
    assert result['counts']['common_audio_genre_profile_population']==0
    assert result['matrix']['shape']==[1,1]
    assert report(tmp_path,finalize=True)==result


def test_interrupted_track_reuses_completed_chunks(tmp_path, monkeypatch):
    from audio_similarity.calibration import method_c_full_worker as worker
    from audio_similarity.calibration.contracts import freeze_json,file_hash
    from audio_similarity.calibration.method_c_full_inputs import RUN
    import audio_similarity.holistic_encoders as encoders
    import audio_similarity.stage5e1_encoders as decoder
    import torch
    from types import SimpleNamespace
    source=tmp_path/'audio'; source.write_bytes(b'fixture')
    provenance=tmp_path/'provenance'; provenance.write_text('{}')
    r={'recording_id':'a','audio_sha256':file_hash(source),'source_path':'audio',
       'provenance_path':'provenance','provenance_sha256':file_hash(provenance),'errors':[]}
    directory=tmp_path/RUN
    freeze_json(directory/'corpus.json',{'recordings':[r]})
    freeze_json(directory/'reuse_manifest.json',{})
    monkeypatch.setattr(worker,'configuration',lambda root:{'fixture':True})
    monkeypatch.setattr(torch,'set_num_threads',lambda _:None)
    monkeypatch.setattr(torch,'set_num_interop_threads',lambda _:None)
    monkeypatch.setattr(decoder,'decode_mono',lambda *args:np.ones(484800,dtype=np.float32))
    calls=[]
    class FakeEncoder:
        def __init__(self,**kwargs): pass
        def encode_segment(self,waveform,sr):
            calls.append(len(waveform))
            if len(calls)==2:
                raise RuntimeError('isolated synthetic interruption')
            v=np.arange(1,513,dtype=np.float64)
            return SimpleNamespace(embedding=v/np.linalg.norm(v))
    monkeypatch.setattr(encoders,'LaionClapEncoder',FakeEncoder)
    first=worker.run(tmp_path)
    assert first['failed']==1 and first['inference_calls']==2
    assert not (directory/'features/a.json').exists()
    original={p:p.read_bytes() for p in (directory/'invocations').rglob('*.json')}
    second=worker.run(tmp_path)
    assert second['computed']==1 and second['inference_calls']==1
    assert calls==[480000,4800,4800]
    from audio_similarity.calibration.method_c_full_inputs import read
    assert read(directory/'features/a.json')['views'][0]==read(directory/'chunks/a/0.json')['vector']
    assert all(p.read_bytes()==raw for p,raw in original.items())
    assert worker.run(tmp_path,replay=True)['inference_calls']==0


def test_existing_sampling_plan_short_boundary_fails_explicitly():
    from audio_similarity.stage5e1_sampling import sampling_plan
    # The shared historical plan also constructs native-fusion metadata.
    # Preserve this legacy boundary failure rather than introduce a C variant.
    with pytest.raises(ValueError,match='native fusion thirds are empty'):
        sampling_plan(480001,'a'*64)
