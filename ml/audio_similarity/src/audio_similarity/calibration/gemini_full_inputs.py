"""Read-only inventory and exact-source reuse for the full frozen corpus."""
from decimal import Decimal
from pathlib import Path
import json

from .contracts import digest, file_hash, freeze_json, require
from ..gemini_free_genre_runner import FreeGenreRunner

RUN = Path('.research_audio/playlist_calibration_gemini_full_v1')
METHOD_C = Path('.research_audio/playlist_calibration_method_c_gpu_v1')
DEV = Path('.research_audio/playlist_calibration_development_v1')
FROZEN100 = Path('.research_audio/gemini_style_pilot/frozen100-free-genre-v1')
PUBLIC = Path('reports/playlist_weight_calibration/v1/gemini_full')
PRIOR_RUNS = (DEV / 'gemini', FROZEN100,
              Path('.research_audio/gemini_style_pilot/free-genre-point-v1'))


def read(path):
    return json.loads(path.read_text())


class HistoricalReader(FreeGenreRunner):
    """Use the original response/cache verifier without creating files or a client."""

    def __init__(self, root, run):
        self.root, self.run = root.resolve(), (root / run).resolve()
        self.manifest = read(self.run / 'execution_manifest.json')
        self.manifest_sha = file_hash(self.run / 'execution_manifest.json')
        self.directory = self.run / 'execution'
        self.tracks = {t['pilot_id']: t for t in self.manifest['tracks']}
        self.prompt = (self.run / 'prompt.txt').read_text()

    def profile(self, pid):
        t = self.tracks[pid]
        indices = [i for i, slot in enumerate(self.manifest['schedule'], 1)
                   if slot['pilot_id'] == pid and not slot['repeat']]
        if indices:
            require(len(indices) == 1, 'multiple primary results')
            result = self.verified_result(indices[0])
            path = self.result_path(indices[0])
            return result['profile'], {'run': str(self.run.relative_to(self.root)),
                'pilot_id': pid, 'result_path': str(path.relative_to(self.root)),
                'result_sha256': file_hash(path), 'manifest_sha256': self.manifest_sha}
        cached = t.get('cached_profile')
        require(cached, 'missing historical primary and cache reference')
        if 'source_run' in cached:
            old = HistoricalReader(self.root, Path(cached['source_run']))
            require(old.manifest_sha == cached['source_manifest_sha256'], 'cached predecessor changed')
            profile, origin = old.profile(cached['source_pilot_id'])
            require(origin['result_sha256'] == cached['result_sha256'], 'cached primary hash differs')
            old_t = old.tracks[cached['source_pilot_id']]
            require(old_t['prepared']['prepared_sha256'] == t['prepared']['prepared_sha256'],
                    'cached predecessor prepared source differs')
            return profile, origin
        # The development sample's one reused record is the frozen100 publication.
        path = self.root / t['cached_profile_path']
        require(file_hash(path) == t['cached_profile_sha256'] and read(path) == cached,
                'published cached profile changed')
        old = HistoricalReader(self.root, FROZEN100)
        matches = [p for p, row in old.tracks.items()
                   if row['spotify_track_id'] == t['stable_track_id']
                   and row['source_sha256'] == t['source_sha256']]
        require(len(matches) == 1, 'ambiguous published cache identity')
        profile, origin = old.profile(matches[0])
        require(profile == cached['profile'], 'published cache differs from provider response')
        return profile, origin


def historical_receipt(root):
    """Capture immutable manifest bytes, then verify all their named payloads."""
    manifests = [(METHOD_C / 'artifact_manifest.json', METHOD_C),
                 (DEV / 'artifact_manifest.private.json', DEV),
                 (Path('reports/gemini_style_pilot/frozen100_free_genre_v1/artifact_manifest.json'),
                  Path('reports/gemini_style_pilot/frozen100_free_genre_v1'))]
    files = {}
    for manifest, directory in manifests:
        files[str(manifest)] = file_hash(root / manifest)
        for name, expected in read(root / manifest)['files'].items():
            require(file_hash(root / directory / name) == expected, 'historical artifact changed: ' + name)
        print(json.dumps({'historical_manifest_verified': str(manifest)}), flush=True)
    return files


