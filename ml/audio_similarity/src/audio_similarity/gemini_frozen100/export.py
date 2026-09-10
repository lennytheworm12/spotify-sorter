"""Deterministic, unreviewed classification export after the entire corpus is frozen."""
from collections import Counter
from decimal import Decimal
import csv
import io
import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import digest, freeze, freeze_json, hashes, read, verify_hashes


def csv_bytes(rows, fields):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fields, lineterminator='\n', extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    return output.getvalue().encode('utf-8')


def export(runner, destination):
    root, run, destination = runner.root, runner.run, Path(destination)
    if not (run / 'profiles_frozen.json').exists():
        raise ValueError('freeze all profiles before aggregate classification export')
    replay = runner.replay()
    m = runner.manifest
    for name in ('execution_manifest.json', 'profiles_frozen.json', 'source_inventory.json',
                 'prepared_inventory.json', 'protocol.md', 'authorization.json', 'prompt.txt', 'response_schema.json'):
        freeze(destination / name, (run / name).read_bytes())
    for path in sorted((run / 'schemas').glob('*.json')):
        freeze(destination / 'schemas' / path.name, path.read_bytes())
    # Every HTTP attempt/response is retained verbatim; no audio or configured keys.
    for path in sorted(runner.directory.rglob('*')):
        if path.is_file() and not path.name.startswith('.'):
            freeze(destination / 'execution' / path.relative_to(runner.directory), path.read_bytes())
    rows, ledger = [], []
    new_index = {s['pilot_id']: i for i, s in enumerate(m['schedule'], 1)}
    for t in m['tracks']:
        pid = t['pilot_id']
        cached = t['cached_profile']
        if cached:
            result = runner.cached[pid]
            producer = root / cached['source_run']
            raw = read(producer / result['response_file'])
            freeze(destination / 'cached_prior' / f'{pid}.result.json',
                   (producer / 'execution/attempts' / f'attempt-{cached["source_attempt"]:02d}.result.json').read_bytes())
            freeze(destination / 'cached_prior' / f'{pid}.raw_response.json', (producer / result['response_file']).read_bytes())
            collection = 'REUSED_EXACT_PRIOR_PROFILE'
        else:
            index = new_index[pid]
            invalid = runner.failure_path(index).exists()
            result = runner.verified_failure(index) if invalid else runner.verified_result(index)
            raw = read(run / result['response_file'])
            collection = 'INVALID_PROFILE' if invalid else 'NEW_VALIDATED_PROFILE'
            reservation = read(runner.directory / 'attempts' / f'attempt-{index:02d}.reservation.json')
            metadata = read((run / result['response_file']).with_suffix('.json'))
            ledger.append({'attempt': index, 'pilot_id': pid, 'neutral_id': t['neutral_id'],
                'status': collection, 'response_id': raw.get('responseId'), 'model_version': raw.get('modelVersion'),
                'finish_reasons': [c.get('finishReason') for c in raw.get('candidates', [])],
                'usage': raw.get('usageMetadata'), 'latency_seconds': metadata['latency_seconds'],
                'counted_input_tokens': reservation['counted_input_tokens'],
                'reserved_upper_cost_usd': reservation['reserved_upper_cost_usd'],
                'actual_cost_usd': result['actual_cost_usd']})
        profile = result['profile']
        freeze_json(destination / 'profiles' / f'{pid}.json', {'spotify_track_id': t['spotify_track_id'],
            'collection_status': collection, 'profile': profile, 'original_cache_reference': cached,
            'response_id': raw.get('responseId'), 'model_version': raw.get('modelVersion')})
        freeze_json(destination / 'preparation' / f'{pid}.json', t['prepared'])
        freeze(destination / 'source_provenance' / f'{pid}.json', (root / t['provenance_path']).read_bytes())
        rows.append({'pilot_id': pid, 'spotify_track_id': t['spotify_track_id'], 'title': t['catalog_title'],
            'artists': t['catalog_artists'], 'collection_status': collection,
            'duration_seconds': t['prepared']['duration_seconds'], 'source_sha256': t['source_sha256'],
            'prepared_sha256': t['prepared']['prepared_sha256'], 'profile_status': profile['status'] if profile else None,
            **{k: profile.get(k) if profile else None for k in ('primary_family', 'primary_style', 'secondary_families',
                'secondary_styles', 'vocal_role', 'arrangement_focus', 'texture_tags', 'active_section_density',
                'section_variation', 'certainty', 'audio_evidence')},
            'owner_confirmed': False})
    freeze_json(destination / 'classifications.json', rows)
    freeze(destination / 'classifications.csv', csv_bytes(rows, list(rows[0])))
    freeze_json(destination / 'usage_ledger.json', ledger)
    new_spend = sum((Decimal(r['actual_cost_usd']) for r in ledger), Decimal(0))
    summary = {'status': 'FROZEN100_CLASSIFICATIONS_AWAITING_OWNER_REVIEW', 'track_count': len(rows),
        'source_blocked_tracks': [], 'replay': replay, 'new_generation_calls': len(ledger),
        'reused_exact_profiles': 16, 'automatic_retries': 0, 'repeat_generation_calls': 0,
        'prior_generation_calls': 38, 'combined_generation_calls': 38 + len(ledger),
        'new_standard_rate_cost_usd': str(new_spend), 'prior_standard_rate_cost_usd': m['prior_settled_usd'],
        'combined_standard_rate_cost_usd': str(new_spend + Decimal(m['prior_settled_usd'])),
        'combined_spend_cap_usd': '2', 'profile_status_counts': dict(sorted(Counter(r['profile_status'] or 'invalid' for r in rows).items())),
        'raw_primary_family_counts': dict(sorted(Counter(r['primary_family'] for r in rows if r['primary_family']).items())),
        'label_normalization': 'None; provider spelling/case retained. Counts are lexical, not inferred musical taxonomy.',
        'manifest_sha256': runner.manifest_sha, 'prompt_sha256': file_sha256(run / 'prompt.txt'),
        'schema_sha256': file_sha256(run / 'response_schema.json'),
        'generation_config_sha256': digest(m['generation_config']),
        'protected_file_count': len(m['protected_hashes']), 'all_protected_hashes_verified': True,
        'owner_confirmed_classifications': 0, 'compatibility_or_accuracy_evaluation_performed': False}
    freeze_json(destination / 'summary.json', summary)
    readme = f'''# Frozen-100 free-form Gemini classifications

All {len(rows)} original amended frozen tracks are retained: {replay['unique_profiles']} validated profiles,
including 16 exact prior profiles and {replay['new_validated_profiles']} new profiles;
{replay['invalid_profiles']} explicitly invalid outputs. No source is missing or quarantined.

Gemini `gemini-3.8-flash`, LOW thinking, described full metadata-stripped native-rate FLAC recordings.
The exact preceding free-form prompt supplies no genre vocabulary, definitions, examples or mappings.
Each request contains only its neutral audio identifier, duration, full audio, prompt and schema.
No artist/song identities, metadata, ratings, neighbors, search or conversation context were supplied.
Source identity reuses the frozen retained recording/provenance; this is not a fresh owner check of all 100 recordings.

There were {len(ledger)} new generation calls, zero automatic retries and zero new repeats.
New standard-rate token cost: ${new_spend}; combined prior/current cost:
${new_spend + Decimal(m['prior_settled_usd'])}, within the preserved $2 cap.
Each generation was preceded by exact request counting and a $0.817152 worst-case reservation.
`usage_ledger.json` preserves billed input, output, thinking, response IDs, returned versions,
finish reasons and latency. The execution directory retains every HTTP request receipt/raw response.

`classifications.csv` / `classifications.json` contain all 100 identities and raw labels/facets.
`profiles/` contains validated profiles or explicit null failures. `source_provenance/` and
`preparation/` record source/prepared hashes, durations, complete PCM equality and conversion commands.
Audio binaries and secrets are excluded from Git.

All new profiles were frozen before this aggregate export. Cache replay made zero API calls;
all {len(m['protected_hashes'])} protected input hashes verified. The 16 reused profiles keep
their original implementation/cache identity rather than pretending to be new calls.

These are unreviewed model descriptions, not owner-confirmed style truth or playlist decisions.
Model size and asserted certainty do not establish classification accuracy. Free-form terminology
is preserved verbatim, including inconsistent spelling/case. No taxonomy normalization,
accuracy score, held-out comparison, reranking or production activation was performed.
The next step is owner inspection of these classifications before any compatibility experiment.

From `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.gemini_frozen100 replay --run {run.relative_to(root)}
.venv/bin/python -m audio_similarity.gemini_frozen100 export --run {run.relative_to(root)} --report {destination.relative_to(root)}
```

The export is create-once and deterministically ordered; changed existing bytes are rejected.
`artifact_manifest.json` covers every public artifact except itself.
'''
    freeze(destination / 'README.md', readme.encode())
    manifest = {'files': hashes([p for p in destination.rglob('*') if p.is_file() and p.name != 'artifact_manifest.json'], destination)}
    freeze_json(destination / 'artifact_manifest.json', manifest)
    verify_hashes(destination, manifest['files'])
    return summary
