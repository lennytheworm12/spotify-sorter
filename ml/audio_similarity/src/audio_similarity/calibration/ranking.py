"""Frozen finite model registry, complete-pair Top-3 scoring and observed-member metrics."""
from dataclasses import asdict, dataclass
import math

from .contracts import Clap, Catalog, Query, digest, finite, require
from .features import PairFeatures

RHO = tuple(i / 10 for i in range(11))
WC = (0., .005, .010, .020, .035, .050, .075, .100)
ETA = (0., .25, .50, .75, 1.)
M3_RHO = .2827018481


@dataclass(frozen=True)
class Model:
    clap: Clap
    rho: float
    w_c: float
    eta: float
    base: str = 'joint'

    def __post_init__(self):
        require(isinstance(self.clap, Clap), 'explicit CLAP representation required')
        for v in (self.rho, self.w_c, self.eta):
            finite(v)
        for field in ('rho', 'w_c', 'eta'):
            object.__setattr__(self, field, float(getattr(self, field)))
        require(0 <= self.rho <= 1 and 0 <= self.w_c <= .10 and 0 <= self.eta <= 1, 'coefficient bounds')
        require(self.w_c != 0 or self.eta == 0, 'eta inactive at w_c=0')
        require(self.base in {'joint', 'frozen_m3'}, 'unknown audio base')
        if self.base == 'frozen_m3':
            require(self.clap == Clap.METHOD_C and self.rho == M3_RHO, 'exact M3 is a separate pinned control')

    @property
    def w_n(self):
        return self.w_c * self.eta

    @property
    def identity(self):
        return digest(asdict(self))

    @property
    def definition(self):
        return {**asdict(self), 'w_n': self.w_n,
                'clap_active': self.base == 'frozen_m3' or self.rho != 1}


def grid(*, deduplicate_clap=True):
    return tuple(Model(h, rho, wc, eta)
                 for h in Clap for rho in RHO for wc in WC for eta in ETA
                 if (wc != 0 or eta == 0)
                 and (not deduplicate_clap or rho != 1 or h == Clap.CENTERED))


def ablations():
    full = grid()
    arms = {'frozen_m3': (Model(Clap.METHOD_C, M3_RHO, 0., 0., 'frozen_m3'),),
            'muq_only': (Model(Clap.CENTERED, 1., 0., 0.),)}
    for h in Clap:
        # Keep categorical single-arm definitions explicit even at an inactive endpoint.
        variants = tuple(Model(Clap.CENTERED if r == 1 else h, r, w, e) for r in RHO for w in WC for e in ETA if w != 0 or e == 0)
        arms[f'{h.value}/clap_only'] = (Model(h, 0., 0., 0.),)
        arms[f'{h.value}/audio_mixture'] = tuple(m for m in variants if m.w_c == 0)
        arms[f'{h.value}/joint_canonical'] = tuple(m for m in variants if m.eta == 0)
        arms[f'{h.value}/joint_residual'] = variants
    arms['m3_canonical'] = tuple(Model(Clap.METHOD_C, M3_RHO, w, 0., 'frozen_m3') for w in WC)
    arms['m3_residual'] = tuple(Model(Clap.METHOD_C, M3_RHO, w, e, 'frozen_m3') for w in WC for e in ETA if w != 0 or e == 0)
    arms['joint_canonical'] = tuple(m for m in full if m.eta == 0)
    arms['joint_residual'] = full
    return arms


def pair_score(features: PairFeatures, model: Model, a: str, b: str):
    c = features.at('C_center30' if model.clap == Clap.CENTERED else 'C_method_c', a, b)
    muq = features.at('M', a, b)
    jc, jnr, residual = (features.at(key, a, b) for key in ('Jc', 'Jnr', 'R'))
    if model.base == 'frozen_m3':
        require('M3' in features.matrices, 'exact frozen M3 matrix unavailable; do not reconstruct it')
        audio = features.at('M3', a, b)
    else:
        audio = (1 - model.rho) * c + model.rho * muq
    return {'F': audio + model.w_c * jc + model.w_n * residual,
            'C': c, 'M': muq, 'Jc': jc, 'Jnr': jnr, 'R': residual,
            'audio': audio, 'canonical_term': model.w_c * jc, 'residual_term': model.w_n * residual}


def distinct_ids(features, ids, exclude=()):
    records = features.records
    excluded = {records[key].version_group_id for key in exclude}
    result = []
    for key in sorted(set(ids)):
        require(key in records, 'unknown recording')
        group = records[key].version_group_id
        if group not in excluded:
            result.append(key)
            excluded.add(group)
    return tuple(result)


def playlist_score(features, model, candidate, seeds):
    support = distinct_ids(features, seeds, exclude=(candidate,))
    if not support:
        return {'Q': None, 'status': 'INSUFFICIENT_DATA', 'seed_count': 0, 'top_support': []}
    scored = [{'recording_id': s, **pair_score(features, model, candidate, s)} for s in support]
    top = sorted(scored, key=lambda row: (-row['F'], row['recording_id']))[:3]
    return {'Q': sum(r['F'] for r in top) / len(top), 'status': 'READY',
            'seed_count': len(support), 'top_support': top}


def rank_query(features, model, query: Query, catalog: Catalog):
    playlists = {p.playlist_id: p for p in features.corpus.playlists}
    require(query.playlist_id in playlists, 'unknown source playlist')
    source = playlists[query.playlist_id]
    require((query.snapshot_id, query.curator_group_id, query.stratum, query.layer) ==
            (source.snapshot_id, source.curator_group_id, source.stratum, source.layer), 'query source provenance mismatch')
    require(set(query.seed_ids + query.hidden_ids) <= set(source.recording_ids), 'mask labels must come from observed source membership')
    require(query.catalog_hash == catalog.identity and query.split_id == catalog.split_id
            and query.role == catalog.role, 'query/catalog identity or role mismatch')
    require(set(query.seed_ids + query.hidden_ids) <= set(catalog.recording_ids), 'mask outside fixed catalog')
    records = features.records
    seed_groups = {records[s].version_group_id for s in query.seed_ids}
    hidden_groups = {records[s].version_group_id for s in query.hidden_ids}
    require(not seed_groups & hidden_groups, 'duplicate recording crosses seed/positive boundary')
    candidates = distinct_ids(features, catalog.recording_ids, exclude=query.seed_ids)
    rows = []
    for candidate in candidates:
        score = playlist_score(features, model, candidate, query.seed_ids)
        rows.append({'candidate_recording_id': candidate, **score,
                     'observed_membership': 'observed_positive' if records[candidate].version_group_id in hidden_groups else 'unlabeled'})
    require(all(r['Q'] is not None for r in rows), 'query has missing score')
    return sorted(rows, key=lambda r: (-r['Q'], r['candidate_recording_id']))


def reconstruction_metrics(ranked_ids, positive_ids):
    require(len(ranked_ids) == len(set(ranked_ids)), 'duplicate ranking entries')
    positive = set(positive_ids)
    require(positive <= set(ranked_ids), 'hidden positives missing from candidate catalog')
    if not positive:
        return {'status': 'INSUFFICIENT_DATA', 'ndcg20': None, 'recall20': None, 'recall10': None}
    relevance = [int(key in positive) for key in ranked_ids]
    ideal = sum(1 / math.log2(i + 2) for i in range(min(20, len(positive))))
    dcg = sum(v / math.log2(i + 2) for i, v in enumerate(relevance[:20]))
    return {'status': 'READY', 'ndcg20': dcg / ideal,
            'recall20': sum(relevance[:20]) / len(positive), 'recall10': sum(relevance[:10]) / len(positive)}
