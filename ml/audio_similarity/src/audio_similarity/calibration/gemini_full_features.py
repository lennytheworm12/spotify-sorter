"""Full ordered genre matrices using the unchanged mechanically verified scorer."""
from pathlib import Path
import io

import numpy as np

from .contracts import Corpus, Recording, digest, file_hash, freeze_json, require
from .features import FEATURE_IDS, FeatureIdentity, PairFeatures, matrix_hash
from .gemini_full_inputs import DEV, METHOD_C, RUN, read
from .development_bundle import genre_pair
from .development_audio import cached_vector, vector_ok
from .audit_capture import read_db
from .method_c_full_readiness import cosine_matrix


def freeze_array(path, array):
    stream = io.BytesIO()
    np.save(stream, np.asarray(array, dtype='<f8'), allow_pickle=False)
    raw = stream.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == raw, 'deterministic matrix replay differs: ' + str(path))
    else:
        with path.open('xb') as out:
            out.write(raw)
    return file_hash(path)


def prepare_audio_features(root):
    """Read existing vectors only; retain the exact Method C matrix bytes."""
    run, prior = root / RUN, root / METHOD_C
    preflight = read(run / 'preflight.json')
    corpus = read(prior / 'corpus.json')
    require(digest(corpus) == preflight['corpus_sha256'], 'corpus changed')
    ids = [r['recording_id'] for r in corpus['recordings']]
    published = read(prior / 'artifact_manifest.json')['files']
    require(file_hash(prior / 'artifact_manifest.json') ==
            preflight['historical_manifest_hashes'][str(METHOD_C / 'artifact_manifest.json')], 'prior manifest changed')
    for name in ('companion_features.json', 'configuration.json', 'matrices/method_c.npy', 'matrices/recording_ids.json'):
        require(file_hash(prior / name) == published[name], 'audio feature provenance changed')
    require(read(prior / 'matrices/recording_ids.json') == ids, 'Method C ordering mismatch')
    companions = read(prior / 'companion_features.json')
    require(companions['source_corpus_sha256'] == digest(corpus), 'companion source population differs')
    require([r['recording_id'] for r in companions['recordings']] == ids, 'companion ordering differs')
    config = read(root / DEV / 'audio_config.json')
    vectors = {'C_center30': [], 'M': []}
    source_checks = []
    for t, row in zip(corpus['recordings'], companions['recordings']):
        require(t['audio_sha256'] == row['audio_sha256'], 'companion source mismatch')
        for key, encoder in [('C_center30', 'laion_clap'), ('M', 'muq_mulan_large')]:
            proof = row[key]
            require(proof is not None, 'missing companion feature')
            path = root / proof['path']
            if proof['origin'] == 'DEVELOPMENT_SOURCE_LINKED_CACHE':
                cached = read(path)
                require(cached['stable_track_id'] == t['recording_id']
                        and cached['source_sha256'] == t['audio_sha256']
                        and cached['configuration_sha256'] == digest(config), 'development companion linkage differs')
                value = np.asarray(cached[key], dtype=np.float64)
            else:
                db = read_db(path)
                try:
                    value, origin = cached_vector(db, 'pooled',
                        "stable_track_id=? AND source_audio_sha256=? AND encoder_id=? AND status='SUCCESS'",
                        (t['recording_id'], t['audio_sha256'], encoder))
                finally:
                    db.close()
                require(origin == proof['origin'], 'cached companion provenance changed')
            require(value is not None and vector_ok(value) and digest(value.tolist()) == proof['vector_sha256'],
                    'cached companion vector changed')
            vectors[key].append(value)
        source_checks.append({'recording_id': t['recording_id'], 'source_sha256': t['audio_sha256'],
                              'C_center30': row['C_center30'], 'M': row['M']})
    matrices = {key: cosine_matrix(value) for key, value in vectors.items()}
    matrices['C_method_c'] = np.load(prior / 'matrices/method_c.npy', allow_pickle=False)
    files = {key: freeze_array(run / 'audio_features' / (key + '.npy'), value) for key, value in matrices.items()}
    require(files['C_method_c'] == published['matrices/method_c.npy'], 'Method C matrix bytes changed')
    freeze_json(run / 'audio_features/recording_ids.json', ids)
    freeze_json(run / 'audio_features/source_checks.json', source_checks)
    result = {'schema': 'gemini-full-cached-audio-v1', 'tracks': len(ids), 'recording_ids_sha256': digest(ids),
        'source_order_sha256': digest([r['audio_sha256'] for r in corpus['recordings']]),
        'corpus_sha256': digest(corpus), 'files': files, 'audio_inference_calls': 0,
        'source_checks_sha256': digest(source_checks), 'companion_manifest_sha256': file_hash(prior / 'companion_features.json'),
        'development_audio_configuration_sha256': digest(config),
        'method_c_configuration_sha256': file_hash(prior / 'configuration.json')}
    freeze_json(run / 'audio_features/manifest.json', result)
    return result