def inventory(root):
    root = root.resolve()
    corpus_path = root / METHOD_C / 'corpus.json'
    corpus = read(corpus_path)
    historical = historical_receipt(root)
    records = corpus['recordings']
    require([t['recording_id'] for t in records] == sorted({t['recording_id'] for t in records}),
            'frozen corpus must be ordered and unique')
    baseline = HistoricalReader(root, DEV / 'gemini')
    readers = [HistoricalReader(root, p) for p in PRIOR_RUNS]
    contracts, candidates = {}, {}
    for reader in readers:
        relative = str(reader.run.relative_to(root))
        compatible = (reader.manifest['model_id'] == baseline.manifest['model_id']
            and reader.manifest['generation_config'] == baseline.manifest['generation_config']
            and reader.manifest['environment'] == baseline.manifest['environment']
            and reader.prompt == baseline.prompt
            and file_hash(reader.run / 'response_schema.json') == file_hash(baseline.run / 'response_schema.json'))
        contracts[relative] = {'manifest_sha256': reader.manifest_sha, 'compatible': compatible,
            'tracks': len(reader.tracks)}
        if not compatible:
            continue
        for pid, t in reader.tracks.items():
            key = (t.get('stable_track_id', t.get('spotify_track_id')),
                   t.get('source_sha256', t['prepared']['source_sha256']))
            candidates.setdefault(key, []).append((reader, pid))
    rows = []
    for i, t in enumerate(records, 1):
        require(not t['errors'], 'frozen source has unresolved errors')
        require(file_hash(root / t['source_path']) == t['audio_sha256'], 'retained audio changed')
        require(file_hash(root / t['provenance_path']) == t['provenance_sha256'], 'source provenance changed')
        profile, origins, prepared = None, [], None
        for reader, pid in candidates.get((t['recording_id'], t['audio_sha256']), []):
            p, origin = reader.profile(pid)
            require(profile is None or profile == p, 'conflicting compatible profiles; review required')
            profile = p
            origins.append(origin)
            receipt = reader.tracks[pid]['prepared']
            require(receipt['source_sha256'] == t['audio_sha256']
                    and receipt['full_recording_preserved'] and receipt['identity_metadata_removed'],
                    'historical profile not linked to full stripped source')
            require(file_hash(Path(receipt['conversion_command'][-1])) == receipt['prepared_sha256'],
                    'historical prepared audio changed')
            prepared = receipt
        rows.append(t | {'profile': profile, 'reuse_origins': origins, 'prepared': prepared,
                         'profile_status': 'REUSED_VALIDATED' if profile is not None else 'MISSING'})
        if i % 200 == 0:
            print(json.dumps({'source_profile_checks': i, 'total': len(records)}), flush=True)
    for name, expected in corpus['protected_files'].items():
        require(file_hash(root / name) == expected, 'frozen source record changed')
    missing = sum(t['profile'] is None for t in rows)
    settlements = [read(p) for p in (baseline.directory / 'attempts').glob('*.settlement.json')]
    prior_cost = sum((Decimal(s['actual_cost_usd']) for s in settlements), Decimal(0))
    counts = {'frozen_recordings': len(rows), 'original_requests': len(corpus['requests']),
        'source_unavailable_requests': sum(t['status'] == 'SOURCE_UNAVAILABLE' for t in corpus['requests']),
        'reused_profiles': len(rows) - missing, 'missing_profiles': missing}
    result = {'schema': 'full-corpus-gemini-preflight-v1', 'corpus_path': str(METHOD_C / 'corpus.json'),
        'corpus_sha256': file_hash(corpus_path), 'counts': counts, 'recordings': rows,
        'historical_manifest_hashes': historical, 'profile_cache_inventory': contracts,
        'prior_observed_calls': len(settlements), 'prior_observed_cost_usd': str(prior_cost),
        'empirical_remaining_cost_usd': str(prior_cost / len(settlements) * missing),
        'per_request_conservative_reservation_usd': str(Decimal(1048576) * Decimal('.75') / 1000000
                                                       + Decimal(8192) * Decimal('3.75') / 1000000),
        'budget_method': 'Same full-input-limit reservation and exact usage settlement as prior runner; empirical estimate is not a bound.',
        'source_use_status': corpus['source_use_status'],
        'upload_authorization': 'Owner approved expanded Gemini spending in current session; numeric cap pending.',
        'new_api_calls': 0, 'extension_included': False}
    freeze_json(root / RUN / 'preflight.json', result)
    summary = {k: v for k, v in result.items() if k != 'recordings'}
    freeze_json(root / PUBLIC / 'preflight.json', summary)
    return summary


if __name__ == '__main__':
    print(json.dumps(inventory(Path.cwd()), indent=2))
