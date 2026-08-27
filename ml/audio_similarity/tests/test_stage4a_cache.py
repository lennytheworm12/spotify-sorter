import numpy as np
from audio_similarity.stage4a_cache import Cache,base_row,key,vector_bytes

def test_vector_bytes_normalizes_hashes_and_rejects_wrong_dimension():
 raw,digest=vector_bytes(np.arange(1,513,dtype=np.float32));saved=np.frombuffer(raw,dtype='<f4')
 assert np.linalg.norm(saved)==np.float32(1.0) and len(digest)==64

def test_sqlite_cache_is_segment_granular_version_isolated_and_resumable(tmp_path):
 cache=Cache(tmp_path/'cache.sqlite');base={'corpus':'fma_small','corpus_version':'v','track_id':1,'source_sha256':'a','canonical_pcm_sha256':'b','encoder_id':'laion_clap','encoder_checkpoint_sha256':'c','encoder_revision':'r','preprocessing_version':'p','sampling_version':'s','embedding_dtype':'float32','embedding_dimension':512};base['analysis_key']=key(base)
 raw,digest=vector_bytes(np.ones(512))
 for index,center in enumerate((3,5,9,15,21,25,27)):
  cache.insert(base|{'segment_index':index,'center_sec':center,'start_sample':index,'end_sample':index+120000,'start_sec':0,'end_sec':5,'embedding':raw,'embedding_sha256':digest,'status':'ok','failure':'','encode_ms':1,'created_at':1})
 assert cache.centers(1,base['analysis_key'])=={3,5,9,15,21,25,27}
 assert cache.manifest()['complete_tracks']==1
 changed=base|{'sampling_version':'other'};changed['analysis_key']=key(changed)
 assert cache.centers(1,changed['analysis_key'])==set()