def mapper_inputs(root):
    from ..genre_registry_review import mapper
    from ..genre_force_export import canonical_profile
    receipt = read(root / DEV / 'genre_input_receipt.json')
    for name, expected in receipt.items():
        require(file_hash(root / name) == expected, 'frozen mapper input changed')
    engine = mapper(root)
    require(len(engine.concepts) == 138 and len(engine.config['neighborhoods']) == 29, 'wrong mapper revision')
    force = read(root / 'configs/genre_force_v1/genre-force-explorer-v1.json')
    concepts = {c['id']: {'kind': c['kind'], 'neighborhoods': {
        n: engine.config['membership_proposal'][rel + '_relation_strength'] for n, rel in c['neighborhoods'].items()}}
        for c in engine.config['concepts'] if not c['mapping_review_required']
        and c['kind'] in force['representations']['canonical']['eligible']}
    return engine, force, concepts, canonical_profile, receipt


def genre_matrices(directory, ids, mapped, concepts, identity, *, shard_size=64, recompute=False):
    """Upper triangle, bounded row shards, one trace per track instead of per pair."""
    require(shard_size > 0 and ids == sorted(set(ids)), 'invalid shard size or recording order')
    require(set(ids) == set(mapped), 'mapping coverage differs')
    n = len(ids)
    jc, jnr = np.zeros((n, n)), np.zeros((n, n))
    for start in range(0, n, shard_size):
        end = min(start + shard_size, n)
        prefix = directory / f'{start:05d}'
        receipt_path = prefix.with_suffix('.json')
        key = digest({'inputs': identity, 'start': start, 'end': end, 'n': n})
        names = {k: prefix.with_name(prefix.name + '-' + k + '.npy') for k in ('Jc', 'Jnr')}
        if receipt_path.exists():
            receipt = read(receipt_path)
            require(receipt['identity'] == key, 'incompatible genre shard')
            for k, path in names.items():
                require(file_hash(path) == receipt['files'][k], 'genre shard hash mismatch')
        if not receipt_path.exists() or recompute:
            x, y = np.zeros((end - start, n)), np.zeros((end - start, n))
            for i in range(start, end):
                for j in range(i, n):
                    x[i - start, j], y[i - start, j] = genre_pair(mapped[ids[i]], mapped[ids[j]], concepts)
            hashes = {k: freeze_array(names[k], a) for k, a in [('Jc', x), ('Jnr', y)]}
            freeze_json(receipt_path, {'identity': key, 'files': hashes})
        jc[start:end] = np.load(names['Jc'], allow_pickle=False)
        jnr[start:end] = np.load(names['Jnr'], allow_pickle=False)
    lower = np.tril_indices(n, -1)
    jc[lower], jnr[lower] = jc.T[lower], jnr.T[lower]
    result = {'Jc': jc, 'Jnr': jnr, 'R': (1 - jc) * jnr}
    for value in result.values():
        require(np.isfinite(value).all() and np.array_equal(value, value.T)
                and (value >= 0).all() and (value <= 1).all(), 'invalid genre matrix')
    return result


def feature_corpus(corpus):
    """A feature catalog, NOT evaluation splits or approved source playlists.

    Exact-source groups are cache deduplication identities only. Broader version
    purges and curator/source cohorts must still be frozen by the next stage.
    All original playlist records are preserved in the linked corpus manifest.
    """
    artists = {}
    for request in corpus['requests']:
        if request['recording_id']:
            artists.setdefault(request['recording_id'], set()).update(request['artists'])
    records = tuple(Recording(t['recording_id'], 'exact-source/' + t['audio_sha256'],
                    tuple(sorted(artists[t['recording_id']])), t['audio_sha256']) for t in corpus['recordings'])
    return Corpus(records, (), (), 'REAL')


