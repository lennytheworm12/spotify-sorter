"""Strict, no-repair validation of the pilot's bounded JSON Schema and semantics."""
from __future__ import annotations

import json
import math


class InvalidProfile(ValueError):
    pass


def strict_json(text: str):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InvalidProfile(f'duplicate JSON key: {key}')
            result[key] = value
        return result

    def constant(value):
        raise InvalidProfile(f'non-finite JSON constant: {value}')

    try:
        return json.loads(text, object_pairs_hook=object_pairs, parse_constant=constant)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidProfile('response is not a JSON object without repair') from exc


def validate_schema(value, schema: dict, path: str = '$') -> None:
    """Evaluate only the exact draft's schema vocabulary; reject unknown keywords."""
    supported = {'type', 'properties', 'required', 'additionalProperties', 'items',
                 'maxItems', 'enum', 'minimum'}
    if set(schema) - supported:
        raise InvalidProfile(f'{path}: unsupported schema keyword')
    kind = schema['type']
    correct_type = {
        'object': isinstance(value, dict), 'array': isinstance(value, list),
        'string': isinstance(value, str),
        'number': type(value) in (int, float) and math.isfinite(value),
    }
    if not correct_type.get(kind, False):
        raise InvalidProfile(f'{path}: expected {kind}')
    if 'enum' in schema and value not in schema['enum']:
        raise InvalidProfile(f'{path}: outside enum')
    if kind == 'object':
        properties = schema.get('properties', {})
        if set(schema.get('required', [])) - set(value):
            raise InvalidProfile(f'{path}: missing required fields')
        if schema.get('additionalProperties') is False and set(value) - set(properties):
            raise InvalidProfile(f'{path}: unexpected fields')
        for key, child in value.items():
            if key in properties:
                validate_schema(child, properties[key], f'{path}.{key}')
    elif kind == 'array':
        if len(value) > schema.get('maxItems', len(value)):
            raise InvalidProfile(f'{path}: too many items')
        for i, child in enumerate(value):
            validate_schema(child, schema['items'], f'{path}[{i}]')
    elif kind == 'number' and value < schema.get('minimum', value):
        raise InvalidProfile(f'{path}: below minimum')


def validate_profile(text: str, *, schema: dict, allowed_families: dict,
                     duration_seconds: float) -> dict:
    profile = strict_json(text)
    validate_schema(profile, schema)
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise InvalidProfile('invalid full-recording duration')
    for field, primary in [('secondary_families', 'primary_family'),
                           ('secondary_styles', 'primary_style'), ('texture_tags', None)]:
        values = profile[field]
        if len(set(values)) != len(values) or (primary and profile[primary] in values):
            raise InvalidProfile(f'{field}: duplicate assignment')
    families = {profile['primary_family'], *profile['secondary_families']}
    for style in [profile['primary_style'], *profile['secondary_styles']]:
        if style != 'unknown' and not families.intersection(allowed_families[style]):
            raise InvalidProfile('style has no compatible chosen family')
    for evidence in profile['audio_evidence']:
        if not 0 <= evidence['start_seconds'] < evidence['end_seconds'] <= duration_seconds:
            raise InvalidProfile('audio evidence outside supplied recording or empty interval')
        if not 1 <= len(evidence['observation'].strip()) <= 220:
            raise InvalidProfile('audio observation must contain 1–220 characters')
    for style in profile['unmapped_styles']:
        if not style['proposed_label'].strip() or not style['audible_basis'].strip():
            raise InvalidProfile('unmapped style requires label and audible basis')
    if profile['status'] == 'not_music':
        if (profile['primary_family'] != 'unknown' or profile['primary_style'] != 'unknown'
                or profile['secondary_families'] or profile['secondary_styles']):
            raise InvalidProfile('not_music must have unknown family/style and no secondaries')
    if profile['primary_family'] == 'unknown' and profile['status'] == 'classified':
        raise InvalidProfile('unknown primary family cannot be classified')
    # Unknown style, vocabulary proposals, and tentative/unresolved certainty are
    # valid scientific outcomes, never transport or schema errors.
    return profile
