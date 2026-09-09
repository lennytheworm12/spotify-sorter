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
