import copy
import csv
import json
from pathlib import Path

import pytest

from audio_similarity.gemini_style_review_store import GeminiStyleReviewStore, FIELDS
from audio_similarity.stage5b1a_models import file_sha256, Stage5B1AValidationError
from audio_similarity.stage5e3_artifacts import read


@pytest.fixture
def packet(tmp_path):
    tracks = []
    for index in (1, 2):
        path = tmp_path / f'.research_audio/fixture{index}.flac'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'ISOLATED TEST AUDIO BYTES')
        tracks.append({'pilot_id': f'A0{index}', 'neutral_id': f'N00{index}', 'spotify_track_id': str(index),
            'title': '=Synthetic song', 'artists': ['Fixture'], 'duration_seconds': 120,
            'audio_path': str(path.relative_to(tmp_path)), 'audio_sha256': file_sha256(path),
            'profile': {'primary_family': 'HIDDEN_SYNTHETIC_CLASSIFICATION'}, 'repeat': None})
    return {'schema': 'gemini-owner-review-v1', 'tracks': tracks, 'profiles_frozen_sha256': 'a'*64}


def revisions(store):
    return {t['pilot_id']: t['answer']['revision'] for t in store.session()['tracks']}


def describe(store):
    for track in store.session()['tracks']:
        value = track['answer']['fields'] | {'owner_recording_identity_ok': 'not_sure',
                                           'owner_family_or_style_words': 'Unsure; synthetic fixture only.'}
        store.save(track['pilot_id'], value, track['answer']['revision'])


def test_two_pass_gate_preserves_independent_notes_and_rejects_premature_disclosure(tmp_path, packet):
    original = copy.deepcopy(packet)
    store = GeminiStyleReviewStore(tmp_path, tmp_path/'state', packet=packet)
    assert 'HIDDEN_SYNTHETIC_CLASSIFICATION' not in json.dumps(store.session())
    assert 'primary_family' not in json.dumps(store.session())
    with pytest.raises(Stage5B1AValidationError, match='Finish'):
        store.profile('A01')
    with pytest.raises(Stage5B1AValidationError, match='Complete every'):
        store.advance(revisions(store))
    fields = dict.fromkeys(FIELDS, '') | {'description_verdict': 'fits'}
    with pytest.raises(Stage5B1AValidationError, match='unavailable'):
        store.save('A01', fields, 0)
    describe(store)
    assert store.session()['listening_completed'] == 2
    assert store.advance(revisions(store))['phase'] == 'compare'
    before = (store.state_dir/'independent_snapshot.json').read_bytes()
    assert store.profile('A01')['primary']['primary_family'] == 'HIDDEN_SYNTHETIC_CLASSIFICATION'
    first = store.session()['tracks'][0]['answer']
    with pytest.raises(Stage5B1AValidationError, match='independent listening notes are frozen'):
        store.save('A01', first['fields'] | {'owner_family_or_style_words': 'AFTER REVEAL'}, first['revision'])
    for t in store.session()['tracks']:
        store.save(t['pilot_id'], t['answer']['fields'] | {'description_verdict': 'not_sure',
                    'model_certainty_appropriate': 'not_sure'}, t['answer']['revision'])
    store.advance(revisions(store))
    assert (store.state_dir/'independent_snapshot.json').read_bytes() == before
    assert read(store.state_dir/'owner_snapshot.json')['new_playlist_ratings'] == 0
    assert store.session()['phase'] == 'complete'
    with pytest.raises(Stage5B1AValidationError, match='frozen'):
        store.save('A01', store.session()['tracks'][0]['answer']['fields'], 2)
    store.close()
    resumed = GeminiStyleReviewStore(tmp_path, tmp_path/'state', packet=packet)
    assert resumed.session()['phase'] == 'complete' and packet == original
    resumed.close()


def test_revision_conflicts_long_notes_export_and_recovery_from_failed_csv_write(tmp_path, packet, monkeypatch):
    store = GeminiStyleReviewStore(tmp_path, tmp_path/'state', packet=packet)
    other = GeminiStyleReviewStore(tmp_path, tmp_path/'state', packet=packet)
    note = '=音楽🎵,\n' * 12_000
    fields = dict.fromkeys(FIELDS, '') | {'owner_recording_identity_ok': 'yes', 'owner_family_or_style_words': note}
    export = store._export
    monkeypatch.setattr(store, '_export', lambda: (_ for _ in ()).throw(OSError('synthetic disk failure')))
    with pytest.raises(OSError):
        store.save('A01', fields, 0)
    assert other.session()['tracks'][0]['answer']['fields']['owner_family_or_style_words'] == note
    monkeypatch.setattr(store, '_export', export)
    result = store.save('A01', fields, 0)  # Idempotent retry repairs the CSV, not another revision.
    assert result['answer']['revision'] == 1
    with pytest.raises(Stage5B1AValidationError, match='Another tab'):
        other.save('A01', fields | {'owner_family_or_style_words': 'stale'}, 0)
    exported = list(csv.DictReader(store.review_path.open(encoding='utf-8-sig')))
    assert exported[0]['owner_family_or_style_words'] == "'" + note
    assert exported[0]['song'].startswith("'=Synthetic")
    assert store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 1
    store.close();other.close()


def test_validation_state_identity_and_source_integrity(tmp_path, packet):
    store = GeminiStyleReviewStore(tmp_path, tmp_path/'state', packet=packet)
    with pytest.raises(Stage5B1AValidationError):
        store.save({}, dict.fromkeys(FIELDS, ''), 0)
    with pytest.raises(Stage5B1AValidationError):
        store.save('A01', dict.fromkeys(FIELDS, '') | {'extra': 'bad'}, 0)
    with pytest.raises(Stage5B1AValidationError):
        store.save('A01', dict.fromkeys(FIELDS, ''), True)
    with pytest.raises(Stage5B1AValidationError, match='nothing was truncated'):
        store.save('A01', dict.fromkeys(FIELDS, '') | {'owner_family_or_style_words': 'x' * 250_001}, 0)
    assert store.session()['tracks'][0]['answer']['revision'] == 0
    with pytest.raises(Stage5B1AValidationError):
        store.advance({'A01': True, 'A02': False})
    assert store.local_audio_for_request('../secrets') is None
    store.close()
    changed = copy.deepcopy(packet);changed['tracks'][0]['profile']['primary_family'] = 'CHANGED'
    with pytest.raises(ValueError, match='another frozen pilot'):
        GeminiStyleReviewStore(tmp_path, tmp_path/'state', packet=changed)
    with pytest.raises(ValueError, match='frozen research'):
        GeminiStyleReviewStore(tmp_path, tmp_path/'reports', packet=packet)
    (tmp_path / packet['tracks'][0]['audio_path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='integrity'):
        GeminiStyleReviewStore(tmp_path, tmp_path/'other', packet=packet)
