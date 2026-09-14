"""Metadata-stripped audio preparation; no provider access or paid calls."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json

from .contracts import digest, file_hash, freeze_json, require
from .gemini_full_inputs import DEV, RUN, read
from ..gemini_style_pilot.prepare import prepare_audio
from ..gemini_style_pilot.manifest import environment


def prepare(root):
    root = root.resolve()
    preflight = read(root / RUN / 'preflight.json')
    require(file_hash(root / preflight['corpus_path']) == preflight['corpus_sha256'], 'corpus changed')
    old = read(root / DEV / 'gemini/execution_manifest.json')
    require(environment() == old['environment'], 'Gemini environment changed')
    missing = [t for t in preflight['recordings'] if t['profile'] is None]
    # Separate runs keep the exact three-digit provider-visible ID contract.
    # Their global spend cap is allocated before any run is authorized.
    groups = [missing[i:i + 900] for i in range(0, len(missing), 900)]
    plans = []
    for batch, tracks in enumerate(groups, 1):
        directory = root / RUN / f'batch_{batch:04d}'
        directory.mkdir(parents=True, exist_ok=True)
        for name in ('prompt.txt', 'response_schema.json'):
            raw = (root / DEV / 'gemini' / name).read_bytes()
            path = directory / name
            if path.exists():
                require(path.read_bytes() == raw, 'frozen prompt/schema changed')
            else:
                path.write_bytes(raw)

        def convert(item):
            index, t = item
            pid, neutral = f'T{index:03d}', f'N{index:03d}'
            receipt = prepare_audio(root / t['source_path'], t['audio_sha256'],
                                    directory / 'prepared' / (neutral + '.flac'))
            schema = read(directory / 'response_schema.json')
            schema['properties']['audio_evidence']['items']['properties']['at_seconds']['maximum'] = receipt['duration_seconds']
            schema_name = f'schemas/{pid}.json'
            freeze_json(directory / schema_name, schema)
            print(json.dumps({'batch': batch, 'prepared': index, 'batch_total': len(tracks)}), flush=True)
            return {'pilot_id': pid, 'neutral_id': neutral, 'recording_id': t['recording_id'],
                'source_path': t['source_path'], 'source_sha256': t['audio_sha256'],
                'prepared': receipt, 'response_schema': schema_name, 'response_schema_sha256': digest(schema)}

        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(convert, enumerate(tracks, 1)))
        plan = {'schema': 'full-corpus-gemini-prepared-batch-v1', 'batch': batch,
            'preflight_sha256': file_hash(root / RUN / 'preflight.json'), 'tracks': rows,
            'model_id': old['model_id'], 'generation_config': old['generation_config'],
            'environment': old['environment'], 'prompt_sha256': file_hash(directory / 'prompt.txt'),
            'base_schema_sha256': file_hash(directory / 'response_schema.json'),
            'prepared_root': str((directory / 'prepared').relative_to(root)), 'new_api_calls': 0}
        freeze_json(directory / 'prepared_plan.json', plan)
        plans.append({'path': str((directory / 'prepared_plan.json').relative_to(root)),
                      'sha256': digest(plan), 'tracks': len(rows)})
    result = {'status': 'AUDIO_PREPARED_NO_CALLS', 'batches': plans, 'new_api_calls': 0,
              'prepared_tracks': len(missing), 'preflight_sha256': file_hash(root / RUN / 'preflight.json')}
    freeze_json(root / RUN / 'prepared.json', result)
    return result


if __name__ == '__main__':
    print(json.dumps(prepare(Path.cwd()), indent=2))
