import numpy as np
import pytest
from audio_similarity.song_space_export import knn_links


def test_neighbors_are_symmetric_unique_ranked_and_exclude_self():
    ids = ['a', 'b', 'c']
    matrix = np.array([[1, .8, .8], [.8, 1, .5], [.8, .5, 1]])
    links = knn_links(ids, matrix, 1)
    assert links == [
        {'source': 'a', 'target': 'b', 'score': .8, 'sourceRank': 1, 'targetRank': 1},
        {'source': 'a', 'target': 'c', 'score': .8, 'sourceRank': None, 'targetRank': 1},
    ]
    assert knn_links(list(reversed(ids)), matrix[::-1, ::-1], 1) == links
    assert knn_links(['a'], np.ones((1, 1)), 12) == []


@pytest.mark.parametrize('matrix', [np.array([[1, np.nan], [np.nan, 1]]), np.array([[1, .8], [.2, 1]]), np.ones((3, 3))])
def test_bad_scores_fail_instead_of_exporting_fake_neighbors(matrix):
    with pytest.raises(ValueError):
        knn_links(['a', 'b'], matrix)


def test_source_correction_is_hash_locked_and_preserves_original(tmp_path):
    import copy
    import hashlib
    import json
    from audio_similarity.song_space_export import apply_source_corrections
    directory = tmp_path / '.research_audio/library_batches_v1'
    directory.mkdir(parents=True)
    replacement = {'state': 'COMPLETE', 'result': {'source_sha256': 'new', 'representation': {
        'status': 'SUCCESS', 'stable_track_id': 'a', 'source_audio_sha256': 'new'}}}
    record = directory / 'correction.json'
    record.write_text(json.dumps(replacement))
    index = {'schema_version': 'library-source-corrections-v1', 'corrections': [{
        'spotify_track_id': 'a', 'expected_old_source_sha256': 'old',
        'record_path': str(record.relative_to(tmp_path)),
        'record_sha256': hashlib.sha256(record.read_bytes()).hexdigest()}]}
    (directory / 'source_corrections.json').write_text(json.dumps(index))
    original = {'a': {'state': 'COMPLETE', 'result': {'source_sha256': 'old'}}}
    rows = copy.deepcopy(original)
    apply_source_corrections(tmp_path, rows, [], set())
    assert rows['a'] == replacement and original['a']['result']['source_sha256'] == 'old'
    with pytest.raises(ValueError, match='frozen-C'):
        apply_source_corrections(tmp_path, copy.deepcopy(original), [], {'a'})
    with pytest.raises(ValueError, match='historical source'):
        apply_source_corrections(tmp_path, rows, [], set())
    record.write_text(json.dumps(replacement) + ' ')
    with pytest.raises(ValueError):
        apply_source_corrections(tmp_path, copy.deepcopy(original), [], set())
