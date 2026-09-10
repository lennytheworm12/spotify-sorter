"""Separate owner feedback for the frozen mapping, reusing review/audio infrastructure."""
import csv
import io
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from .gemini_style_review_store import GeminiStyleReviewStore, STATE as OLD_STATE, load_packet
from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5e3_artifacts import digest, freeze_json, read, verify_hashes
from .taxonomy_review_store import safe_cell

REPORT = Path('reports/genre_neighborhood_map/v1/pilot16')
STATE = Path('artifacts/genre_neighborhood_review/pilot16')
FIELDS = ('mapping_verdict', 'classification_verdict', 'notes')
CHOICES = ('', 'fits', 'partly', 'does_not_fit', 'not_sure')


def load_mapping_packet(root):
    report = root / REPORT
    verify_hashes(report, read(report / 'artifact_manifest.json')['files'])
    mapped = {r['pilot_id']: r for r in read(report / 'mapped_review.json')}
    original = load_packet(root)
    if set(mapped) != {t['pilot_id'] for t in original['tracks']} or len(mapped) != 16:
        raise ValueError('The exact original 16 mapped tracks are required')
    tracks = []
    for t in original['tracks']:
        row = mapped[t['pilot_id']]
        if row['spotify_track_id'] != t['spotify_track_id']:
            raise ValueError('Mapped track/audio identity differs')
        tracks.append({k: v for k, v in t.items() if k not in ('profile', 'repeat')} | {'mapping': row})
    return {'schema': 'gemini-owner-review-v1', 'review_kind': 'genre-neighborhood-owner-review-v1',
            'mapping_artifact_sha256': file_sha256(report / 'artifact_manifest.json'),
            'map': read(report / 'genre-neighborhood-map-v1.json'), 'tracks': tracks}


