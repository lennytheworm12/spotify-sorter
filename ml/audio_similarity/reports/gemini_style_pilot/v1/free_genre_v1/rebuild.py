"""Offline export of both free-genre arms; no API client is constructed."""
import csv
import io
from decimal import Decimal
from pathlib import Path

from audio_similarity.gemini_free_genre_runner import FreeGenreRunner
from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import freeze, freeze_json, hashes, read, verify_hashes


def csv_bytes(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8-sig')


def main():
    here = Path(__file__).resolve().parent
    root = here.parents[3]
    old_report = here.parent / 'duration_v3'
    run = root / '.research_audio/gemini_style_pilot/free-genre-point-v1'
    stopped = root / '.research_audio/gemini_style_pilot/free-genre-v1'
    runner = FreeGenreRunner(root, run, transport_factory=lambda: (_ for _ in ()).throw(AssertionError('NO API')))
    before = hashes(list((run / 'execution').rglob('*')), run)
    replay = runner.replay()
    assert replay['unique_profiles'] == 16 and replay['new_api_calls'] == 0
    assert hashes(list((run / 'execution').rglob('*')), run) == before
    freeze_json(here / 'cache_replay.json', replay | {'execution_bytes_unchanged': True})
    verify_hashes(old_report, read(old_report / 'artifact_manifest.json')['files'])
    for name in ('owner_listening_v1', 'owner_clarification_v1'):
        folder = here.parent / name
        verify_hashes(folder, read(folder / 'artifact_manifest.json')['files'])
    for name in ('execution_manifest.json', 'profiles_frozen.json', 'protocol.md', 'prompt.txt', 'response_schema.json', 'owner_retry_authorization.json'):
        freeze(here / name, (run / name).read_bytes())
    freeze(here / 'source_provenance.json', (old_report / 'source_provenance.json').read_bytes())
    for path in sorted((run / 'schemas').glob('*.json')):
        freeze(here / 'schemas' / path.name, path.read_bytes())
    for name in ('execution_manifest.json', 'protocol.md', 'prompt.txt', 'response_schema.json', 'implementation_snapshot.json'):
        freeze(here / 'stopped_interval_arm' / name, (stopped / name).read_bytes())
    freeze(here / 'stopped_interval_arm/STOPPED.json', (stopped / 'execution/STOPPED.json').read_bytes())
    for p in sorted((stopped / 'implementation_snapshot').rglob('*.py')):
        freeze(here / 'stopped_interval_arm/implementation_snapshot' / p.relative_to(stopped / 'implementation_snapshot'), p.read_bytes())
    rows = []
    for source, offset, label in ((stopped, 0, 'interval_smokes'), (run, 2, 'point_primary')):
        m = read(source / 'execution_manifest.json')
        calls = [p for p in sorted((source / 'execution/transport').glob('call-*.request.json'))
                 if read(p)['label'] == 'generateContent']
        for index, call in enumerate(calls, 1):
            slot = m['schedule'][index - 1]
            stem = here / 'attempts' / f'call-{offset + index:02d}'
            result_path = source / 'execution/attempts' / f'attempt-{index:02d}.result.json'
            for suffix in ('request', 'reservation', 'settlement'):
                freeze(stem.with_suffix(f'.{suffix}.json'), (source / 'execution/attempts' / f'attempt-{index:02d}.{suffix}.json').read_bytes())
            response_file = call.with_name(call.name.replace('.request.json', '.response.bin'))
            freeze(stem.with_suffix('.raw_response.json'), response_file.read_bytes())
            http_file = call.with_name(call.name.replace('.request.json', '.response.json'))
            freeze(stem.with_suffix('.http.json'), http_file.read_bytes())
            freeze(stem.with_suffix('.transport_request.json'), call.read_bytes())
            count_file = call.with_name(f'call-{int(call.name.split("-")[1].split(".")[0]) - 1:03d}.response.bin')
            freeze(stem.with_suffix('.count_tokens.json'), count_file.read_bytes())
            if result_path.exists(): freeze(stem.with_suffix('.validated_result.json'), result_path.read_bytes())
            value = read(response_file)
            usage = value['usageMetadata']
            settlement = read(source / 'execution/attempts' / f'attempt-{index:02d}.settlement.json')
            rows.append({'new_attempt': offset + index, 'global_attempt': 20 + offset + index,
                'arm': label, 'pilot_id': slot['pilot_id'], 'repeat': slot['repeat'],
                'response_id': value['responseId'], 'model_version': value['modelVersion'],
                'finish_reason': value['candidates'][0]['finishReason'],
                'validation_status': 'VALIDATED' if result_path.exists() else 'INVALID_EVIDENCE_INTERVAL',
                'prompt_tokens': usage['promptTokenCount'], 'output_tokens': usage['candidatesTokenCount'],
                'thinking_tokens': usage.get('thoughtsTokenCount', 0), 'total_tokens': usage['totalTokenCount'],
                'audio_tokens': sum(t['tokenCount'] for t in usage['promptTokensDetails'] if t['modality'] == 'AUDIO'),
                'latency_seconds': read(http_file)['latency_seconds'],
                'cost_usd': settlement['actual_cost_usd'], 'raw_response_sha256': file_sha256(response_file)})
        for p in sorted((source / 'execution/transport').glob('upload-*.json')):
            freeze(here / 'upload_receipts' / label / p.name, p.read_bytes())
    assert len(rows) == 18 and sum(r['validation_status'] == 'VALIDATED' for r in rows) == 17
    freeze_json(here / 'usage_ledger.json', rows)
    freeze(here / 'usage_ledger.csv', csv_bytes(rows))
    profiles = {}
    for i in range(1, 17):
        result = runner.verified_result(i)
        profiles[result['pilot_id']] = result['profile']
        freeze_json(here / 'profiles' / f'{result["pilot_id"]}.json', result['profile'])
    notes = read(here.parent / 'owner_listening_v1/saved_answers_at_submission.json')['answers']
    summary = []
    for pid, track in sorted(runner.tracks.items()):
        old = read(old_report / 'profiles' / f'{pid}.json')
        new = profiles[pid]
        summary.append({'pilot_id': pid, 'spotify_track_id': track['spotify_track_id'],
            'song': track['catalog_title'] + ' — ' + ', '.join(track['catalog_artists']),
            'original_family': old['primary_family'], 'original_styles': '; '.join([old['primary_style'], *old['secondary_styles']]),
            'free_family': new['primary_family'], 'free_styles': '; '.join([new['primary_style'], *new['secondary_styles']]),
            'free_vocal_role': new['vocal_role'], 'free_arrangement': new['arrangement_focus'],
            'free_family_certainty': new['certainty']['family'], 'free_style_certainty': new['certainty']['style'],
            'owner_first_pass_verbatim': notes[pid]['fields']['owner_family_or_style_words'],
            'owner_followup': 'Hyperpop label seems more plausible; not a full-profile approval.' if pid == 'C01' else
                              'Hyperpop identity still does not fit.' if pid == 'A07' else '',
            'owner_verdict_on_new_profile': 'NOT_REVIEWED'})
    freeze_json(here / 'profile_comparison.json', summary)
    freeze(here / 'profile_comparison.csv', csv_bytes(summary))
    for filename, count in [('joined_pair_diagnostics.json', 15), ('unrated_diagnostics.json', 3)]:
        pairs = read(old_report / filename)
        assert len(pairs) == count
        joined = []
        for pair in pairs:
            for side in ('a', 'b'):
                assert runner.tracks[pair['pilot_' + side]]['spotify_track_id'] == pair['spotify_' + side]
            joined.append({'frozen_pair_evidence': pair,
                'free_profile_a': profiles[pair['pilot_a']], 'free_profile_b': profiles[pair['pilot_b']],
                'owner_first_pass_a': notes[pair['pilot_a']]['fields'], 'owner_first_pass_b': notes[pair['pilot_b']]['fields'],
                'new_playlist_rating': None, 'owner_review_of_new_profiles': 'PENDING',
                'numeric_reranking_score': None})
        freeze_json(here / filename, sorted(joined, key=lambda p: p['frozen_pair_evidence']['pair_id']))
    cost = sum(Decimal(r['cost_usd']) for r in rows)
    freeze_json(here / 'execution_summary.json', {
        'new_generation_attempts': 18, 'new_primary_profiles': 16,
        'new_api_http_operations': sum(len(list((p / 'execution/transport').glob('call-*.request.json'))) for p in (stopped, run)),
        'new_uploads': 0, 'reused_audio_uploads': 16,
        'new_arm_cost_usd': str(cost), 'combined_generation_attempts': 38,
        'combined_cost_usd': str(Decimal('0.14680800') + cost),
        'source_tracks_blocked': [], 'invalid_interval_smokes': 1,
        'final_arm_validation': '16/16 VALIDATED', 'final_arm_repeats': 0,
        'repeat_stability': 'NOT_TESTED: original two free-genre smokes consumed planned repeat slots.',
        'prior_inference_manifest_verified_files': len(read(old_report / 'artifact_manifest.json')['files']),
        'protected_historical_files_verified': len(runner.manifest['protected_hashes']),
        'all_frozen_manifest_inputs_verified': len(runner.manifest['input_hashes']),
        'new_playlist_ratings': 0, 'production_changes': False,
    })
    freeze_json(here / 'artifact_manifest.json', {'files': hashes(
        [p for p in here.rglob('*') if p.is_file() and p.name != 'artifact_manifest.json' and '__pycache__' not in p.parts], here)})
    print('Offline export verified; all 16 profiles, all 18 new attempts, all 15 existing playlist pairs.')


if __name__ == '__main__':
    main()
