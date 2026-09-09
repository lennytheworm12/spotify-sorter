"""Offline, create-once evidence export. Run from ml/audio_similarity with its venv.

No provider client is allowed; no historical labels or profiles are changed.
The lexical comparisons describe this selected pilot, not a fitted reranker.
"""
from collections import Counter
from decimal import Decimal
from itertools import combinations
from pathlib import Path
import csv
import io
import json

import numpy as np

from audio_similarity.gemini_style_pilot.runner import PilotRunner
from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5c2_analysis import canonical_pair_id
from audio_similarity.stage5e3_artifacts import freeze, freeze_json, hashes, read, verify_hashes


ROOT = Path.cwd()
RUN = ROOT / '.research_audio/gemini_style_pilot/style-pilot-v1-duration-v3'
OUT = Path(__file__).resolve().parent
E3 = ROOT / 'reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3'
CONTROLS = [('A01', 'C01', 1), ('A06', 'A03', 2), ('A06', 'C01', 2),
            ('C06', 'A10', 2), ('C02', 'C03', 4), ('A05', 'C02', 4)]


def csv_file(name, rows):
    text = io.StringIO(newline='')
    writer = csv.DictWriter(text, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else v
                         for k, v in row.items()})
    freeze(OUT / name, text.getvalue().encode())


def labels(profile, primary, secondary):
    return {profile[primary], *profile[secondary]} - {'unknown'}


def comparison(a, b, rating):
    family = sorted(labels(a, 'primary_family', 'secondary_families') & labels(b, 'primary_family', 'secondary_families'))
    style = sorted(labels(a, 'primary_style', 'secondary_styles') & labels(b, 'primary_style', 'secondary_styles'))
    # This transparent description is post-profile analysis, not a frozen
    # efficacy metric or a rule used to change any similarity or ranking.
    if rating is None or rating == 3 or a['status'] != 'classified' or b['status'] != 'classified':
        implication = 'no information'
    elif (rating >= 4 and not style) or (rating <= 2 and style):
        implication = 'conflict'
    elif style:
        implication = 'possible contraction'
    else:
        implication = 'possible separation'
    return {'shared_families': family, 'shared_styles': style,
            'primary_family_a': a['primary_family'], 'primary_family_b': b['primary_family'],
            'primary_style_a': a['primary_style'], 'primary_style_b': b['primary_style'],
            'vocal_role_a': a['vocal_role'], 'vocal_role_b': b['vocal_role'],
            'arrangement_a': a['arrangement_focus'], 'arrangement_b': b['arrangement_focus'],
            'texture_a': a['texture_tags'], 'texture_b': b['texture_tags'],
            'sections_a': a['section_variation'], 'sections_b': b['section_variation'],
            'certainty_a': a['certainty'], 'certainty_b': b['certainty'],
            'qualitative_implication': implication}