class GenreNeighborhoodReviewStore(GeminiStyleReviewStore):
    """Same durable revision/audio plumbing; independent packet, fields and state."""

    def __init__(self, root, state_dir, *, packet=None):
        root, state = Path(root).resolve(), Path(state_dir).resolve()
        old = root / OLD_STATE
        if state == old or old in state.parents:
            raise ValueError('Mapping feedback must not use the earlier listening-review state')
        packet = packet if packet is not None else load_mapping_packet(root)
        if packet.get('review_kind') != 'genre-neighborhood-owner-review-v1':
            raise ValueError('Wrong mapping review packet')
        super().__init__(root, state, packet=packet)

    def _initialize(self):
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS answers (pilot_id TEXT PRIMARY KEY, answer TEXT, revision INTEGER, updated_at TEXT)')
            self.db.execute('CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, pilot_id TEXT, answer TEXT, revision INTEGER, updated_at TEXT, phase TEXT)')
            stored = self.db.execute("SELECT value FROM metadata WHERE key='packet_hash'").fetchone()
            if stored and stored[0] != self.packet_hash:
                raise ValueError('State belongs to a different mapping packet')
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('packet_hash', ?)", (self.packet_hash,))
            for pid in self.tracks:
                self.db.execute('INSERT OR IGNORE INTO answers VALUES (?, ?, 0, ?)', (pid, json.dumps(dict.fromkeys(FIELDS, '')), ''))

    def _phase(self):
        return 'complete' if self._snapshot('owner_snapshot') else 'compare'

    def session(self):
        with self.lock:
            answers = self._answers()
            tracks = [{k: t[k] for k in ('pilot_id', 'neutral_id', 'spotify_track_id', 'title', 'artists', 'duration_seconds', 'mapping')} |
                      {'audio_url': '/audio/track/' + pid, 'answer': answers[pid]} for pid, t in self.tracks.items()]
            return {'packet_hash': self.packet_hash, 'review_kind': self.packet['review_kind'], 'phase': self._phase(),
                    'tracks': tracks, 'total': len(tracks), 'field_order': list(FIELDS),
                    'max_note_length': self.max_note_length, 'map': self.packet['map']}

    def save(self, pid, fields, revision):
        if not isinstance(pid, str) or pid not in self.tracks or not isinstance(fields, dict) or set(fields) != set(FIELDS):
            raise Stage5B1AValidationError('Unknown mapping track or answer fields.')
        if type(revision) is not int or revision < 0:
            raise Stage5B1AValidationError('Missing answer revision.')
        if any(not isinstance(v, str) or len(v) > self.max_note_length for v in fields.values()):
            raise Stage5B1AValidationError('Invalid note; maximum 250,000 characters, never truncated.')
        if any(fields[k] not in CHOICES for k in FIELDS[:2]):
            raise Stage5B1AValidationError('Invalid review choice.')
        with self.lock:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                if self._phase() == 'complete':
                    raise Stage5B1AValidationError('Completed review is frozen; export remains available.')
                current = self._answers()[pid]
                if fields == current['fields']:
                    self._export()
                    return {'ok': True, 'answer': current}
                if revision != current['revision']:
                    raise Stage5B1AValidationError('Another tab changed this answer. Retry your draft or reload the saved answer.')
                answer = {'fields': fields, 'revision': revision + 1, 'updated_at': datetime.now(timezone.utc).isoformat()}
                self.db.execute('UPDATE answers SET answer=?, revision=?, updated_at=? WHERE pilot_id=?',
                                (json.dumps(fields, ensure_ascii=False), answer['revision'], answer['updated_at'], pid))
                self.db.execute('INSERT INTO events(pilot_id,answer,revision,updated_at,phase) VALUES (?,?,?,?,?)',
                                (pid, json.dumps(fields, ensure_ascii=False), answer['revision'], answer['updated_at'], 'mapping_review'))
            self._export()
            return {'ok': True, 'answer': answer}

    def advance(self, revisions):
        with self.lock:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                answers = self._answers()
                if not isinstance(revisions, dict) or any(type(v) is not int for v in revisions.values()) or revisions != {k: v['revision'] for k, v in answers.items()}:
                    raise Stage5B1AValidationError('Answers changed. Reload before finishing.')
                if not all(all(a['fields'][k] for k in FIELDS[:2]) for a in answers.values()):
                    raise Stage5B1AValidationError('Answer both questions for every song; Not sure is valid.')
                if not self._snapshot('owner_snapshot'):
                    snapshot = {'packet_hash': self.packet_hash, 'semantic_tag': 'OWNER_GENRE_MAPPING_REVIEW_V1',
                                'answers': answers, 'created_at': datetime.now(timezone.utc).isoformat(),
                                'new_playlist_ratings': 0, 'frozen_model_outputs_modified': False}
                    self.db.execute('INSERT INTO metadata VALUES (?, ?)', ('owner_snapshot', json.dumps(snapshot, ensure_ascii=False)))
            self._export()
            return {'ok': True, 'phase': self._phase()}

    def _export(self):
        output = io.StringIO(newline='')
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['packet_hash', 'pilot_id', 'spotify_track_id', 'song', *FIELDS, 'revision', 'updated_at', 'save_status'])
        for pid, answer in self._answers().items():
            t = self.tracks[pid]
            row = [self.packet_hash, pid, t['spotify_track_id'], t['title'] + ' — ' + ', '.join(t['artists']),
                   *[answer['fields'][k] for k in FIELDS], answer['revision'], answer['updated_at'], 'SAVED']
            writer.writerow([safe_cell(v) for v in row])
        temporary = self.review_path.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
        with temporary.open('w', encoding='utf-8-sig', newline='') as handle:
            handle.write(output.getvalue()); handle.flush(); os.fsync(handle.fileno())
        temporary.replace(self.review_path)
        snapshot = self._snapshot('owner_snapshot')
        if snapshot:
            freeze_json(self.state_dir / 'owner_snapshot.json', snapshot)
