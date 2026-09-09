from pathlib import Path
from collections import Counter
from audio_similarity.stage5e3_artifacts import read
from audio_similarity.style_prior_review import select, REVIEW
from audio_similarity.taxonomy_review_store import TaxonomyReviewStore

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_review_selection_and_isolated_store(tmp_path):
    run = ROOT / 'reports/style_prior_pilot/v2'
    tracks = {t['spotify_track_id']: t for t in read(run / 'tracks.json')}
    rows = [p for p in read(run / 'pair_results.json') if p['rubric'] == 'playlist']
    excluded = {p['pair_id'] for p in read(ROOT / 'reports/stage5g1b_taxonomy_review/v1/packet.json')['pairs']}
    selected = select(rows, tracks, excluded)
    assert selected == select(list(reversed(rows)), tracks, excluded)
    assert len(selected) == 12 and len({tid for p in selected for tid in p['tracks']}) == 24
    assert not {p['pair_id'] for p in selected} & excluded
    assert sorted(Counter(p['selection_stratum'] for p in selected).values()) == [6, 6]
    store = TaxonomyReviewStore(ROOT / REVIEW / 'packet.json', tmp_path, ROOT)
    try:
        session = store.session()
        assert session['total'] == 12 and session['completed'] == 0
        for pair in session['pairs']:
            assert set(pair) == {'pair_id', 'left', 'right', 'answer', 'complete'}
            assert not {'rating', 'style_distance', 'selection_stratum'} & set(pair)
    finally:
        store.close()
