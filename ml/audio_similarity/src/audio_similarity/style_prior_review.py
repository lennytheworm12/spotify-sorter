"""Bounded explanatory audit, with existing compatibility ratings kept private."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
from .stage5e3_artifacts import read, freeze_json, hashes, verify_hashes, digest
from .taxonomy_review_store import TaxonomyReviewStore
from .cli.stage5b1b_review_server import serve
from .style_prior import RUN

REVIEW = Path('reports/style_prior_pilot/review_v1')


def order(value):
    return hashlib.sha256(('style-prior-audit-v1:' + value).encode()).hexdigest()


def select(rows, tracks, excluded):
    pools = {'accepted_high_distance': sorted((p for p in rows if p['rating'] >= 4 and p['pair_id'] not in excluded), key=lambda p: (-p['style_distance'], p['pair_id'])),
             'rejected_low_distance': sorted((p for p in rows if p['rating'] <= 2 and p['pair_id'] not in excluded), key=lambda p: (p['style_distance'], p['pair_id']))}
    selected, used, artists = [], set(), Counter()
    for _ in range(6):
        for stratum, pool in pools.items():
            available = [(rank, p) for rank, p in enumerate(pool) if not used.intersection(p['tracks'])]
            if not available:
                raise ValueError('Cannot prepare all 12 pairs without repeated tracks')
            def key(item):
                rank, pair = item
                credited = {a.casefold().strip() for tid in pair['tracks'] for a in tracks[tid]['artists']}
                return sum(artists[a] for a in credited), rank, pair['pair_id']
            _, pair = min(available, key=key)
            selected.append(pair | {'selection_stratum': stratum})
            used.update(pair['tracks'])
            artists.update({a.casefold().strip() for tid in pair['tracks'] for a in tracks[tid]['artists']})
    return selected


def prepare(root):
    run = root / REVIEW
    prior = root / RUN
    verify_hashes(root, read(prior / 'input_hashes.json'))
    tracks = {t['spotify_track_id']: t for t in read(prior / 'tracks.json')}
    old_packet = root / 'reports/stage5g1b_taxonomy_review/v1/packet.json'
    excluded = {p['pair_id'] for p in read(old_packet)['pairs']}
    rows = [p for p in read(prior / 'pair_results.json') if p['rubric'] == 'playlist']
    selected = select(rows, tracks, excluded)
    pairs = []
    for i, pair in enumerate(sorted(selected, key=lambda p: order(p['pair_id']))):
        left, right = sorted(pair['tracks'], key=lambda tid: order(pair['pair_id'] + tid))
        pairs.append({'pair_id': pair['pair_id'], 'review_index': i + 1, 'left': tracks[left], 'right': tracks[right]})
    packet = {'schema': 'taxonomy-audit-v1', 'pairs': pairs}
    freeze_json(run / 'selection_protocol.json', {'purpose': 'Post-result explanatory audit, not an untouched efficacy test', 'pairs': 12, 'allocation': 'six accepted/high style distance and six rejected/low style distance', 'selection': 'round-robin; no repeated tracks; exclude all 16 prior taxonomy pairs; minimize credited-artist reuse then distance rank then pair ID', 'question': 'Which audible differences matter for sharing a playlist? If a pair works despite a difference, explain what connects it. No genre vocabulary required.', 'historical_ratings': 'reused unchanged; hidden, not overwritten by these annotations', 'blinding': 'model labels, scores, ranks, strata and old ratings absent from public payload', 'analysis_limit': 'Annotate first; distinguish detector error from acceptable style difference after annotation snapshot freezes. No tuning or production activation.'})
    freeze_json(run / 'packet.json', packet)
    freeze_json(run / 'selection_private.json', selected)
    freeze_json(run / 'preparation.json', {'status': 'READY_FOR_HUMAN_REVIEW', 'pairs': 12, 'tracks': 24, 'prior_taxonomy_pairs_repeated': 0, 'existing_compatibility_ratings_reused': 12, 'packet_hash': digest(packet)})
    paths = [prior / 'pair_results.json', old_packet, root / 'src/audio_similarity/style_prior_review.py', root / 'src/audio_similarity/taxonomy_review_store.py', root / 'src/audio_similarity/cli/stage5b1b_review_server.py', root / 'evaluation/static/style_prior_review.html']
    freeze_json(run / 'input_hashes.json', hashes(paths, root))
    freeze_json(run / 'artifact_manifest.json', hashes([p for p in run.iterdir() if p.is_file() and p.name != 'artifact_manifest.json'], run))
    return read(run / 'preparation.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'review', 'freeze'])
    parser.add_argument('--port', type=int, default=8792)
    parser.add_argument('--state-dir', type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    if args.command == 'prepare':
        print(prepare(root))
        return
    run = root / REVIEW
    verify_hashes(root, read(run / 'input_hashes.json'))
    verify_hashes(run, read(run / 'artifact_manifest.json'))
    real = root / 'artifacts/style_prior_pilot/review_v1'
    if args.state_dir and args.state_dir.resolve() == real.resolve():
        raise ValueError('disposable state must not target real review')
    store = TaxonomyReviewStore(run / 'packet.json', args.state_dir or real, root)
    try:
        if args.command == 'freeze':
            print(store.freeze())
        else:
            serve(store, '127.0.0.1', args.port, open_browser=False, static=root / 'evaluation/static/style_prior_review.html', mode='style_audit_disposable' if args.state_dir else 'style_audit', export_filename='style-audit-answers.csv', server_name='Style compatibility audit')
    finally:
        store.close()


if __name__ == '__main__':
    main()
