import copy
import json
from pathlib import Path

import pytest

from audio_similarity.gemini_style_pilot.contract import extract_contract, freeze_contract
from audio_similarity.gemini_style_pilot.inputs import ModelInput, profile_cache_key, request_body
from audio_similarity.gemini_style_pilot.validation import InvalidProfile, validate_profile, validate_schema
from audio_similarity.gemini_style_pilot.duration_revision import bounded_schema


FIXTURES = Path(__file__).parent / 'fixtures/gemini_style_pilot'
SCHEMA = json.loads((FIXTURES / 'response_schema.json').read_text())
FAMILIES = json.loads((FIXTURES / 'style_allowed_families.json').read_text())


def profile():
    return {
        'status': 'classified', 'primary_family': 'hip_hop_rap', 'secondary_families': [],
        'primary_style': 'unknown', 'secondary_styles': [], 'vocal_role': 'unclear',
        'arrangement_focus': 'unclear', 'texture_tags': [], 'active_section_density': 'unclear',
        'section_variation': 'cannot_assess', 'certainty': {'family': 'clear', 'style': 'unresolved'},
        'audio_evidence': [], 'unmapped_styles': [],
    }


def validate(value):
    return validate_profile(json.dumps(value), schema=SCHEMA, allowed_families=FAMILIES, duration_seconds=100)


def test_vocabulary_gap_uncertainty_and_nonmusic_are_valid_outcomes():
    value = profile()
    value['unmapped_styles'] = [{'proposed_label': 'unlisted synthetic example', 'audible_basis': 'synthetic fixture only'}]
    assert validate(value) == value
    value.update(status='uncertain', primary_family='unknown')
    value['certainty']['family'] = 'unresolved'
    assert validate(value) == value
    value.update(status='not_music', unmapped_styles=[])
    assert validate(value) == value


@pytest.mark.parametrize('change', [
    {'primary_style': 'made_up'},
    {'extra': 'not allowed'},
    {'primary_style': 'indie_rock'},
    {'secondary_families': ['unknown']},
    {'secondary_families': ['pop', 'pop']},
    {'secondary_families': ['hip_hop_rap']},
    {'texture_tags': ['hazy', 'hazy']},
    {'texture_tags': ['hazy', 'layered', 'clean', 'acoustic']},
    {'status': 'not_music'},
    {'primary_family': 'unknown'},
    {'audio_evidence': [{'start_seconds': 90, 'end_seconds': 101, 'observation': 'past end'}]},
    {'audio_evidence': [{'start_seconds': 50, 'end_seconds': 50, 'observation': 'empty interval'}]},
    {'audio_evidence': [{'start_seconds': True, 'end_seconds': 2, 'observation': 'bool is not time'}]},
    {'audio_evidence': [{'start_seconds': 0, 'end_seconds': 2, 'observation': 'x' * 221}]},
    {'unmapped_styles': [{'proposed_label': '', 'audible_basis': 'missing label'}]},
])
def test_invalid_profile_is_rejected_without_repair(change):
    value = profile()
    value.update(change)
    before = copy.deepcopy(value)
    with pytest.raises(InvalidProfile):
        validate(value)
    assert value == before


@pytest.mark.parametrize('text', ['```json\n{}\n```', '{"x": 1, "x": 2}', '{"x": NaN}', '{}'])
def test_invalid_json_or_missing_fields_are_not_repaired(text):
    with pytest.raises(InvalidProfile):
        validate_profile(text, schema=SCHEMA, allowed_families=FAMILIES, duration_seconds=100)


def test_cross_family_style_and_exact_end_timestamp_are_supported():
    value = profile()
    value.update(primary_style='pop_rnb', secondary_families=['pop'])
    value['audio_evidence'] = [{'start_seconds': 0, 'end_seconds': 100, 'observation': 'synthetic observation'}]
    assert validate(value) == value
    with pytest.raises(InvalidProfile, match='unsupported schema'):
        validate_schema('anything', {'type': 'string', 'minLength': 2})


