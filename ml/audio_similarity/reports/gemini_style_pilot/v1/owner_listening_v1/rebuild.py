"""Offline, create-once listening-pass exports; never writes live review state."""
import csv
import io
from decimal import Decimal
from pathlib import Path

from audio_similarity.gemini_style_review_store import FIELDS, COMPARISON
from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import freeze_json, read, verify_hashes
from audio_similarity.taxonomy_review_store import safe_cell


def main():
    here = Path(__file__).resolve().parent
    root = here.parents[3]
    inference = here.parent / 'duration_v3'
    receipt = read(here / 'receipt.json')
    verify_hashes(inference, read(inference / 'artifact_manifest.json')['files'])
    assert file_sha256(inference / 'artifact_manifest.json') == receipt['source_artifact_manifest_sha256']
    assert file_sha256(inference / 'profiles_frozen.json') == receipt['profiles_frozen_sha256']
    assert file_sha256(here / 'submitted_review.csv') == receipt['source_sha256']
    saved = read(here / 'saved_answers_at_submission.json')
    snapshot = read(here / 'independent_snapshot.json')
    assert snapshot['answers'] == saved['answers']
    assert snapshot['packet_hash'] == saved['packet_hash'] == receipt['packet_hash']
    assert snapshot['phase'] == 'listen'
    assert snapshot['new_playlist_ratings'] == 0 and not snapshot['model_profiles_modified']
    answers = saved['answers']
    csv.field_size_limit(8_388_608)
    submitted = list(csv.DictReader(io.StringIO((here / 'submitted_review.csv').read_text(encoding='utf-8-sig'))))
    tracks = {t['pilot_id']: t for t in read(inference / 'execution_manifest.json')['tracks']}
    assert len(submitted) == len(tracks) == len(answers) == 16
    assert {r['pilot_id'] for r in submitted} == set(tracks) == set(answers)
    for row in submitted:
        pid = row['pilot_id']
        track, answer = tracks[pid], answers[pid]
        assert row['packet_hash'] == receipt['packet_hash']
        assert row['spotify_track_id'] == track['spotify_track_id']
        assert row['neutral_id'] == track['neutral_id']
        assert row['save_status'] == 'SAVED' and row['phase'] == 'listen'
        assert row['revision'] == str(answer['revision']) and row['updated_at'] == answer['updated_at']
        assert all(row[k] == safe_cell(answer['fields'][k]) for k in FIELDS)
        assert answer['fields']['owner_recording_identity_ok'] == 'yes'
        assert answer['fields']['owner_family_or_style_words'].strip()
        assert all(not answer['fields'][k] for k in COMPARISON)
    profile_rows = []
    for pid, track in sorted(tracks.items()):
        repeat = inference / 'repeats' / f'{pid}.json'
        profile_rows.append({
            'pilot_id': pid, 'spotify_track_id': track['spotify_track_id'],
            'song': track['catalog_title'] + ' — ' + ', '.join(track['catalog_artists']),
            'owner_fields_verbatim': answers[pid]['fields'],
            'frozen_primary': read(inference / 'profiles' / f'{pid}.json'),
            'frozen_repeat': read(repeat) if repeat.exists() else None,
            'owner_comparison_status': 'NOT_YET_REVIEWED',
            'owner_description_verdict': None,
        })
    freeze_json(here / 'track_comparison_pending.json', profile_rows)
    for source, target, count in (
        ('joined_pair_diagnostics.json', 'all_playlist_pairs_with_owner_notes.json', 15),
        ('unrated_diagnostics.json', 'unrated_diagnostics_with_owner_notes.json', 3),
    ):
        pairs = read(inference / source)
        assert len(pairs) == count and len({p['pair_id'] for p in pairs}) == count
        joined = []
        for pair in sorted(pairs, key=lambda p: (p['pilot_a'], p['pilot_b'])):
            assert (pair['human_playlist_rating'] is None) == (count == 3)
            for side in ('a', 'b'):
                assert tracks[pair['pilot_' + side]]['spotify_track_id'] == pair['spotify_' + side]
            joined.append({
                'frozen_model_and_playlist_evidence': pair,
                'owner_a_verbatim': answers[pair['pilot_a']]['fields'],
                'owner_b_verbatim': answers[pair['pilot_b']]['fields'],
                'owner_validation_of_model_evidence': 'PENDING',
                'new_playlist_rating': None,
                'owner_validated_reranking_implication': None,
            })
        freeze_json(here / target, joined)
    integrity = read(inference / 'historical_integrity.json')
    verify_hashes(root, integrity['protected_hashes'])
    ledger = read(inference / 'usage_ledger.json')
    assert len(ledger) == 20
    freeze_json(here / 'verification.json', {
        'submitted_rows_equal_saved_rows': 16,
        'frozen_listening_snapshot_equals_submitted_answers': True,
        'source_inference_artifacts_verified': len(read(inference / 'artifact_manifest.json')['files']),
        'protected_historical_files_verified': len(integrity['protected_hashes']),
        'preserved_revision_events': len(saved['events']),
        'playlist_pairs_joined_by_stable_identity': 15,
        'qualitative_pairs_with_null_playlist_ratings': 3,
        'new_numeric_ratings': 0, 'new_gemini_calls': 0,
        'historical_generation_attempts': len(ledger),
        'historical_token_accounted_cost_usd': str(sum(Decimal(r['settled_standard_rate_usd']) for r in ledger)),
        'owner_model_comparisons_completed': 0,
        'status': 'LISTENING_COMPLETE_COMPARISON_PENDING',
    })
    files = {str(p.relative_to(here)): file_sha256(p) for p in sorted(here.rglob('*'))
             if p.is_file() and p.name != 'artifact_manifest.json' and '__pycache__' not in p.parts}
    freeze_json(here / 'artifact_manifest.json', {'files': files})
    verify_hashes(here, files)
    print(f'Verified {len(files)} owner-listening artifacts; 16 tracks, 15 rated pairs, zero API calls.')


if __name__ == '__main__':
    main()
