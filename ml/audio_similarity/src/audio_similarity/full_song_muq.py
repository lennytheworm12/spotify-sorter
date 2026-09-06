"""Revision-2 full-recording MuQ policy; no historical encoder behavior changes."""
from __future__ import annotations
import hashlib
from pathlib import Path
import numpy as np
from .stage5b1a_models import file_sha256

SAMPLE_RATE = 24000
CHUNK_SAMPLES = 240000
NORM_FLOOR = 1e-12
STATUSES = ('OK', 'SOURCE_MISSING', 'SOURCE_CHANGED', 'DECODE_FAILED', 'EMPTY_AUDIO',
            'NONFINITE_AUDIO', 'INFERENCE_FAILED', 'INVALID_EMBEDDING', 'ZERO_NORM')
POLICY = dict(sample_rate_hz=SAMPLE_RATE, chunk_samples=CHUNK_SAMPLES,
              stride_samples=CHUNK_SAMPLES, chunk_seconds=10, stride_seconds=10,
              final_partial_policy='cyclic_final_chunk_own_samples',
              segment_normalization='float64_L2', track_pooling='all_chunks_equal_float64_mean',
              pooled_normalization='float64_L2', storage_dtype='float32',
              norm_floor=NORM_FLOOR, dimension=512, version='full_song_muq_v1')


class InvalidVector(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def normalize(vector):
    vector = np.asarray(vector, dtype=np.float64)
    if vector.shape != (512,) or not np.isfinite(vector).all():
        raise InvalidVector('INVALID_EMBEDDING', 'expected finite vector of shape (512,)')
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm):
        raise InvalidVector('INVALID_EMBEDDING', 'nonfinite L2 norm')
    if norm <= NORM_FLOOR:
        raise InvalidVector('ZERO_NORM', 'L2 norm at or below 1e-12')
    return vector / norm, norm


def chunk_plan(length):
    return [(start, min(start + CHUNK_SAMPLES, length))
            for start in range(0, length, CHUNK_SAMPLES)]


def padded_chunk(waveform, start, end):
    chunk = waveform[start:end]
    if not len(chunk):
        raise ValueError('cannot pad empty chunk')
    return np.ascontiguousarray(chunk[np.arange(CHUNK_SAMPLES) % len(chunk)], dtype=np.float32)


def decode_full(path):
    # Same downmix-before-resample convention as Stage 5E.1, via shared decoder.
    import torchaudio
    from .audio import load_audio
    waveform, sr = load_audio(path)
    waveform = waveform.float().mean(dim=0, keepdim=True)
    if sr != SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sr, SAMPLE_RATE)
    return waveform.squeeze(0).contiguous().cpu().numpy().astype(np.float32)


def raw_forward(adapter, chunk):
    """Reuse the installed MuQMulanEncoder model, validate before adapter L2."""
    import torch
    tensor = torch.from_numpy(chunk).unsqueeze(0).to(adapter.device)
    with torch.inference_mode():
        output = adapter.model(wavs=tensor)
    if isinstance(output, dict):
        output = output['output']
    if tuple(output.shape) != (1, 512):
        raise InvalidVector('INVALID_EMBEDDING', f'invalid model batch shape {tuple(output.shape)}')
    return output[0].detach().float().cpu().numpy()


def extract_waveform(waveform, forward, *, saved=None, persist=None):
    """Return explicit failure plus completed chunks; never pool a partial track."""
    waveform = np.asarray(waveform)
    result = {'status': 'OK', 'failing_chunk_index': None, 'message': None,
              'sample_count': int(waveform.size), 'chunks': [], 'vector': None,
              'forward_passes': 0, 'chunk_cache_hits': 0}
    if not waveform.size:
        result['status'] = 'EMPTY_AUDIO'
        return result
    if waveform.ndim != 1 or not np.isfinite(waveform).all():
        result['status'] = 'NONFINITE_AUDIO'
        return result
    vectors = []
    for index, (start, end) in enumerate(chunk_plan(len(waveform))):
        metadata = dict(chunk_index=index, start_sample=start, end_sample=end,
                        start_seconds=start/SAMPLE_RATE,
                        nominal_end_seconds=(start+CHUNK_SAMPLES)/SAMPLE_RATE,
                        observed_audio_seconds=(end-start)/SAMPLE_RATE,
                        padding_seconds=(CHUNK_SAMPLES-end+start)/SAMPLE_RATE,
                        padding_policy=POLICY['final_partial_policy'], status='OK', warnings=[])
        try:
            cached = saved(index) if saved else None
            if cached is not None:
                vector, cached_meta = cached
                checked, _ = normalize(vector)
                if not np.allclose(vector, checked, atol=1e-6, rtol=0):
                    raise InvalidVector('INVALID_EMBEDDING', 'cached chunk is not normalized')
                metadata.update(cached_meta)
                result['chunk_cache_hits'] += 1
            else:
                result['forward_passes'] += 1
                vector, norm = normalize(forward(padded_chunk(waveform, start, end)))
                metadata['embedding_norm_before_normalization'] = norm
                metadata['embedding_sha256'] = hashlib.sha256(vector.astype('<f4').tobytes()).hexdigest()
                if persist:
                    persist(index, vector, metadata)
            vectors.append(np.asarray(vector, dtype=np.float64))
            result['chunks'].append(metadata)
        except Exception as exc:
            result.update(status=exc.status if isinstance(exc, InvalidVector) else 'INFERENCE_FAILED',
                          failing_chunk_index=index, message=str(exc))
            return result
    try:
        vector, _ = normalize(np.mean(vectors, axis=0, dtype=np.float64))
        result['vector'] = vector.astype('<f4')
    except InvalidVector as exc:
        result.update(status=exc.status, message=str(exc))
    return result


def extract_source(track, forward, **kwargs):
    path = Path(track['retained_source_path'])
    base = dict(status='SOURCE_MISSING', vector=None, chunks=[], forward_passes=0,
                chunk_cache_hits=0, failing_chunk_index=None, message=None, sample_count=0)
    if not path.is_file():
        return base
    if file_sha256(path) != track['source_sha256']:
        return base | {'status': 'SOURCE_CHANGED'}
    try:
        waveform = decode_full(path)
    except Exception as exc:
        from .audio import DurationInvalidError
        status = 'EMPTY_AUDIO' if isinstance(exc, DurationInvalidError) else (
            'NONFINITE_AUDIO' if 'non-finite' in str(exc) else 'DECODE_FAILED')
        return base | {'status': status, 'message': str(exc)}
    return extract_waveform(waveform, forward, **kwargs)


def cosine_matrix(vectors):
    normalized = np.stack([normalize(v)[0] for v in vectors])
    matrix = normalized @ normalized.T
    if np.max(np.abs(matrix)) > 1 + 1e-6:
        raise ValueError('invalid cosine overshoot')
    matrix = np.clip(matrix, -1, 1)
    if not np.allclose(matrix, matrix.T, atol=1e-6, rtol=0) or not np.allclose(np.diag(matrix), 1, atol=1e-6, rtol=0):
        raise ValueError('cosine invariant failed')
    return matrix
