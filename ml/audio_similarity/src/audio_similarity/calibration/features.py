"""Hash-verified pair features. Matrix bytes and representation identities are inseparable."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
from pathlib import Path
from types import MappingProxyType

import numpy as np

from .contracts import Clap, Corpus, digest, file_hash, freeze_json, require, sha, strict_fields, text_id

FEATURE_IDS = {
    'C_center30': Clap.CENTERED.value,
    'C_method_c': Clap.METHOD_C.value,
    'M': 'muq_centered30_v1',
    'Jc': 'canonical_weighted_jaccard_v1',
    'Jnr': 'unmatched_neighborhood_jaccard_v1',
    'R': 'canonical_residual_v1',
    'M3': 'M3_C_PLUS_FIXED_MUQ',
}
REQUIRED = frozenset(FEATURE_IDS) - {'M3'}


def matrix_hash(value):
    return hashlib.sha256(np.asarray(value, dtype='<f8', order='C').tobytes()).hexdigest()


@dataclass(frozen=True)
class FeatureIdentity:
    feature: str
    representation_id: str
    checkpoint_sha256: str
    preprocessing_sha256: str
    implementation_sha256: str
    environment_sha256: str
    source_order_sha256: str
    track_order_sha256: str
    matrix_sha256: str
    mapper_sha256: str
    prompt_sha256: str
    schema_sha256: str
    ontology_sha256: str
    source_manifest_sha256: str

    def __post_init__(self):
        require(self.feature in FEATURE_IDS, 'unknown pair feature')
        require(self.representation_id == FEATURE_IDS[self.feature], 'representation ID mismatch')
        for name, value in asdict(self).items():
            if name.endswith('_sha256'):
                sha(value)
        text_id(self.representation_id)


class PairFeatures:
    """Common ordered population for every comparison; missing genre is an explicit no-op.

    Float64 pair matrices may be supplied from a cache or verified NPY files. This
    layer never estimates a feature, performs audio inference, or fits a scaler.
    """

    def __setattr__(self, name, value):
        require(not getattr(self, "_sealed", False), "feature bundle is immutable")
        object.__setattr__(self, name, value)

    def __init__(self, corpus: Corpus, track_ids, matrices, identities, genre_available):
        self.corpus = corpus
        self.records = MappingProxyType(corpus.by_id)
        self.track_ids = tuple(track_ids)
        require(self.track_ids == tuple(r.recording_id for r in corpus.recordings), 'corpus/feature ordering mismatch')
        require(set(matrices) == set(identities) and REQUIRED <= set(matrices)
                and set(matrices) <= set(FEATURE_IDS), 'feature bundle incomplete or unknown')
        self._positions = {key: i for i, key in enumerate(self.track_ids)}
        n = len(self.track_ids)
        mask = np.asarray(genre_available)
        require(mask.shape == (n,) and mask.dtype == bool, 'explicit genre-availability mask required')
        self.genre_available = tuple(bool(x) for x in mask)
        sources = tuple(r.source_sha256 for r in corpus.recordings)
        verified = {}
        for key in sorted(matrices):
            identity = identities[key]
            require(isinstance(identity, FeatureIdentity) and identity.feature == key, 'feature identity mismatch')
            require(identity.track_order_sha256 == digest(self.track_ids), 'track-order hash mismatch')
            require(identity.source_order_sha256 == digest(sources), 'source-order hash mismatch')
            a = np.asarray(matrices[key], dtype='<f8')
            require(a.shape == (n, n) and np.isfinite(a).all(), 'invalid or missing common-population matrix')
            require(np.allclose(a, a.T, rtol=0, atol=1e-12), 'asymmetric pair matrix')
            lower, upper = (0, 1) if key in {'Jc', 'Jnr', 'R'} else (-1, 1)
            require((a >= lower - 1e-12).all() and (a <= upper + 1e-12).all(), 'pair feature outside bounds')
            require(matrix_hash(a) == identity.matrix_sha256, 'pair matrix hash mismatch')
            # Back arrays by immutable bytes; caller mutations cannot change a frozen bundle.
            verified[key] = np.frombuffer(a.tobytes(), dtype='<f8').reshape(n, n)
        require(np.allclose(verified['R'], (1 - verified['Jc']) * verified['Jnr'], rtol=0, atol=1e-12), 'R formula mismatch')
        for key in ('Jc', 'Jnr', 'R'):
            require(np.all(verified[key][~mask, :] == 0) and np.all(verified[key][:, ~mask] == 0),
                    'missing genre must remain a zero no-op')
        genre_ids = [identities[key] for key in ('Jc', 'Jnr', 'R')]
        for field in ('mapper_sha256', 'prompt_sha256', 'schema_sha256', 'ontology_sha256', 'source_manifest_sha256'):
            require(len({getattr(i, field) for i in genre_ids}) == 1, 'genre provenance disagreement')
        require(identities['C_center30'].checkpoint_sha256 == identities['C_method_c'].checkpoint_sha256,
                'CLAP checkpoint disagreement')
        self.matrices = MappingProxyType(verified)
        self.identities = MappingProxyType(dict(identities))
        self.identity = digest({'corpus': corpus.identity, 'track_ids': self.track_ids,
                                'features': {k: asdict(v) for k, v in sorted(identities.items())},
                                'genre_available': self.genre_available})
        self._sealed = True

    def at(self, feature, a, b):
        return float(self.matrices[feature][self._positions[a], self._positions[b]])

    def save(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        files = {}
        for name, matrix in self.matrices.items():
            stream = io.BytesIO()
            np.save(stream, matrix, allow_pickle=False)
            raw = stream.getvalue()
            path = directory / f'{name}.npy'
            if path.exists():
                require(path.read_bytes() == raw, 'immutable matrix replay differs')
            else:
                with path.open('xb') as target:
                    target.write(raw)
            files[name] = {'filename': path.name, 'sha256': hashlib.sha256(raw).hexdigest()}
        freeze_json(directory / 'bundle.json', {'schema': 'playlist-pair-features-v1',
                    'corpus': asdict(self.corpus), 'track_ids': self.track_ids, 'files': files,
                    'identities': {k: asdict(v) for k, v in self.identities.items()},
                    'genre_available': self.genre_available, 'bundle_id': self.identity})

    @classmethod
    def load(cls, directory: Path):
        value = json.loads((directory / 'bundle.json').read_text())
        require(set(value) == {'schema', 'corpus', 'track_ids', 'files', 'identities', 'genre_available', 'bundle_id'}, 'bundle schema mismatch')
        require(value['schema'] == 'playlist-pair-features-v1', 'unsupported feature schema')
        matrices = {}
        for key, item in value['files'].items():
            require(item['filename'] == f'{key}.npy' and key in FEATURE_IDS, 'invalid feature file')
            path = directory / item['filename']
            require(file_hash(path) == item['sha256'], 'feature file hash mismatch')
            matrices[key] = np.load(path, allow_pickle=False)
        require(isinstance(value['genre_available'], list) and all(type(x) is bool for x in value['genre_available']), 'genre mask must contain booleans')
        result = cls(Corpus.from_dict(value['corpus']), value['track_ids'], matrices,
                     {k: strict_fields(FeatureIdentity, v) for k, v in value['identities'].items()},
                     np.asarray(value['genre_available'], dtype=bool))
        require(result.identity == value['bundle_id'], 'bundle identity mismatch')
        return result
