"""Prepare full retained recordings without identity metadata or excerpt sampling."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from audio_similarity.stage5e3_artifacts import freeze, freeze_json, read, verify_hashes
from audio_similarity.stage5b1a_models import file_sha256


def probe(path: Path) -> dict:
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def pcm_digest(path: Path) -> tuple[str, int]:
    """Compare the entire decoded 16-bit PCM, preserving sample rate and channels."""
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            ['ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-map', '0:a:0',
             '-c:a', 'pcm_s16le', '-f', 's16le', '-'], stdout=subprocess.PIPE, stderr=errors,
        )
        digest, size = hashlib.sha256(), 0
        assert process.stdout is not None
        while chunk := process.stdout.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        if process.wait() != 0:
            raise ValueError('full audio decode failed')
    if size == 0:
        raise ValueError('empty audio')
    return digest.hexdigest(), size


def prepare_audio(source: Path, expected_sha256: str, destination: Path) -> dict:
    """Create once; reruns verify bytes and perform no conversion."""
    source, destination = source.resolve(), destination.resolve()
    if file_sha256(source) != expected_sha256:
        raise ValueError('source hash mismatch')
    if source == destination or destination.suffix != '.flac':
        raise ValueError('prepared audio must be a separate FLAC file')
    receipt_path = destination.with_suffix('.json')
    if receipt_path.exists():
        receipt = read(receipt_path)
        if receipt['source_sha256'] != expected_sha256 or receipt['source_path'] != str(source):
            raise ValueError('prepared receipt source mismatch')
        verify_hashes(destination.parent, {destination.name: receipt['prepared_sha256']})
        return receipt
    if destination.exists():
        raise ValueError('unreceipted prepared file; inspect before resuming')
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = probe(source)
    streams = [s for s in before['streams'] if s['codec_type'] == 'audio']
    if len(streams) != 1:
        raise ValueError('expected exactly one audio stream')
    stream = streams[0]
    command = ['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-n', '-i', str(source),
               '-map', '0:a:0', '-vn', '-sn', '-dn', '-map_metadata', '-1',
               '-map_chapters', '-1', '-fflags', '+bitexact', '-flags:a', '+bitexact',
               '-c:a', 'flac', '-sample_fmt', 's16', '-compression_level', '8', str(destination)]
    # Publish only after conversion and verification complete.
    with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
        temporary = Path(scratch) / destination.name
        subprocess.run(command[:-1] + [str(temporary)], check=True, capture_output=True)
        after = probe(temporary)
        if len(after['streams']) != 1 or after['streams'][0]['codec_type'] != 'audio':
            raise ValueError('prepared file contains non-audio streams')
        prepared_stream = after['streams'][0]
        if any(s.get('tags') for s in after['streams']) or after['format'].get('tags'):
            raise ValueError('prepared file contains metadata tags')
        if any(prepared_stream[k] != stream[k] for k in ['sample_rate', 'channels']):
            raise ValueError('unexpected sample-rate or channel conversion')
        source_pcm, source_bytes = pcm_digest(source)
        prepared_pcm, prepared_bytes = pcm_digest(temporary)
        if (source_pcm, source_bytes) != (prepared_pcm, prepared_bytes):
            raise ValueError('prepared audio does not preserve the complete 16-bit waveform')
        frame_bytes = 2 * stream['channels']
        if source_bytes % frame_bytes:
            raise ValueError('partial PCM frame')
        frames = source_bytes // frame_bytes
        receipt = {
            'schema_version': 'gemini-style-prepared-audio-v1',
            'source_path': str(source), 'source_sha256': expected_sha256,
            'prepared_sha256': file_sha256(temporary), 'prepared_bytes': temporary.stat().st_size,
            'prepared_filename': destination.name, 'mime_type': 'audio/flac',
            'duration_seconds': frames / int(stream['sample_rate']), 'decoded_frames': frames,
            'sample_rate_hz': int(stream['sample_rate']), 'channels': stream['channels'],
            'pcm_s16le_sha256': prepared_pcm, 'pcm_s16le_bytes': prepared_bytes,
            'full_recording_preserved': True, 'identity_metadata_removed': True,
            'conversion_command': command,
            'ffmpeg_version': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
            'normalization': 'none; native sample rate/channels; quantized once to signed 16-bit PCM',
        }
        freeze(destination, temporary.read_bytes())
    freeze_json(receipt_path, receipt)
    return receipt