def main():
    assert (RUN / 'profiles_frozen.json').is_file(), 'Do not inspect ratings before profile freeze'
    verify_hashes(RUN, read(RUN / 'profiles_frozen.json')['files'])
    runner = PilotRunner(ROOT, RUN, transport_factory=lambda: (_ for _ in ()).throw(AssertionError('API prohibited')))
    replay = runner.replay()
    manifest = runner.manifest
    tracks = {t['pilot_id']: t for t in manifest['tracks']}
    results = [runner.verified_result(i) for i in range(1, 19)]
    primaries = {r['pilot_id']: r['profile'] for r in results if not r['repeat']}
    assert len(primaries) == 16 and replay['new_api_calls'] == 0
    for r in results:
        folder = 'repeats' if r['repeat'] else 'profiles'
        freeze_json(OUT / folder / f'{r["pilot_id"]}.json', r['profile'])
    for relative in ('execution_manifest.json', 'profiles_frozen.json', 'cache_replay.json',
                     'post_profile_analysis_boundary.json', 'revision/approval.json',
                     'revision/reused_uploads.json', 'execution/smoke_gate.json'):
        freeze(OUT / relative, (RUN / relative).read_bytes())
    for p in sorted((RUN / 'revision/schemas').glob('*.json')):
        freeze(OUT / 'schemas' / p.name, p.read_bytes())
    freeze_json(OUT / 'source_provenance.json', {'tracks': manifest['tracks'],
                'scope': 'Full retained recordings, not asserted byte-equivalent to Spotify album masters.'})
    for p in sorted((RUN / 'contract/model').iterdir()):
        freeze(OUT / 'model_contract' / p.name, p.read_bytes())

    # Preserve every real generation across both contracts, including invalid A01.
    prior = ROOT / manifest['continuation']['prior_run']
    usage_rows = []
    for phase, run in [('original_schema', prior), ('duration_bounded_schema', RUN)]:
        run_manifest = read(run / 'execution_manifest.json')
        track_by_neutral = {t['neutral_id']: t for t in run_manifest['tracks']}
        calls = [p for p in sorted((run / 'execution/transport').glob('call-*.request.json'))
                 if read(p)['label'] == 'generateContent']
        for index, call in enumerate(calls, 1):
            number = len(usage_rows) + 1
            prefix = f'call-{number:02d}'
            attempts = run / 'execution/attempts'
            reservation = read(attempts / f'attempt-{index:02d}.reservation.json')
            settlement = read(attempts / f'attempt-{index:02d}.settlement.json')
            raw = call.with_name(call.name.replace('.request.json', '.response.bin'))
            metadata = read(call.with_name(call.name.replace('.request.json', '.response.json')))
            response = read(raw)
            track = track_by_neutral[reservation['neutral_id']]
            u = response['usageMetadata']
            assert settlement['usage'] == u
            # countTokens immediately precedes this generation in the transport ledger.
            call_index = int(call.name.split('.')[0].split('-')[1])
            count_stem = call.with_name(f'call-{call_index - 1:03d}')
            assert read(count_stem.with_suffix('.request.json'))['label'] == 'countTokens'
            count_response = count_stem.with_suffix('.response.bin')
            assert read(count_response)['totalTokens'] == reservation['counted_input_tokens']
            freeze(OUT / 'attempts' / f'{prefix}.count_tokens.json', count_response.read_bytes())
            freeze(OUT / 'attempts' / f'{prefix}.raw_response.json', raw.read_bytes())
            for suffix in ('request', 'reservation', 'settlement'):
                freeze(OUT / 'attempts' / f'{prefix}.{suffix}.json',
                       (attempts / f'attempt-{index:02d}.{suffix}.json').read_bytes())
            freeze_json(OUT / 'attempts' / f'{prefix}.http.json', metadata)
            usage_rows.append({'global_attempt': number, 'phase': phase, 'run_attempt': index,
                'pilot_id': track['pilot_id'], 'neutral_id': track['neutral_id'], 'repeat': reservation['repeat'],
                'prepared_sha256': track['prepared']['prepared_sha256'],
                'validation_status': 'VALIDATED' if (attempts / f'attempt-{index:02d}.result.json').exists() else 'INVALID_TIMESTAMP',
                'response_id': response['responseId'], 'requested_model': run_manifest['model_id'],
                'returned_model_version': response['modelVersion'], 'finish_reason': response['candidates'][0]['finishReason'],
                'http_status': metadata['http_status'], 'latency_seconds': metadata['latency_seconds'],
                'counted_input_tokens': reservation['counted_input_tokens'], 'prompt_tokens': u['promptTokenCount'],
                'audio_tokens': sum(v['tokenCount'] for v in u['promptTokensDetails'] if v['modality'] == 'AUDIO'),
                'candidate_tokens': u['candidatesTokenCount'], 'thinking_tokens': u.get('thoughtsTokenCount', 0),
                'total_tokens': u['totalTokenCount'], 'reserved_upper_usd': reservation['reserved_upper_cost_usd'],
                'settled_standard_rate_usd': settlement['actual_cost_usd'],
                'raw_response_sha256': file_sha256(raw), 'request_sha256': reservation['request_sha256']})
    assert len(usage_rows) == 20
    cost = sum((Decimal(r['settled_standard_rate_usd']) for r in usage_rows), Decimal(0))
    assert cost <= 2
    freeze_json(OUT / 'usage_ledger.json', usage_rows)
    csv_file('usage_ledger.csv', usage_rows)
    for receipt in sorted((RUN / 'execution/transport').glob('upload-*.json')):
        freeze(OUT / 'uploads' / receipt.name, receipt.read_bytes())

    # Canonical snapshot is the sole numeric source. Derived copies must agree.
    snapshot_path = E3 / 'post_review_rating_snapshot.json'
    snapshot = read(snapshot_path)
    canonical = {k: v for k, v in snapshot['labels'].items()
                 if snapshot['semantic_tags'].get(k) == 'PLAYLIST_COMPATIBILITY_V1'}
    assert all(type(v) is int and v in range(1, 6) for v in canonical.values())
    mirrors = [ROOT / f'reports/{name}/evidence.json' for name in
               ('style_prior_pilot/v1', 'style_prior_pilot/v2', 'style_band_prior/v1', 'stage5g1b_identity_probes/v1')]
    checked = []
    for p in mirrors:
        if p.exists():
            assert {v['pair_id']: v['rating'] for v in read(p)['playlist']} == canonical
            checked.append(p)
    matrix_path = E3 / 'historical_reference_matrices.npz'
    with np.load(matrix_path, allow_pickle=False) as archive:
        ids = {str(v): i for i, v in enumerate(archive['spotify_ids'])}
        scores = archive['c_clap'].copy()
    all_pairs, rated = [], []
    for a, b in combinations(sorted(tracks), 2):
        ta, tb = tracks[a], tracks[b]
        x, y = ta['spotify_track_id'], tb['spotify_track_id']
        pair = canonical_pair_id(x, y)
        score = float(scores[ids[x], ids[y]]) if x in ids and y in ids else None
        assert score is None or np.isfinite(score)
        rating = canonical.get(pair)
        row = {'pair_id': pair, 'pilot_a': a, 'pilot_b': b, 'spotify_a': x, 'spotify_b': y,
               'song_a': ta['catalog_description'], 'song_b': tb['catalog_description'],
               'human_playlist_rating': rating,
               'rating_status': 'PLAYLIST_COMPATIBILITY_V1' if rating is not None else
                   ('OLDER_HOLISTIC_ONLY_EXCLUDED' if pair in snapshot['labels'] else 'UNRATED_UNKNOWN'),
               'original_c_similarity': score, 'c_status': 'FROZEN_C_AVAILABLE' if score is not None else 'NOT_IN_FROZEN_C',
               **comparison(primaries[a], primaries[b], rating)}
        all_pairs.append(row)
        if rating is not None:
            rated.append(row)
    assert len(all_pairs) == 120 and len({r['pair_id'] for r in rated}) == len(rated)
    freeze_json(OUT / 'joined_pair_diagnostics.json', rated)
    csv_file('joined_pair_diagnostics.csv', rated)
    csv_file('all_pair_inventory.csv', all_pairs)
    controls = []
    for a, b, expected in CONTROLS:
        row = next(r for r in rated if {r['pilot_a'], r['pilot_b']} == {a, b})
        assert row['human_playlist_rating'] == expected
        controls.append({'pilot_a': a, 'pilot_b': b, 'pair_id': row['pair_id'], 'draft_rating': expected,
                         'verified_playlist_rating': row['human_playlist_rating'], 'status': 'VERIFIED'})
    freeze_json(OUT / 'controls_verification.json', controls)
    qualitative = [r for r in all_pairs if {r['pilot_a'], r['pilot_b']} in
                   ({'C04', 'C05'}, {'A06', 'A08'}, {'A07', 'A08'})]
    assert all(r['human_playlist_rating'] is None for r in qualitative)
    freeze_json(OUT / 'unrated_diagnostics.json', qualitative)
    freeze_json(OUT / 'rating_provenance.json', {'source_hashes': hashes([snapshot_path, matrix_path, *checked], ROOT),
        'canonical_playlist_pairs': len(canonical), 'pilot_playlist_pairs': len(rated),
        'rating_counts': dict(sorted(Counter(r['human_playlist_rating'] for r in rated).items())),
        'all_pair_status_counts': dict(Counter(r['rating_status'] for r in all_pairs)),
        'derived_mirrors_are_not_additional_labels': True, 'new_ratings': 0, 'rubrics_pooled': False,
        'annotation_only_reviews': ['stage5g1b taxonomy review', 'style_prior explanatory review'],
        'annotation_policy': 'Taxonomy notes do not create numeric playlist judgments.',
        'profile_freeze_before_inventory': read(RUN / 'post_profile_analysis_boundary.json')})

    repeat_rows = []
    unordered = {'secondary_families', 'secondary_styles', 'texture_tags'}
    for r in results:
        if not r['repeat']:
            continue
        p, q = primaries[r['pilot_id']], r['profile']
        changed = {k: {'primary': p[k], 'repeat': q[k]} for k in p
                   if (set(p[k]) != set(q[k]) if k in unordered else p[k] != q[k])}
        repeat_rows.append({'pilot_id': r['pilot_id'], 'same_prepared_audio_and_request_config': True,
                           'primary_family_stable': p['primary_family'] == q['primary_family'],
                           'primary_style_stable': p['primary_style'] == q['primary_style'],
                           'changed_fields': changed, 'independent_correctness_evidence': False})
    freeze_json(OUT / 'repeat_stability.json', {'repeats': repeat_rows, 'attempted': 2,
                'unattempted_due_to_global_cap': ['A08', 'C05'], 'primary_profiles_never_replaced': True})
    summary, owner = [], []
    for pid, t in tracks.items():
        p = primaries[pid]
        identity = {'pilot_id': pid, 'neutral_id': t['neutral_id'], 'song': t['catalog_description'],
                    'duration_seconds': t['prepared']['duration_seconds']}
        summary.append({**identity, **{k: v for k, v in p.items() if k != 'audio_evidence'},
                        'audio_evidence': p['audio_evidence'], 'owner_style_truth': None})
        owner.append({**identity, 'audio_file': 'audio/' + t['prepared']['prepared_filename'],
            'owner_recording_identity_ok': '', 'owner_family_or_style_words': '',
            'owner_vocals_and_arrangement': '', 'owner_section_changes': '',
            'acceptable_alternative_labels': '', 'model_description_or_timestamp_issues': '',
            'model_certainty_appropriate': '', 'notes': ''})
    csv_file('profile_summary.csv', summary)
    csv_file('owner_review_sheet.csv', owner)
    family_overlap = Counter('good' if r['human_playlist_rating'] >= 4 else 'bad' if r['human_playlist_rating'] <= 2 else 'ambiguous'
                             for r in rated if r['shared_families'])
    no_style_overlap = Counter('good' if r['human_playlist_rating'] >= 4 else 'bad' if r['human_playlist_rating'] <= 2 else 'ambiguous'
                               for r in rated if not r['shared_styles'])
    freeze_json(OUT / 'descriptive_summary.json', {
        'status': 'INFERENCE_COMPLETE_AWAITING_OWNER_AUDIO_REVIEW', 'generation_attempts': 20,
        'new_duration_bounded_attempts': 18, 'valid_unique_primary_profiles': 16,
        'total_settled_standard_rate_usd': str(cost), 'remaining_generation_allowance': 0,
        'prior_invalid_attempts_preserved': 1, 'new_schema_or_transport_failures': 0,
        'profile_status_counts': dict(Counter(p['status'] for p in primaries.values())),
        'primary_family_counts': dict(Counter(p['primary_family'] for p in primaries.values())),
        'family_certainty_counts': dict(Counter(p['certainty']['family'] for p in primaries.values())),
        'style_certainty_counts': dict(Counter(p['certainty']['style'] for p in primaries.values())),
        'primary_vocabulary_gaps': {pid: p['unmapped_styles'] for pid, p in primaries.items() if p['unmapped_styles']},
        'rated_pairs_with_any_shared_family': dict(family_overlap),
        'rated_pairs_with_no_shared_style': dict(no_style_overlap),
        'qualitative_category_definition': 'For classified rated pairs: style-label overlap suggests possible contraction, no overlap suggests possible separation; conflict marks disagreement with a 4–5 or 1–2 rating respectively. Rating 3/unrated/uncertain means no information. These are descriptive review cues, not a reranking rule or correctness score.',
        'limitations': ['Owner style truth not yet collected', 'Selected development pilot, not held out',
                        'Same family is never automatic playlist compatibility',
                        'No weights, score fitting, graph changes or production activation',
                        'Unknown and older holistic-only pairs retain null playlist ratings']})
    verify_hashes(ROOT, manifest['input_hashes'])
    verify_hashes(ROOT, manifest['protected_hashes'])
    freeze_json(OUT / 'historical_integrity.json', {
        'protected_original_files_verified': len(manifest['protected_hashes']),
        'frozen_manifest_inputs_verified': len(manifest['input_hashes']),
        'protected_hashes': manifest['protected_hashes'],
        'historical_rating_snapshot_unchanged': file_sha256(snapshot_path),
        'all_revised_profiles_and_attempts_unchanged': file_sha256(RUN / 'profiles_frozen.json'),
        'replay': replay, 'historical_verdicts_modified': False, 'production_activated': False})
    print(json.dumps({'status': 'OFFLINE_EVIDENCE_EXPORTED', 'calls': 20, 'cost_usd': str(cost),
                      'rated_pairs': len(rated), 'controls_verified': len(controls)}, sort_keys=True))


if __name__ == '__main__':
    main()
