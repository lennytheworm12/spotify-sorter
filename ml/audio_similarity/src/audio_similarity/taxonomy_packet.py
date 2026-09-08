"""Freeze a small, balanced taxonomy audit without exposing selection metadata."""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
from .stage5e3_artifacts import read, freeze_json, hashes, verify_hashes, digest

PRIOR = Path('reports/stage5g1b_identity_probes/v1')
REPORT = Path('reports/stage5g1b_taxonomy_review/v1')
CHOICES = {
    'FAMILY': ('Musical style / family', 'The overall musical language or style feels different.'),
    'VOCALS': ('Vocal role / delivery', 'Singing, rapping, vocal presence, or how the voice is used.'),
    'GROOVE': ('Groove / rhythmic feel', 'The pace, beat, swing, or rhythmic feel.'),
    'TEXTURE': ('Production / sound texture', 'The instruments, sound palette, distortion, or recording texture.'),
    'STRUCTURE': ('Arrangement / development', 'How layers, sections, or intensity change through the song.'),
    'MELODY': ('Melody / harmony', 'The melodic writing, chords, or harmonic character.'),
    'OTHER': ('Another difference', 'A difference that does not fit these choices; describe it below.'),
    'NONE': ('No meaningful mismatch', 'No difference stands out enough to keep these songs apart.'),
    'UNSURE': ('Not sure', 'I cannot identify a clear main difference.')}


def order(namespace, value):
    return hashlib.sha256(f'taxonomy-review-v1:{namespace}:{value}'.encode()).hexdigest()


def select_pairs(pairs, probes, tracks):
    by_pair = defaultdict(list)
    for row in probes:
        if row['rubric'] == 'playlist':
            by_pair[row['pair_id']].append(row)
    buckets = {}
    for kind in ('bad', 'good'):
        eligible = [p for p in pairs if (p['rating'] <= 2 if kind == 'bad' else p['rating'] >= 4)]
        ranked = sorted(eligible, key=lambda p: (
            not any(r['flag'] is True for r in by_pair[p['pair_id']]),
            -max(r['distance'] for r in by_pair[p['pair_id']]), p['pair_id']))
        middle = len(ranked) // 2
        buckets[kind + '_high'] = ranked[:middle]
        buckets[kind + '_low'] = ranked[middle:]
    # No track repeats. Prefer artists not already represented, then a frozen hash.
    selected, used, artist_counts = [], set(), Counter()
    for round_index in range(4):
        for bucket in ('bad_high', 'good_high', 'bad_low', 'good_low'):
            options = [p for p in buckets[bucket] if not used.intersection(p['tracks'])]
            if not options:
                raise ValueError('Cannot build 16 track-disjoint pairs under frozen allocation; do not shrink silently')
            def key(pair):
                artists = {a.casefold().strip() for id in pair['tracks'] for a in tracks[id]['artists']}
                return (sum(artist_counts[a] for a in artists),
                        not any(r['flag'] is True for r in by_pair[pair['pair_id']]) if bucket.endswith('high') else False,
                        order(bucket, pair['pair_id']))
            pair = min(options, key=key)
            selected.append(pair | {'selection_stratum': bucket})
            used.update(pair['tracks'])
            artist_counts.update({a.casefold().strip() for id in pair['tracks'] for a in tracks[id]['artists']})
    return selected, dict(sorted(artist_counts.items()))


def prepare(root):
    run = root / REPORT
    if (run / 'artifact_manifest.json').exists():
        verify_hashes(run, read(run / 'artifact_manifest.json'))
        verify_hashes(root, read(run / 'input_hashes.json'))
        return read(run / 'preparation.json')
    verify_hashes(root / PRIOR, read(root / PRIOR / 'artifact_manifest.json'))
    verify_hashes(root, read(root / PRIOR / 'input_hashes.json'))
    tracks = {t['spotify_track_id']: t for t in read(root / PRIOR / 'tracks.json')}
    specification = {'pairs': 16, 'primary_rubric': 'PLAYLIST_COMPATIBILITY_V1',
        'allocation': 'four bad/high, four bad/low, four good/high, four good/low',
        'ranking': 'confident union flags first, then maximum axis divergence, then pair ID; upper/lower halves within rating bin',
        'selection': 'round-robin strata, no repeated tracks, minimize repeated credited artists then confident flags in high strata then frozen hash',
        'presentation': 'hash-shuffled pairs and left/right order; no prior labels, probe values, strata or model metadata in public payload',
        'annotation': 'one dominant difference; OTHER needs a note to count complete; NONE and UNSURE are valid answers',
        'analysis_limit': 'purposefully balanced developmental audit; do not estimate corpus prevalence from this sample',
        'choices': CHOICES}
    freeze_json(run / 'selection_protocol.json', specification)
    selected, artists = select_pairs(read(root / PRIOR / 'evidence.json')['playlist'],
                                     read(root / PRIOR / 'pair_probes.json'), tracks)
    public_pairs = []
    for i, pair in enumerate(sorted(selected, key=lambda p: order('presentation', p['pair_id']))):
        ids = sorted(pair['tracks'], key=lambda id: order(pair['pair_id'], id))
        public_pairs.append({'pair_id': pair['pair_id'], 'review_index': i + 1,
                             'left': tracks[ids[0]], 'right': tracks[ids[1]]})
    packet = {'schema': 'taxonomy-audit-v1', 'pairs': public_pairs}
    freeze_json(run / 'packet.json', packet)
    freeze_json(run / 'selection_private.json', {'selected': selected, 'credited_artist_pair_counts': artists})
    freeze_json(run / 'preparation.json', {'status': 'READY_FOR_HUMAN_REVIEW', 'pairs': 16,
                'unique_tracks': 32, 'unique_credited_artists': len(artists),
                'maximum_pairs_per_artist': max(artists.values()), 'packet_hash': digest(packet)})
    protected = read(root / PRIOR / 'input_hashes.json') | hashes(list((root / PRIOR).rglob('*')), root)
    freeze_json(run / 'input_hashes.json', protected)
    freeze_json(run / 'artifact_manifest.json', hashes([p for p in run.iterdir() if p.is_file()], run))
    return read(run / 'preparation.json')
