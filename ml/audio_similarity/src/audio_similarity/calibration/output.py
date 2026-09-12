"""Descriptive F/Q/reference output; suitability fitting and policies are separate gates."""
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Protocol

import numpy as np

from .contracts import Role, State, digest, finite, require, sha, text_id
from .ranking import Model, distinct_ids, playlist_score
from .splits import hash_order

REFERENCE_PROTOCOL = 'equal-seed-min20-m20-eight-hash-subsets-v1'


@dataclass(frozen=True)
class RankerFreeze:
    model: Model
    feature_bundle_sha256: str
    mapper_sha256: str
    prompt_sha256: str
    source_policy_sha256: str
    candidate_policy_id: str
    selection_evidence_sha256: str | None = None
    selected: bool = False
    aggregator_id: str = 'complete-F-top3-mean-v1'
    tie_policy: str = 'raw-score-desc-recording-id-asc-v1'

    def __post_init__(self):
        for name in ('feature_bundle_sha256', 'mapper_sha256', 'prompt_sha256', 'source_policy_sha256'):
            sha(getattr(self, name))
        text_id(self.candidate_policy_id)
        require(self.aggregator_id == 'complete-F-top3-mean-v1' and self.tie_policy == 'raw-score-desc-recording-id-asc-v1',
                'ranker aggregator/tie contract changed')
        if self.selected:
            sha(self.selection_evidence_sha256)

    @property
    def identity(self):
        return digest(asdict(self))


def reference_percentile(features, model, candidate, playlist_ids, *, snapshot_id):
    playlist_ids = tuple(playlist_ids)
    invalid = candidate not in features.records or not set(playlist_ids) <= set(features.records)
    members = () if invalid else distinct_ids(features, playlist_ids)
    base = {'reference_protocol_id': REFERENCE_PROTOCOL, 'reference_count': len(members),
            'reference_seed_size': None, 'subsets_per_query': 8, 'member_reference_score': None,
            'member_reference_percentile': None, 'status': 'INSUFFICIENT_DATA'}
    if invalid:
        return {**base, 'reason': 'candidate/reference recording unavailable in feature bundle'}
    if len(members) < 20:
        return {**base, 'reason': 'fewer than 20 distinct usable reference recordings'}
    m = min(20, len(members) - 1)
    schedule = digest([REFERENCE_PROTOCOL, snapshot_id, members])

    def reference(key):
        available = distinct_ids(features, members, exclude=(key,))
        require(len(available) >= m, 'insufficient equal-size reference support')
        subsets = [hash_order(available, f'{schedule}/{key}/{i}')[:m] for i in range(8)]
        scores = [playlist_score(features, model, key, subset)['Q'] for subset in subsets]
        require(all(value is not None for value in scores), 'invalid reference scores')
        return {'recording_id': key, 'mean': sum(scores) / 8,
                'subset_scores': scores, 'subset_std': float(np.std(scores)), 'subsets': subsets}

    values = [reference(key) for key in members]
    candidate_value = reference(candidate)
    q = candidate_value['mean']
    u = (sum(row['mean'] < q for row in values) + .5 * sum(row['mean'] == q for row in values)) / len(values)
    return {**base, 'status': 'READY', 'reference_seed_size': m, 'member_reference_score': q,
            'member_reference_percentile': u, 'schedule_sha256': schedule,
            'candidate_reference': candidate_value, 'member_references': values,
            'display_label': 'member-reference percentile, equal-sized seed comparison'}


