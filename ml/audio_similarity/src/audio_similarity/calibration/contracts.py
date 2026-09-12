"""Immutable research contracts. No inference or production dependencies."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, TypeVar


class ContractError(ValueError):
    pass


class Clap(str, Enum):
    CENTERED = 'centered30_v1'
    METHOD_C = 'method_c_full_song'


class Layer(str, Enum):
    ORIGINAL = 'A'
    POOLED = 'B'
    MIXED = 'C'


class Role(str, Enum):
    RANKING = 'ranking_development'
    INNER = 'inner_validation'
    OUTER = 'outer_validation'
    OUTPUT = 'output_fit'
    POLICY = 'policy_development'
    LOCKBOX = 'ranking_lockbox'
    FINAL = 'final_end_to_end_test'


class State(str, Enum):
    READY = 'READY'
    WAITING = 'WAITING_FOR_FEATURES'
    INSUFFICIENT = 'INSUFFICIENT_DATA'
    UNCALIBRATED = 'NOT_CALIBRATED'
    LABELS = 'LABELS_REQUIRED'
    SOURCE = 'SOURCE_NOT_READY'


def require(condition: bool, message: str):
    if not condition:
        raise ContractError(message)


def text_id(value: str):
    require(isinstance(value, str) and bool(value.strip()), 'nonempty identity required')


def sha(value: str):
    require(isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None,
            'SHA-256 must be explicit lowercase hex')


def finite(value: float):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value), 'finite number required')


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                       allow_nan=False) + '\n').encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def freeze_json(path: Path, value: Any):
    data = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == data, f'immutable artifact differs: {path}')
    else:
        with path.open('xb') as stream:
            stream.write(data)


T = TypeVar('T')


def strict_fields(cls: type[T], value: dict) -> T:
    require(isinstance(value, dict), 'contract must be an object')
    names = {f.name for f in fields(cls)}
    require(not set(value) - names, f'unknown {cls.__name__} fields: {set(value) - names}')
    try:
        return cls(**value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f'invalid {cls.__name__}: {exc}') from exc


@dataclass(frozen=True)
class Recording:
    recording_id: str
    version_group_id: str
    artist_group_ids: tuple[str, ...]
    source_sha256: str
    identity_status: str = 'VERIFIED'

    def __post_init__(self):
        text_id(self.recording_id)
        text_id(self.version_group_id)
        require(isinstance(self.artist_group_ids, tuple) and bool(self.artist_group_ids), 'artist groups required')
        for artist in self.artist_group_ids:
            text_id(artist)
        sha(self.source_sha256)
        require(self.identity_status in {'VERIFIED', 'SYNTHETIC'}, 'recording identity unresolved')


@dataclass(frozen=True)
class SourceGroup:
    group_id: str
    curator_id: str
    provenance: str

    def __post_init__(self):
        for value in asdict(self).values():
            text_id(value)


@dataclass(frozen=True)
class Playlist:
    playlist_id: str
    snapshot_id: str
    curator_group_id: str
    duplicate_group_id: str
    stratum: str
    layer: Layer
    cohort: str
    recording_ids: tuple[str, ...]
    source_title: str
    source_description: str
    declared_intent: str
    membership_source: str
    discovery_source: str
    observed_at: str
    membership_permission: str
    audio_permission: str
    remote_processing_permission: str
    redistribution_permission: str
    parent_playlist_ids: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ('playlist_id', 'snapshot_id', 'curator_group_id', 'duplicate_group_id',
                     'stratum', 'cohort', 'source_title', 'declared_intent', 'membership_source',
                     'discovery_source', 'observed_at'):
            text_id(getattr(self, name))
        require(isinstance(self.layer, Layer), 'explicit benchmark layer required')
        require(isinstance(self.recording_ids, tuple) and len(set(self.recording_ids)) == len(self.recording_ids)
                and bool(self.recording_ids), 'playlist IDs must be unique and nonempty')
        require(isinstance(self.parent_playlist_ids, tuple), 'parent source IDs must be immutable')
        require(self.layer == Layer.ORIGINAL or bool(self.parent_playlist_ids)
                or self.cohort == 'real_mixed', 'derived cohorts need parent source identities')
        for name in ('membership_permission', 'audio_permission', 'remote_processing_permission',
                     'redistribution_permission'):
            require(getattr(self, name) in {'CLEARED', 'PENDING', 'SYNTHETIC', 'NOT_APPLICABLE'},
                    f'invalid permission state: {name}')

    @property
    def source_ready(self):
        return self.membership_permission in {'CLEARED', 'SYNTHETIC'} and self.audio_permission in {'CLEARED', 'SYNTHETIC'}


@dataclass(frozen=True)
class Corpus:
    recordings: tuple[Recording, ...]
    playlists: tuple[Playlist, ...]
    groups: tuple[SourceGroup, ...]
    evidence_kind: str

    def __post_init__(self):
        require(all(isinstance(value, tuple) for value in (self.recordings, self.playlists, self.groups)), 'corpus containers must be immutable tuples')
        require(self.evidence_kind in {'SYNTHETIC', 'REAL'}, 'evidence kind required')
        ids = [r.recording_id for r in self.recordings]
        require(len(ids) == len(set(ids)), 'duplicate recording identity')
        pids = [p.playlist_id for p in self.playlists]
        require(len(pids) == len(set(pids)), 'duplicate playlist identity')
        gids = [g.group_id for g in self.groups]
        require(len(gids) == len(set(gids)), 'duplicate source group identity')
        for p in self.playlists:
            require(set(p.recording_ids) <= set(ids), 'unknown playlist recording')
            require(p.curator_group_id in gids, 'unknown curator group')
            require(set(p.parent_playlist_ids) <= set(pids), 'unknown derived source')
        if self.evidence_kind == 'SYNTHETIC':
            require(all(r.identity_status == 'SYNTHETIC' for r in self.recordings), 'mixed synthetic/real identities')

    @property
    def by_id(self):
        return {r.recording_id: r for r in self.recordings}

    @property
    def identity(self):
        return digest(asdict(self))

    @classmethod
    def from_dict(cls, value):
        require(set(value) == {'recordings', 'playlists', 'groups', 'evidence_kind'}, 'corpus schema mismatch')
        recordings = tuple(strict_fields(Recording, dict(r, artist_group_ids=tuple(r['artist_group_ids'])))
                           for r in value['recordings'])
        playlists = tuple(strict_fields(Playlist, dict(p, layer=Layer(p['layer']),
                          recording_ids=tuple(p['recording_ids']),
                          parent_playlist_ids=tuple(p.get('parent_playlist_ids', ())))) for p in value['playlists'])
        return cls(recordings, playlists, tuple(strict_fields(SourceGroup, g) for g in value['groups']), value['evidence_kind'])


@dataclass(frozen=True)
class Catalog:
    catalog_id: str
    split_id: str
    role: Role
    recording_ids: tuple[str, ...]
    candidate_policy_id: str

    def __post_init__(self):
        for value in (self.catalog_id, self.split_id, self.candidate_policy_id):
            text_id(value)
        require(isinstance(self.role, Role), 'catalog role required')
        require(isinstance(self.recording_ids, tuple) and bool(self.recording_ids)
                and self.recording_ids == tuple(sorted(set(self.recording_ids))), 'catalog must be sorted/unique')

    @property
    def identity(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class Query:
    query_id: str
    playlist_id: str
    snapshot_id: str
    curator_group_id: str
    cluster_id: str
    stratum: str
    layer: Layer
    role: Role
    split_id: str
    seed_ids: tuple[str, ...]
    hidden_ids: tuple[str, ...]
    catalog_hash: str
    mask_protocol_id: str

    def __post_init__(self):
        for name in ('query_id', 'playlist_id', 'snapshot_id', 'curator_group_id', 'cluster_id',
                     'stratum', 'split_id', 'mask_protocol_id'):
            text_id(getattr(self, name))
        sha(self.catalog_hash)
        require(isinstance(self.layer, Layer) and isinstance(self.role, Role), 'query roles required')
        require(isinstance(self.seed_ids, tuple) and isinstance(self.hidden_ids, tuple), 'query masks must be immutable tuples')
        require(bool(self.seed_ids) and bool(self.hidden_ids), 'empty reconstruction mask')
        require(len(set(self.seed_ids)) == len(self.seed_ids) and len(set(self.hidden_ids)) == len(self.hidden_ids), 'duplicate mask IDs')
        require(not set(self.seed_ids) & set(self.hidden_ids), 'seed/hidden overlap')
