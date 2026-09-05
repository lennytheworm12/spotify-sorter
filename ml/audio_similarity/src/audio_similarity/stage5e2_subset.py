"""Restrict frozen similarities on both axes before ranking; never infer audio."""
import numpy as np

from .stage5e1_analysis import _neighbors


def subset_retrieval(tracks, selected, matrices):
    sources = {row['spotify_track_id']: row['selected_youtube_video_id'] for row in selected['tracks']}
    if len(sources) != 100 or len(selected['tracks']) != 100:
        raise ValueError('expected exactly 100 amended frozen sources')
    ids = sorted(sources)
    if any(t not in tracks or tracks[t]['youtube_video_id'] != sources[t] for t in ids):
        raise ValueError('original-100 source identity mismatch')
    matrix_ids = list(matrices['spotify_ids'])
    if len(set(matrix_ids)) != len(matrix_ids) or set(matrix_ids) != set(tracks):
        raise ValueError('matrix corpus identity mismatch')
    indices = [matrix_ids.index(t) for t in ids]
    restricted = {}
    for arm in ('A', 'D'):
        for mode in ('CLAP', 'COMBINED'):
            matrix = matrices[f'{arm}_{mode}'.lower()]
            if matrix.shape != (len(tracks), len(tracks)):
                raise ValueError('matrix shape mismatch')
            sub = matrix[np.ix_(indices, indices)]
            if not np.isfinite(sub).all() or not np.allclose(sub, sub.T) or not np.allclose(sub.diagonal(), 1):
                raise ValueError('invalid frozen similarity matrix')
            restricted[arm, mode] = sub
    subset = {t: tracks[t] for t in ids}
    return subset, _neighbors(list(subset.values()), restricted)