def test_duration_schema_is_only_a_physical_bound_and_rejects_out_of_range_without_repair():
    original = copy.deepcopy(SCHEMA)
    revised = bounded_schema(SCHEMA, 100.25)
    assert SCHEMA == original
    restored = copy.deepcopy(revised)
    fields = restored['properties']['audio_evidence']['items']['properties']
    for key in ('start_seconds', 'end_seconds'):
        assert fields[key].pop('maximum') == 100.25
    assert restored == SCHEMA
    value = profile()
    value['audio_evidence'] = [{'start_seconds': 0, 'end_seconds': 100.25, 'observation': 'synthetic'}]
    validate_schema(value, revised)
    value['audio_evidence'][0]['end_seconds'] = 100.25001
    with pytest.raises(InvalidProfile, match='above maximum'):
        validate_schema(value, revised)
    assert value['audio_evidence'][0]['end_seconds'] == 100.25001
    with pytest.raises(ValueError, match='invalid recording'):
        bounded_schema(SCHEMA, float('nan'))


def document():
    ids = [f'A{i:02d}' for i in range(1, 11)] + [f'C{i:02d}' for i in range(1, 7)]
    table = '\n'.join(f'| {pid} | slice | PRIVATE TITLE | [{i:022d}](https://open.spotify.com/track/{i:022d}) | PRIVATE EXPECTATION | PRIVATE STYLE | PRIVATE RATING |' for i, pid in enumerate(ids))
    styles = '\n'.join(f'| {style} | {", ".join(families)} | DEFINITION |' for style, families in FAMILIES.items())
    return ('### Candidate manifest and pre-run hypotheses\n' + table
            + '\n**Resolution notes\nPRIVATE RATING AND EXPECTATIONS\n## 3. Operational ontology\n'
            + '### 3.2 Allowed styles\n' + styles
            + '\n### 3.3 Vocal roles\nSAFE ROLES\n## 4. Exact JSON response contract\n```json\n'
            + json.dumps(SCHEMA) + '\n```\n')


def test_contract_extracts_all_identities_but_never_private_hypotheses_into_model_files(tmp_path):
    design, prompt, destination = tmp_path / 'design.md', tmp_path / 'prompt.txt', tmp_path / 'frozen'
    design.write_text(document())
    prompt.write_text('SUPPLIED PROMPT')
    extracted = freeze_contract(design, prompt, destination)
    assert len(extracted['candidates']) == 16
    assert extracted['style_allowed_families'] == FAMILIES
    before = {p: p.read_bytes() for p in destination.rglob('*') if p.is_file()}
    freeze_contract(design, prompt, destination)
    assert before == {p: p.read_bytes() for p in destination.rglob('*') if p.is_file()}
    assert all(b'PRIVATE' not in p.read_bytes() for p in (destination / 'model').iterdir())
    with pytest.raises(ValueError, match='complete ordered'):
        extract_contract(document().replace('| A02 |', '| A01 |'))
    prompt.write_text('CHANGED')
    with pytest.raises(ValueError, match='frozen artifact differs'):
        freeze_contract(design, prompt, destination)


def test_request_payload_contains_only_permitted_context_and_cache_key_pins_all_inputs():
    track = ModelInput('N001', 120.25, 'a' * 64)
    config = {'temperature': 1, 'topP': 0.95, 'topK': 64, 'candidateCount': 1,
              'maxOutputTokens': 8192, 'thinkingConfig': {'thinkingLevel': 'LOW', 'includeThoughts': False},
              'responseMimeType': 'application/json'}
    body = request_body(track, file_uri='https://generativelanguage.googleapis.com/v1beta/files/abc-123',
                        prompt='SUPPLIED PROMPT', ontology='SAFE ONTOLOGY', schema=SCHEMA, generation_config=config)
    assert set(body) == {'systemInstruction', 'contents', 'generationConfig'}
    parts = body['contents'][0]['parts']
    assert len(parts) == 2 and parts[0]['text'] == 'Clip: N001\nFull recording duration in seconds: 120.250000000'
    assert body['generationConfig']['responseJsonSchema'] == SCHEMA
    kwargs = {'model_id': 'gemini-3.8-flash', 'generation_config': config, 'prompt_sha256': 'b'*64,
              'ontology_sha256': 'c'*64, 'schema_sha256': 'd'*64, 'implementation_sha256': 'e'*64}
    key = profile_cache_key(track, **kwargs)
    for field in kwargs:
        changed = {**kwargs, field: {'temperature': 0} if field == 'generation_config' else 'changed'}
        assert profile_cache_key(track, **changed) != key
    assert profile_cache_key(ModelInput('N001', 120.25, 'f'*64), **kwargs) != key
    assert profile_cache_key(ModelInput('N002', 120.25, 'a'*64), **kwargs) != key
    with pytest.raises(ValueError, match='neutral audio ID'):
        ModelInput('PRIVATE SONG NAME', 120, 'a'*64)
