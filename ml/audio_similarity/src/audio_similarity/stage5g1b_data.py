"""Freeze inputs, rubric-separated evidence, and a label-independent probe protocol."""
from collections import Counter
from itertools import combinations
from pathlib import Path
import csv
import importlib.metadata
from .stage5c2_analysis import canonical_pair_id
from .stage5e3_artifacts import read, freeze_json, hashes, verify_hashes
from .stage5g1_segments import encoder_identity

G1 = Path('reports/stage5g1_clap_similarity/v1')
G1A = Path('reports/stage5g1a_scorer_diagnostic/v1')
E3 = Path('reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3')
CSV = Path('reports/stage5e3_completed_review_v1/playlist-review-ratings-and-notes.csv')


def evidence(root):
    tracks = read(root / G1 / 'tracks.json')
    ids = sorted(t['spotify_track_id'] for t in tracks)
    endpoints = {canonical_pair_id(a, b): [a, b] for a, b in combinations(ids, 2)}
    snapshot = read(root / E3 / 'post_review_rating_snapshot.json')
    playlist = []
    excluded = []
    for pair, rating in sorted(snapshot['labels'].items()):
        if snapshot['semantic_tags'].get(pair) != 'PLAYLIST_COMPATIBILITY_V1':
            continue
        if pair not in endpoints or rating not in (1, 2, 3, 4, 5):
            excluded.append(pair)
            continue
        playlist.append({'pair_id': pair, 'tracks': endpoints[pair], 'rating': rating})
    holistic = read(root / G1 / 'human_evidence.json')['pairs']
    with (root / CSV).open(encoding='utf-8-sig', newline='') as handle:
        notes = [dict(row, tracks=endpoints[row['pair_id']]) for row in csv.DictReader(handle) if row['note'].strip()]
    diagnostic_ids = {id for note in notes for id in note['tracks']}
    diagnostic_artists = sorted({a.casefold().strip() for t in tracks if t['spotify_track_id'] in diagnostic_ids for a in t['artists']})
    inventory = {'tracks': len(tracks), 'playlist_pairs': len(playlist), 'holistic_pairs': len(holistic),
                 'playlist_rating_counts': dict(sorted(Counter(p['rating'] for p in playlist).items())),
                 'holistic_rating_counts': dict(sorted(Counter(p['rating'] for p in holistic).items())),
                 'playlist_excluded_unjoinable_or_uncertain': excluded, 'existing_notes': len(notes),
                 'note_anchor_count': len({n['anchor'] for n in notes}),
                 'diagnostic_artist_exclusions': diagnostic_artists,
                 'causal_taxonomy_labels': 0, 'new_human_judgments': 0,
                 'rubrics_pooled': False, 'unrated_pairs_are_unknown': True}
    return tracks, {'playlist': playlist, 'holistic': holistic}, notes, inventory


def prepare(root, run):
    if (run / 'input_hashes.json').exists():
        verify_hashes(root, read(run / 'input_hashes.json'))
    verify_hashes(root / G1A, read(root / G1A / 'artifact_manifest.json'))
    verify_hashes(root, read(root / G1A / 'input_hashes.json'))
    config = read(root / 'configs/stage5g1b_v1.json')
    freeze_json(run / 'protocol.json', config)
    tracks, labels, notes, inventory = evidence(root)
    for name, value in [('tracks', tracks), ('evidence', labels), ('notes', notes), ('inventory', inventory)]:
        freeze_json(run / f'{name}.json', value)
    # Explicit offline tokenizer provenance, not an implicit new model download.
    tokenizer = Path.home() / '.cache/huggingface/hub/models--roberta-base'
    tokenizer_hashes = hashes([p for p in tokenizer.rglob('*') if p.is_file()], tokenizer)
    if not tokenizer_hashes:
        raise ValueError('local roberta tokenizer/model assets missing')
    identity = {'encoder': encoder_identity(root), 'tokenizer_assets': tokenizer_hashes,
                'implementation': hashes([root / 'src/audio_similarity/stage5g1b_probes.py'], root),
                'device': 'cpu', 'batch_size': 8, 'precision': 'float32 inference, float64 normalization',
                'offline': True}
    freeze_json(run / 'text_identity.json', identity)
    paths = list((root / G1A).rglob('*')) + [root / E3 / 'post_review_rating_snapshot.json', root / CSV]
    paths += list((root / 'src/audio_similarity').glob('stage5g1b_*.py'))
    paths += [root / 'configs/stage5g1b_v1.json', root / 'tests/test_stage5g1b.py']
    paths += list(run.glob('*.json'))
    protected = read(root / G1A / 'input_hashes.json') | hashes(paths, root)
    # The manifest must never include itself on a subsequent prepare replay.
    protected.pop(str((run / 'input_hashes.json').relative_to(root)), None)
    if (run / 'input_hashes.json').exists():
        return inventory
    freeze_json(run / 'input_hashes.json', protected)
    verify_hashes(root, protected)
    return inventory
