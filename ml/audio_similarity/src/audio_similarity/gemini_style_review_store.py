"""Durable owner listening notes, separate from frozen Gemini outputs and ratings."""
import csv
import io
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5e3_artifacts import digest, freeze_json, read, verify_hashes
from .taxonomy_review_store import safe_cell

REPORT = Path('reports/gemini_style_pilot/v1/duration_v3')
RUN = Path('.research_audio/gemini_style_pilot/style-pilot-v1-duration-v3')
STATE = Path('artifacts/gemini_style_pilot_review/duration_v3')
INDEPENDENT = ('owner_recording_identity_ok', 'owner_family_or_style_words',
               'owner_vocals_and_arrangement', 'owner_section_changes')
COMPARISON = ('description_verdict', 'acceptable_alternative_labels',
              'model_description_or_timestamp_issues', 'model_certainty_appropriate', 'notes')
FIELDS = INDEPENDENT + COMPARISON
CHOICES = {
    'owner_recording_identity_ok': ('', 'yes', 'not_sure', 'different_recording'),
    'description_verdict': ('', 'fits', 'partly', 'does_not_fit', 'not_sure'),
    'model_certainty_appropriate': ('', 'appropriate', 'too_certain', 'too_tentative', 'not_sure'),
}


def listening_complete(answer):
    return bool(answer['owner_recording_identity_ok'] and answer['owner_family_or_style_words'].strip())


def comparison_complete(answer):
    return bool(answer['description_verdict'] and answer['model_certainty_appropriate'])


def load_packet(root):
    report = root / REPORT
    verify_hashes(report, read(report / 'artifact_manifest.json')['files'])
    manifest = read(report / 'execution_manifest.json')
    tracks = []
    for t in manifest['tracks']:
        prepared = t['prepared']
        tracks.append({'pilot_id': t['pilot_id'], 'neutral_id': t['neutral_id'],
            'spotify_track_id': t['spotify_track_id'], 'title': t['catalog_title'],
            'artists': t['catalog_artists'], 'duration_seconds': prepared['duration_seconds'],
            'audio_path': str(RUN / 'prepared' / prepared['prepared_filename']),
            'audio_sha256': prepared['prepared_sha256'],
            'profile': read(report / 'profiles' / f'{t["pilot_id"]}.json'),
            'repeat': read(report / 'repeats' / f'{t["pilot_id"]}.json') if (report / 'repeats' / f'{t["pilot_id"]}.json').exists() else None})
    if len(tracks) != 16:
        raise ValueError('The complete frozen 16-track pilot is required')
    return {'schema': 'gemini-owner-review-v1', 'source_artifact_manifest_sha256': file_sha256(report / 'artifact_manifest.json'),
            'profiles_frozen_sha256': file_sha256(report / 'profiles_frozen.json'), 'tracks': tracks}