def descriptive_row(features, freeze, candidate, seeds, *, snapshot_id, observed_membership='unlabeled'):
    require(freeze.feature_bundle_sha256 == features.identity, 'ranker feature bundle changed')
    require(freeze.mapper_sha256 == features.identities['Jc'].mapper_sha256
            and freeze.prompt_sha256 == features.identities['Jc'].prompt_sha256, 'ranker mapper/prompt changed')
    require(observed_membership in {'observed_member', 'observed_positive', 'unlabeled'}, 'invalid membership evidence')
    if features.corpus.evidence_kind != 'SYNTHETIC' and not freeze.selected:
        return {'status': 'NOT_CALIBRATED', 'reason': 'ranking model selection/freeze required',
                'suitability_probability': None, 'decision': 'not_calibrated'}
    raw = playlist_score(features, freeze.model, candidate, seeds)
    reference = reference_percentile(features, freeze.model, candidate, seeds, snapshot_id=snapshot_id)
    return {'ranking_model_id': freeze.identity, 'representation_manifest_hash': features.identity,
            'mapper_hash': freeze.mapper_sha256, 'playlist_snapshot_id': snapshot_id,
            'candidate_recording_id': candidate, 'candidate_policy_id': freeze.candidate_policy_id,
            'observed_membership': observed_membership, 'raw_playlist_score': raw['Q'],
            'seed_count': raw['seed_count'], 'top_support': raw['top_support'], **reference,
            'calibration_id': None, 'policy_id': None, 'suitability_probability': None,
            'calibration_status': 'LABELS_REQUIRED', 'label_target': None, 'domain_status': 'UNVALIDATED',
            'strictness': None, 'threshold': None, 'threshold_domain': None, 'decision': 'not_calibrated',
            'warnings': ['Synthetic development preset, not selected'] if not freeze.selected else []}


class Suitability(str, Enum):
    SUITABLE = 'suitable'
    UNSUITABLE = 'unsuitable'
    UNCERTAIN = 'uncertain'
    CANNOT_ASSESS = 'cannot_assess'


@dataclass(frozen=True)
class SuitabilityLabel:
    candidate_recording_id: str
    playlist_snapshot_id: str
    label: Suitability
    target_id: str
    reviewer_id: str
    source_group_id: str
    candidate_policy_id: str
    role: Role
    provenance_sha256: str
    origin: str = 'human_adjudicated'

    def __post_init__(self):
        for name in ('candidate_recording_id', 'playlist_snapshot_id', 'target_id', 'reviewer_id',
                     'source_group_id', 'candidate_policy_id'):
            text_id(getattr(self, name))
        require(isinstance(self.label, Suitability) and isinstance(self.role, Role), 'explicit suitability/role required')
        require(self.origin == 'human_adjudicated', 'membership, genre and model outputs are not suitability labels')
        sha(self.provenance_sha256)


def suitability_readiness(labels, ranker, *, independent_roles_verified=False, sampling_protocol_sha256=None):
    counts = {label.value: sum(row.label == label for row in labels) for label in Suitability}
    if not ranker.selected:
        state = State.UNCALIBRATED
    elif not labels:
        state = State.LABELS
    elif len({row.target_id for row in labels}) != 1 or len({row.candidate_policy_id for row in labels}) != 1:
        state = State.SOURCE
    elif not all(row.role == Role.OUTPUT for row in labels):
        state = State.SOURCE
    elif not counts['suitable'] or not counts['unsuitable']:
        state = State.LABELS
    elif not independent_roles_verified or sampling_protocol_sha256 is None:
        state = State.INSUFFICIENT
    else:
        sha(sampling_protocol_sha256)
        # This is structural readiness only; no sample size or validation adequacy is asserted.
        state = State.READY
    return {'status': state, 'counts': counts, 'independent_groups': len({r.source_group_id for r in labels}),
            'scope': 'structural readiness only; reviewed power/domain/regularization plan still required'}


class MonotoneCalibrationBackend(Protocol):
    """Future implementations may fit sigmoid(a*Q+b), a>=0, or reviewed isotonic."""
    def fit_playlist_q(self, scores, labels, *, frozen_protocol): ...


