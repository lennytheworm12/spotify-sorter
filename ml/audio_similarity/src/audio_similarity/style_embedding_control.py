"""Single frozen Discogs latent-embedding control; no fitting or score tuning."""
from pathlib import Path
from itertools import combinations
import numpy as np
from .stage5e3_artifacts import read, freeze, freeze_json, hashes, verify_hashes, npz_bytes
from .stage5g1_evidence import preferences
from .stage5g1b_data import E3
from .style_prior_analysis import agreement, interval, discrimination

PRIOR = Path('reports/style_prior_pilot/v2')
RUN = Path('reports/style_embedding_control/v1')
CONFIRMED = ['0mjbciwK9zhfQl44jXfQv6', '1ON9XudZFxwu43tQXBszIX', '6B9HXnRzmokTTxZNdV5T48']


def pooled(patches):
    x = np.asarray(patches, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 1280 or len(x) == 0 or not np.isfinite(x).all():
        raise ValueError('expected finite nonempty patches x 1280')
    mean = x.mean(axis=0)
    norm = np.linalg.norm(mean)
    if norm <= 1e-12:
        raise ValueError('degenerate pooled embedding')
    return mean, mean / norm


def prepare(root):
    prior, run = root / PRIOR, root / RUN
    verify_hashes(root, read(prior / 'input_hashes.json'))
    verify_hashes(prior, read(prior / 'artifact_manifest.json'))
    audit = root / 'reports/style_source_audit/v1'
    verify_hashes(audit, read(audit / 'artifact_manifest.json'))
    confirmation = {'user_statement': 'they are good', 'scope': 'Owner confirms all three questioned retained recordings are intended. No replacement audio or ratings.', 'tracks': CONFIRMED, 'artist_identity_limitation': 'Recording confirmation is not independent verification of credited artist aliases; exclude these three from an additional evaluation sensitivity.'}
    freeze_json(root / 'reports/style_source_audit/owner_resolution_v1.json', confirmation)
    config = {'version': 'discogs-latent-control-v1', 'model': 'same frozen discogs-effnet-bs64-1.pb',
              'output': 'PartitionedCall:1', 'dimension': 1280,
              'preprocessing': read(prior / 'protocol.json')['preprocessing'],
              'pooling': 'float64 arithmetic mean of raw 1280-D patch embeddings, then one L2 normalization; no patch normalization, scaler or fitted transform',
              'similarity': 'cosine; clip numerical roundoff to [-1,1]',
              'primary': 'existing playlist rubric; same three frozen artist/source-grouped heldout partitions; strict ordinal preference anchor macro',
              'comparators': ['exact D cosine', 'C cosine sensitivity', '1 - frozen 400-label Jensen-Shannon divergence'],
              'secondary': ['gap >= 2 preferences', 'bad <= 2 versus good >= 4 discrimination', 'separate holistic rubric', 'exclude three owner-confirmed alias/title cases from evaluation only'],
              'uncertainty': '5000 paired anchor bootstrap replicates, PCG64 seed 5101, descriptive 95% intervals; shared candidates and three folds limit independence',
              'material_delta': .03, 'tie_tolerance': 1e-6,
              'decision': 'Label-output bottleneck supported only if latent-minus-label primary delta >= .03 and descriptive lower bound > 0. A complementary-representation candidate additionally requires the same improvement over D. Otherwise no demonstrated latent advantage. C comparison always reported, never selected away.',
              'no_training': True, 'no_fusion': True, 'no_new_labels': True, 'all_evidence_previously_exposed': True,
              'reference_patch_count': 'must equal cached classifier patch count for each track',
              'cache': 'source hash, model/metadata hashes, full extraction configuration, worker hash, serialization hash, runtime/native binary/FFmpeg identity; fail rather than infer on replay'}
    freeze_json(run / 'protocol.json', config)
    for name in ('tracks.json', 'evidence.json', 'folds.json'):
        freeze(run / name, (prior / name).read_bytes())
    paths = list((root / 'src/audio_similarity').glob('style_embedding_*.py')) + [root / 'tests/test_style_embedding_control.py', root / 'reports/style_source_audit/owner_resolution_v1.json']
    paths += list(prior.iterdir()) + list(audit.iterdir()) + list(run.glob('*.json'))
    protected = read(prior / 'input_hashes.json') | hashes([p for p in paths if p.name != 'input_hashes.json'], root)
    freeze_json(run / 'input_hashes.json', protected)


def evaluate(root):
    run, prior = root / RUN, root / PRIOR
    verify_hashes(root, read(run / 'input_hashes.json'))
    tracks = read(run / 'tracks.json'); ids = [t['spotify_track_id'] for t in tracks]
    with np.load(run / 'embeddings.npz', allow_pickle=False) as z:
        if set(z.files) != set(ids):
            raise ValueError('all 100 tracks required')
        vectors = np.stack([z[tid] for tid in ids])
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-12)
    matrices = {'latent': np.clip(vectors @ vectors.T, -1, 1)}
    with np.load(prior / 'style_distributions.npz', allow_pickle=False) as z:
        old = list(z['ids']); ix = [old.index(t) for t in ids]
        matrices['labels'] = 1 - z['distances'][np.ix_(ix, ix)]
    with np.load(root / E3 / 'historical_reference_matrices.npz', allow_pickle=False) as z:
        old = list(z['spotify_ids']); ix = [old.index(t) for t in ids]
        matrices.update({name: z[field][np.ix_(ix, ix)] for name, field in [('D', 'd_clap'), ('C', 'c_clap')]})
    scores = {name: {(a, b): float(mat[i, j]) for i, a in enumerate(ids) for j, b in enumerate(ids) if a < b} for name, mat in matrices.items()}
    results = {}
    for rubric, pairs in read(run / 'evidence.json').items():
        fold_results = []
        for fold in read(run / 'folds.json'):
            constraints = preferences(pairs, fold['heldout'])[0]
            variants = {'ordinal': constraints, 'strong': [p for p in constraints if p['gap'] >= 2],
                        'exclude_alias_cases': [p for p in constraints if not set(CONFIRMED) & {p['anchor'], p['preferred'], p['other']}]}
            fold_results.append({'fold': fold['fold'], 'metrics': {variant: {name: agreement(score, ps) for name, score in scores.items()} for variant, ps in variants.items()}})
        combined = {}
        for variant in ('ordinal', 'strong', 'exclude_alias_cases'):
            per = {name: {a: value for fold in fold_results for a, value in fold['metrics'][variant][name]['per_anchor'].items()} for name in scores}
            combined[variant] = {'performance': {name: interval(list(values.values())) for name, values in per.items()},
                                 'paired_latent_delta': {name: interval([per['latent'][a] - per[name][a] for a in per['latent']]) for name in ('labels', 'D', 'C')},
                                 'anchors': len(per['latent'])}
        results[rubric] = {'folds': fold_results, 'grouped': combined,
                          'all_pair_discrimination': {name: discrimination(pairs, {k: 1-v for k, v in score.items()}, scores['D']) for name, score in scores.items()}}
    primary = results['playlist']['grouped']['ordinal']['paired_latent_delta']
    def passes(name):
        x = primary[name]
        return x['point'] is not None and x['point'] >= .03 and x['low'] > 0
    results['diagnosis'] = ('COMPLEMENTARY_CANDIDATE_DEVELOPMENT_ONLY' if passes('labels') and passes('D') else 'LABEL_OUTPUT_BOTTLENECK_DEVELOPMENT_ONLY' if passes('labels') else 'LATENT_ADVANTAGE_NOT_ESTABLISHED')
    freeze(run / 'similarity_matrices.npz', npz_bytes({'ids': np.array(ids), **matrices}))
    freeze_json(run / 'results.json', results)
    print(results['diagnosis'], primary)


if __name__ == '__main__':
    import sys
    {'prepare': prepare, 'evaluate': evaluate}[sys.argv[1]](Path.cwd())