class GeminiStyleReviewStore:
    max_request_bytes = 8_388_608
    max_note_length = 250_000

    def __init__(self, root, state_dir, *, packet=None):
        self.root, self.state_dir = Path(root).resolve(), Path(state_dir).resolve()
        if self.state_dir == self.root or any(p == self.state_dir or p in self.state_dir.parents
                                              for p in (self.root / 'reports', self.root / '.research_audio')):
            raise ValueError('Review state must not target frozen research inputs')
        self.packet = packet if packet is not None else load_packet(self.root)
        if self.packet.get('schema') != 'gemini-owner-review-v1':
            raise ValueError('Wrong review packet')
        self.packet_hash = digest(self.packet)
        self.tracks = {t['pilot_id']: t for t in self.packet['tracks']}
        if not self.tracks or len(self.tracks) != len(self.packet['tracks']):
            raise ValueError('Duplicate or empty track inventory')
        self.audio = {}
        for t in self.tracks.values():
            path = (self.root / t['audio_path']).resolve()
            if self.root / '.research_audio' not in path.parents or file_sha256(path) != t['audio_sha256']:
                raise ValueError('Prepared audio integrity failed')
            self.audio[t['pilot_id']] = (path, 'audio/flac')
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.review_path = self.state_dir / 'owner-review-answers.csv'
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.state_dir / 'answers.sqlite', check_same_thread=False)
        try:
            self._initialize()
            self._export()
        except Exception:
            self.db.close()
            raise

    def _initialize(self):
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS answers (pilot_id TEXT PRIMARY KEY, answer TEXT, revision INTEGER, updated_at TEXT)')
            self.db.execute('CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, pilot_id TEXT, answer TEXT, revision INTEGER, updated_at TEXT, phase TEXT)')
            saved = self.db.execute("SELECT value FROM metadata WHERE key='packet_hash'").fetchone()
            if saved and saved[0] != self.packet_hash:
                raise ValueError('State belongs to another frozen pilot packet')
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('packet_hash', ?)", (self.packet_hash,))
            for pid in self.tracks:
                self.db.execute('INSERT OR IGNORE INTO answers VALUES (?, ?, 0, ?)', (pid, json.dumps(dict.fromkeys(FIELDS, '')), ''))

    def local_audio_for_request(self, pilot_id):
        return self.audio.get(pilot_id)

    def _answers(self):
        return {pid: {'fields': json.loads(answer), 'revision': revision, 'updated_at': timestamp}
                for pid, answer, revision, timestamp in self.db.execute('SELECT * FROM answers ORDER BY pilot_id')}

    def _snapshot(self, name):
        row = self.db.execute('SELECT value FROM metadata WHERE key=?', (name,)).fetchone()
        return json.loads(row[0]) if row else None

    def _phase(self):
        return 'complete' if self._snapshot('owner_snapshot') else 'compare' if self._snapshot('independent_snapshot') else 'listen'

    def session(self):
        with self.lock:
            answers, phase = self._answers(), self._phase()
            tracks = []
            for pid, t in self.tracks.items():
                answer = answers[pid]
                tracks.append({k: t[k] for k in ('pilot_id', 'neutral_id', 'spotify_track_id', 'title', 'artists', 'duration_seconds')} |
                              {'audio_url': '/audio/track/' + pid, 'answer': answer,
                               'listening_complete': listening_complete(answer['fields']),
                               'comparison_complete': comparison_complete(answer['fields'])})
            return {'packet_hash': self.packet_hash, 'phase': phase, 'tracks': tracks, 'total': len(tracks),
                    'listening_completed': sum(t['listening_complete'] for t in tracks),
                    'comparison_completed': sum(t['comparison_complete'] for t in tracks),
                    'field_order': list(FIELDS), 'max_note_length': self.max_note_length}

    def profile(self, pid):
        with self.lock:
            if self._phase() == 'listen':
                raise Stage5B1AValidationError('Finish and save the listening pass before viewing Gemini descriptions.')
            if pid not in self.tracks:
                raise Stage5B1AValidationError('Unknown track')
            t = self.tracks[pid]
            return {'pilot_id': pid, 'primary': t['profile'], 'repeat': t['repeat']}

    def save(self, pid, fields, revision):
        if not isinstance(pid, str) or pid not in self.tracks or not isinstance(fields, dict) or set(fields) != set(FIELDS):
            raise Stage5B1AValidationError('Unknown track or answer fields.')
        if type(revision) is not int or revision < 0:
            raise Stage5B1AValidationError('Missing answer revision.')
        for key, value in fields.items():
            if not isinstance(value, str) or len(value) > self.max_note_length or (key in CHOICES and value not in CHOICES[key]):
                raise Stage5B1AValidationError('Invalid answer or note exceeds 250,000 characters; nothing was truncated.')
        with self.lock:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                phase = self._phase()
                current = self._answers()[pid]
                if phase == 'complete':
                    raise Stage5B1AValidationError('The completed review is frozen. Export remains available.')
                if phase == 'listen' and any(fields[k] for k in COMPARISON):
                    raise Stage5B1AValidationError('Gemini comparison answers are unavailable during the listening pass.')
                if phase == 'compare' and any(fields[k] != current['fields'][k] for k in INDEPENDENT):
                    raise Stage5B1AValidationError('Your independent listening notes are frozen; add corrections in comparison notes.')
                if fields == current['fields']:
                    self._export()
                    return {'ok': True, 'answer': current, 'phase': phase}
                if revision != current['revision']:
                    raise Stage5B1AValidationError('Another tab changed this answer. Retry save to keep your draft, or Reload saved answer to discard it.')
                answer = {'fields': fields, 'revision': revision + 1, 'updated_at': datetime.now(timezone.utc).isoformat()}
                self.db.execute('UPDATE answers SET answer=?, revision=?, updated_at=? WHERE pilot_id=?',
                                (json.dumps(fields, ensure_ascii=False), answer['revision'], answer['updated_at'], pid))
                self.db.execute('INSERT INTO events(pilot_id,answer,revision,updated_at,phase) VALUES (?,?,?,?,?)',
                                (pid, json.dumps(fields, ensure_ascii=False), answer['revision'], answer['updated_at'], phase))
            self._export()
            return {'ok': True, 'answer': answer, 'phase': phase}

    def advance(self, expected_revisions):
        """An explicit global transition freezes independent notes before disclosure."""
        if not isinstance(expected_revisions, dict) or any(type(v) is not int for v in expected_revisions.values()):
            raise Stage5B1AValidationError('Expected saved answer revisions.')
        with self.lock:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                phase, answers = self._phase(), self._answers()
                if expected_revisions != {k: v['revision'] for k, v in answers.items()}:
                    raise Stage5B1AValidationError('Answers changed in another tab. Reload before continuing.')
                if phase == 'complete':
                    self._export()
                    return {'ok': True, 'phase': phase}
                predicate = listening_complete if phase == 'listen' else comparison_complete
                if not all(predicate(a['fields']) for a in answers.values()):
                    raise Stage5B1AValidationError('Complete every track in this pass before continuing. “Not sure” is a valid answer.')
                name = 'independent_snapshot' if phase == 'listen' else 'owner_snapshot'
                snapshot = {'packet_hash': self.packet_hash, 'semantic_tag': 'OWNER_AUDIO_STYLE_REVIEW_V1',
                            'phase': phase, 'answers': answers, 'created_at': datetime.now(timezone.utc).isoformat(),
                            'new_playlist_ratings': 0, 'model_profiles_modified': False}
                if phase == 'compare':
                    snapshot['independent_snapshot_hash'] = digest(self._snapshot('independent_snapshot'))
                self.db.execute('INSERT INTO metadata VALUES (?, ?)', (name, json.dumps(snapshot, ensure_ascii=False)))
            self._export()
            return {'ok': True, 'phase': self._phase()}

    def _export(self):
        """SQLite is authoritative; snapshots and CSV regenerate after interruption."""
        output = io.StringIO(newline='')
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['packet_hash', 'pilot_id', 'neutral_id', 'spotify_track_id', 'song', 'duration_seconds',
                         *FIELDS, 'revision', 'updated_at', 'phase', 'save_status'])
        answers, phase = self._answers(), self._phase()
        for pid, t in self.tracks.items():
            a = answers[pid]
            row = [self.packet_hash, pid, t['neutral_id'], t['spotify_track_id'], t['title'] + ' — ' + ', '.join(t['artists']),
                   t['duration_seconds'], *[a['fields'][k] for k in FIELDS], a['revision'], a['updated_at'], phase, 'SAVED']
            writer.writerow([safe_cell(v) for v in row])
        temporary = self.review_path.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
        with temporary.open('w', encoding='utf-8-sig', newline='') as handle:
            handle.write(output.getvalue())
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.review_path)
        for name in ('independent_snapshot', 'owner_snapshot'):
            snapshot = self._snapshot(name)
            if snapshot:
                freeze_json(self.state_dir / f'{name}.json', snapshot)

    def close(self):
        self.db.close()