@dataclass(frozen=True)
class CalibrationHook:
    method: str
    readiness: State
    protocol_sha256: str | None
    score_domain: str = 'raw_playlist_Q'

    def validate_fit_request(self):
        require(self.readiness == State.READY, 'NOT_CALIBRATED: fitting gate is not READY')
        require(self.method in {'sigmoid', 'isotonic'}, 'unsupported monotone calibration')
        require(self.score_domain == 'raw_playlist_Q', 'playlist calibrator cannot consume F or percentile')
        sha(self.protocol_sha256)
        # No backend is installed or called by this scaffolding.
        return {'method': self.method, 'score_domain': self.score_domain, 'protocol_sha256': self.protocol_sha256}


class Strictness(str, Enum):
    BROAD = 'Broad'
    BALANCED = 'Balanced'
    TIGHT = 'Tight'


@dataclass(frozen=True)
class ValidatedThresholds:
    broad: float
    balanced: float
    tight: float
    ranking_model_id: str
    candidate_policy_id: str
    validation_sha256: str
    domain_id: str
    evidence_kind: str
    threshold_domain: str = 'raw_playlist_Q'

    def __post_init__(self):
        for value in (self.broad, self.balanced, self.tight):
            finite(value)
        require(self.broad <= self.balanced <= self.tight, 'strictness thresholds must be ordered')
        require(self.threshold_domain == 'raw_playlist_Q', 'probability thresholds need a future validated mapping adapter')
        require(self.evidence_kind in {'SYNTHETIC', 'VALIDATED'}, 'threshold validation evidence required')
        sha(self.ranking_model_id)
        sha(self.validation_sha256)
        text_id(self.candidate_policy_id)
        text_id(self.domain_id)


def preview(features, ranker, candidates, seeds, *, snapshot_id, strictness, policy=None, domain_id=None):
    require(isinstance(strictness, Strictness), 'unknown strictness')
    require(ranker.feature_bundle_sha256 == features.identity, 'ranker bundle changed')
    seeds = tuple(seeds)  # Snapshot once; accepted candidates never enter the seed context.
    groups = {features.records[s].version_group_id for s in seeds}
    rows = []
    threshold = None
    supported = policy is None or policy.domain_id == domain_id
    if policy is not None:
        require(policy.ranking_model_id == ranker.identity and policy.candidate_policy_id == ranker.candidate_policy_id,
                'policy belongs to a different ranker/candidate protocol')
        require((policy.evidence_kind == 'SYNTHETIC' and features.corpus.evidence_kind == 'SYNTHETIC')
                or (policy.evidence_kind == 'VALIDATED' and ranker.selected), 'unvalidated policy')
        threshold = {Strictness.BROAD: policy.broad, Strictness.BALANCED: policy.balanced,
                     Strictness.TIGHT: policy.tight}[strictness] if supported else None
    for candidate in sorted(set(candidates)):
        raw = playlist_score(features, ranker.model, candidate, seeds)
        if features.records[candidate].version_group_id in groups:
            decision = 'already_present'
        elif raw['Q'] is None:
            decision = 'needs_review'
        elif threshold is None:
            decision = 'not_calibrated' if policy is None else 'needs_review'
        else:
            decision = 'recommend' if raw['Q'] >= threshold else 'below_requested_fit'
        rows.append({'candidate_recording_id': candidate, 'raw_playlist_score': raw['Q'],
                     'decision': decision, 'top_support': raw['top_support']})
    rows.sort(key=lambda r: (r['raw_playlist_score'] is None, -(r['raw_playlist_score'] or 0), r['candidate_recording_id']))
    return {'status': 'NOT_CALIBRATED' if policy is None else 'READY' if supported else 'NEEDS_REVIEW', 'ranking_model_id': ranker.identity,
            'snapshot_id': snapshot_id, 'seed_snapshot_sha256': digest(seeds), 'strictness': strictness,
            'threshold': threshold, 'threshold_domain': policy.threshold_domain if policy else None,
            'rows': rows, 'playlist_writes': 0}
