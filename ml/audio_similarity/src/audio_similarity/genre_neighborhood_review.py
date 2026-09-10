"""Offline, original-16-only mapped review; never scores or maps the full 100."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import io
import json
from pathlib import Path

from .genre_neighborhood import compile_map, map_profile
from .stage5b1a_models import file_sha256
from .stage5e3_artifacts import digest, freeze, freeze_json, hashes, read, verify_hashes

SOURCE = Path('reports/gemini_style_pilot/v1/free_genre_v1')
CONFIG = Path('configs/genre-neighborhood-map-v1.json')
NOTES = Path('evaluation/genre_neighborhood_pilot_review_notes_v1.json')
PILOT_IDS = tuple([f'A{i:02d}' for i in range(1, 11)] + [f'C{i:02d}' for i in range(1, 7)])


def protected_inputs(root):
    files = [root / CONFIG, root / NOTES]
    for name in ('genre_neighborhood.py', 'genre_neighborhood_review.py', 'stage5e3_artifacts.py', 'stage5b1a_models.py'):
        path = root / 'src/audio_similarity' / name
        if path.is_file():
            files.append(path)
    # Integrity checks read bytes only; no mapping of the full-100 profiles.
    for relative in (SOURCE, Path('reports/gemini_style_pilot/v1/duration_v3'),
                     Path('reports/gemini_style_pilot/v1/owner_listening_v1'),
                     Path('reports/gemini_style_pilot/v1/owner_clarification_v1'),
                     Path('reports/gemini_style_pilot/frozen100_free_genre_v1')):
        manifest_path = root / relative / 'artifact_manifest.json'
        if not manifest_path.exists():
            if relative == SOURCE:
                raise ValueError('missing frozen 16-song source manifest')
            continue
        manifest = read(manifest_path)['files']
        verify_hashes(root / relative, manifest)
        files.extend([manifest_path, *(root / relative / name for name in manifest)])
    for name in ('historical_reference_matrices.npz', 'post_review_rating_snapshot.json'):
        path = root / 'reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3' / name
        if path.is_file():
            files.append(path)
    files.extend((root / '.research_audio/song_space/v3').glob('*.json'))
    files.extend(root.glob('artifacts/**/representations.sqlite'))
    return hashes(files, root)


def map_pilot(source, spec):
    """Enforce original membership before mapping any row; no corpus override."""
    tracks = read(source / 'source_provenance.json')['tracks']
    by_pid = {t['pilot_id']: t for t in tracks}
    paths = {p.stem for p in (source / 'profiles').glob('*.json')}
    if (len(tracks) != 16 or set(by_pid) != set(PILOT_IDS) or paths != set(PILOT_IDS)
            or len({t['spotify_track_id'] for t in tracks}) != 16):
        raise ValueError('exact original 16-song membership required; no substitutions or full-100 mapping')
    compiled = compile_map(spec)
    rows = []
    for pid in PILOT_IDS:
        track = by_pid[pid]
        profile = read(source / 'profiles' / f'{pid}.json')
        result = map_profile(profile, compiled)
        rows.append({'pilot_id': pid, 'spotify_track_id': track['spotify_track_id'],
                     'song': track['catalog_description'], 'input_profile_sha256': file_sha256(source / 'profiles' / f'{pid}.json'),
                     'source_profile': str(SOURCE / 'profiles' / f'{pid}.json'), **result})
    return rows


def add_review_context(rows, source, notes):
    comparisons = {r['spotify_track_id']: r for r in read(source / 'profile_comparison.json')}
    annotations = {r['spotify_track_id']: r for r in notes['notes']}
    if set(comparisons) != {r['spotify_track_id'] for r in rows} or set(annotations) != set(comparisons):
        raise ValueError('review notes do not match all 16 stable identities')
    for row in rows:
        previous, annotation = comparisons[row['spotify_track_id']], annotations[row['spotify_track_id']]
        if previous['pilot_id'] != row['pilot_id'] or annotation['pilot_id'] != row['pilot_id']:
            raise ValueError('review note identity mismatch')
        row['review_context_not_mapper_inputs'] = {
            'owner_first_pass_verbatim': previous['owner_first_pass_verbatim'],
            'owner_followup_on_earlier_ontology_arm': previous['owner_followup'],
            'owner_verdict_on_current_gemini_profile': previous['owner_verdict_on_new_profile'],
            'older_ontology_arm_labels_not_mapper_inputs': {
                'family': previous['original_family'], 'styles': previous['original_styles']},
            **{k: annotation[k] for k in ('classification_review_suggested', 'assistant_review_note', 'note_type')},
            'owner_mapping_decision': '', 'owner_classification_decision': '', 'owner_review_notes': ''}


def label_audit(rows):
    variants, flagged = defaultdict(lambda: defaultdict(list)), []
    field_warnings = []
    for row in rows:
        for t in row['trace']:
            occurrence = {'pilot_id': row['pilot_id'], 'spotify_track_id': row['spotify_track_id'],
                          'song': row['song'], 'source_path': t['source_path'], 'trace_id': t['trace_id']}
            variants[t['canonical_concept_id'] or '<unrecognized>'][t['raw_label']].append(occurrence)
            if t['mapping_status'] != 'mapped':
                flagged.append({**occurrence, **t})
        field_warnings.extend({'pilot_id': row['pilot_id'], **w} for w in row['warnings']
                              if w['code'] in ('style_concept_in_family_slot', 'repeated_concept_not_extra_weight'))
    return {'unresolved_or_review_required': flagged,
            'observed_alias_groups': {cid: dict(sorted(labels.items())) for cid, labels in sorted(variants.items())},
            'multiple_raw_spellings': [cid for cid, labels in sorted(variants.items()) if len(labels) > 1],
            'field_or_duplication_warnings': field_warnings,
            'cross_concept_alias_collisions': 0,
            'note': 'Counts concern deterministic label handling, not musical classification accuracy.'}


def pair_context(rows, source):
    by_pid = {r['pilot_id']: r for r in rows}
    evidence = []
    for item in read(source / 'joined_pair_diagnostics.json'):
        e = item['frozen_pair_evidence']
        if e['rating_status'] != 'PLAYLIST_COMPATIBILITY_V1':
            continue
        a, b = by_pid[e['pilot_a']], by_pid[e['pilot_b']]
        if (a['spotify_track_id'], b['spotify_track_id']) != (e['spotify_a'], e['spotify_b']):
            raise ValueError('pair evidence stable identities differ')
        evidence.append((a, b, e['human_playlist_rating'], 'Existing playlist judgment; not genre ground truth.'))
    for pa, pb, note in (
        ('A01', 'A04', 'Unrated boom-bap / lo-fi lineage illustration; no numeric judgment invented.'),
        ('A01', 'A05', 'Unrated boom-bap / chillhop lineage illustration; no numeric judgment invented.'),
        ('A07', 'A08', 'Unrated shared-family / different-substyle illustration.'),
        ('C04', 'C05', 'Owner-specific exploratory pairing only; shared labels are not confirmatory genre truth.')):
        if not any({a['pilot_id'], b['pilot_id']} == {pa, pb} for a, b, _, _ in evidence):
            evidence.append((by_pid[pa], by_pid[pb], None, note))
    output = []
    for a, b, rating, note in evidence:
        output.append({'pilot_a': a['pilot_id'], 'pilot_b': b['pilot_id'],
            'spotify_a': a['spotify_track_id'], 'spotify_b': b['spotify_track_id'],
            'song_a': a['song'], 'song_b': b['song'], 'existing_playlist_rating': rating,
            'shared_broad_families': sorted(set(a['broad_families']) & set(b['broad_families'])),
            'shared_style_neighborhoods': sorted(set(a['style_neighborhoods']) & set(b['style_neighborhoods'])),
            'note': note, 'numeric_genre_score': None, 'genre_accuracy_label': None})
    return sorted(output, key=lambda r: tuple(sorted((r['spotify_a'], r['spotify_b']))))


def table_cell(value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    return value.replace('|', '\\|').replace('\n', '<br>')


def review_markdown(rows):
    lines = ['# Original 16: genre-neighborhood manual review', '',
        'Mapping uses only the four raw Gemini family/style fields. Context and owner comments below are display-only.',
        'Each card separates a literal-label mapping decision from a possible classification disagreement. Blank owner decisions remain unsubmitted.', '']
    for row in rows:
        context = row['review_context_not_mapper_inputs']
        lines += [f'## {row["pilot_id"]} — {row["song"]}', '',
                  f'Stable Spotify ID: `{row["spotify_track_id"]}`', '',
                  '| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |',
                  '| --- | --- | --- | --- | --- | --- | --- |']
        for t in row['trace']:
            values = [t['source_path'], json.dumps(t['raw_label'], ensure_ascii=False), t['canonical_label'],
                      t['broad_families'], t['style_neighborhoods'], t['scene_contexts'], t['mapping_status']]
            lines.append('| ' + ' | '.join(table_cell(v) for v in values) + ' |')
        lines += ['', f'**Broad families:** {", ".join(row["broad_families"]) or "none"}', '',
                  f'**Overlapping neighborhoods:** {", ".join(row["style_neighborhoods"]) or "none"}', '',
                  f'**Separate scene/context:** {", ".join(row["scene_contexts"]) or "none"}', '',
                  '**Gemini context, display only:** ' + table_cell(row['gemini_context_display_only']), '',
                  '**Existing owner first-pass words, verbatim:** ' + json.dumps(context['owner_first_pass_verbatim'], ensure_ascii=False), '',
                  '**Review note:** ' + context['assistant_review_note'], '',
                  '**Warnings:** ' + ('; '.join(f'{w["code"]}: {w["message"]}' for w in row['warnings']) or 'No mapper warning.'), '',
                  '**Owner mapping decision:** __________  **Owner classification decision:** __________', '',
                  '**Owner notes:** __________', '']
    return '\n'.join(lines).encode()


def review_csv(rows):
    output = io.StringIO(newline='')
    fields = ['pilot_id', 'spotify_track_id', 'song', 'raw_genre_labels', 'canonical_labels', 'broad_families',
              'style_neighborhoods', 'scene_contexts', 'gemini_context_display_only', 'warnings', 'trace',
              'owner_first_pass_verbatim', 'classification_review_suggested', 'assistant_review_note',
              'owner_mapping_decision', 'owner_classification_decision', 'owner_review_notes']
    writer = csv.DictWriter(output, fields, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        values = {**row, **row['review_context_not_mapper_inputs']}
        writer.writerow({f: json.dumps(values[f], ensure_ascii=False) if isinstance(values[f], (dict, list)) else values[f] for f in fields})
    return output.getvalue().encode()


def build_review(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    source = root / SOURCE
    if output == root or output in source.parents or source == output or source in output.parents:
        raise ValueError('review must use a separate output directory, never the frozen input directory')
    before = protected_inputs(root)
    if any(output == (root / p).parent or output in (root / p).parents for p in before):
        raise ValueError('output overlaps protected artifacts')
    spec = read(root / CONFIG)
    rows = map_pilot(source, spec)
    notes = read(root / NOTES)
    add_review_context(rows, source, notes)
    audit, pairs = label_audit(rows), pair_context(rows, source)
    freeze_json(output / 'genre-neighborhood-map-v1.json', spec)
    freeze_json(output / 'mapped_review.json', rows)
    freeze(output / 'manual_review.md', review_markdown(rows))
    freeze(output / 'manual_review.csv', review_csv(rows))
    freeze_json(output / 'label_audit.json', audit)
    freeze_json(output / 'pair_context.json', pairs)
    freeze_json(output / 'classification_review_cases.json', [
        {'pilot_id': r['pilot_id'], 'spotify_track_id': r['spotify_track_id'], 'song': r['song'],
         'raw_genre_labels': r['raw_genre_labels'], **r['review_context_not_mapper_inputs']}
        for r in rows if r['review_context_not_mapper_inputs']['classification_review_suggested']])
    freeze_json(output / 'scope.json', {'mapped_tracks': 16, 'pilot_ids': list(PILOT_IDS), 'new_api_calls': 0,
        'full100_mapping_performed': False, 'reranking_performed': False, 'production_changes': False,
        'deferred': notes['scope_note'], 'purpose': 'Manual mapping/classification inspection, not a genre accuracy benchmark.'})
    freeze_json(output / 'input_hashes.json', before)
    verify_hashes(root, before)
    summary = {'mapped_tracks': len(rows), 'review_required_label_occurrences': len(audit['unresolved_or_review_required']),
            'unrecognized_label_occurrences': sum(t['canonical_concept_id'] is None for r in rows for t in r['trace']),
            'protected_files_verified': len(before), 'mapping_config_sha256': digest(spec),
            'new_api_calls': 0, 'full100_mapping_performed': False}
    freeze_json(output / 'summary.json', summary)
    if (output / 'artifact_manifest.json').exists():
        verify_hashes(output, read(output / 'artifact_manifest.json')['files'])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build_review(Path.cwd(), args.output))


if __name__ == '__main__':
    main()
