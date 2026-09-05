from audio_similarity.stage5e2 import resolve_labels, missing_queue, evaluate
from audio_similarity.stage5e1_review import Stage5E1ReviewStore
from audio_similarity.stage5c2_analysis import canonical_pair_id
from audio_similarity.stage5e2 import audit_labels
import csv
import json
import numpy as np
import pytest
from audio_similarity.stage5e2_subset import subset_retrieval


def test_labels_deduplicate_copies_and_conflicts_require_review():
    evidence = [{'pair_id':'p','label':'3'}, {'pair_id':'p','label':'3'},
                {'pair_id':'p','label':'UNSURE'}, {'pair_id':'q','label':'1'},
                {'pair_id':'q','label':'5'}, {'pair_id':'r','label':'UNSURE'}]
    labels, conflicts = resolve_labels(evidence)
    assert labels == {'p':3}
    assert conflicts == {'q':['1','5']}


def test_missing_queue_is_deterministic_deduplicated_and_blinded():
    tracks = {str(i): {'spotify_track_id':str(i), 'title':str(i), 'artists':['x']} for i in range(4)}
    pairs = {canonical_pair_id('0',str(i)):('0',str(i)) for i in range(1,4)}
    labels = {canonical_pair_id('0','1'):4}
    first = missing_queue(tracks,pairs,labels)
    assert first == missing_queue(tracks,dict(reversed(list(pairs.items()))),labels)
    assert len(first['pairs']) == 2
    for p in first['pairs']:
        assert not {'origins','rank','similarity','arm','model'} & p.keys()
        public = Stage5E1ReviewStore.__new__(Stage5E1ReviewStore)._public_track(p['left'])
        assert not {'source_sha256','youtube_video_id','retained_source_path'} & public.keys()


def test_paired_metrics_require_complete_both_pools():
    rows = [{'rank':i,'spotify_track_id':str(i),'similarity':1-i/10} for i in range(1,6)]
    neighbors = {'tracks':[{'spotify_track_id':'q','retrievals':{k:rows for k in ('D_CLAP','D_COMBINED','A_CLAP','A_COMBINED')}}]}
    labels = {canonical_pair_id('q',str(i)):3 for i in range(1,5)}
    pairs, metrics = evaluate(neighbors,labels)
    assert len(pairs)==5
    assert metrics['paired_D_vs_A']['CLAP']['fully_rated_queries']==0
    labels[canonical_pair_id('q','5')]=4
    _, metrics = evaluate(neighbors,labels)
    assert metrics['paired_D_vs_A']['CLAP']['ties']==1
    assert metrics['quality']['D_CLAP']['complete_query_similarity_at5']==3.2


def test_label_reuse_requires_current_scale_and_frozen_source(tmp_path):
    directory = tmp_path / 'reports' / 'historical'
    directory.mkdir(parents=True)
    tracks = {x: {'youtube_video_id': x} for x in ('a', 'b')}
    selected = {'tracks': [{'spotify_track_id': x, 'selected_youtube_video_id': x} for x in tracks]}
    (directory / 'selected_sources.json').write_text(json.dumps(selected))
    path = directory / 'human_review.csv'
    fields = ['review_schema_version', 'query_spotify_id', 'neighbor_spotify_id', 'pair_id', 'human_label']
    with path.open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for version in ('v1', 'v2'):
            writer.writerow(dict(zip(fields, [f'stage5c2-human-similarity-review-{version}', 'a', 'b', canonical_pair_id('a','b'), '3'])))
    audit, evidence = audit_labels(tmp_path, tracks)
    assert len(evidence) == 1
    assert audit[0]['outcomes']['incompatible_rating_contract'] == 1
    tracks['b']['youtube_video_id'] = 'different-source'
    _, evidence = audit_labels(tmp_path, tracks)
    assert evidence == []


def test_original100_restricts_both_axes_before_ranking():
    tracks = {str(i): {'spotify_track_id':str(i), 'youtube_video_id':str(i),
                      'source_sha256':str(i), 'title':str(i), 'artists':['artist']} for i in range(101)}
    selected = {'tracks':[{'spotify_track_id':str(i), 'selected_youtube_video_id':str(i)} for i in range(100)]}
    matrix = np.full((101,101), .2)
    np.fill_diagonal(matrix, 1)
    matrix[100,:100] = matrix[:100,100] = .99
    matrices = {'spotify_ids':np.array(list(tracks)), **{k:matrix for k in ('a_clap','a_combined','d_clap','d_combined')}}
    subset, neighbors = subset_retrieval(tracks,selected,matrices)
    assert len(subset) == len(neighbors['tracks']) == 100
    for query in neighbors['tracks']:
        for pool in query['retrievals'].values():
            assert len(pool) == 10
            assert all(r['spotify_track_id'] in subset and r['spotify_track_id'] != query['spotify_track_id'] for r in pool)
    assert neighbors == subset_retrieval(tracks,selected,matrices)[1]
    selected['tracks'][0]['selected_youtube_video_id'] = 'wrong'
    with pytest.raises(ValueError, match='source identity'):
        subset_retrieval(tracks,selected,matrices)
