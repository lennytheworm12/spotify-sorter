"""Invented deterministic evidence for engineering tests, never musical conclusions."""
from dataclasses import asdict
from pathlib import Path
import numpy as np

from .contracts import Corpus, Layer, Playlist, Recording, SourceGroup, digest, file_hash, freeze_json
from .features import FEATURE_IDS, FeatureIdentity, PairFeatures, matrix_hash
from .output import RankerFreeze, descriptive_row
from .ranking import Clap, Model, grid
from .search import nested_synthetic
from .splits import nested_plan, reserve_lockbox


def fixture(*, groups=9, members=5, seed=81):
    records, playlists, curators = [], [], []
    for group in range(groups):
        ids = tuple(f'r{group:02d}_{i:02d}' for i in range(members))
        records.extend(Recording(key, f'version/{key}', (f'artist/{key}',), digest(['source', key]), 'SYNTHETIC') for key in ids)
        curators.append(SourceGroup(f'group{group}', f'curator{group}', 'synthetic-v1'))
        playlists.append(Playlist(f'p{group}', f'snapshot{group}', f'group{group}', f'dup{group}',
                         f'stratum{group % 3}', Layer.ORIGINAL, 'synthetic', ids,
                         f'Invented playlist {group}', 'No real songs or labels', 'Invented local group',
                         'synthetic', 'synthetic', 'synthetic-frozen-time',
                         'SYNTHETIC', 'SYNTHETIC', 'NOT_APPLICABLE', 'SYNTHETIC'))
    corpus = Corpus(tuple(records), tuple(playlists), tuple(curators), 'SYNTHETIC')
    rng = np.random.default_rng(seed)
    n = len(records)
    def cosine(vectors):
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        return np.clip(vectors @ vectors.T, -1, 1)
    c30 = cosine(rng.normal(size=(n, 8)))
    class_vectors = np.repeat(np.eye(groups), members, axis=0)
    cm = cosine(class_vectors + rng.normal(scale=.1, size=(n, groups)))
    muq = cosine(class_vectors + rng.normal(scale=.5, size=(n, groups)))
    jc = class_vectors @ class_vectors.T
    jnr = np.where(jc == 0, .25, 0.)
    matrices = {'C_center30': c30, 'C_method_c': cm, 'M': muq, 'Jc': jc, 'Jnr': jnr,
                'R': (1 - jc) * jnr, 'M3': .7172981519 * cm + .2827018481 * muq}
    ids = tuple(r.recording_id for r in records)
    identities = {}
    for key, representation in FEATURE_IDS.items():
        identities[key] = FeatureIdentity(key, representation, digest('synthetic-checkpoint'),
            digest(['preprocessing', representation]), digest('synthetic-implementation-v1'),
            digest('synthetic-environment-v1'), digest(tuple(r.source_sha256 for r in records)),
            digest(ids), matrix_hash(matrices[key]), digest('frozen-synthetic-mapper'),
            digest('frozen-synthetic-prompt'), digest('frozen-synthetic-schema'),
            digest('frozen-synthetic-ontology'), digest('synthetic-source-manifest'))
    return PairFeatures(corpus, ids, matrices, identities, np.ones(n, dtype=bool))


def run_demo(output, *, bootstrap_draws=32):
    features = fixture()
    implementation = {path.name: file_hash(path) for path in sorted(Path(__file__).parent.glob('*.py'))}
    config = {'implementation_sha256': implementation, 'schema': 'synthetic-calibration-execution-v1', 'evidence': 'SYNTHETIC',
              'nominal_grid': 880, 'eta_deduplicated_grid': len(grid(deduplicate_clap=False)),
              'fully_deduplicated_grid': len(grid()), 'bootstrap_draws': bootstrap_draws,
              'bootstrap_seed': 1701, 'mask_repetitions': 1, 'outer_folds': 3, 'inner_folds': 2,
              'reference_protocol': 'equal-seed-min20-m20-eight-hash-subsets-v1',
              'real_weight_selection_enabled': False}
    freeze_json(output / 'execution_contract.json', config)
    features.save(output / 'features')
    lockbox = reserve_lockbox(features.corpus, [p.playlist_id for p in features.corpus.playlists], 1, 'synthetic-lockbox')
    freeze_json(output / 'lockbox_metadata.json', asdict(lockbox))
    plan = nested_plan(features.corpus, lockbox.partition.fit_playlists,
                       allowed=lockbox.partition.fit_recordings)
    freeze_json(output / 'nested_plan.json', [asdict(p) for p in plan])
    result = nested_synthetic(features, plan, output=output / 'search', bootstrap_draws=bootstrap_draws)
    preset = RankerFreeze(Model(Clap.CENTERED, .5, .05, .25), features.identity,
                          features.identities['Jc'].mapper_sha256, features.identities['Jc'].prompt_sha256,
                          digest('synthetic-source-policy'), 'synthetic-candidate-policy')
    row = descriptive_row(features, preset, features.track_ids[-1], features.track_ids[:-1], snapshot_id='synthetic-descriptive')
    freeze_json(output / 'descriptive.json', row)
    report = {'status': 'SYNTHETIC_SCAFFOLD_VERIFIED', 'grid': config,
              'outer_folds_executed': len(result['folds']), 'lockbox_opened': False,
              'real_weights_selected': False, 'suitability_probability': None, 'policy_status': 'NOT_CALIBRATED'}
    freeze_json(output / 'report.json', report)
    return report
