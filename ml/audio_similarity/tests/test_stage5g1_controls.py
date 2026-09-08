"""Additional fault-injection controls; isolated from real ratings and audio."""
from pathlib import Path
import numpy as np
import pytest
from audio_similarity.stage5g1_segments import SegmentCache,extract
from audio_similarity.stage5e3_artifacts import hashes,verify_hashes,freeze_json
from audio_similarity.stage5g1_evidence import split_inventory


def test_interrupted_cache_reuses_successful_chunks(tmp_path):
    c=SegmentCache(tmp_path/'segments.sqlite');calls=[]
    def forward(x):
        calls.append(1)
        if len(calls)==2:raise ValueError('synthetic failure')
        return np.ones(512)
    with pytest.raises(ValueError,match='synthetic'):extract(np.ones(480001),forward,c,'source-key')
    assert c.get('source-key',0) is not None and c.get('source-key',1) is None
    a,plan,n=extract(np.ones(480001),lambda x:np.ones(512),c,'source-key')
    assert n==1 and a.shape==(2,512)
    c.close()


def test_historical_immutability_guard(tmp_path):
    historical=tmp_path/'historical.json';freeze_json(historical,{'human_label':4})
    manifest=hashes([historical],tmp_path);verify_hashes(tmp_path,manifest)
    with pytest.raises(ValueError,match='frozen'):freeze_json(historical,{'human_label':1})
    historical.write_text('{}')
    with pytest.raises(ValueError):verify_hashes(tmp_path,manifest)


def test_cross_partition_pairs_never_become_training_preferences():
    tracks=[{'spotify_track_id':str(i),'source_sha256':str(i),'youtube_video_id':str(i),'artists':[str(i)]} for i in range(30)]
    pairs=[{'tracks':[str(i),str(j)],'rating':(j%5)+1} for i in range(30) for j in range(i+1,30)]
    gate={part:{'anchors':1,'preferences':1} for part in ['train','validation','test']}
    split=split_inventory(tracks,pairs,gate)
    for part,rows in split['constraints'].items():
        assert all({r['anchor'],r['preferred'],r['other']}<=set(split['partitions'][part]) for r in rows)
    assert split['counts']['cross_partition_pairs']>0
