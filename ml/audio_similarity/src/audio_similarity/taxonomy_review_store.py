"""Separate durable taxonomy answers; reuses the local audio/range server."""
import csv
import io
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5c2_analysis import canonical_pair_id
from .stage5e3_artifacts import read, digest, freeze_json
from .taxonomy_packet import CHOICES


def complete(label, note):
    return bool(label) and (label != 'OTHER' or bool(note.strip()))


def safe_cell(value):
    text = str(value)
    return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else text


class TaxonomyReviewStore:
    max_request_bytes = 1_048_576
    max_note_length = 50_000

    def __init__(self, packet_path, state_dir, root):
        self.root = Path(root).resolve()
        self.packet = read(packet_path)
        if self.packet.get('schema') != 'taxonomy-audit-v1':
            raise ValueError('wrong taxonomy packet')
        self.packet_hash = digest(self.packet)
        self.pairs = {p['pair_id']: p for p in self.packet['pairs']}
        if len(self.pairs) != len(self.packet['pairs']):
            raise ValueError('duplicate pair')
        self.audio = {}
        for pair in self.pairs.values():
            a, b = pair['left'], pair['right']
            if pair['pair_id'] != canonical_pair_id(a['spotify_track_id'], b['spotify_track_id']):
                raise ValueError('pair identity mismatch')
            for track in (a, b):
                path = (self.root / track['retained_source_path']).resolve()
                if (self.root / '.research_audio').resolve() not in path.parents or not path.is_file() or file_sha256(path) != track['source_sha256']:
                    raise ValueError('local audio source integrity failed')
                mime = {'.webm': 'audio/webm', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.opus': 'audio/ogg', '.wav': 'audio/wav'}.get(path.suffix)
                if not mime:
                    raise ValueError('unsupported local media')
                self.audio[track['spotify_track_id']] = (path, mime)
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.review_path = self.state_dir / 'taxonomy-answers.csv'
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.state_dir / 'answers.sqlite', check_same_thread=False)
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS answers (pair_id TEXT PRIMARY KEY, label TEXT, note TEXT, revision INTEGER, updated_at TEXT)')
            self.db.execute('CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, pair_id TEXT, label TEXT, note TEXT, revision INTEGER, updated_at TEXT)')
            stored = self.db.execute("SELECT value FROM metadata WHERE key='packet_hash'").fetchone()
            if stored and stored[0] != self.packet_hash:
                raise ValueError('state belongs to a different frozen packet')
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('packet_hash', ?)", (self.packet_hash,))
            for pair_id in self.pairs:
                self.db.execute('INSERT OR IGNORE INTO answers VALUES (?, ?, ?, ?, ?)', (pair_id, '', '', 0, ''))
        self._export()

    def local_audio_for_request(self, spotify_id):
        return self.audio.get(spotify_id)

    def _answers(self):
        return {row[0]: {'label': row[1], 'note': row[2], 'revision': row[3], 'updated_at': row[4]}
                for row in self.db.execute('SELECT * FROM answers ORDER BY pair_id')}

    def _frozen(self):
        return (self.state_dir / 'labels_snapshot.json').exists()

    def session(self):
        with self.lock:
            answers = self._answers()
            pairs = []
            def public(track):
                return {'spotify_track_id': track['spotify_track_id'], 'title': track['title'],
                        'artists': track['artists'], 'audio_url': '/audio/track/' + track['spotify_track_id']}
            for pair in self.packet['pairs']:
                answer = answers[pair['pair_id']]
                pairs.append({'pair_id': pair['pair_id'], 'left': public(pair['left']), 'right': public(pair['right']),
                              'answer': answer, 'complete': complete(answer['label'], answer['note'])})
            return {'packet_hash': self.packet_hash, 'pairs': pairs,
                    'choices': [{'value': key, 'title': text[0], 'description': text[1]} for key, text in CHOICES.items()],
                    'completed': sum(p['complete'] for p in pairs), 'total': len(pairs), 'frozen': self._frozen()}

    def submit(self, stable_track_id, video_id, label, candidate_note='', track_note=''):
        if not isinstance(label, str) or label not in ('', *CHOICES) or not isinstance(candidate_note, str) or len(candidate_note) > self.max_note_length:
            raise Stage5B1AValidationError('Invalid taxonomy answer or note.')
        pair_id = canonical_pair_id(str(stable_track_id), str(video_id))
        if pair_id not in self.pairs:
            raise Stage5B1AValidationError('Unknown review pair.')
        try:
            expected_revision = int(track_note)
        except (ValueError, TypeError):
            raise Stage5B1AValidationError('Missing answer revision.') from None
        with self.lock:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                if self._frozen():
                    raise Stage5B1AValidationError('This review has been frozen.')
                current = self._answers()[pair_id]
                if current['label'] == label and current['note'] == candidate_note:
                    return {'ok': True, 'answer': current}
                if expected_revision != current['revision']:
                    raise Stage5B1AValidationError('Another tab changed this answer. Retry save to keep your draft, or Reload saved answer to discard it.')
                answer = {'label': label, 'note': candidate_note, 'revision': current['revision'] + 1,
                          'updated_at': datetime.now(timezone.utc).isoformat()}
                self.db.execute('UPDATE answers SET label=?, note=?, revision=?, updated_at=? WHERE pair_id=?',
                                (*answer.values(), pair_id))
                self.db.execute('INSERT INTO events(pair_id,label,note,revision,updated_at) VALUES (?,?,?,?,?)',
                                (pair_id, *answer.values()))
            self._export()
            return {'ok': True, 'answer': answer}

    def _export(self):
        answers = self._answers()
        output = io.StringIO(newline='')
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['packet_hash', 'pair_id', 'left_id', 'left_song', 'left_artists', 'right_id', 'right_song',
                         'right_artists', 'dominant_difference', 'note', 'revision', 'updated_at', 'complete'])
        for pair in self.packet['pairs']:
            a, b = pair['left'], pair['right']
            answer = answers[pair['pair_id']]
            values = [self.packet_hash, pair['pair_id'], a['spotify_track_id'], a['title'], '; '.join(a['artists']),
                      b['spotify_track_id'], b['title'], '; '.join(b['artists']), answer['label'], answer['note'],
                      answer['revision'], answer['updated_at'], complete(answer['label'], answer['note'])]
            writer.writerow([safe_cell(v) for v in values])
        temporary = self.review_path.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
        with temporary.open('w', encoding='utf-8-sig', newline='') as handle:
            handle.write(output.getvalue())
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.review_path)

    def freeze(self):
        with self.lock, self.db:
            self.db.execute('BEGIN IMMEDIATE')
            answers = self._answers()
            if not all(complete(a['label'], a['note']) for a in answers.values()):
                raise ValueError('All answers must be complete before freezing.')
            freeze_json(self.state_dir / 'labels_snapshot.json', {'packet_hash': self.packet_hash, 'answers': answers,
                         'semantic_tag': 'DOMINANT_PLAYLIST_MISMATCH_V1'})
            return {'status': 'FROZEN', 'path': str(self.state_dir / 'labels_snapshot.json')}

    def close(self):
        self.db.close()
