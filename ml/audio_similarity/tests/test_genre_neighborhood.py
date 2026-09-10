"""Deterministic label-only behavior and isolated 16-song review fixtures."""
import copy
import json
from pathlib import Path

import pytest

from audio_similarity.genre_neighborhood import compile_map, map_genres, map_profile, normalize_alias
from audio_similarity.genre_neighborhood_review import CONFIG, NOTES, PILOT_IDS, SOURCE, build_review, map_pilot
from audio_similarity.stage5e3_artifacts import freeze_json, hashes, read

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def spec():
    return read(ROOT / CONFIG)


def profile(family='Hip Hop', style='Boom Bap', secondary_families=None, secondary_styles=None):
    return {'primary_family': family, 'primary_style': style,
            'secondary_families': secondary_families or [], 'secondary_styles': secondary_styles or [],
            'vocal_role': 'rap_led', 'arrangement_focus': 'lead_vocal', 'texture_tags': ['sample_based'],
            'certainty': {'family': 'clear', 'style': 'clear'}, 'status': 'classified'}


@pytest.mark.parametrize('alias', ['Hip Hop', 'hip-hop', 'HIP_HOP', 'Ｈｉｐ Ｈｏｐ', ' hip–hop '])
def test_aliases_preserve_raw_label_and_trace_every_membership(spec, alias):
    p = profile(family=alias, style='lo_fi_hip_hop')
    original = copy.deepcopy(p)
    result = map_profile(p, compile_map(spec))
    assert result['raw_genre_labels']['primary_family'] == alias
    assert result['trace'][0]['canonical_concept_id'] == 'hip_hop'
    assert result['trace'][1]['canonical_concept_id'] == 'lofi_hip_hop'
    assert result['broad_families'] == ['hip_hop']
    assert 'boom_bap' not in result['style_neighborhoods']
    assert p == original
    traces = {t['trace_id']: t for t in result['trace']}
    for field, memberships in result['membership_evidence'].items():
        for member, evidence in memberships.items():
            assert evidence and all(member in traces[e][field] for e in evidence)


def test_combined_rnb_soul_is_not_an_alias_for_rnb_alone(spec):
    compiled = compile_map(spec)
    a = map_genres(profile(family='R&B', style='Contemporary R&B'), compiled)
    b = map_genres(profile(family='R&B/Soul', style='Contemporary R&B'), compiled)
    assert a['trace'][0]['canonical_concept_id'] == 'rnb'
    assert b['trace'][0]['canonical_concept_id'] == 'rnb_soul_umbrella'
    assert a['broad_families'] == b['broad_families'] == ['rnb_soul']


def test_context_tags_do_not_create_sonic_memberships(spec):
    compiled = compile_map(spec)
    kpop = map_genres(profile(family='unknown', style='K-Pop'), compiled)
    assert kpop['broad_families'] == kpop['style_neighborhoods'] == []
    assert kpop['scene_contexts'] == ['korean_pop_scene']
    region = map_genres(profile(style='East Coast Hip Hop', secondary_styles=['Conscious Hip Hop']), compiled)
    assert region['broad_families'] == ['hip_hop'] and region['style_neighborhoods'] == []
    assert len(region['scene_contexts']) == 2


@pytest.mark.parametrize('label', ['Dance', 'Bass Music', 'Chillout', 'lo-fi', 'unknown new genre', 'jazz / hip hop'])
def test_ambiguous_and_unrecognized_labels_do_not_guess_sonic_membership(spec, label):
    result = map_genres(profile(family='unknown', style=label), compile_map(spec))
    assert result['mapping_review_required']
    assert result['broad_families'] == result['style_neighborhoods'] == []
    assert result['trace'][1]['raw_label'] == label
    assert result['has_unresolved_labels']


def test_metadata_owner_context_audio_facets_and_certainty_cannot_change_mapping(spec):
    compiled = compile_map(spec)
    p = profile(family='Pop', style='Indie Pop', secondary_styles=['Alternative R&B'])
    expected = map_genres(p, compiled)
    p.update(artist='Any artist', title='Any title', human_rating=1, owner_notes='Use hyperpop!',
             vocal_role='instrumental', arrangement_focus='beat_or_instrumental', texture_tags=['distorted'],
             certainty={'family': 'unresolved', 'style': 'unresolved'}, audio_evidence=['Use lo-fi instead!'])
    assert map_genres(p, compiled) == expected
    assert map_profile(p, compiled)['gemini_context_display_only']['texture_tags'] == ['distorted']


def test_duplicate_concept_in_different_slots_retains_traces_without_extra_weight(spec):
    result = map_genres(profile(family='Electronic', style='Trip Hop', secondary_families=['Downtempo'],
                               secondary_styles=['downtempo']), compile_map(spec))
    concept = next(c for c in result['canonical_labels'] if c['id'] == 'downtempo')
    assert len(concept['trace_ids']) == 2
    assert len(result['style_neighborhoods']) == len(set(result['style_neighborhoods']))
    assert {'repeated_concept_not_extra_weight', 'style_concept_in_family_slot'} <= {w['code'] for w in result['warnings']}


