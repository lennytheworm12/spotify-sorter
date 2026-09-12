"""Model-blind grouping, recording purges and nested development partitions."""
from dataclasses import asdict, dataclass
import math

from .contracts import Catalog, Corpus, Layer, Query, Role, digest, require


def hash_order(ids, seed):
    return tuple(sorted(set(ids), key=lambda key: (digest([seed, key]), key)))


def source_clusters(corpus: Corpus):
    playlists = corpus.playlists
    parents = {p.playlist_id: p.playlist_id for p in playlists}
    records = corpus.by_id
    curators = {g.group_id: g.curator_id for g in corpus.groups}

    def find(key):
        while parents[key] != key:
            key = parents[key]
        return key

    def union(a, b):
        a, b = find(a), find(b)
        parents[max(a, b)] = min(a, b)

    for i, a in enumerate(playlists):
        av = {records[k].version_group_id for k in a.recording_ids}
        for b in playlists[i + 1:]:
            bv = {records[k].version_group_id for k in b.recording_ids}
            overlap = len(av & bv)
            duplicate = overlap / len(av | bv) >= .8 or overlap / min(len(av), len(bv)) >= .9
            if (curators[a.curator_group_id] == curators[b.curator_group_id]
                    or a.duplicate_group_id == b.duplicate_group_id or duplicate
                    or a.playlist_id in b.parent_playlist_ids or b.playlist_id in a.parent_playlist_ids):
                union(a.playlist_id, b.playlist_id)
    return {key: find(key) for key in sorted(parents)}


@dataclass(frozen=True)
class Partition:
    split_id: str
    evaluation_role: Role
    fit_playlists: tuple[str, ...]
    evaluation_playlists: tuple[str, ...]
    fit_recordings: tuple[str, ...]
    evaluation_recordings: tuple[str, ...]
    purged_recordings: tuple[str, ...]
    cluster_map: tuple[tuple[str, str], ...]
    seed: str

    def __post_init__(self):
        from .contracts import sha, text_id
        sha(self.split_id)
        text_id(self.seed)
        require(isinstance(self.evaluation_role, Role), 'partition role required')
        for values in (self.fit_playlists, self.evaluation_playlists, self.fit_recordings, self.evaluation_recordings, self.purged_recordings):
            require(isinstance(values, tuple) and values == tuple(sorted(set(values))), 'partition IDs must be sorted and unique')
        require(not set(self.fit_playlists) & set(self.evaluation_playlists), 'partition source overlap')
        require(not set(self.fit_recordings) & set(self.evaluation_recordings), 'partition recording overlap')
        require(not set(self.fit_recordings) & set(self.purged_recordings), 'purged recording in fit')


def make_partition(corpus, fit_ids, eval_ids, role, seed, allowed=None):
    require(isinstance(role, Role) and role != Role.RANKING, 'explicit evaluation role required')
    playlists = {p.playlist_id: p for p in corpus.playlists}
    fit_ids, eval_ids = set(fit_ids), set(eval_ids)
    require(fit_ids and eval_ids and not fit_ids & eval_ids, 'empty or overlapping source partition')
    require(fit_ids | eval_ids <= set(playlists), 'unknown source partition')
    clusters = source_clusters(corpus)
    require(not {clusters[k] for k in fit_ids} & {clusters[k] for k in eval_ids}, 'curator/duplicate leakage')
    allowed = set(corpus.by_id) if allowed is None else set(allowed)
    evaluation = {r for p in eval_ids for r in playlists[p].recording_ids} & allowed
    initial_fit = {r for p in fit_ids for r in playlists[p].recording_ids} & allowed
    blocked_versions = {corpus.by_id[k].version_group_id for k in evaluation}
    purged = {k for k in initial_fit if corpus.by_id[k].version_group_id in blocked_versions}
    fit = initial_fit - purged
    require(fit and evaluation, 'INSUFFICIENT_DATA after recording/version purge')
    definition = {'fit': sorted(fit_ids), 'evaluation': sorted(eval_ids), 'role': role,
                  'fit_recordings': sorted(fit), 'evaluation_recordings': sorted(evaluation),
                  'seed': seed, 'corpus_id': corpus.identity}
    return Partition(digest(definition), role, tuple(sorted(fit_ids)), tuple(sorted(eval_ids)),
                     tuple(sorted(fit)), tuple(sorted(evaluation)), tuple(sorted(purged)),
                     tuple(sorted(clusters.items())), seed)


def grouped_folds(corpus, playlist_ids, n_folds, role, seed, allowed=None):
    require(isinstance(n_folds, int) and n_folds >= 2, 'at least two grouped folds required')
    clusters = source_clusters(corpus)
    groups = hash_order((clusters[k] for k in playlist_ids), seed)
    require(len(groups) >= n_folds, 'INSUFFICIENT_DATA: too few independent source groups')
    outputs = []
    for fold in range(n_folds):
        held_groups = set(groups[fold::n_folds])
        evaluation = {p for p in playlist_ids if clusters[p] in held_groups}
        outputs.append(make_partition(corpus, set(playlist_ids) - evaluation, evaluation,
                                      role, f'{seed}/{fold}', allowed))
    return tuple(outputs)


