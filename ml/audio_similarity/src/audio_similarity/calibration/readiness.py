"""Read-only acquisition/cache census. Completion markers are not feature proof."""
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sqlite3

import numpy as np

from .contracts import digest, file_hash, freeze_json, require
from ..stage5a_contract import load_contract


def summarize_inventory(inventory):
    rows = inventory['recordings']
    n = len(rows)
    counts = {key: sum(row[key] for row in rows) for key in
              ('processed', 'centered30', 'method_c', 'muq', 'canonical')}
    errors = [error for row in rows for error in row['errors']]
    return {'schema': 'playlist-calibration-readiness-v1', 'inventory_sha256': digest(inventory),
            'total_referenced_recordings': n, 'identity_unit': 'distinct frozen recording requests; aliases not globally adjudicated',
            'processed_recordings': counts['processed'],
            'verified_centered30': counts['centered30'], 'missing_centered30': n - counts['centered30'],
            'verified_method_c': counts['method_c'], 'missing_method_c': n - counts['method_c'],
            'verified_muq': counts['muq'], 'missing_muq': n - counts['muq'],
            'verified_gemini_canonical': counts['canonical'], 'missing_gemini_canonical': n - counts['canonical'],
            'hash_mismatches': sum('hash mismatch' in e for e in errors), 'validation_errors': errors,
            'queue_states': dict(Counter(row['queue_state'] for row in rows)),
            'source_readiness': 'SOURCE_NOT_READY', 'split_readiness': 'SOURCE_NOT_READY',
            'feature_readiness': 'WAITING_FOR_FEATURES' if any(n != counts[k] for k in ('centered30', 'method_c', 'muq', 'canonical')) or errors else 'READY',
            'ranking_calibration_readiness': 'SOURCE_NOT_READY',
            'output_descriptive_readiness': 'NOT_CALIBRATED',
            'suitability_calibration_readiness': 'LABELS_REQUIRED', 'lockbox_readiness': 'SOURCE_NOT_READY',
            'blocked_on': ['source/curator and recording-version adjudication; frozen split/catalog/masks absent',
                           'Method C and Gemini/canonical artifacts not enrolled in a provenance-aligned calibration bundle',
                           'ranker representation/weights not selected or frozen',
                           'candidate-playlist suitability labels and independent output/policy/final roles absent'],
            'scope': 'read-only snapshot, not a musical result; missing means not verified for this corpus/source identity'}