def build(root, *, recompute=False):
    from .gemini_full_recovery import freeze_profiles
    root = root.resolve()
    run = root / RUN
    frozen = freeze_profiles(root)  # Complete real responses required; no transport.
    preflight = read(run / 'preflight.json')
    corpus = read(root / preflight['corpus_path'])
    ids = [t['recording_id'] for t in corpus['recordings']]
    require(set(frozen['profiles']) == set(ids), 'cannot publish a subset bundle')
    audio = prepare_audio_features(root)
    engine, force, concepts, canonical_profile, mapper_hashes = mapper_inputs(root)
    mapped = {sid: canonical_profile(frozen['profiles'][sid], engine, force) for sid in ids}
    freeze_json(run / 'mapped_profiles.json', mapped)
    implementation = {str(p.relative_to(root)): file_hash(p) for p in [Path(__file__).resolve(),
        root / 'src/audio_similarity/calibration/development_bundle.py',
        root / 'src/audio_similarity/genre_force_export.py', root / 'src/audio_similarity/genre_registry_review.py']}
    inputs = {'profile_snapshot_sha256': digest(frozen), 'mapper_hashes': mapper_hashes,
        'implementation_hashes': implementation, 'mapped_sha256': digest(mapped),
        'concepts_sha256': digest(concepts), 'audio_manifest_sha256': digest(audio),
        'corpus_sha256': digest(corpus), 'recording_ids_sha256': digest(ids), 'numpy': np.__version__}
    freeze_json(run / 'bundle_inputs.json', inputs)
    matrices = genre_matrices(run / 'genre_shards', ids, mapped, concepts, digest(inputs), recompute=recompute)
    for name, expected in audio['files'].items():
        path = run / 'audio_features' / (name + '.npy')
        require(file_hash(path) == expected, 'audio matrix changed')
        matrices[name] = np.load(path, allow_pickle=False)
    config = read(root / DEV / 'audio_config.json')
    c_config = read(root / METHOD_C / 'configuration.json')
    gm = read(root / DEV / 'gemini/execution_manifest.json')
    identities = {}
    no_ontology = digest({'ontology': None, 'free_genre_prompt': True})
    for key in sorted(matrices):
        checkpoint = (config['models']['clap']['sha256'] if key.startswith('C_') else
            config['models']['muq']['pytorch_model.bin']['sha256'] if key == 'M' else digest({'model': gm['model_id']}))
        identities[key] = FeatureIdentity(key, FEATURE_IDS[key], checkpoint,
            digest(c_config if key == 'C_method_c' else config if key in ('C_center30', 'M') else mapper_hashes),
            digest(implementation), digest({'gemini': gm['environment'], 'numpy': np.__version__}),
            audio['source_order_sha256'], digest(ids), matrix_hash(matrices[key]),
            mapper_hashes['configs/genre_registry_v1/genre-neighborhood-map-v1.json'],
            gm['prompt_sha256'], gm['base_schema_sha256'], no_ontology, digest(inputs))
    mask = np.asarray([bool(mapped[sid]['specificStyleIds']) for sid in ids])
    bundle = PairFeatures(feature_corpus(corpus), ids, matrices, identities, mask)
    bundle.save(run / 'features')
    result = {'status': 'FEATURE_BUNDLE_READY', 'tracks': len(ids), 'bundle_id': bundle.identity,
        'usable_specific_style': int(mask.sum()), 'valid_but_noninformative': int((~mask).sum()),
        'profile_coverage': len(frozen['profiles']), 'profile_missing': 0, 'pair_feature_names': sorted(matrices),
        'audio_inference_calls': 0, 'gemini_replay_new_api_calls': 0,
        'ranking_calibration_status': 'NOT_AUTHORIZED_EVALUATION_PROTOCOL_NOT_FROZEN',
        'source_use_status': corpus['source_use_status'],
        'feature_catalog_scope': 'All retained recordings. No evaluation playlists/splits inferred; use linked original source corpus.',
        'broader_recording_version_purges': 'NOT_FROZEN', 'feature_bundle_sha256': file_hash(run / 'features/bundle.json')}
    freeze_json(run / 'bundle_report.json', result)
    return result
