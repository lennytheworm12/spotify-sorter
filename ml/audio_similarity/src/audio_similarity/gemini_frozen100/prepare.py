"""Resolve, prepare and freeze 100 identities; reuse only exact prior requests."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from audio_similarity.gemini_free_genre_runner import FreeGenreRunner
from audio_similarity.gemini_style_pilot.manifest import CONFIG, MODEL, environment
from audio_similarity.gemini_style_pilot.prepare import prepare_audio
from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import digest, freeze, freeze_json, hashes, read, verify_hashes

CORPUS = Path('reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3')
PILOT = Path('.research_audio/gemini_style_pilot/free-genre-point-v1')
PILOT_REPORT = Path('reports/gemini_style_pilot/v1/free_genre_v1')
LIBRARY = Path('.research_audio/library_batches_v1')


def inventory(root, prior_manifest):
    source_path = root / CORPUS / 'source_manifest.json'
    verify_hashes(root / CORPUS, {'source_manifest.json': read(root / CORPUS / 'preparation_manifest.json')['source_manifest.json']})
    source = read(source_path)
    tracks = source['tracks']
    if source['track_count'] != 100 or len(tracks) != 100 or len({t['spotify_track_id'] for t in tracks}) != 100:
        raise ValueError('the exact frozen 100 identities are required')
    prior = {t['spotify_track_id']: t for t in prior_manifest['tracks']}
    if len(prior) != 16 or not set(prior) <= {t['spotify_track_id'] for t in tracks}:
        raise ValueError('expected all 16 pilot tracks within the frozen 100')
    current = read(root / '.research_audio/song_space/v3/audio-index.json')
    corrections = {t['spotify_track_id']: t for t in read(root / LIBRARY / 'source_corrections.json')['corrections']}
    quarantined = {t['spotify_track_id'] for t in read(root / LIBRARY / 'source_quarantines.json')['tracks']}
    rows, blocked = [], []
    neutral_index = 17
    for index, t in enumerate(sorted(tracks, key=lambda t: t['spotify_track_id']), 1):
        tid = t['spotify_track_id']
        old = prior.get(tid)
        neutral = old['neutral_id'] if old else f'N{neutral_index:03d}'
        if not old:
            neutral_index += 1
        path = root / t['retained_source_path']
        provenance_path = root / '.research_audio' / tid / 'provenance.json'
        reason = None
        if tid in quarantined:
            reason = 'QUARANTINED_SOURCE'
        elif tid in corrections or current.get(tid, {}).get('sha256') != t['source_sha256']:
            reason = 'CURRENT_SOURCE_DIFFERS_FROM_FROZEN_SOURCE_REQUIRES_EXPLICIT_VERSION_DECISION'
        elif not path.exists() or file_sha256(path) != t['source_sha256']:
            reason = 'MISSING_OR_CHANGED_FROZEN_SOURCE'
        elif not provenance_path.exists():
            reason = 'MISSING_PROVENANCE'
        if not reason:
            provenance = read(provenance_path)
            if (provenance.get('spotify_track_id') != tid or provenance.get('source_sha256') != t['source_sha256']
                or not provenance.get('full_decode_validated')):
                reason = 'INCOMPATIBLE_SOURCE_PROVENANCE'
            if old and old['prepared']['source_sha256'] != t['source_sha256']:
                reason = 'CACHED_PILOT_SOURCE_DIFFERS'
        row = {'pilot_id': f'F{index:03d}', 'neutral_id': neutral, 'spotify_track_id': tid,
               'catalog_title': t['title'], 'catalog_artists': t['artists'],
               'retained_source_path': str(path.relative_to(root)), 'source_sha256': t['source_sha256'],
               'provenance_path': str(provenance_path.relative_to(root)),
               'previous_pilot_id': old['pilot_id'] if old else None,
               'source_status': reason or 'MATCHES_FROZEN_RETAINED_SOURCE_AND_PROVENANCE',
               'source_correction_applied': False, 'eligible': reason is None}
        rows.append(row)
        if reason:
            blocked.append({'spotify_track_id': tid, 'title': t['title'], 'status': reason})
    return {'track_count': 100, 'tracks': rows, 'blocked': blocked,
            'identity_limit': 'Reuses the previously reviewed retained recording and provenance; not a fresh independent owner identity check of all 100.'}


def prepare_inventory(root, run, *, workers=4):
    prior = FreeGenreRunner(root, root / PILOT)
    prior.replay()
    value = inventory(root, prior.manifest)
    freeze_json(run / 'source_inventory.json', value)
    if value['blocked']:
        raise ValueError('source inventory has blocked tracks; no substitutions or inference')
    old_tracks = {t['pilot_id']: t for t in prior.manifest['tracks']}
    results = [prior.verified_result(i) for i in range(1, 17)]
    old_results = {r['pilot_id']: r for r in results}

    def prepare_one(t):
        destination = run / 'prepared' / f'{t["neutral_id"]}.flac'
        if t['previous_pilot_id']:
            old = old_tracks[t['previous_pilot_id']]
            prepared = old['prepared']
            original = root / prior.manifest['prepared_root'] / prepared['prepared_filename']
            verify_hashes(original.parent, {original.name: prepared['prepared_sha256']})
            freeze(destination, original.read_bytes())
            freeze_json(destination.with_suffix('.json'), prepared)
            result = old_results[t['previous_pilot_id']]
            cached = {'source_run': str(PILOT), 'source_attempt': result['attempt'],
                      'source_pilot_id': result['pilot_id'], 'cache_key': result['cache_key'],
                      'result_sha256': file_sha256(prior.result_path(result['attempt'])),
                      'source_manifest_sha256': prior.manifest_sha}
        else:
            prepared = prepare_audio(root / t['retained_source_path'], t['source_sha256'], destination)
            cached = None
        return t | {'prepared': prepared, 'cached_profile': cached}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = []
        for row in pool.map(prepare_one, value['tracks']):
            rows.append(row)
            print(f'Prepared {len(rows)}/100 ({row["neutral_id"]}; {"reuse" if row["cached_profile"] else "new FLAC"})', flush=True)
    freeze_json(run / 'prepared_inventory.json', value | {'tracks': rows, 'prepared_count': len(rows)})
    return rows


def reconciled_prior_spend(root):
    """All 38 previous attempts, including failed responses, remain charged."""
    total, count, files = Decimal(0), 0, []
    for report in (root / 'reports/gemini_style_pilot/v1/duration_v3', root / PILOT_REPORT):
        verify_hashes(report, read(report / 'artifact_manifest.json')['files'])
        files += [report / 'artifact_manifest.json', *[report / name for name in read(report / 'artifact_manifest.json')['files']]]
        for path in sorted((report / 'attempts').glob('call-*.raw_response.json')):
            usage = read(path)['usageMetadata']
            p, o, h = usage['promptTokenCount'], usage['candidatesTokenCount'], usage.get('thoughtsTokenCount', 0)
            if any(type(n) is not int or n < 0 for n in (p, o, h)) or usage['totalTokenCount'] != p + o + h:
                raise ValueError('prior token usage does not reconcile')
            if usage.get('toolUsePromptTokenCount', 0) or usage.get('serviceTier', 'standard') not in ('standard', 'unspecified'):
                raise ValueError('unexpected prior billing tier or tool use')
            total += (p * Decimal('.75') + (o + h) * Decimal('3.75')) / 1_000_000
            count += 1
    if count != 38:
        raise ValueError('expected all 38 prior generation attempts')
    return total, files


def freeze_manifest(root, run):
    if read(run / 'authorization.json').get('owner_message') != 'feel free to run the gemini calls on the 100 songs too':
        raise ValueError('expected the explicit frozen-100 execution authorization')
    if not (run / 'protocol.md').is_file():
        raise ValueError('freeze the corpus execution protocol before inference')
    rows = read(run / 'prepared_inventory.json')['tracks']
    if len(rows) != 100 or any(not r['eligible'] for r in rows):
        raise ValueError('complete eligible frozen-100 preparation required')
    cached = [t for t in rows if t['cached_profile']]
    schedule = [{'pilot_id': t['pilot_id'], 'repeat': False} for t in rows if not t['cached_profile']]
    if len(cached) != 16 or len(schedule) != 84:
        raise ValueError('expected 16 exact cached profiles and 84 new requests')
    prior = FreeGenreRunner(root, root / PILOT)
    prior.replay()
    freeze(run / 'prompt.txt', (root / PILOT / 'prompt.txt').read_bytes())
    base = read(root / PILOT / 'response_schema.json')
    freeze_json(run / 'response_schema.json', base)
    schemas = {}
    for t in rows:
        schema = copy.deepcopy(base)
        schema['properties']['audio_evidence']['items']['properties']['at_seconds']['maximum'] = t['prepared']['duration_seconds']
        name = f'schemas/{t["neutral_id"]}.json'
        freeze_json(run / name, schema)
        schemas[t['pilot_id']] = name
        if t['cached_profile'] and schema != prior.schema_for(t['previous_pilot_id']):
            raise ValueError('cached request schema differs from corpus schema')
    spent, protected = reconciled_prior_spend(root)
    protected += [root / CORPUS / name for name in read(root / CORPUS / 'preparation_manifest.json')]
    protected += [root / CORPUS / name for name in ('preparation_manifest.json', 'post_review_rating_snapshot.json', 'historical_reference_matrices.npz')]
    protected += [root / LIBRARY / name for name in ('manifest.json', 'source_corrections.json', 'source_quarantines.json')]
    protected += list((root / '.research_audio/song_space/v3').glob('*.json'))
    protected += list(root.glob('artifacts/**/representations.sqlite'))
    protected += [root / t[k] for t in rows for k in ('retained_source_path', 'provenance_path')]
    for name in ('owner_listening_v1', 'owner_clarification_v1'):
        protected += list((root / 'reports/gemini_style_pilot/v1' / name).glob('*'))
    implementation = list(Path(__file__).parent.glob('*.py'))
    implementation += [root / p for p in prior.manifest['implementation_hashes']]
    code_hashes = hashes(implementation, root)
    input_files = [p for p in run.rglob('*') if p.is_file()]
    inputs = hashes(input_files, root)
    # Per-request checks avoid hashing gigabytes of unrelated audio repeatedly;
    # all bytes are verified at startup, replay and freeze, and each upload checks its exact prepared hash.
    critical = {k: v for k, v in inputs.items() if not k.endswith('.flac')}
    m = {'schema_version': 'gemini-frozen100-v1', 'model_id': MODEL, 'generation_config': CONFIG,
         'environment': environment(), 'rates': prior.manifest['rates'], 'input_token_limit': 1048576,
         'tracks': rows, 'schedule': schedule, 'response_schemas': schemas,
         'prepared_root': str((run / 'prepared').relative_to(root)),
         'ontology': None, 'genre_examples': None, 'genre_definitions': None,
         'max_attempts': 84, 'prior_attempts': 38, 'combined_attempt_cap': 122,
         'prior_settled_usd': str(spent), 'spend_cap_usd': str(Decimal(2) - spent),
         'combined_spend_cap_usd': '2', 'automatic_retries': 0,
         'cached_profiles': {t['pilot_id']: t['cached_profile'] for t in cached},
         'implementation_hashes': code_hashes, 'implementation_sha256': digest(code_hashes),
         'input_hashes': inputs, 'critical_input_hashes': critical, 'protected_hashes': hashes(protected, root),
         'cache_compatibility': 'Exact source/prepared hash, neutral context, model/config, prompt/schema and original producer implementation identity verified; preserve original cache identity, do not rerun for wrapper changes.',
         'frozen_utc': datetime.now(timezone.utc).isoformat(),
         'failure_policy': 'Two new engineering smokes first. Stop globally on smoke failure, transport/audio-envelope/budget/accounting failures. After smokes, an accounted schema/semantic output failure is an explicit per-track null; continue other tracks without retries.',
         'analysis_policy': 'Freeze profiles before aggregate classifications or rating joins. No label normalization beyond display, genre rules, new labels, ranking or production changes.',
         'api_sources': prior.manifest['api_sources']}
    freeze_json(run / 'execution_manifest.json', m)
    return m