def scan_batches(root: Path, runs: tuple[Path, ...]):
    contract = load_contract(root / 'reports/holistic_stage4a_dual/audio_representation_v1.json')
    inputs, tracks, states = [], {}, {}

    def read(path):
        raw = path.read_bytes()
        inputs.append({'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(raw).hexdigest()})
        return json.loads(raw)

    for run in runs:
        manifest = read(run / 'manifest.json')
        # Existing batch manifests use pretty-JSON document hashing, not this package's digest.
        from ..stage5d0a_manifest import document_sha256
        require(document_sha256(manifest) == read(run / 'manifest_hash.json')['sha256'], 'batch manifest hash mismatch')
        for batch in manifest['batches']:
            for row in batch['tracks']:
                key = row.get('local_recording_id') or row['spotify_track_id']
                if key in tracks:
                    require(tracks[key] == row, 'conflicting frozen request identity')
                tracks[key] = row
            state_path = run / f"batch_{batch['batch_number']:04d}" / 'state.json'
            if state_path.exists():
                states.update(read(state_path)['tracks'])
    rows = []
    source_hashes = {}
    connections = {}
    with ExitStack() as stack:
        for key in sorted(tracks):
            state = states.get(key, {})
            result = state.get('result', {})
            row = {'recording_id': key, 'queue_state': state.get('state', 'NOT_STARTED'),
                   'processed': state.get('state') == 'COMPLETE', 'centered30': False,
                   'method_c': False, 'muq': False, 'canonical': False, 'errors': []}
            representation = result.get('representation')
            if representation and result.get('retained_relative_path'):
                source = (root / '.research_audio' / result['retained_relative_path']).resolve()
                cache = (root / representation['cache_path']).resolve()
                try:
                    require(source.is_relative_to((root / '.research_audio').resolve()), 'source path escapes root')
                    require(cache.is_relative_to((root / 'artifacts').resolve()), 'cache path escapes root')
                    require(source.is_file(), 'retained source missing')
                    provenance = read(source.parent / 'provenance.json')
                    require(provenance.get('full_decode_validated') is True, 'retained source not decode-validated')
                    require((provenance.get('local_recording_id') or provenance.get('spotify_track_id')) == representation['stable_track_id'], 'retained recording identity mismatch')
                    if source not in source_hashes:
                        source_hashes[source] = file_hash(source)
                    source_hash = source_hashes[source]
                    require(source_hash == result['source_sha256'] == representation['source_audio_sha256'] == provenance['source_sha256'], 'source hash mismatch')
                    require(representation['vector_contract_sha256'] == contract.vector_contract_sha256, 'representation contract hash mismatch')
                    if cache not in connections:
                        connection = sqlite3.connect(cache.as_uri() + '?mode=ro', uri=True)
                        stack.callback(connection.close)
                        connection.row_factory = sqlite3.Row
                        connection.execute('PRAGMA query_only=ON')
                        connection.execute('BEGIN')  # Consistent reader; never instantiate write-capable Stage5ACache.
                        connections[cache] = connection
                    db = connections[cache]
                    for i, encoder in enumerate(contract.encoders):
                        identity = contract.encoder_analysis_identity(corpus=representation['corpus'],
                            corpus_version=representation['corpus_version'], stable_track_id=representation['stable_track_id'],
                            source_audio_sha256=source_hash, canonical_pcm_sha256=representation['canonical_pcm_sha256'],
                            encoder_id=encoder.encoder_id)
                        pooled = db.execute("SELECT * FROM pooled WHERE encoder_analysis_identity=? AND status='SUCCESS'", (identity,)).fetchall()
                        segments = db.execute("SELECT * FROM segments WHERE encoder_analysis_identity=? AND status='SUCCESS'", (identity,)).fetchall()
                        require(len(pooled) == 1 and len(segments) == 3 and {r['center_sec'] for r in segments} == {5, 15, 25}, 'cache vectors incomplete')
                        for vector in pooled + segments:
                            require(vector['source_audio_sha256'] == source_hash and vector['vector_contract_sha256'] == contract.vector_contract_sha256,
                                    'cached vector provenance hash mismatch')
                            require(hashlib.sha256(vector['embedding']).hexdigest() == vector['embedding_sha256'], 'embedding hash mismatch')
                            array = np.frombuffer(vector['embedding'], dtype='<f4')
                            require(array.shape == (encoder.dimension,) and np.isfinite(array).all() and np.isclose(np.linalg.norm(array), 1, atol=1e-5), 'invalid cached vector')
                        row['centered30' if i == 0 else 'muq'] = True
                    row['source_sha256'] = source_hash
                    row['vector_contract_sha256'] = contract.vector_contract_sha256
                    row['cache_recording_id'] = representation['stable_track_id']
                except (ValueError, OSError, sqlite3.Error) as exc:
                    row['errors'].append(f'{key}: {exc}')
            rows.append(row)
    return {'schema': 'captured-calibration-inventory-v1', 'recordings': rows,
            'input_snapshots': inputs, 'capture_semantics': 'queue JSON captured once; per-cache read-only SQLite transaction; ongoing work may advance afterward',
            'feature_enrollment': 'centered30 adapter only; Method C/profile enrollment requires explicit aligned manifests',
            'protocol_sha256': contract.vector_contract_sha256}


def write_readiness(root, runs, output):
    inventory = scan_batches(root, runs)
    freeze_json(output / 'inventory.private.json', inventory)
    report = summarize_inventory(inventory)
    freeze_json(output / 'readiness.json', report)
    return report
