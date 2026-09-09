"""Development-only selection, correction accounting and grouped uncertainty."""
from collections import defaultdict
import numpy as np

from .stage5g1a_data import groups
from .stage5g1_evidence import preferences
from .style_band_math import adjust
from .style_prior_analysis import agreement, interval, win


def key(a, b):
    return tuple(sorted((a, b)))


def validate_folds(tracks, pairs, folds):
    ids = {t['spotify_track_id'] for t in tracks}
    if len(ids) != len(tracks):
        raise ValueError('duplicate tracks')
    pair_keys = [key(*p['tracks']) for p in pairs]
    if len(pair_keys) != len(set(pair_keys)):
        raise ValueError('duplicate or conflicting pairs')
    if any(len(set(p['tracks'])) != 2 or not set(p['tracks']) <= ids or p['rating'] not in range(1, 6) for p in pairs):
        raise ValueError('invalid human pair')
    seen = set()
    for fold in folds:
        train, heldout = set(fold['train']), set(fold['heldout'])
        if train & heldout or train | heldout != ids or seen & heldout:
            raise ValueError('track leakage or incomplete partition')
        seen |= heldout
        for group in groups(tracks, True):
            if set(group) & train and set(group) & heldout:
                raise ValueError('artist/source leakage')
        for part in ('train', 'heldout'):
            expected = preferences(pairs, fold[part])[0]
            if expected != fold[part + '_preferences']:
                raise ValueError('label leakage or changed frozen preferences')
    if seen != ids:
        raise ValueError('incomplete heldout coverage')


def select(scores, distance, train_preferences, grid):
    if list(grid) != sorted(set(grid)) or not grid or grid[0] != 0:
        raise ValueError('ordered grid including zero required')
    rows = [{'lambda': strength, **agreement(adjust(scores, distance, strength), train_preferences)} for strength in grid]
    if rows[0]['macro'] is None:
        raise ValueError('no training preferences')
    best = max(r['macro'] for r in rows)
    return next(r['lambda'] for r in rows if r['macro'] >= best - 1e-12), rows


def crossings(scores, adjusted, constraints, ratings):
    rows = []
    for p in constraints:
        a, good, bad = p['anchor'], p['preferred'], p['other']
        before = win(scores[key(a, good)] - scores[key(a, bad)])
        after = win(adjusted[key(a, good)] - adjusted[key(a, bad)])
        rows.append(p | {'before': before, 'after': after, 'delta': after - before,
                         'good_bad': ratings[key(a, good)] >= 4 and ratings[key(a, bad)] <= 2,
                         'transition': 'corrected' if before == 0 and after == 1 else 'broken' if before == 1 and after == 0 else 'tie_change' if before != after else 'unchanged'})
    return rows


def correction_summary(rows):
    strong = [r for r in rows if r['good_bad']]
    result = {'good_bad_constraints': len(strong), 'baseline_strict_errors': sum(r['before'] == 0 for r in strong),
              'baseline_strict_correct': sum(r['before'] == 1 for r in strong),
              'all_ordinal_net_credit': sum(r['delta'] for r in rows)}
    for kind, endpoint in [('corrected', 'other'), ('broken', 'preferred')]:
        selected = [r for r in strong if r['transition'] == kind]
        result[kind + '_orderings'] = len(selected)
        result[kind + '_unique_pairs'] = len({key(r['anchor'], r[endpoint]) for r in selected})
    result['good_bad_tie_changes'] = sum(r['transition'] == 'tie_change' for r in strong)
    result['good_bad_net_credit'] = sum(r['delta'] for r in strong)
    return result


def top_changes(scores, adjusted, queries, candidates, ratings, k=5):
    """Never label an unknown entrant a good match or a removed unknown a correction."""
    rows = []
    for a in sorted(queries):
        pool = sorted(set(candidates) - {a})
        old = sorted(pool, key=lambda b: (-scores[key(a, b)], b))[:k]
        new = sorted(pool, key=lambda b: (-adjusted[key(a, b)], b))[:k]
        for b in sorted(set(old) | set(new)):
            rows.append({'anchor': a, 'candidate': b, 'rating': ratings.get(key(a, b)),
                         'before_rank': old.index(b) + 1 if b in old else None,
                         'after_rank': new.index(b) + 1 if b in new else None,
                         'transition': 'kept' if b in old and b in new else 'removed' if b in old else 'added'})
    counts = {}
    for change in ('kept', 'removed', 'added'):
        for label in ('bad', 'middle', 'good', 'unknown'):
            selected = [r for r in rows if r['transition'] == change and (
                'unknown' if r['rating'] is None else 'bad' if r['rating'] <= 2 else 'good' if r['rating'] >= 4 else 'middle') == label]
            counts[change + '_' + label] = {'directed': len(selected), 'unique_pairs': len({key(r['anchor'], r['candidate']) for r in selected})}
    return {'counts': counts, 'rows': rows}


def cluster_interval(per_anchor, tracks):
    """Resample connected artist/source groups, retaining anchor-macro weighting."""
    blocks = [[per_anchor[t] for t in g if t in per_anchor] for g in groups(tracks, True)]
    blocks = [b for b in blocks if b]
    if not blocks:
        return {'point': None, 'low': None, 'high': None, 'groups': 0}
    sums, sizes = np.array([sum(b) for b in blocks]), np.array([len(b) for b in blocks])
    ix = np.random.default_rng(5101).integers(0, len(blocks), (5000, len(blocks)))
    estimates = sums[ix].sum(axis=1) / sizes[ix].sum(axis=1)
    low, high = np.quantile(estimates, [.025, .975])
    return {'point': float(sums.sum() / sizes.sum()), 'low': float(low), 'high': float(high), 'groups': len(blocks)}


def breakdown(per_anchor, track_bands, field):
    buckets = defaultdict(dict)
    for anchor, delta in sorted(per_anchor.items()):
        buckets[track_bands[anchor][field]][anchor] = delta
    return {band: {'anchors': len(values), 'delta': interval(list(values.values())), 'per_anchor': values}
            for band, values in sorted(buckets.items())}


def verdict(delta, clustered, corrections, regions, excluded_delta, config):
    gate = config['positive_gate']
    eligible = {name: r for name, r in regions.items() if r['anchors'] >= gate['minimum_anchors_per_region']}
    largest = sorted(eligible, key=lambda name: (-eligible[name]['anchors'], name))[0] if eligible else None
    remainder = [value for name, region in regions.items() if name != largest for value in region['per_anchor'].values()]
    remainder_delta = interval(remainder)
    checks = {
        'material_primary_gain': delta['point'] is not None and delta['point'] >= gate['minimum_macro_delta'],
        'anchor_interval_positive': delta['low'] is not None and delta['low'] > 0,
        'cluster_interval_positive': clustered['low'] is not None and clustered['low'] > 0,
        'more_corrections_than_damage': corrections['corrected_orderings'] > corrections['broken_orderings'],
        'multiple_regions': sum(r['delta']['point'] > 0 for r in eligible.values()) >= gate['minimum_positive_parent_regions'],
        'diagnostic_exclusion_positive': excluded_delta['point'] is not None and excluded_delta['point'] > 0,
        'largest_region_exclusion_positive': remainder_delta['point'] is not None and remainder_delta['point'] > 0,
    }
    return {'outcome': 'COMPLEMENTARY_STYLE_BAND_SIGNAL_DEVELOPMENT_ONLY' if all(checks.values()) else 'STYLE_BAND_SHORTCUT_NOT_ESTABLISHED',
            'checks': checks, 'largest_parent_region': largest, 'without_largest_parent_delta': remainder_delta}
