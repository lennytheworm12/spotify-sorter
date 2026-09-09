import csv
import hashlib
import json
import wave
import numpy as np
import pytest
from audio_similarity.taxonomy_packet import select_pairs
from audio_similarity.taxonomy_review_store import TaxonomyReviewStore, complete
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5c2_analysis import canonical_pair_id


@pytest.fixture
def packet(tmp_path):
    tracks = []
    for id in ('a', 'b'):
        path = tmp_path / '.research_audio' / id / 'source.wav'
        path.parent.mkdir(parents=True)
        with wave.open(str(path), 'wb') as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
            audio.writeframes(np.zeros(32000, dtype='<i2').tobytes())
        tracks.append({'spotify_track_id': id, 'retained_source_path': str(path.relative_to(tmp_path)),
                       'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'title': '=song', 'artists': ['artist']})
    path = tmp_path / 'packet.json'
    path.write_text(json.dumps({'schema': 'taxonomy-audit-v1', 'pairs': [{'pair_id': canonical_pair_id('a', 'b'),
                                                                      'left': tracks[0], 'right': tracks[1]}]}))
    return path


def test_persistence_conflict_export_and_freeze(packet, tmp_path):
    store = TaxonomyReviewStore(packet, tmp_path / 'state', tmp_path)
    assert store.session()['completed'] == 0
    with pytest.raises(ValueError):store.freeze()
    result = store.submit('a', 'b', 'OTHER', '', '0')
    assert result['answer']['revision'] == 1 and store.session()['completed'] == 0
    with pytest.raises(Stage5B1AValidationError):store.submit('a', 'b', 'NONE', '', '0')
    result = store.submit('a', 'b', 'OTHER', '=a note, with\nnewlines', '1')
    assert store.session()['completed'] == 1
    assert store.submit('b', 'a', 'OTHER', '=a note, with\nnewlines', '1') == result
    exported = list(csv.DictReader(store.review_path.open(encoding='utf-8-sig')))
    assert exported[0]['note'].startswith("'=a note") and exported[0]['left_song'].startswith("'=song")
    assert store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 2
    store.close()
    resumed = TaxonomyReviewStore(packet, tmp_path / 'state', tmp_path)
    assert resumed.session()['pairs'][0]['answer']['note'] == '=a note, with\nnewlines'
    resumed.freeze()
    with pytest.raises(Stage5B1AValidationError):resumed.submit('a', 'b', 'NONE', '', '2')
    resumed.close()


def test_public_whitelist_and_unknown_pairs(packet, tmp_path):
    store = TaxonomyReviewStore(packet, tmp_path / 'state', tmp_path)
    session = store.session()
    assert set(session['pairs'][0]) == {'pair_id', 'left', 'right', 'answer', 'complete'}
    assert set(session['pairs'][0]['left']) == {'spotify_track_id', 'title', 'artists', 'audio_url'}
    for forbidden in ['source_sha256', 'retained_source_path', 'rating', 'distance', 'stratum', 'probe']:
        assert forbidden not in json.dumps(session)
    assert store.local_audio_for_request('../secrets') is None
    with pytest.raises(Stage5B1AValidationError):store.submit('a', 'z', 'NONE', '', '0')
    with pytest.raises(Stage5B1AValidationError):store.submit('a', 'b', '1', '', '0')
    with pytest.raises(Stage5B1AValidationError):store.submit('a', 'b', 'NONE', 'x'*50001, '0')
    store.close()


def test_balanced_selection_deterministic_and_no_track_reuse():
    tracks = {str(i): {'artists': [str(i)]} for i in range(64)}
    pairs = [{'pair_id': str(i), 'tracks': [str(2*i), str(2*i+1)], 'rating': 1 if i < 16 else 5} for i in range(32)]
    probes = [{'pair_id': str(i), 'rubric': 'playlist', 'distance': i/32, 'flag': i%5==0} for i in range(32)]
    selected, artists = select_pairs(pairs, probes, tracks)
    assert (selected, artists) == select_pairs(list(reversed(pairs)), list(reversed(probes)), tracks)
    assert len(selected) == 16 and len({id for p in selected for id in p['tracks']}) == 32
    assert all(sum(p['selection_stratum']==s for p in selected)==4 for s in ('bad_high','bad_low','good_high','good_low'))
    assert complete('UNSURE', '') and complete('NONE', '') and not complete('', 'note')


def test_long_unicode_note_persists_without_truncation(packet, tmp_path):
    store = TaxonomyReviewStore(packet, tmp_path / 'long-state', tmp_path)
    note = '音楽🎵,\n' * 5000
    assert len(note) > 2000
    store.submit('a', 'b', 'OTHER', note, '0')
    assert store.session()['pairs'][0]['answer']['note'] == note
    assert list(csv.DictReader(store.review_path.open(encoding='utf-8-sig')))[0]['note'] == note
    store.close()