@dataclass(frozen=True)
class LockboxMetadata:
    partition: Partition
    opened: bool
    plan_sha256: str

    def __post_init__(self):
        require(self.partition.evaluation_role == Role.LOCKBOX, 'lockbox role mismatch')
        from .contracts import sha
        sha(self.plan_sha256)


def reserve_lockbox(corpus, playlist_ids, count, seed, inspected_recordings=()):
    require(count >= 1, 'lockbox group count required')
    clusters = source_clusters(corpus)
    inspected_versions = {corpus.by_id[k].version_group_id for k in inspected_recordings}
    blocked = {clusters[p.playlist_id] for p in corpus.playlists
               if any(corpus.by_id[k].version_group_id in inspected_versions for k in p.recording_ids)}
    eligible = hash_order({clusters[k] for k in playlist_ids} - blocked, seed)
    require(len(eligible) >= count, 'INSUFFICIENT_DATA: no novel lockbox groups')
    groups = set(eligible[:count])
    held = {p for p in playlist_ids if clusters[p] in groups}
    partition = make_partition(corpus, set(playlist_ids) - held, held, Role.LOCKBOX, seed)
    return LockboxMetadata(partition, False, digest(asdict(partition)))


@dataclass(frozen=True)
class NestedFold:
    outer: Partition
    inner: tuple[Partition, ...]


def nested_plan(corpus, development_ids, *, outer_folds=3, inner_folds=2, seed='nested-v1', allowed=None):
    for p in corpus.playlists:
        if p.playlist_id in development_ids:
            require(p.layer == Layer.ORIGINAL and p.source_ready, 'SOURCE_NOT_READY: only cleared Layer A sources select weights')
    outer = grouped_folds(corpus, development_ids, outer_folds, Role.OUTER, seed, allowed)
    return tuple(NestedFold(p, grouped_folds(corpus, p.fit_playlists, inner_folds, Role.INNER,
                            f'{seed}/{i}/inner', p.fit_recordings)) for i, p in enumerate(outer))


def validate_partition(corpus, partition):
    expected = make_partition(corpus, partition.fit_playlists, partition.evaluation_playlists,
                              partition.evaluation_role, partition.seed,
                              set(partition.fit_recordings + partition.evaluation_recordings + partition.purged_recordings))
    require(partition == expected, 'partition identity/grouping/purge validation failed')


def query_masks(corpus, partition, *, repetitions=8):
    validate_partition(corpus, partition)
    require(repetitions > 0, 'mask repetitions must be positive')
    catalog = Catalog(f'catalog/{partition.split_id}', partition.split_id, partition.evaluation_role,
                      partition.evaluation_recordings, 'full-evaluation-population-minus-seeds-v1')
    allowed = set(catalog.recording_ids)
    playlists = {p.playlist_id: p for p in corpus.playlists}
    clusters = dict(partition.cluster_map)
    queries = []
    excluded = []
    for pid in partition.evaluation_playlists:
        p = playlists[pid]
        # Canonical representative within this playlist; hidden positives later join by version group.
        by_version = {}
        for key in sorted(set(p.recording_ids) & allowed):
            by_version.setdefault(corpus.by_id[key].version_group_id, key)
        ids = tuple(by_version.values())
        if len(ids) < 2:
            excluded.append({'playlist_id': pid, 'reason': 'INSUFFICIENT_DATA_AFTER_PURGE'})
            continue
        hidden_count = max(1, math.ceil(len(ids) * .2))
        for repeat in range(repetitions):
            order = hash_order(ids, f'{partition.seed}/{pid}/{repeat}')
            queries.append(Query(f'{partition.split_id}/{pid}/{repeat}', pid, p.snapshot_id,
                          p.curator_group_id, clusters[pid], p.stratum, p.layer, partition.evaluation_role,
                          partition.split_id, tuple(sorted(order[hidden_count:])), tuple(sorted(order[:hidden_count])),
                          catalog.identity, 'hash-order-ceil20percent-v1'))
    require(bool(queries), 'INSUFFICIENT_DATA: no usable reconstruction queries')
    return catalog, tuple(queries), tuple(excluded)


def audit_roles(corpus, role_playlists, role_recordings):
    """Includes seeds, positives AND challengers, not only labeled endpoints."""
    clusters = source_clusters(corpus)
    roles = sorted(role_playlists, key=lambda role: role.value)
    require(set(role_playlists) == set(role_recordings), 'role manifest mismatch')
    overlaps = []
    for i, a in enumerate(roles):
        require(isinstance(a, Role), 'explicit data role required')
        for b in roles[i + 1:]:
            cg = {clusters[p] for p in role_playlists[a]} & {clusters[p] for p in role_playlists[b]}
            versions = {corpus.by_id[r].version_group_id for r in role_recordings[a]} & {
                corpus.by_id[r].version_group_id for r in role_recordings[b]}
            artists = {x for r in role_recordings[a] for x in corpus.by_id[r].artist_group_ids} & {
                x for r in role_recordings[b] for x in corpus.by_id[r].artist_group_ids}
            overlaps.append({'roles': [a, b], 'source_clusters': sorted(cg), 'versions': sorted(versions),
                             'artist_overlap': sorted(artists)})
    return {'status': 'READY' if all(not r['source_clusters'] and not r['versions'] for r in overlaps) else 'INSUFFICIENT_DATA',
            'overlaps': overlaps, 'artist_disjoint_claim': all(not r['artist_overlap'] for r in overlaps)}
