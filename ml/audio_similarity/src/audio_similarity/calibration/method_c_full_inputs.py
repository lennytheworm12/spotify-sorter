"""Freeze the original complete playlist corpus without model-based selection."""
import json
import os

from .audit_capture import Capture, method_c_evidence, read_db, vector_valid
from .contracts import digest, file_hash, freeze_json, require
from .development_inputs import AUDIT, RUN as DEVELOPMENT

RUN = os.environ.get('METHOD_C_RUN_DIRECTORY', '.research_audio/playlist_calibration_method_c_full_v1')
CHECKPOINT = 'models/music_audioset_epoch_15_esc_90.14.pt'
CHECKPOINT_SHA = 'fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd'


def read(path):
    return json.loads(path.read_text())


def prepare(root):
    run = root / RUN
    captured = read(root / AUDIT / 'capture.private.json')
    audited = read(root / AUDIT / 'audit.private.json')
    batch = root / '.research_audio/example_playlist_batches_v1'
    manifest = read(batch / 'manifest.json')
    require(manifest == captured['runs']['example_playlist_batches_v1']['manifest'], 'original corpus manifest changed')
    states = {}
    protected = {str((batch/'manifest.json').relative_to(root)): file_hash(batch/'manifest.json')}
    for b in manifest['batches']:
        path = batch / f"batch_{b['batch_number']:04d}/state.json"
        state = read(path)
        require(state['status'] == 'FINISHED', 'original source acquisition still active')
        require(state['tracks'] == {k: captured['runs']['example_playlist_batches_v1']['states'][k] for k in state['tracks']}, 'audited original state changed')
        states.update(state['tracks'])
        protected[str(path.relative_to(root))] = file_hash(path)
    sources = {s['request_id']: s for s in captured['sources']}
    tracks = {t['local_recording_id']: t for b in manifest['batches'] for t in b['tracks']}
    require(set(states) == set(tracks), 'incomplete source-state population')
    corrections_path = '.research_audio/source_corrections/problem_cases_v1/published_corrections.json'
    quarantine_path = '.research_audio/source_corrections/problem_cases_v1/quarantines.json'
    require(read(root/corrections_path) == captured['corrections'], 'source correction overlay changed; re-audit required')
    require(read(root/quarantine_path) == captured['quarantines'], 'quarantine overlay changed; re-audit required')
    protected.update({p: file_hash(root/p) for p in (corrections_path, quarantine_path)})
    quarantined = {t['spotify_track_id'] for t in captured['quarantines']['tracks']}
    records, requests = {}, []
    for key, t in sorted(tracks.items()):
        status = states[key]['state']
        request = {'request_id': key, 'title': t['title'], 'artists': t['artists'], 'memberships': t['memberships'], 'source_state': status}
        if key not in sources:
            requests.append(request | {'recording_id': None, 'status': 'SOURCE_UNAVAILABLE', 'reason': status})
            continue
        s = sources[key]
        sid = s['result']['representation']['stable_track_id']
        p = s['provenance']
        source = root / s['source_path']
        provenance = source.parent / 'provenance.json'
        errors = []
        if file_hash(source) != s['actual_source_sha256'] or not s['source_bytes_verified']:
            errors.append('AUDIO_HASH_MISMATCH')
        if read(provenance) != p or p['source_sha256'] != s['actual_source_sha256']:
            errors.append('PROVENANCE_HASH_MISMATCH')
        if not p.get('full_decode_validated'):
            errors.append('SOURCE_NOT_FULLY_VALIDATED')
        if (p.get('spotify_track_id') or p.get('local_recording_id')) != sid:
            errors.append('AMBIGUOUS_RECORDING_IDENTITY')
        if sid in quarantined:
            errors.append('SOURCE_QUARANTINED')
        correction = [c for c in captured['corrections']['corrections'] if c.get('spotify_track_id') == sid]
        for c in correction:
            record_path = root / c['record_path']
            require(file_hash(record_path) == c['record_sha256'], 'correction record changed')
            protected[c['record_path']] = c['record_sha256']
            corrected = read(record_path)['result']['source_sha256']
            if s['actual_source_sha256'] != corrected:
                errors.append('SOURCE_CORRECTION_CONFLICT')
        if s['actual_source_sha256'] in {c['expected_old_source_sha256'] for c in captured['corrections']['corrections']}:
            errors.append('SUPERSEDED_SOURCE')
        row = {'recording_id': sid, 'source_path': s['source_path'], 'audio_sha256': s['actual_source_sha256'],
            'provenance_path': str(provenance.relative_to(root)), 'provenance_sha256': file_hash(provenance),
            'prior_representation': s['result']['representation'], 'duration_seconds': p.get('duration_seconds'),
            'identity_status': 'HASH_LINKED_AUTO_SELECTED_NOT_OWNER_ADJUDICATED', 'errors': errors}
        if sid in records:
            require(records[sid]['audio_sha256'] == row['audio_sha256'], 'ambiguous recording ID maps to multiple source hashes')
            records[sid]['errors'] = sorted(set(records[sid]['errors'] + errors))
        else:
            records[sid] = row
        requests.append(request | {'recording_id': sid, 'status': 'BLOCKED' if errors else 'ELIGIBLE', 'errors': errors})
        protected[str(provenance.relative_to(root))] = file_hash(provenance)
    value = {'schema': 'complete-original-playlist-method-c-corpus-v1', 'scope': 'original 28 source playlists; extension explicitly separate',
        'source_manifest_sha256': file_hash(batch/'manifest.json'), 'audit_sha256': file_hash(root/AUDIT/'audit.private.json'),
        'requests': requests, 'recordings': [records[k] for k in sorted(records)],
        'source_playlists': audited['playlists'], 'protected_files': protected,
        'extension': {'included': False, 'manifest_sha256': file_hash(root/'.research_audio/example_playlist_batches_v2/manifest.json'),
            'reason': 'Separate still-processing extension, not the frozen original calibration corpus.'},
        'no_downloads': True, 'no_tuning': True, 'source_use_status': 'PENDING_OWNER_AUTHORIZED_PERSONAL_FEATURE_PRECOMPUTATION'}
    freeze_json(run/'corpus.json', value)
    return value


