"""Offline unchanged-v1 mapping and isolated owner review of frozen 100 profiles."""
import argparse
from pathlib import Path

from .genre_neighborhood import compile_map, map_profile
from .genre_neighborhood_review import CONFIG, label_audit, review_csv, review_markdown
from .genre_neighborhood_review_store import GenreNeighborhoodReviewStore
from .stage5b1a_models import file_sha256
from .stage5e3_artifacts import read, freeze, freeze_json, verify_hashes

SOURCE = Path('reports/gemini_style_pilot/frozen100_free_genre_v1')
REPORT = Path('reports/genre_neighborhood_map/v1/frozen100')
STATE = Path('artifacts/genre_neighborhood_review/frozen100')


def build(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or any(p == output or output in p.parents or p in output.parents
                            for p in (root / SOURCE, root / '.research_audio', root / 'artifacts',
                                      root / 'reports/genre_neighborhood_map/v1/pilot16')):
        raise ValueError('Output overlaps protected inputs or owner state')
    source = root / SOURCE
    manifest = read(source / 'artifact_manifest.json')['files']
    verify_hashes(source, manifest)
    spec = read(root / CONFIG)
    if file_sha256(root / CONFIG) != file_sha256(root / 'reports/genre_neighborhood_map/v1/pilot16/genre-neighborhood-map-v1.json'):
        raise ValueError('The original v1 mapper must remain unchanged')
    execution = read(source / 'execution_manifest.json')
    tracks = execution['tracks']
    if len(tracks) != 100 or len({t['spotify_track_id'] for t in tracks}) != 100 or {t['pilot_id'] for t in tracks} != {f'F{i:03d}' for i in range(1,101)}:
        raise ValueError('Exact frozen 100 identities required')
    rows, audio = [], []
    compiled = compile_map(spec)
    for t in sorted(tracks, key=lambda t: t['pilot_id']):
        pid = t['pilot_id']
        path = source / 'profiles' / f'{pid}.json'
        profile = read(path)
        if profile['spotify_track_id'] != t['spotify_track_id']:
            raise ValueError('Profile identity differs')
        prepared = t['prepared']
        audio_path = Path(execution['prepared_root']) / prepared['prepared_filename']
        if not prepared['full_recording_preserved'] or file_sha256(root / audio_path) != prepared['prepared_sha256']:
            raise ValueError('Missing, partial or changed prepared recording')
        row = {'pilot_id': pid, 'spotify_track_id': t['spotify_track_id'],
               'song': t['catalog_title'] + ' — ' + ', '.join(t['catalog_artists']),
               'source_profile': str(path.relative_to(root)), 'input_profile_sha256': file_sha256(path),
               **map_profile(profile['profile'], compiled),
               'review_context_not_mapper_inputs': {'owner_first_pass_verbatim': '',
                   'classification_review_suggested': False, 'assistant_review_note':
                   'Inspect the unchanged mapping and original classification separately. No prior answer is inferred.',
                   'owner_mapping_decision': '', 'owner_classification_decision': '', 'owner_review_notes': ''}}
        rows.append(row)
        audio.append({'pilot_id': pid, 'neutral_id': t['neutral_id'], 'spotify_track_id': t['spotify_track_id'],
                      'title': t['catalog_title'], 'artists': t['catalog_artists'],
                      'duration_seconds': prepared['duration_seconds'], 'audio_path': str(audio_path),
                      'audio_sha256': prepared['prepared_sha256'], 'mapping': row})
    audit = label_audit(rows)
    packet = {'schema': 'gemini-owner-review-v1', 'review_kind': 'genre-neighborhood-owner-review-v1',
              'corpus': 'original-frozen100', 'source_manifest_sha256': file_sha256(source / 'artifact_manifest.json'),
              'mapper_sha256': file_sha256(root / CONFIG), 'map': spec, 'tracks': audio}
    freeze_json(output / 'review_packet.json', packet)
    freeze_json(output / 'mapped_review.json', rows)
    freeze_json(output / 'genre-neighborhood-map-v1.json', spec)
    freeze_json(output / 'label_audit.json', audit)
    freeze(output / 'manual_review.csv', review_csv(rows))
    freeze(output / 'manual_review.md', review_markdown(rows).replace(b'# Original 16:', b'# Frozen 100:'))
    freeze_json(output / 'summary.json', {'tracks': 100, 'model_calls': 0, 'mapper_changed': False,
        'tracks_with_unresolved_labels': sum(r['has_unresolved_labels'] for r in rows),
        'tracks_requiring_mapping_review': sum(r['mapping_review_required'] for r in rows),
        'flagged_label_occurrences': len(audit['unresolved_or_review_required']),
        'purpose': 'Manual coverage inspection only; no accuracy or ranking benchmark.'})
    verify_hashes(source, manifest)
    freeze_json(output / 'artifact_manifest.json', {'files': {p.name: file_sha256(p) for p in sorted(output.iterdir())
                                                           if p.is_file() and p.name != 'artifact_manifest.json'}})
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--port', type=int, default=8798)
    parser.add_argument('--state-dir', type=Path, help='Separate disposable testing state only')
    parser.add_argument('--output', type=Path, default=REPORT)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if not args.serve:
        build(root, root / args.output)
        return
    report = root / REPORT
    verify_hashes(report, read(report / 'artifact_manifest.json')['files'])
    packet = read(report / 'review_packet.json')
    real = root / STATE
    if args.state_dir and (args.state_dir.resolve() == real or real in args.state_dir.resolve().parents
                          or root / 'artifacts' in args.state_dir.resolve().parents):
        parser.error('Disposable testing must not use real artifact state')
    from .cli.gemini_style_review import handler, STATIC
    from .cli.stage5b1b_review_server import ReviewHTTPServer
    store = GenreNeighborhoodReviewStore(root, args.state_dir or real, packet=packet)
    base = handler(store, disposable=bool(args.state_dir), neighborhood=store)

    class Handler(base):
        def do_GET(self):
            if self.path.split('?')[0] in ('/', '/neighborhood', '/neighborhood/'):
                page = STATIC.with_name('genre_neighborhood_review.html').read_text()
                page = page.replace('A quick check of 16 songs:', 'A review of the frozen 100 songs:')
                page = page.replace('href="/">← Earlier audio-style review',
                                    'href="http://127.0.0.1:8794/neighborhood">← Original 16-song review')
                return self._bytes(page.encode(), 'text/html; charset=utf-8')
            return super().do_GET()

    try:
        server = ReviewHTTPServer(('127.0.0.1', args.port), Handler)
        print(f'Frozen-100 review: http://127.0.0.1:{args.port}/neighborhood', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        store.close()


if __name__ == '__main__':
    main()
