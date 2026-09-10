"""Pure, label-only mapping. No audio, model, identity, rating or scoring inputs."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import re
import unicodedata

GENRE_FIELDS = ('primary_family', 'secondary_families', 'primary_style', 'secondary_styles')
CONTEXT_FIELDS = ('vocal_role', 'arrangement_focus', 'texture_tags')
MEMBERSHIP_FIELDS = ('broad_families', 'style_neighborhoods', 'scene_contexts')


def normalize_alias(value: str) -> str:
    """Lexical normalization only; composite genres are never split or guessed."""
    text = unicodedata.normalize('NFKC', value).casefold()
    text = re.sub(r'[-_\u2010-\u2015\u2212]', ' ', text)
    text = text.replace('&', ' and ')
    text = text.replace('/', ' / ')
    return ' '.join(text.split())


def compile_map(spec: dict) -> dict:
    if spec['schema_version'] != 'genre-neighborhood-map-v1':
        raise ValueError('unsupported mapper version')
    concepts, lookup = {}, {}
    for concept in spec['concepts']:
        cid = concept['id']
        if cid in concepts:
            raise ValueError(f'duplicate concept: {cid}')
        concepts[cid] = concept
        if concept['mapping_status'] not in ('mapped', 'mapping_review_required', 'unresolved'):
            raise ValueError('invalid mapping status')
        for field in MEMBERSHIP_FIELDS:
            if len(set(concept[field])) != len(concept[field]) or not set(concept[field]) <= set(spec[field]):
                raise ValueError(f'invalid membership: {cid}/{field}')
        if concept['kind'] in ('scene_context', 'ambiguous_context_style') and concept['style_neighborhoods']:
            raise ValueError('context labels cannot imply sonic neighborhoods')
        if concept['mapping_status'] != 'mapped' and (concept['broad_families'] or concept['style_neighborhoods']):
            raise ValueError('unresolved/review-required labels cannot assert sonic memberships')
        for alias in concept['aliases']:
            key = normalize_alias(alias)
            if not key:
                raise ValueError('empty alias')
            if key in lookup and lookup[key] != cid:
                raise ValueError(f'cross-concept alias collision: {alias}')
            lookup[key] = cid
        if normalize_alias(concept['label']) not in lookup or lookup[normalize_alias(concept['label'])] != cid:
            raise ValueError('canonical display label is not registered as its own alias')
    return {'spec': deepcopy(spec), 'concepts': deepcopy(concepts), 'lookup': lookup}


def label_occurrences(profile: dict):
    for field in GENRE_FIELDS:
        value = profile[field]
        if field.startswith('primary_'):
            if not isinstance(value, str):
                raise ValueError(f'{field} must be a string')
            yield field, value
        else:
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                raise ValueError(f'{field} must be a list of strings')
            for index, label in enumerate(value):
                yield f'{field}[{index}]', label


def map_genres(profile: dict, compiled: dict) -> dict:
    """Map only four genre fields; every membership carries its raw-label trace."""
    trace, warnings = [], []
    members = {field: defaultdict(list) for field in MEMBERSHIP_FIELDS}
    canonical = {}
    for path, raw in label_occurrences(profile):
        normalized = normalize_alias(raw)
        cid = compiled['lookup'].get(normalized)
        concept = compiled['concepts'].get(cid)
        tid = f'label-{len(trace) + 1:02d}'
        entry = {'trace_id': tid, 'source_path': path, 'raw_label': raw,
                 'normalized_lookup': normalized, 'canonical_concept_id': cid,
                 'canonical_label': concept['label'] if concept else None,
                 'kind': concept['kind'] if concept else 'unrecognized_label',
                 'mapping_status': concept['mapping_status'] if concept else 'mapping_review_required',
                 'note': concept['note'] if concept else 'No explicit alias. Preserve the label; do not infer a concept.',
                 'review_candidates': concept['review_candidates'] if concept else [],
                 **{field: list(concept[field]) if concept else [] for field in MEMBERSHIP_FIELDS}}
        trace.append(entry)
        if cid:
            canonical.setdefault(cid, {'id': cid, 'label': concept['label'], 'trace_ids': []})['trace_ids'].append(tid)
        for field in MEMBERSHIP_FIELDS:
            for member in entry[field]:
                members[field][member].append(tid)
        if entry['mapping_status'] != 'mapped':
            warnings.append({'code': entry['mapping_status'], 'trace_id': tid, 'message': entry['note']})
        if concept and concept['scene_contexts']:
            warnings.append({'code': 'context_separate_from_sonic_style', 'trace_id': tid, 'message': entry['note']})
        if concept and 'famil' in path and concept['kind'] in ('style', 'style_umbrella'):
            warnings.append({'code': 'style_concept_in_family_slot', 'trace_id': tid,
                             'message': 'Resolve by explicit concept, not by the model field name; original slot retained.'})
        if cid == 'trap':
            warnings.append({'code': 'broad_style_subtype_unspecified', 'trace_id': tid, 'message': entry['note']})
    for concept in canonical.values():
        if len(concept['trace_ids']) > 1:
            warnings.append({'code': 'repeated_concept_not_extra_weight', 'trace_ids': concept['trace_ids'],
                             'message': 'All raw occurrences retained; one set membership, no extra vote or confidence.'})
    return {'raw_genre_labels': {f: deepcopy(profile[f]) for f in GENRE_FIELDS},
            'canonical_labels': list(canonical.values()), 'trace': trace,
            **{field: sorted(members[field]) for field in MEMBERSHIP_FIELDS},
            'membership_evidence': {field: dict(sorted(members[field].items())) for field in MEMBERSHIP_FIELDS},
            'warnings': warnings,
            'mapping_review_required': any(t['mapping_status'] == 'mapping_review_required' for t in trace),
            'has_unresolved_labels': any(t['mapping_status'] == 'unresolved' for t in trace)}


def map_profile(profile: dict, compiled: dict) -> dict:
    """Display-only context is copied separately and cannot influence map_genres."""
    return {**map_genres(profile, compiled),
            'gemini_context_display_only': {f: deepcopy(profile.get(f)) for f in CONTEXT_FIELDS},
            'gemini_status': profile.get('status'), 'gemini_certainty_display_only': deepcopy(profile.get('certainty'))}
