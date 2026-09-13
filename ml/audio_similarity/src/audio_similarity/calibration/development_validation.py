"""Read-only execution checks and receipts, separate from ranking selection."""
from collections import Counter
from decimal import Decimal
import importlib.metadata
import json
from pathlib import Path

from .contracts import digest, file_hash, freeze_json, require
from .development_inputs import AUDIT, RUN, load


def dependencies(root):
    names = ['holistic_encoders.py', 'stage5a_contract.py', 'stage5c1_pipeline.py',
        'stage4a_sampling.py', 'stage5e1_sampling.py', 'stage5e1_encoders.py']
    paths = [root / 'src/audio_similarity' / name for name in names]
    packages = ['torch', 'torchaudio', 'numpy', 'librosa', 'laion-clap', 'muq', 'transformers', 'httpx']
    versions = {}
    for name in packages:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = 'NO_DISTRIBUTION_METADATA'
    value = {'schema': 'development-dependency-receipt-v1',
        'purpose': 'Supplement producer configuration with exact reused implementation/package identities.',
        'implementation_hashes': {str(p.relative_to(root)): file_hash(p) for p in paths}, 'packages': versions}
    freeze_json(root / RUN / 'dependency_receipt.json', value)
    return value


def frozen_genre_inputs(root):
    packet = json.loads((root / '.research_audio/genre_force/v1_m3/input.json').read_text())
    names = ['configs/genre_registry_v1/mapper_reference.py',
        'configs/genre_force_v1/genre-neighborhood-map-v1.json',
        'configs/genre_force_v1/genre-force-explorer-v1.json']
    original = packet['provenance']['input_hashes']
    values = {name: original[name] for name in names}
    values['configs/genre_registry_v1/genre-neighborhood-map-v1.json'] = values['configs/genre_force_v1/genre-neighborhood-map-v1.json']
    for name, expected in values.items():
        require(file_hash(root / name) == expected, 'frozen genre mapper/scoring configuration changed')
    freeze_json(root / RUN / 'genre_input_receipt.json', values)
    return values


def integrity(root):
    captured = json.loads((root / AUDIT / 'capture.private.json').read_text())
    protected = {p: entry['sha256'] for p, entry in captured['files'].items()
        if not p.startswith('.research_audio/example_playlist_batches_v2/')}
    changed = [p for p, expected in protected.items() if file_hash(root / p) != expected]
    sources = captured['sources']
    changed_sources = [s['request_id'] for s in sources if file_hash(root / s['source_path']) != s['actual_source_sha256']]
    result = {'status': 'PASS' if not changed and not changed_sources else 'FAIL',
        'protected_text_files': len(protected), 'retained_source_files': len(sources),
        'changed_text_files': changed, 'changed_sources': changed_sources,
        'active_extension_state_excluded': True}
    require(result['status'] == 'PASS', 'historical input integrity changed')
    return result


def historical_payloads(root):
    directories = ['reports/stage5e1_four_arm_retrieval',
        'reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3',
        'reports/gemini_style_pilot/frozen100_free_genre_v1',
        'reports/genre_force_mechanical_gate/v1']
    checked, changed = {}, []
    for directory in directories:
        manifest = json.loads((root / directory / 'artifact_manifest.json').read_text())
        entries = manifest.get('files', manifest)
        if isinstance(entries, list):
            entries = {entry['path']: entry['sha256'] for entry in entries}
        for relative, expected in entries.items():
            path = root / directory / relative
            if file_hash(path) != expected:
                changed.append(str(path.relative_to(root)))
        checked[directory] = len(entries)
    require(not changed, 'historical published payload differs from original manifest')
    return {'status': 'PASS', 'checked_original_manifests': checked, 'changed': changed}


def audio_receipt(root):
    from .development_audio import vector_ok
    plan, run = load(root), root / RUN
    config = json.loads((run / 'audio_config.json').read_text())
    counters, hashes, repairs = Counter(), {}, []
    for t in plan['tracks']:
        path = run / 'audio' / (t['request_id'] + '.json')
        ledger = run / 'audio_ledger' / (t['request_id'] + '.json')
        require(path.exists() and ledger.exists(), 'WAITING_FOR_FEATURES')
        row = json.loads(path.read_text())
        require(row['configuration_sha256'] == digest(config) and row['source_sha256'] == t['source_sha256'], 'cache linkage changed')
        require(all(vector_ok(row[k]) for k in ('C_center30', 'C_method_c', 'M')), 'pooled vector invalid')
        counters.update(json.loads(ledger.read_text())['inference_calls'])
        hashes[str(path.relative_to(root))] = file_hash(path)
        hashes[str(ledger.relative_to(root))] = file_hash(ledger)
        if t['repair_required']:
            repairs.append({'request_id': t['request_id'], 'title': t['title'], 'artists': t['artists'],
                'retained_source_sha256': t['source_sha256'], 'old_linked_source_sha256': t['prior_representation']['source_audio_sha256'],
                'new_cache_path': str(path.relative_to(root)), 'origins': row['origins']})
    result = {'status': 'AUDIO_FEATURES_COMPLETE', 'tracks': len(plan['tracks']),
        'sample_tracks': sum(t['in_sample'] for t in plan['tracks']), 'original_inference_calls': dict(counters),
        'source_link_repairs': repairs, 'files': hashes}
    freeze_json(run / 'audio_receipt.json', result)
    return result


def verify_audio_replay(root):
    original = json.loads((root / RUN / 'audio_receipt.json').read_text())
    for name, expected in original['files'].items():
        require(file_hash(root / name) == expected, 'original audio artifact/ledger changed during replay')
    result = {'status': 'PASS', 'unchanged_artifacts_and_ledgers': len(original['files']),
        'audio_tracks': original['tracks'], 'original_execution_ledger_preserved': True}
    freeze_json(root / RUN / 'audio_replay_integrity.json', result)
    return result


def usage(root):
    directory = root / RUN / 'gemini/execution/attempts'
    settlements = [json.loads(p.read_text()) for p in sorted(directory.glob('*.settlement.json'))]
    return {'generation_attempts': len(list(directory.glob('*.reservation.json'))),
        'settled_attempts': len(settlements), 'actual_cost_usd': str(sum((Decimal(s['actual_cost_usd']) for s in settlements), Decimal(0))),
        'unsettled_attempts': len(list(directory.glob('*.reservation.json'))) - len(settlements)}
