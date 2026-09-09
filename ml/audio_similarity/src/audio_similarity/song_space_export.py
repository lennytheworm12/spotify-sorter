"""Read-only export of processed CLAP evidence for the private song-space UI."""
from pathlib import Path
import argparse
import hashlib
import json
import sqlite3
import numpy as np
from .stage5a_contract import load_contract
from .stage5e3_artifacts import freeze_json, hashes, read, verify_hashes, digest

E3 = Path('reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3')


def knn_links(ids, matrix, k=12):
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.shape != (len(ids), len(ids)) or len(set(ids)) != len(ids) or not np.isfinite(matrix).all():
        raise ValueError('invalid similarity matrix or identities')
    if not np.allclose(matrix, matrix.T, atol=1e-6, rtol=0):
        raise ValueError('this snapshot requires symmetric scores')
    if not 1 <= k <= 100:
        raise ValueError('k must be 1..100')
    links = {}
    for i, source in enumerate(ids):
        candidates = sorted((j for j in range(len(ids)) if i != j), key=lambda j: (-matrix[i, j], ids[j]))[:k]
        for rank, j in enumerate(candidates, 1):
            a, b = sorted((source, ids[j]))
            row = links.setdefault((a, b), {'source': a, 'target': b, 'score': float(np.clip(matrix[i, j], -1, 1)), 'sourceRank': None, 'targetRank': None})
            row['sourceRank' if source == a else 'targetRank'] = rank
    return [links[key] for key in sorted(links)]


def apply_source_corrections(root, rows, paths, protected_ids):
    """Apply explicit, hash-locked corrections without changing historical ledgers."""
    index = root / '.research_audio/library_batches_v1/source_corrections.json'
    if not index.exists():
        return
    document = read(index)
    if document.get('schema_version') != 'library-source-corrections-v1':
        raise ValueError('unsupported source correction index')
    paths.append(index)
    seen = set()
    for correction in document['corrections']:
        tid = correction['spotify_track_id']
        if tid in seen or tid not in rows or tid in protected_ids:
            raise ValueError('duplicate, unknown, or frozen-C source correction')
        seen.add(tid)
        if rows[tid]['result']['source_sha256'] != correction['expected_old_source_sha256']:
            raise ValueError('source correction does not match historical source')
        record_path = (root / correction['record_path']).resolve()
        if not record_path.is_relative_to((root / '.research_audio').resolve()):
            raise ValueError('source correction record outside private data root')
        verify_hashes(root, {str(record_path.relative_to(root)): correction['record_sha256']})
        replacement = read(record_path)
        result = replacement.get('result', {})
        representation = result.get('representation', {})
        if (replacement.get('state') != 'COMPLETE'
                or representation.get('status') != 'SUCCESS'
                or representation.get('stable_track_id') != tid
                or representation.get('source_audio_sha256') != result.get('source_sha256')
                or result.get('source_sha256') == correction['expected_old_source_sha256']):
            raise ValueError('incomplete or inconsistent source correction')
        rows[tid] = replacement
        paths.append(record_path)


def load_processed(root):
    library = root / '.research_audio/library_batches_v1'
    manifest = read(library / 'manifest.json')
    if digest(manifest) != read(library / 'manifest_hash.json')['sha256']:
        raise ValueError('library manifest mismatch')
    tracks = {t['spotify_track_id']: t for batch in manifest['batches'] for t in batch['tracks']}
    rows = {}
    paths = [library / 'manifest.json', library / 'manifest_hash.json']
    for path in sorted(library.glob('batch_*/state.json')):
        paths.append(path)
        rows.update({tid: row for tid, row in read(path)['tracks'].items() if row['state'] == 'COMPLETE'})
    index = library / 'recovery_index.json'
    if index.exists():
        recovery = read(index)
        audit = root / recovery['recovery_run'] / 'audit.json'
        verify_hashes(root, {str(audit.relative_to(root)): recovery['audit_sha256']})
        state = root / recovery['recovery_run'] / 'execution/state.json'
        paths.extend([index, audit, state])
        for tid, row in read(state)['tracks'].items():
            if row['state'] == 'COMPLETE':
                rows[tid] = row
    with np.load(root / E3 / 'historical_reference_matrices.npz', allow_pickle=False) as frozen:
        protected_ids = set(map(str, frozen['spotify_ids']))
    apply_source_corrections(root, rows, paths, protected_ids)
    if not set(tracks) <= set(rows):
        raise ValueError(f'{len(set(tracks) - set(rows))} library tracks not processed; do not silently shrink the map')
    contract = load_contract(root / 'reports/holistic_stage4a_dual/audio_representation_v1.json')
    encoder = next(e for e in contract.encoders if 'clap' in e.encoder_id.lower())
    vectors, media, receipts = {}, {}, []
    connections = {}
    try:
        for tid, track in sorted(tracks.items()):
            result = rows[tid]['result']; record = result['representation']
            cache = root / record['cache_path']
            if not cache.resolve().is_relative_to((root / 'artifacts').resolve()):
                raise ValueError('cache outside artifact root')
            if cache not in connections:
                connections[cache] = sqlite3.connect(f'file:{cache.resolve()}?mode=ro', uri=True)
                connections[cache].row_factory = sqlite3.Row
            db = connections[cache]
            identity = contract.encoder_analysis_identity(corpus=record['corpus'], corpus_version=record['corpus_version'], stable_track_id=tid,
                source_audio_sha256=record['source_audio_sha256'], canonical_pcm_sha256=record['canonical_pcm_sha256'], encoder_id=encoder.encoder_id)
            row = db.execute("SELECT * FROM pooled WHERE encoder_analysis_identity=? AND status='SUCCESS'", (identity,)).fetchone()
            if row is None:
                raise ValueError(f'missing CLAP vector for {tid}')
            blob = bytes(row['embedding'])
            if hashlib.sha256(blob).hexdigest() != row['embedding_sha256']:
                raise ValueError('CLAP vector hash mismatch')
            vector = np.frombuffer(blob, dtype='<f4').astype(np.float64)
            if vector.shape != (encoder.dimension,) or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector), 1, atol=1e-5):
                raise ValueError('invalid CLAP vector')
            vectors[tid] = vector / np.linalg.norm(vector)
            source = (root / '.research_audio' / result['retained_relative_path']).resolve()
            if not source.is_relative_to((root / '.research_audio').resolve()) or not source.is_file():
                raise ValueError('missing or invalid retained source')
            media[tid] = {'path': str(source), 'sha256': result['source_sha256']}
            receipts.append({'track_id': tid, 'cache': str(cache.relative_to(root)), 'encoder_analysis_identity': identity, 'embedding_sha256': row['embedding_sha256']})
    finally:
        for db in connections.values():
            db.close()
    return tracks, vectors, media, receipts, paths


