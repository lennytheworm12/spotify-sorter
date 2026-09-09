"""Freeze the exact 16-track execution contract before any provider upload."""
from __future__ import annotations

import importlib.metadata
import platform
from datetime import date
from pathlib import Path

from audio_similarity.stage5e3_artifacts import digest, freeze_json, hashes, read, verify_hashes


MODEL = 'gemini-3.8-flash'
CONFIG = {
    'candidateCount': 1, 'maxOutputTokens': 8192, 'responseMimeType': 'application/json',
    'temperature': 1, 'topP': 0.95, 'topK': 64,
    'thinkingConfig': {'includeThoughts': False, 'thinkingLevel': 'LOW'},
}
PILOT_IDS = [f'A{i:02d}' for i in range(1, 11)] + [f'C{i:02d}' for i in range(1, 7)]
PRIMARY_ORDER = ['A01', 'A03'] + [pid for pid in PILOT_IDS if pid not in ('A01', 'A03')]
REPEAT_ORDER = ['A01', 'A03', 'A08', 'C05']


def environment() -> dict:
    return {'python': platform.python_version(), 'httpx': importlib.metadata.version('httpx')}


def make_manifest(root: Path, run: Path, inventory_path: Path) -> dict:
    root, run, inventory_path = root.resolve(), run.resolve(), inventory_path.resolve()
    inventory = read(inventory_path)
    tracks = inventory['tracks']
    if ([t['pilot_id'] for t in tracks] != PILOT_IDS
            or len({t['spotify_track_id'] for t in tracks}) != 16
            or len({t['neutral_id'] for t in tracks}) != 16):
        raise ValueError('the complete original ordered 16-track set is required')
    blocked = [t['pilot_id'] for t in tracks if t.get('eligible') is not True
               or t.get('source_status', '').startswith('BLOCKED')]
    if blocked:
        raise ValueError(f'source identity unresolved: {", ".join(blocked)}')
    verify_hashes(run / 'contract', read(run / 'contract/input_hashes.json'))
    designed = read(run / 'contract/private/candidates.json')
    if [(t['pilot_id'], t['spotify_track_id']) for t in tracks] != [(t['pilot_id'], t['spotify_track_id']) for t in designed]:
        raise ValueError('inventory substitutes a designed Spotify identity')
    protected = read(run / 'source_checks/protected_hashes.json')
    verify_hashes(root, protected)
    api = read(run / 'preflight/api_contract.json')
    if api['requested_model'] != MODEL or api['generation_config'] != CONFIG:
        raise ValueError('model or sampler differs from verified preflight')
    rates = api['rates_usd_per_million']
    if rates != {'input': '0.75', 'output_including_thinking': '3.75',
                 'tier': 'standard', 'valid_through': '2026-12-31'}:
        raise ValueError('pricing requires a new reviewed execution contract')
    if date.today() > date.fromisoformat(rates['valid_through']):
        raise ValueError('verified prices expired')
    metadata_path = run / 'preflight/model_access.json'
    metadata = read(metadata_path)['model']
    if (metadata['name'] != f'models/{MODEL}' or metadata['inputTokenLimit'] != 1048576
            or metadata['outputTokenLimit'] < CONFIG['maxOutputTokens']):
        raise ValueError('verified model token bounds do not match')
    files = [inventory_path, run / 'preflight/api_contract.json', run / 'contract/input_hashes.json', metadata_path]
    files += [run / 'contract' / name for name in read(run / 'contract/input_hashes.json')]
    for track in tracks:
        prepared = track['prepared']
        path = run / 'prepared' / prepared['prepared_filename']
        source = Path(prepared['source_path'])
        verify_hashes(path.parent, {path.name: prepared['prepared_sha256']})
        verify_hashes(source.parent, {source.name: prepared['source_sha256']})
        if not prepared['full_recording_preserved'] or not prepared['identity_metadata_removed']:
            raise ValueError('prepared full-recording contract is not satisfied')
        files += [path, path.with_suffix('.json'), source]
    implementation = hashes(list(Path(__file__).parent.glob('*.py')), Path(__file__).parent)
    value = {
        'schema_version': 'gemini-style-execution-v1', 'model_id': MODEL,
        'generation_config': CONFIG, 'environment': environment(), 'rates': rates,
        'input_token_limit': 1048576, 'spend_cap_usd': '2', 'max_attempts': 20,
        'automatic_retries': 0, 'tracks': tracks,
        'service_tier': 'standard (documented default when omitted)',
        'schedule': [{'pilot_id': pid, 'repeat': False} for pid in PRIMARY_ORDER]
                    + [{'pilot_id': pid, 'repeat': True} for pid in REPEAT_ORDER],
        'input_hashes': hashes(files, root), 'protected_hashes': protected,
        'implementation_hashes': implementation, 'implementation_sha256': digest(implementation),
        'smoke_policy': 'First two attempts must pass transport, audio-input, usage and schema checks. No semantic agreement gate.',
        'failure_policy': 'Stop on any operational failure; retain every attempt; no automatic retry or winner selection.',
        'transport': 'Files API; neutral display names; full FLAC; verify returned uploaded-byte SHA-256.',
        'post_profile_boundary': 'Freeze all 16 primaries and attempted repeats before rating inventory or owner-style analysis.',
    }
    freeze_json(run / 'execution_manifest.json', value)
    return value


def load_manifest(root: Path, run: Path) -> dict:
    path = run / 'execution_manifest.json'
    if not path.exists():
        raise ValueError('no frozen execution manifest; source identity may still be blocked')
    value = read(path)
    if value['model_id'] != MODEL or value['generation_config'] != CONFIG:
        raise ValueError('unsupported frozen model/configuration')
    if environment() != value['environment']:
        raise ValueError('execution environment changed')
    verify_hashes(root, value['input_hashes'])
    verify_hashes(Path(__file__).parent, value['implementation_hashes'])
    verify_hashes(root, value['protected_hashes'])
    return value
