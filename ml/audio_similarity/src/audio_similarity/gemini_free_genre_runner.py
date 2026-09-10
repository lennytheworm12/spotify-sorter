"""Small new inference arm using the original transport, ledger and replay machinery."""
from __future__ import annotations

import argparse
import fcntl
from datetime import date
from pathlib import Path

from .stage5b1a_models import file_sha256
from .stage5e3_artifacts import digest, freeze_json, hashes, read, verify_hashes
from .gemini_free_genre import load, prepare, validate_free_profile
from .gemini_style_pilot.inputs import request_body
from .gemini_style_pilot.runner import PilotRunner, RunStopped
from .gemini_style_pilot.transport import GeminiTransport, configured_key


def parse_response(value, schema, duration):
    candidates = value.get('candidates', [])
    if not value.get('responseId') or not value.get('modelVersion'):
        raise RunStopped('missing response ID or model version')
    if len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
        raise RunStopped('expected one complete STOP candidate')
    candidate = candidates[0]
    if candidate.get('groundingMetadata') or candidate.get('urlContextMetadata'):
        raise RunStopped('prohibited external grounding')
    audio = [p.get('tokenCount') for p in value.get('usageMetadata', {}).get('promptTokensDetails', [])
             if p.get('modality') == 'AUDIO']
    if not audio or any(type(n) is not int or n <= 0 for n in audio):
        raise RunStopped('provider did not confirm audio input tokens')
    parts = candidate.get('content', {}).get('parts', [])
    if not parts or any(p.get('thought') or not isinstance(p.get('text'), str) for p in parts):
        raise RunStopped('unexpected output parts')
    text = ''.join(p['text'] for p in parts)
    profile = validate_free_profile(text, schema=schema, duration=duration)
    return {'response_id': value['responseId'], 'model_version': value['modelVersion'],
            'finish_reason': candidate['finishReason'], 'usage': value['usageMetadata'],
            'response_text': text, 'profile': profile}


