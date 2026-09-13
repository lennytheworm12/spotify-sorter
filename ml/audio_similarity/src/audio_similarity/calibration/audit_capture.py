"""Read-only evidence capture for the real-corpus audit; never constructs encoders."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3

import numpy as np

from .contracts import digest, file_hash, require
from .readiness import scan_batches
from ..stage5e1_cache import representation_identity
from ..stage5d0a_manifest import document_sha256


class Capture:
    def __init__(self, root):
        self.root = root.resolve()
        self.files = {}

    def text(self, relative):
        path = self.root / relative
        raw = path.read_bytes()
        entry = {'sha256': hashlib.sha256(raw).hexdigest(), 'text': raw.decode()}
        require(relative not in self.files or self.files[relative] == entry,
                f'input changed during capture: {relative}')
        self.files[relative] = entry
        return entry['text']

    def read(self, relative):
        return json.loads(self.text(relative))


def read_db(path):
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    connection.execute('BEGIN')
    return connection


def vector_valid(row, dimension=512):
    blob = row['embedding']
    if blob is None or hashlib.sha256(blob).hexdigest() != row['embedding_sha256']:
        return False
    values = np.frombuffer(blob, dtype='<f4')
    return bool(values.shape == (dimension,) and np.isfinite(values).all()
                and np.isclose(np.linalg.norm(values), 1., atol=1e-5))


def method_c_evidence(cap, source_hashes):
    """Validate exact historical C identities and all views, without reading scores."""
    base = 'reports/stage5e1_four_arm_retrieval/'
    config = cap.read(base + 'experiment_config.json')
    plans = cap.read(base + 'sampling_plans.json')
    manifest = cap.read(base + 'corpus_manifest.json')
    config_hash = cap.files[base + 'experiment_config.json']['sha256']
    require(plans['experiment_config_sha256'] == config_hash, 'C config/plan mismatch')
    require(plans['corpus_manifest_sha256'] == cap.files[base + 'corpus_manifest.json']['sha256'],
            'C corpus/plan mismatch')
    tracks = {t['spotify_track_id']: t for t in manifest['tracks']}
    plan_by_id = {t['spotify_track_id']: t for t in plans['tracks']}
    output = []
    path = cap.root / 'artifacts/stage5e1_four_arm_retrieval/representations.sqlite'
    db = read_db(path)
    try:
        for row in db.execute("SELECT * FROM vectors WHERE arm='C' ORDER BY spotify_track_id"):
            if row['source_sha256'] not in source_hashes:
                continue
            p = plan_by_id[row['spotify_track_id']]
            plan_hash = p['plan']['sampling_plan_sha256']
            plan_payload = {k: v for k, v in p['plan'].items() if k != 'sampling_plan_sha256'}
            require(hashlib.sha256(json.dumps(plan_payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    == plan_hash, 'C embedded sampling plan hash mismatch')
            identity = representation_identity(spotify_track_id=row['spotify_track_id'], arm='C',
                source_sha256=row['source_sha256'], config_sha256=config_hash,
                sampling_plan_sha256=plan_hash,
                checkpoint_sha256=config['arms']['C']['checkpoint_sha256'])
            views = db.execute('SELECT * FROM views WHERE representation_identity=? ORDER BY view_index',
                               (identity,)).fetchall()
            chunks = p['plan']['full_song_chunks']
            ok = (row['representation_identity'] == identity and row['status'] == 'SUCCESS'
                  and row['config_sha256'] == config_hash and row['sampling_plan_sha256'] == plan_hash
                  and row['checkpoint_sha256'] == config['arms']['C']['checkpoint_sha256']
                  and p['source_sha256'] == row['source_sha256'] == tracks[row['spotify_track_id']]['source_sha256']
                  and vector_valid(row) and len(views) == row['view_count'] == len(chunks))
            for i, (view, chunk) in enumerate(zip(views, chunks)):
                ok = ok and (view['view_index'] == i and view['view_kind'] == 'FULL_SONG_CHUNK'
                    and view['start_unit'] == chunk['start_sample'] and view['end_unit'] == chunk['end_sample']
                    and vector_valid(view))
            if ok:
                mean = np.mean([np.frombuffer(v['embedding'], dtype='<f4') for v in views], axis=0)
                mean /= np.linalg.norm(mean)
                ok = bool(np.allclose(mean, np.frombuffer(row['embedding'], dtype='<f4'), atol=1e-6))
            output.append({k: row[k] for k in ('spotify_track_id', 'source_sha256', 'representation_identity',
                'config_sha256', 'sampling_plan_sha256', 'checkpoint_sha256', 'embedding_sha256', 'view_count')} |
                {'verified': bool(ok), 'view_hashes': [v['embedding_sha256'] for v in views]})
    finally:
        db.close()
    return output


def profile_evidence(cap, source_hashes):
    base = 'reports/gemini_style_pilot/frozen100_free_genre_v1/'
    execution = cap.read(base + 'execution_manifest.json')
    hashes = cap.read(base + 'artifact_manifest.json')['files']
    require(cap.files[base + 'execution_manifest.json']['sha256'] == hashes['execution_manifest.json'],
            'Gemini execution hash mismatch')
    mapped_base = 'reports/genre_registry_review/v1/frozen100/'
    mapped_hashes = cap.read(mapped_base + 'artifact_manifest.json')['files']
    mapped = cap.read(mapped_base + 'comparison.json')
    require(cap.files[mapped_base + 'comparison.json']['sha256'] == mapped_hashes['comparison.json'],
            'mapper comparison hash mismatch')
    provenance = cap.read(mapped_base + 'provenance.json')
    require(cap.files[mapped_base + 'provenance.json']['sha256'] == mapped_hashes['provenance.json'],
            'mapper provenance hash mismatch')
    for path, expected in provenance['inputs'].items():
        cap.text(path)
        require(cap.files[path]['sha256'] == expected, f'mapper input mismatch: {path}')
    by_id = {t['spotify_track_id']: t for t in mapped['tracks']}
    output = []
    for t in execution['tracks']:
        if t['source_sha256'] not in source_hashes:
            continue
        relative = 'profiles/' + t['pilot_id'] + '.json'
        profile = cap.read(base + relative)
        prepared = t['prepared']
        prepared_path = Path(prepared['conversion_command'][-1])
        prepared_ok = prepared_path.is_file() and file_hash(prepared_path) == prepared['prepared_sha256']
        ok = (cap.files[base + relative]['sha256'] == hashes[relative]
              and profile['spotify_track_id'] == t['spotify_track_id']
              and t['source_sha256'] == prepared['source_sha256']
              and prepared['full_recording_preserved'] and prepared_ok)
        mapping_ok = ok and t['spotify_track_id'] in by_id and by_id[t['spotify_track_id']]['raw_profile'] == profile['profile']
        output.append({'spotify_track_id': t['spotify_track_id'], 'source_sha256': t['source_sha256'],
            'profile_sha256': cap.files[base + relative]['sha256'], 'prepared_sha256': prepared['prepared_sha256'],
            'model_id': execution['model_id'], 'generation_config_hash': digest(execution['generation_config']),
            'gemini_verified': bool(ok), 'mapped_verified': bool(mapping_ok),
            'mapping_row_sha256': digest(by_id[t['spotify_track_id']]) if mapping_ok else None})
    return output


def capture(root):
    cap = Capture(root)
    runs = {}
    for name in ('example_playlist_batches_v1', 'example_playlist_batches_v2'):
        base = '.research_audio/' + name + '/'
        m = cap.read(base + 'manifest.json')
        require(document_sha256(m) == cap.read(base + 'manifest_hash.json')['sha256'], 'queue manifest hash mismatch')
        states, batch_status = {}, {}
        for b in m['batches']:
            path = base + f"batch_{b['batch_number']:04d}/state.json"
            if (root / path).exists():
                state = cap.read(path)
                states.update(state['tracks'])
                batch_status[str(b['batch_number'])] = state['status']
        runs[name] = {'manifest': m, 'states': states, 'batch_status': batch_status}
    # The initial run must be stable. The extension is metadata-only, never a fitting input.
    require(all(s == 'FINISHED' for s in runs['example_playlist_batches_v1']['batch_status'].values())
            and len(runs['example_playlist_batches_v1']['batch_status']) == len(runs['example_playlist_batches_v1']['manifest']['batches']),
            'initial acquisition still changing; audit a completed initial run')
    inventory = scan_batches(root, (root / '.research_audio/example_playlist_batches_v1',))
    for item in inventory['input_snapshots']:
        cap.text(item['path'])
        require(cap.files[item['path']]['sha256'] == item['sha256'], 'initial capture changed')
    intakes = {}
    for version in ('589be5ae1ef5', '15127df33fca'):
        base = '.research_audio/playlist_reference_intake/' + version + '/'
        intake = cap.read(base + 'intake.private.json')
        for p in intake['playlists']:
            text = cap.text(base + 'vault_sources/' + Path(p['vault_path']).name)
            require(hashlib.sha256(text.encode()).hexdigest() == p['sha256'], 'source note hash mismatch')
        intakes[version] = intake
    source_rows = []
    for key, state in sorted(runs['example_playlist_batches_v1']['states'].items()):
        result = state.get('result', {})
        path = result.get('retained_relative_path')
        if not path or state['state'] != 'COMPLETE':
            continue
        full_path = root / '.research_audio' / path
        actual = file_hash(full_path)
        provenance = cap.read(str(full_path.parent.relative_to(root) / 'provenance.json'))
        source_rows.append({'request_id': key, 'source_path': str(full_path.relative_to(root)),
            'actual_source_sha256': actual, 'provenance': provenance,
            'result': result, 'source_bytes_verified': actual == result['source_sha256'] == provenance['source_sha256']})
    hashes = {r['actual_source_sha256'] for r in source_rows if r['source_bytes_verified']}
    c = method_c_evidence(cap, hashes)
    profiles = profile_evidence(cap, hashes)
    corrections = cap.read('.research_audio/source_corrections/problem_cases_v1/published_corrections.json')
    quarantines = cap.read('.research_audio/source_corrections/problem_cases_v1/quarantines.json')
    for correction in corrections['corrections']:
        cap.read(correction['record_path'])
        require(cap.files[correction['record_path']]['sha256'] == correction['record_sha256'], 'correction record hash mismatch')
    mismatches = []
    bad_ids = {r['recording_id'] for r in inventory['recordings'] if r['errors']}
    for row in source_rows:
        if row['request_id'] not in bad_ids:
            continue
        stable = row['result']['representation']['stable_track_id']
        alternatives = []
        for path in sorted((root / 'artifacts').rglob('representations.sqlite')):
            db = read_db(path)
            try:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'pooled' in tables:
                    for value in db.execute('SELECT * FROM pooled WHERE stable_track_id=?', (stable,)):
                        alternatives.append({k: value[k] for k in ('encoder_id', 'source_audio_sha256', 'embedding_sha256', 'status')} |
                            {'cache_path': str(path.relative_to(root)), 'vector_valid': vector_valid(value),
                             'matches_retained_hash': value['source_audio_sha256'] == row['actual_source_sha256']})
                if 'vectors' in tables:
                    for value in db.execute("SELECT * FROM vectors WHERE spotify_track_id=? AND arm IN ('A','C','MUQ')", (stable,)):
                        alternatives.append({k: value[k] for k in ('arm', 'source_sha256', 'embedding_sha256', 'status')} |
                            {'cache_path': str(path.relative_to(root)), 'vector_valid': vector_valid(value),
                             'matches_retained_hash': value['source_sha256'] == row['actual_source_sha256']})
            finally:
                db.close()
        mismatches.append({'request_id': row['request_id'], 'stable_track_id': stable,
            'actual_source_sha256': row['actual_source_sha256'],
            'linked_feature_source_sha256': row['result']['representation']['source_audio_sha256'],
            'alternatives': alternatives, 'resolution': 'NO_ARTIFACT_SELECTED_OR_OVERWRITTEN'})
    # Do not call a live extension state immutable; only completed initial evidence is protected.
    protected = {p: item['sha256'] for p, item in cap.files.items()
                 if not p.startswith('.research_audio/example_playlist_batches_v2/')}
    changed = [p for p, sha in protected.items() if file_hash(root / p) != sha]
    changed_sources = [r['request_id'] for r in source_rows
                       if file_hash(root / r['source_path']) != r['actual_source_sha256']]
    require(not changed and not changed_sources, 'completed input changed during audit')
    return {'schema': 'real-calibration-audit-capture-v1', 'runs': runs, 'intakes': intakes,
        'inventory': inventory, 'sources': source_rows, 'method_c': c, 'profiles': profiles,
        'mismatches': mismatches, 'corrections': corrections, 'quarantines': quarantines,
        'files': cap.files, 'protected_input_check': {'status': 'PASS', 'text_files': len(protected),
            'retained_sources': len(source_rows), 'changed': changed, 'changed_sources': changed_sources},
        'semantics': 'initial finished queues verified stable; extension state snapshot only; SQLite read-only transactions; no inference or score inspection'}
