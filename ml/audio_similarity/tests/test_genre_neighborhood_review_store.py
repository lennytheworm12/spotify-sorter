import copy
import csv

import pytest

from audio_similarity.genre_neighborhood_review_store import GenreNeighborhoodReviewStore, FIELDS
from audio_similarity.gemini_style_review_store import GeminiStyleReviewStore, STATE as OLD_STATE
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5e3_artifacts import hashes, read
from tests.test_gemini_style_review import packet as original_packet


@pytest.fixture
def mapping_packet(original_packet):
    packet = copy.deepcopy(original_packet)
    packet.update(review_kind='genre-neighborhood-owner-review-v1', map={})
    for t in packet['tracks']:
        t['mapping'] = {'raw_genre_labels': {'primary_family': 'Raw spelling unchanged'}}
    return packet


def test_separate_autosave_resume_revision_history_and_completed_freeze(tmp_path, original_packet, mapping_packet):
    old = GeminiStyleReviewStore(tmp_path, tmp_path / OLD_STATE, packet=original_packet)
    old.close()
    before = hashes(list((tmp_path / OLD_STATE).rglob('*')), tmp_path)
    store = GenreNeighborhoodReviewStore(tmp_path, tmp_path/'mapping-state', packet=mapping_packet)
    session = store.session()
    assert session['phase'] == 'compare' and session['tracks'][0]['mapping'] == mapping_packet['tracks'][0]['mapping']
    note = '=Synthetic, "quoted"\n音楽' + 'z'*50000
    answer = {'mapping_verdict': 'fits', 'classification_verdict': 'does_not_fit', 'notes': note}
    store.save('A01', answer, 0)
    with pytest.raises(Stage5B1AValidationError, match='Another tab'):
        store.save('A01', answer | {'notes': 'stale'}, 0)
    with pytest.raises(Stage5B1AValidationError, match='250,000'):
        store.save('A01', answer | {'notes': 'x'*250001}, 1)
    assert store.session()['tracks'][0]['answer']['fields']['notes'] == note
    store.close()
    store = GenreNeighborhoodReviewStore(tmp_path, tmp_path/'mapping-state', packet=mapping_packet)
    assert store.session()['tracks'][0]['answer']['revision'] == 1
    assert store.db.execute('SELECT count(*) FROM events').fetchone()[0] == 1
    with pytest.raises(Stage5B1AValidationError, match='both questions'):
        store.advance({t['pilot_id']:t['answer']['revision'] for t in store.session()['tracks']})
    store.save('A02', dict.fromkeys(FIELDS,'') | {'mapping_verdict':'not_sure','classification_verdict':'partly'}, 0)
    revisions = {t['pilot_id']:t['answer']['revision'] for t in store.session()['tracks']}
    assert store.advance(revisions)['phase'] == 'complete'
    assert store.advance(revisions)['phase'] == 'complete'
    assert read(store.state_dir/'owner_snapshot.json')['semantic_tag'] == 'OWNER_GENRE_MAPPING_REVIEW_V1'
    with pytest.raises(Stage5B1AValidationError, match='frozen'): store.save('A01',answer,1)
    with store.review_path.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    assert rows[0]['notes'] == "'" + note
    assert rows[0]['mapping_verdict']=='fits' and rows[0]['classification_verdict']=='does_not_fit'
    store.close()
    assert before==hashes(list((tmp_path/OLD_STATE).rglob('*')),tmp_path)


def test_refuse_old_state_and_changed_packet(tmp_path, mapping_packet):
    with pytest.raises(ValueError, match='earlier listening'):
        GenreNeighborhoodReviewStore(tmp_path,tmp_path/OLD_STATE,packet=mapping_packet)
    store=GenreNeighborhoodReviewStore(tmp_path,tmp_path/'state',packet=mapping_packet)
    store.close()
    changed=copy.deepcopy(mapping_packet);changed['map']={'new_version':True}
    with pytest.raises(ValueError, match='different mapping packet'):
        GenreNeighborhoodReviewStore(tmp_path,tmp_path/'state',packet=changed)


@pytest.mark.parametrize('field,value', [('mapping_verdict','approved'),('classification_verdict',True),('notes',None)])
def test_invalid_answers_are_not_saved(tmp_path,mapping_packet,field,value):
    store=GenreNeighborhoodReviewStore(tmp_path,tmp_path/'state',packet=mapping_packet)
    with pytest.raises(Stage5B1AValidationError):store.save('A01',dict.fromkeys(FIELDS,'')|{field:value},0)
    assert store.session()['tracks'][0]['answer']['revision']==0
    store.close()
