"""Label-free, fixed hierarchical aggregation of cached Discogs outputs."""
import numpy as np

from .style_prior import distances


def mapping(classes, config):
    """Expand family defaults and exact style overrides; never use track metadata."""
    if len(classes) != len(set(classes)):
        raise ValueError('duplicate style classes')
    unknown = set(config['style_overrides']) - set(classes)
    if unknown:
        raise ValueError(f'unknown override styles: {sorted(unknown)}')
    bands = sorted(config['parents']) + ['unknown']
    matrix = np.zeros((len(classes), len(bands)), dtype=np.float64)
    records = []
    for i, style in enumerate(classes):
        family = style.split('---')[0]
        weights = config['style_overrides'].get(style)
        if weights is None:
            weights = {config['family_defaults'][family]: 1.0}
        if not weights or not np.isclose(sum(weights.values()), 1, atol=1e-12):
            raise ValueError('mapping weights must sum to one')
        for band, weight in weights.items():
            if not np.isfinite(weight) or weight <= 0 or band not in bands:
                raise ValueError('invalid mapping weight')
            matrix[i, bands.index(band)] = weight
        records.append({'style': style, 'bands': weights,
                        'rule': 'override' if style in config['style_overrides'] else 'family_default'})
    return bands, matrix, records


def aggregate(raw, classes, config):
    raw = np.asarray(raw, dtype=np.float64)
    if raw.ndim != 2 or raw.shape[1] != len(classes) or not np.isfinite(raw).all() or np.any((raw < 0) | (raw > 1)):
        raise ValueError('invalid cached sigmoid means')
    bands, weights, _ = mapping(classes, config)
    masses = raw @ weights
    known = masses[:, :-1].sum(axis=1)
    total = masses.sum(axis=1)
    fraction = np.divide(known, total, out=np.zeros_like(known), where=total > 0)
    profiles = masses[:, :-1] + config['epsilon']
    profiles /= profiles.sum(axis=1, keepdims=True)
    parents = sorted(set(config['parents'].values()))
    parent_weights = np.array([[float(config['parents'][b] == p) for p in parents] for b in bands[:-1]])
    parent_profiles = profiles @ parent_weights
    distance = fraction[:, None] * fraction[None, :] * (
        .5 * distances(profiles) + .5 * distances(parent_profiles))
    np.fill_diagonal(distance, 0)
    return {'band_mass': masses, 'band_profiles': profiles, 'parent_profiles': parent_profiles,
            'known_fraction': fraction, 'distance': distance,
            'bands': np.array(bands[:-1]), 'parents': np.array(parents)}


def adjust(scores, distance, strength):
    if not np.isfinite(strength) or strength < 0 or strength > .1:
        raise ValueError('penalty outside frozen conservative bound')
    if set(scores) != set(distance):
        raise ValueError('score/distance identity mismatch')
    if any(not np.isfinite(v) for v in scores.values()) or any(not np.isfinite(v) or v < 0 or v > 1 for v in distance.values()):
        raise ValueError('invalid pair values')
    return {key: scores[key] - strength * distance[key] for key in sorted(scores)}
