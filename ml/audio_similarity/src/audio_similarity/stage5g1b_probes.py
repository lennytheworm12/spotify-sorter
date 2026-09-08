"""Fixed semantic probes; no labels, fitted transformations, or similarity training."""
from pathlib import Path
import os
import time
import numpy as np
from .stage5e3_artifacts import digest, freeze, freeze_json, npz_bytes, read


def normalize_rows(values):
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 512 or not np.isfinite(values).all():
        raise ValueError('expected finite N by 512 embeddings')
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if np.any(norms < 1e-12):
        raise ValueError('zero embedding')
    return values / norms


def prompt_list(config):
    return [template.format(pair[variant]) for axis in sorted(config['axes'])
            for variant, template in enumerate(config['prompt_templates'])
            for pair in config['axes'][axis]]


def cached_text(path, identity, prompts, forward=None):
    """Content-addressed complete batch; replay cannot instantiate a model."""
    key = digest({'identity': identity, 'prompts': prompts})
    target = Path(path) / key
    if (target / 'manifest.json').exists():
        manifest = read(target / 'manifest.json')
        if manifest['identity'] != identity or manifest['prompts'] != prompts:
            raise ValueError('text cache identity mismatch')
        from .stage5b1a_models import file_sha256
        if file_sha256(target / 'vectors.npz') != manifest['sha256']:
            raise ValueError('text cache checksum mismatch')
        with np.load(target / 'vectors.npz', allow_pickle=False) as archive:
            vectors = archive['vectors']
        if vectors.shape != (len(prompts), 512):
            raise ValueError('text cache shape mismatch')
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6)
        if not np.isfinite(vectors).all():
            raise ValueError('nonfinite cache')
        return vectors, 0, key
    if forward is None:
        raise ValueError('cache replay would require text inference')
    vectors = normalize_rows(forward(prompts))
    if vectors.shape[0] != len(prompts):
        raise ValueError('incomplete text batch')
    freeze(target / 'vectors.npz', npz_bytes({'vectors': vectors}))
    from .stage5b1a_models import file_sha256
    freeze_json(target / 'manifest.json', {'identity': identity, 'prompts': prompts,
                'sha256': file_sha256(target / 'vectors.npz')})
    return vectors, len(prompts), key


def materialize_text(root, run, replay=False):
    config = read(run / 'protocol.json')
    identity = read(run / 'text_identity.json')
    from .stage5g1_segments import encoder_identity
    from .stage5e3_artifacts import hashes
    tokenizer = Path.home() / '.cache/huggingface/hub/models--roberta-base'
    if encoder_identity(root) != identity['encoder'] or hashes([p for p in tokenizer.rglob('*') if p.is_file()], tokenizer) != identity['tokenizer_assets']:
        raise ValueError('text encoder environment or tokenizer changed')
    def forward(prompts):
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        import torch
        from .stage5e1_encoders import NativeFusionClapEncoder
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(config['seed'])
        encoder = NativeFusionClapEncoder(root / identity['encoder']['checkpoint'], device='cpu')
        rows = []
        with torch.no_grad():
            for start in range(0, len(prompts), 8):
                rows.extend(encoder.module.get_text_embedding(prompts[start:start + 8]))
        return np.stack(rows)
    started = time.perf_counter()
    vectors, calls, key = cached_text(root / 'artifacts/stage5g1b_identity_probes/text', identity,
                                      prompt_list(config), None if replay else forward)
    freeze(run / 'text_vectors.npz', npz_bytes({'vectors': vectors}))
    ledger = {'new_text_embeddings': calls, 'audio_inference': 0, 'cache_key': key,
              'cache_hits': len(vectors) - calls, 'seconds': time.perf_counter() - started}
    number = len(list(run.glob('text_execution_*.json')))
    freeze_json(run / f'text_execution_{number:03d}.json', ledger)
    return ledger


def profiles(audio, text, config):
    """Mean cosine over existing views: preserves mixtures without max selection."""
    mean_audio = normalize_rows(audio).mean(axis=0)
    offset = 0
    result = {}
    for axis in sorted(config['axes']):
        count = len(config['axes'][axis])
        logits = np.stack([text[offset + v * count:offset + (v + 1) * count] @ mean_audio
                           for v in range(2)])
        offset += 2 * count
        scaled = logits / config['temperature']
        weights = np.exp(scaled - scaled.max(axis=1, keepdims=True))
        weights /= weights.sum(axis=1, keepdims=True)
        top = logits.argmax(axis=1)
        ordered = np.sort(logits, axis=1)
        margins = ordered[:, -1] - ordered[:, -2]
        reliable = bool(top[0] == top[1] and np.all(margins >= config['minimum_cosine_margin']))
        result[axis] = {'cosines': logits.tolist(), 'weights': weights.tolist(),
                        'top': top.tolist(), 'margins': margins.tolist(),
                        'reliable': reliable, 'status': 'OK' if reliable else 'ABSTAIN_AMBIGUOUS_PROBE'}
    return result


def js_distance(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape or np.any(a <= 0) or np.any(b <= 0):
        raise ValueError('expected positive probability profiles')
    middle = (a + b) / 2
    return float((np.sum(a * np.log(a / middle)) + np.sum(b * np.log(b / middle))) / (2 * np.log(2)))


def compare(a, b):
    reliable = a['reliable'] and b['reliable']
    wa, wb = np.asarray(a['weights']), np.asarray(b['weights'])
    return {'distance': js_distance(wa.mean(axis=0), wb.mean(axis=0)),
            'variant_distances': [js_distance(wa[v], wb[v]) for v in range(2)],
            'flag': bool(a['top'][0] != b['top'][0]) if reliable else None,
            'status': 'OK' if reliable else 'ABSTAIN_AMBIGUOUS_PROBE'}