def export(root, output, k):
    tracks, vectors, media, receipts, paths = load_processed(root)
    def dataset(ids, matrix, label, scorer_id, description):
        return {'schemaVersion': 'song-space-v1', 'id': scorer_id + '-' + digest(ids)[:12], 'name': label, 'description': description,
                'scorer': {'id': scorer_id, 'label': label, 'description': description, 'scoreRange': [-1, 1], 'higherIsCloser': True},
                'neighborhoodSize': k,
                'songs': [{'id': tid, 'title': tracks[tid]['title'], 'artists': tracks[tid]['artists'], 'album': tracks[tid].get('album') or 'Unknown album',
                           'durationMs': tracks[tid]['duration_ms'], 'audioUrl': '/__song-space/audio/' + tid} for tid in ids],
                'links': knn_links(ids, matrix, k)}
    ids = sorted(tracks)
    x = np.stack([vectors[tid] for tid in ids])
    library = dataset(ids, np.clip(x @ x.T, -1, 1), 'Library · excerpt CLAP', 'centered30-clap-v1',
                      'All processed library songs. Existing CLAP embeddings pooled from three windows in the retained 30-second excerpt. This is not full-song CLAP C; MuQ and fusion are not map inputs.')
    with np.load(root / E3 / 'historical_reference_matrices.npz', allow_pickle=False) as data:
        order = list(data['spotify_ids']); c_ids = sorted(str(t) for t in order)
        if not set(c_ids) <= set(tracks):
            raise ValueError('frozen C subset does not belong to this library')
        ix = [order.index(t) for t in c_ids]
        c = dataset(c_ids, data['c_clap'][np.ix_(ix, ix)], 'Frozen 100 · full-song CLAP C', 'full-song-clap-c-v1',
                    'Exact frozen Stage 5E full-song music-CLAP C cosine scores for the amended 100-song subset. Communities are exploratory, not validated playlist labels.')
    for name, value in [('library', library), ('clap-c', c), ('audio-index', media), ('vector-receipts', receipts)]:
        freeze_json(output / (name + '.json'), value)
    freeze_json(output / 'catalog.json', [{'id': name, 'label': data['name'], 'url': '/__song-space/data/' + name} for name, data in [('library', library), ('clap-c', c)]])
    freeze_json(output / 'provenance.json', {'input_hashes': hashes(paths + [Path(__file__), root / E3 / 'historical_reference_matrices.npz'], root),
                'configuration': {'k': k, 'knn': 'union of directed top-k, exact score descending, stable track ID tie break', 'inference_calls': 0},
                'library_tracks': len(ids), 'clap_c_tracks': len(c_ids), 'score_inputs': 'CLAP only; no fusion, MuQ, labels, genre or style features'})
    print({'library_tracks': len(ids), 'library_links': len(library['links']), 'C_tracks': len(c_ids), 'output': str(output), 'inference_calls': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.research_audio/song_space/v1'))
    parser.add_argument('--neighbors', type=int, default=12)
    args = parser.parse_args()
    root = Path.cwd()
    output = args.output.resolve()
    if not output.is_relative_to((root / '.research_audio').resolve()):
        parser.error('keep private library exports under .research_audio')
    export(root, output, args.neighbors)