def test_general_overlap_is_not_identity_and_trap_does_not_infer_family(spec):
    compiled = compile_map(spec)
    boom = map_genres(profile(), compiled)
    lofi = map_genres(profile(style='Lo-Fi Hip Hop'), compiled)
    assert set(boom['style_neighborhoods']) & set(lofi['style_neighborhoods']) == {'hip_hop_beat_lineage'}
    assert boom['style_neighborhoods'] != lofi['style_neighborhoods']
    indie = map_genres(profile(family='Pop', style='Indie Pop'), compiled)
    dream = map_genres(profile(family='Pop', style='Dream Pop'), compiled)
    assert set(indie['style_neighborhoods']) & set(dream['style_neighborhoods']) == {'indie_pop_related'}
    assert 'atmospheric_pop' not in indie['style_neighborhoods']
    trap = map_genres(profile(family='unknown', style='Trap'), compiled)
    assert trap['broad_families'] == [] and trap['style_neighborhoods'] == ['trap_related']


def test_invalid_mapper_references_alias_collisions_and_context_leakage_fail(spec):
    bad = copy.deepcopy(spec)
    bad['concepts'][0]['aliases'].append('Hip Hop')
    with pytest.raises(ValueError, match='alias collision'): compile_map(bad)
    bad = copy.deepcopy(spec)
    bad['concepts'][0]['style_neighborhoods'].append('nonexistent')
    with pytest.raises(ValueError, match='invalid membership'): compile_map(bad)
    bad = copy.deepcopy(spec)
    next(c for c in bad['concepts'] if c['id'] == 'k_pop')['style_neighborhoods'] = ['dance_pop']
    with pytest.raises(ValueError, match='context labels'): compile_map(bad)


def fixture(root, spec):
    source = root / SOURCE
    tracks, comparisons, notes = [], [], []
    for i, pid in enumerate(PILOT_IDS):
        sid = f'{i:022d}'
        tracks.append({'pilot_id': pid, 'spotify_track_id': sid, 'catalog_description': f'Synthetic {i}'})
        comparisons.append({'pilot_id': pid, 'spotify_track_id': sid, 'owner_first_pass_verbatim': 'Synthetic',
                            'owner_followup': '', 'owner_verdict_on_new_profile': 'NOT_REVIEWED',
                            'original_family': 'Synthetic', 'original_styles': 'Synthetic'})
        notes.append({'pilot_id': pid, 'spotify_track_id': sid, 'classification_review_suggested': False,
                      'assistant_review_note': 'Synthetic only', 'note_type': 'synthetic'})
        freeze_json(source / 'profiles' / f'{pid}.json', profile())
    freeze_json(source / 'source_provenance.json', {'tracks': tracks})
    freeze_json(source / 'profile_comparison.json', comparisons)
    freeze_json(source / 'joined_pair_diagnostics.json', [])
    freeze_json(source / 'artifact_manifest.json', {'files': hashes(list(source.rglob('*')), source)})
    freeze_json(root / CONFIG, spec)
    freeze_json(root / NOTES, {'notes': notes, 'scope_note': 'Synthetic: outside-pilot track is deferred.'})
    return source


def test_complete_16_review_replay_is_deterministic_and_frozen_inputs_unchanged(tmp_path, spec, monkeypatch):
    source = fixture(tmp_path, spec)
    # Network dependency is unnecessary and fails if accidentally introduced.
    import socket
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('network access'))
    before = hashes(list(source.rglob('*')), source)
    output = tmp_path / 'review'
    result = build_review(tmp_path, output)
    assert result['mapped_tracks'] == 16 and result['new_api_calls'] == 0
    assert result['full100_mapping_performed'] is False
    first = hashes(list(output.rglob('*')), output)
    assert build_review(tmp_path, output) == result
    assert hashes(list(output.rglob('*')), output) == first
    assert hashes(list(source.rglob('*')), source) == before
    assert len(read(output / 'mapped_review.json')) == 16
    assert all(p['existing_playlist_rating'] is None for p in read(output / 'pair_context.json'))
    with pytest.raises(ValueError, match='separate output'): build_review(tmp_path, source)


def test_extra_track_or_source_tamper_stops_before_mapping(tmp_path, spec, monkeypatch):
    source = fixture(tmp_path, spec)
    freeze_json(source / 'profiles' / 'A11.json', profile())
    monkeypatch.setattr('audio_similarity.genre_neighborhood_review.map_profile', lambda *a: pytest.fail('mapped extra track'))
    with pytest.raises(ValueError, match='exact original 16'): map_pilot(source, spec)
    (source / 'profiles' / 'A01.json').write_text('{}')
    with pytest.raises(ValueError, match='integrity mismatch'): build_review(tmp_path, tmp_path / 'review')