class FreeGenreRunner(PilotRunner):
    """Preserve original runner code; reuse its accounting, smoke/freeze and replay methods."""

    def __init__(self, root, run, *, transport_factory=None):
        self.root, self.run = Path(root).resolve(), Path(run).resolve()
        self.manifest = load(self.root, self.run)
        self.manifest_sha = file_sha256(self.run / 'execution_manifest.json')
        self.directory = self.run / 'execution'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.tracks = {t['pilot_id']: t for t in self.manifest['tracks']}
        self.transport_factory = transport_factory
        self.prompt = (self.run / 'prompt.txt').read_text()

    def key(self, pid):
        return digest({'arm': 'free-genre-v1', 'audio': vars(self.track_input(pid)),
                       'model': self.manifest['model_id'], 'config': self.manifest['generation_config'],
                       'prompt_sha256': file_sha256(self.run / 'prompt.txt'), 'ontology': None,
                       'schema_sha256': file_sha256(self.schema_path(pid)),
                       'implementation_sha256': self.manifest['implementation_sha256'],
                       'environment': self.manifest['environment']})

    def verified_result(self, index):
        result = read(self.result_path(index))
        slot = self.manifest['schedule'][index - 1]
        if (result['attempt'] != index or result['pilot_id'] != slot['pilot_id']
            or result['repeat'] != slot['repeat'] or result['manifest_sha256'] != self.manifest_sha
            or result['cache_key'] != self.key(slot['pilot_id'])):
            raise RunStopped('incompatible cached free-genre result')
        verify_hashes(self.run, result['evidence_hashes'])
        if result['response_file'] not in result['evidence_hashes']:
            raise RunStopped('raw response missing from evidence')
        parsed = parse_response(read(self.run / result['response_file']), self.schema_for(slot['pilot_id']),
                                self.track_input(slot['pilot_id']).duration_seconds)
        if any(result[k] != v for k, v in parsed.items()):
            raise RunStopped('cached result differs from raw response')
        if not slot['repeat'] and read(self.directory / 'profiles' / f'{result["cache_key"]}.json') != result:
            raise RunStopped('primary cache differs from original result')
        return result

    def _attempt(self, index, transport):
        slot = self.manifest['schedule'][index - 1]
        pid = slot['pilot_id']
        track = self.track_input(pid)
        prepared = self.root / self.manifest['prepared_root'] / self.tracks[pid]['prepared']['prepared_filename']
        uploaded = transport.upload(prepared, neutral_id=track.neutral_id, expected_sha256=track.prepared_sha256)
        body = request_body(track, file_uri=uploaded['uri'], prompt=self.prompt, ontology='',
                            schema=self.schema_for(pid), generation_config=self.manifest['generation_config'])
        body['systemInstruction']['parts'] = [{'text': self.prompt}]
        count, count_stem = transport.count_tokens(self.manifest['model_id'], body)
        ledger = self.ledger()
        reservation = ledger.reserve(counted_input=count.get('totalTokens'),
            max_output_tokens=self.manifest['generation_config']['maxOutputTokens'],
            request_sha256=digest(body), manifest_sha256=self.manifest_sha,
            neutral_id=track.neutral_id, repeat=slot['repeat'])
        if reservation['attempt'] != index:
            raise RunStopped('attempt ledger sequence diverged')
        attempts = self.directory / 'attempts'
        request = attempts / f'attempt-{index:02d}.request.json'
        freeze_json(request, body)
        response, response_stem = transport.generate(self.manifest['model_id'], body)
        if not response.is_success:
            raise RunStopped('generation HTTP failure; reservation remains unresolved')
        value = response.json()
        settlement = ledger.settle(index, value.get('usageMetadata', {}))
        parsed = parse_response(value, self.schema_for(pid), track.duration_seconds)
        evidence = [request, count_stem.with_suffix('.response.bin'), response_stem.with_suffix('.response.bin'),
                    response_stem.with_suffix('.response.json'), attempts / f'attempt-{index:02d}.reservation.json',
                    attempts / f'attempt-{index:02d}.settlement.json',
                    transport.directory / f'upload-{track.neutral_id}.json']
        result = {'attempt': index, 'pilot_id': pid, 'neutral_id': track.neutral_id, 'repeat': slot['repeat'],
                  'cache_key': self.key(pid), 'manifest_sha256': self.manifest_sha, **parsed,
                  'actual_cost_usd': settlement['actual_cost_usd'],
                  'response_file': str(response_stem.with_suffix('.response.bin').relative_to(self.run)),
                  'evidence_hashes': hashes(evidence, self.run)}
        freeze_json(self.result_path(index), result)
        if not slot['repeat']:
            freeze_json(self.directory / 'profiles' / f'{result["cache_key"]}.json', result)
        return result

    def next(self):
        with (self.directory / '.runner.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            load(self.root, self.run)
            if (self.directory / 'STOPPED.json').exists():
                raise RunStopped('previous operational failure; no automatic retry')
            index = 1
            while index <= len(self.manifest['schedule']) and self.result_path(index).exists():
                self.verified_result(index)
                index += 1
            if index > len(self.manifest['schedule']):
                return {'status': 'ALL_ATTEMPTS_COMPLETE', 'new_generation_calls': 0}
            if len(list((self.directory / 'attempts').glob('*.reservation.json'))) != index - 1:
                raise RunStopped('interrupted or unaccounted generation')
            if index > 2 and read(self.directory / 'smoke_gate.json') != self.smoke_record():
                raise RunStopped('engineering smokes do not verify')
            if date.today() > date.fromisoformat(self.manifest['rates']['valid_through']):
                raise RunStopped('verified rates expired')
            transport = None
            try:
                transport = self.transport_factory() if self.transport_factory else GeminiTransport(
                    self.directory / 'transport', configured_key(self.root / '.env'))
                result = self._attempt(index, transport)
                if index == 2:
                    freeze_json(self.directory / 'smoke_gate.json', self.smoke_record())
                return {'status': 'ATTEMPT_VALIDATED', 'attempt': index, 'neutral_id': result['neutral_id'],
                        'repeat': result['repeat'], 'new_generation_calls': 1, 'cost_usd': result['actual_cost_usd']}
            except Exception as exc:
                freeze_json(self.directory / 'STOPPED.json', {'attempt_slot': index,
                    'exception_type': type(exc).__name__, 'manifest_sha256': self.manifest_sha,
                    'reason': 'Operational failure. Inspect raw evidence; no automatic retry or output repair.'})
                raise
            finally:
                if transport:
                    transport.close()

    def reuse_uploads(self):
        """Copy only exact, still-valid receipts. Expired uploads are re-uploaded once normally."""
        from .gemini_style_pilot.transport import TransportStopped
        copied, expired = [], []
        for pid, name in self.manifest['reusable_uploads'].items():
            receipt = read(self.root / name)
            track = self.track_input(pid)
            path = self.root / self.manifest['prepared_root'] / self.tracks[pid]['prepared']['prepared_filename']
            if receipt['prepared_sha256'] != track.prepared_sha256:
                raise RunStopped('incompatible upload receipt')
            try:
                GeminiTransport._verify_file(receipt['file'], track.prepared_sha256, path.stat().st_size, track.neutral_id)
            except TransportStopped as exc:
                if 'expired' not in str(exc):
                    raise
                expired.append(pid)
                continue
            freeze_json(self.directory / 'transport' / f'upload-{track.neutral_id}.json', receipt)
            copied.append(pid)
        return {'reused_uploads': copied, 'expired_requiring_upload': expired, 'new_api_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'reuse-uploads', 'next', 'replay', 'freeze'])
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--prior', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--approval', type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    if args.action == 'prepare':
        m = prepare(root, args.prior, args.run, args.report, args.approval)
        print({'status': 'MANIFEST_FROZEN', 'attempt_cap': m['max_attempts'], 'prior_settled_usd': m['prior_settled_usd']})
        return
    runner = FreeGenreRunner(root, args.run)
    actions = {'next': runner.next, 'reuse-uploads': runner.reuse_uploads,
               'replay': runner.replay, 'freeze': runner.freeze_profiles}
    result = actions[args.action]()
    print({k: v for k, v in result.items() if k != 'files'})


if __name__ == '__main__':
    main()