def reusable(root, corpus):
    """Accept only independently verified exact-ID, exact-source Method C."""
    dev = root / DEVELOPMENT
    original = read(dev/'artifact_manifest.private.json')['files']
    config = read(dev/'audio_config.json')
    require(config['models']['clap']['sha256'] == CHECKPOINT_SHA, 'development CLAP checkpoint differs')
    for name in ('audio_config.json', 'dependency_receipt.json'):
        require(file_hash(dev/name) == original[name], 'historical development cache provenance changed')
    dependencies = read(dev/'dependency_receipt.json')['implementation_hashes']
    for name, expected in dependencies.items():
        require(file_hash(root/name) == expected, 'historical extraction dependency changed')
    indexed = {}
    for path in sorted((dev/'audio').glob('*.json')):
        name = str(path.relative_to(dev))
        require(file_hash(path) == original[name], 'development feature hash changed')
        row = read(path)
        require(row['configuration_sha256'] == digest(config), 'development config linkage changed')
        indexed[row['stable_track_id'], row['source_sha256']] = (path, row)
    cap = Capture(root)
    e1 = { (r['spotify_track_id'], r['source_sha256']): r for r in method_c_evidence(cap, {r['audio_sha256'] for r in corpus['recordings']}) }
    db = read_db(root/'artifacts/stage5e1_four_arm_retrieval/representations.sqlite')
    output = {}
    try:
        for r in corpus['recordings']:
            key = r['recording_id'], r['audio_sha256']
            if key in indexed:
                path, data = indexed[key]
                views = data['views'].get('C_method_c')
                if views is None:
                    require(key in e1 and e1[key]['verified'], 'reused development C lacks verified historical views')
                output[r['recording_id']] = {'kind': 'DEVELOPMENT_CACHE', 'path': str(path.relative_to(root)),
                    'sha256': file_hash(path), 'vector': data['C_method_c'], 'views': views,
                    'origin': data['origins']['C_method_c']}
            elif key in e1:
                proof = e1[key]
                require(proof['verified'] and proof['checkpoint_sha256'] == CHECKPOINT_SHA, 'incompatible Method C artifact')
                row = db.execute('SELECT * FROM vectors WHERE representation_identity=?', (proof['representation_identity'],)).fetchone()
                require(vector_valid(row), 'historical Method C blob changed')
                import numpy as np
                output[r['recording_id']] = {'kind': 'STAGE5E1_CACHE', 'proof': proof,
                    'vector': np.frombuffer(row['embedding'], dtype='<f4').tolist(), 'views': None}
    finally:
        db.close()
    continuation = root/RUN/'continuation_imports.json'
    if continuation.exists():
        from .method_c_continuation import verified_imports
        output.update(verified_imports(root, corpus, read(continuation)))
    freeze_json(root/RUN/'reuse_manifest.json', output)
    return output
