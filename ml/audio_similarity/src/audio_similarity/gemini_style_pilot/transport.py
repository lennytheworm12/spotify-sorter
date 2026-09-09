"""Audited Gemini REST transport. No retries, identity metadata, or output repair."""
from __future__ import annotations

import base64
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5e3_artifacts import freeze, freeze_json, read


BASE = 'https://generativelanguage.googleapis.com'


class TransportStopped(ValueError):
    pass


def configured_key(env_path: Path) -> str:
    """Read a configured key without shell execution, logging, or environment dumps."""
    values = {k: os.environ.get(k, '') for k in ['GOOGLE_API_KEY', 'GEMINI_API_KEY']}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            match = re.fullmatch(r'\s*(?:export\s+)?(GOOGLE_API_KEY|GEMINI_API_KEY)\s*=\s*(.*?)\s*', line)
            if match and not values[match[1]]:
                values[match[1]] = match[2].strip('"\'')
    key = values['GEMINI_API_KEY'] or values['GOOGLE_API_KEY']
    if not key or any(c.isspace() for c in key):
        raise TransportStopped('no usable Gemini key configured locally')
    return key


class GeminiTransport:
    def __init__(self, directory: Path, key: str, *, client=None, sleep=time.sleep):
        self.directory, self.key, self.sleep = directory, key, sleep
        directory.mkdir(parents=True, exist_ok=True)
        self.client = client or httpx.Client(timeout=httpx.Timeout(300, connect=30), follow_redirects=False)

    def close(self):
        self.client.close()

    def request(self, method: str, url: str, *, label: str, headers=None, **kwargs):
        # Even provider-returned upload locations must stay on the documented host.
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'generativelanguage.googleapis.com':
            raise TransportStopped('unexpected provider host')
        count = len(list(self.directory.glob('call-*.request.json'))) + 1
        stem = self.directory / f'call-{count:03d}'
        freeze_json(stem.with_suffix('.request.json'), {
            'method': method, 'path': parsed.path, 'label': label,
            'query_present': bool(parsed.query), 'started_utc': datetime.now(timezone.utc).isoformat(),
        })
        started = time.monotonic()
        try:
            response = self.client.request(method, url, headers={'x-goog-api-key': self.key, **(headers or {})}, **kwargs)
        except Exception as exc:
            # Exception text may contain signed URLs or headers; preserve type only.
            freeze_json(stem.with_suffix('.transport_error.json'), {
                'exception_type': type(exc).__name__, 'elapsed_seconds': time.monotonic() - started,
            })
            raise TransportStopped(f'{label}: transport failed; no retry') from None
        freeze(stem.with_suffix('.response.bin'), response.content)
        freeze_json(stem.with_suffix('.response.json'), {
            'http_status': response.status_code, 'latency_seconds': time.monotonic() - started,
            'response_sha256': file_sha256(stem.with_suffix('.response.bin')),
            'headers': {k: v for k, v in response.headers.items()
                        if k.lower() in {'content-type', 'date', 'x-request-id', 'x-goog-request-id'}},
        })
        return response, stem

    def upload(self, path: Path, *, neutral_id: str, expected_sha256: str) -> dict:
        if not re.fullmatch(r'N\d{3}', neutral_id) or file_sha256(path) != expected_sha256:
            raise TransportStopped('invalid neutral audio or prepared hash')
        receipt_path = self.directory / f'upload-{neutral_id}.json'
        if receipt_path.exists():
            receipt = read(receipt_path)
            if receipt['prepared_sha256'] != expected_sha256:
                raise TransportStopped('upload receipt content changed')
            self._verify_file(receipt['file'], expected_sha256, path.stat().st_size, neutral_id)
            return receipt['file']
        response, _ = self.request('POST', BASE + '/upload/v1beta/files', label='upload-start',
            headers={'X-Goog-Upload-Protocol': 'resumable', 'X-Goog-Upload-Command': 'start',
                     'X-Goog-Upload-Header-Content-Length': str(path.stat().st_size),
                     'X-Goog-Upload-Header-Content-Type': 'audio/flac'},
            json={'file': {'displayName': neutral_id}})
        if not response.is_success or not response.headers.get('x-goog-upload-url'):
            raise TransportStopped('upload start failed; inspect preserved response')
        upload_url = response.headers['x-goog-upload-url']
        # URI is used in memory only; never print/store bearer upload URLs.
        with path.open('rb') as audio:
            response, _ = self.request('POST', upload_url, label='upload-finalize',
                headers={'Content-Length': str(path.stat().st_size), 'Content-Type': 'audio/flac',
                         'X-Goog-Upload-Offset': '0', 'X-Goog-Upload-Command': 'upload, finalize'},
                content=audio)
        if not response.is_success:
            raise TransportStopped('audio upload failed; inspect preserved response')
        value = response.json()['file']
        for _ in range(30):
            if value.get('state') != 'PROCESSING':
                break
            name = value['name']
            if not re.fullmatch(r'files/[a-z0-9-]+', name):
                raise TransportStopped('invalid uploaded file resource')
            self.sleep(2)
            response, _ = self.request('GET', BASE + '/v1beta/' + name, label='file-processing-check')
            if not response.is_success:
                raise TransportStopped('file processing lookup failed')
            value = response.json()
        self._verify_file(value, expected_sha256, path.stat().st_size, neutral_id)
        freeze_json(receipt_path, {'prepared_sha256': expected_sha256, 'file': value})
        return value

    @staticmethod
    def _verify_file(value: dict, expected_sha256: str, size: int, neutral_id: str):
        if (value.get('state') != 'ACTIVE' or value.get('mimeType') != 'audio/flac'
                or value.get('displayName') != neutral_id or int(value.get('sizeBytes', -1)) != size
                or value.get('sha256Hash') != base64.b64encode(bytes.fromhex(expected_sha256)).decode()):
            raise TransportStopped('provider did not verify the full prepared audio bytes')
        if not re.fullmatch(re.escape(BASE) + r'/v1beta/files/[a-z0-9-]+', value.get('uri', '')):
            raise TransportStopped('invalid provider audio URI')
        if not value.get('expirationTime') or datetime.fromisoformat(value['expirationTime'].replace('Z', '+00:00')) <= datetime.now(timezone.utc):
            raise TransportStopped('uploaded audio expired; explicit re-upload required')

    def count_tokens(self, model: str, body: dict):
        response, stem = self.request('POST', f'{BASE}/v1beta/models/{model}:countTokens', label='countTokens',
            json={'generateContentRequest': {'model': f'models/{model}', **body}})
        if not response.is_success:
            raise TransportStopped('exact request token counting failed')
        return response.json(), stem

    def generate(self, model: str, body: dict):
        return self.request('POST', f'{BASE}/v1beta/models/{model}:generateContent',
                            label='generateContent', json=body)
