"""Freeze a common-population research bundle from completed, verified caches."""
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from .contracts import Corpus, Layer, Playlist, Recording, SourceGroup, digest, file_hash, freeze_json, require
from .development_inputs import RUN, load
from .features import FEATURE_IDS, FeatureIdentity, PairFeatures, matrix_hash


def corpus_from_plan(plan):
    tracks = sorted((t for t in plan['tracks'] if t['in_sample']), key=lambda t: t['request_id'])
    ids = {t['request_id'] for t in tracks}
    records = tuple(Recording(t['request_id'], t['purge_group'], tuple(t['artists']), t['source_sha256']) for t in tracks)
    groups, playlists = {}, []
    for p in sorted(plan['playlists'], key=lambda p: p['playlist_id']):
        members = tuple(sorted(ids.intersection(p['sample_request_ids'])))
        require(len(members) >= 20, 'development sample below frozen minimum')
        gid = 'curator/' + digest(p['curator'])
        groups[gid] = SourceGroup(gid, p['curator'], p['provenance_resolution'])
        playlists.append(Playlist(p['playlist_id'], p['source_note_sha256'], gid,
            plan['source_clusters'][p['playlist_id']], p['stratum'], Layer.ORIGINAL,
            'owner_authorized_development', members, p['title'], p['source_description'] or '',
            p['declared_intent'], p['source_url'], p['source_path'], 'audit-20260913',
            'PENDING', 'PENDING', 'PENDING', 'PENDING'))
    return Corpus(records, tuple(playlists), tuple(groups[k] for k in sorted(groups)), 'REAL')


def jaccard(a, b):
    keys = sorted(set(a) | set(b))
    total = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return sum(min(a.get(k, 0), b.get(k, 0)) for k in keys) / total if total else 0.


def project(values, concepts):
    out = {}
    for k in sorted(values):
        c = concepts[k]
        if c['kind'] not in ('style', 'style_umbrella'):
            continue
        for n, strength in c['neighborhoods'].items():
            if values[k] * strength > 0:
                out[n] = max(out.get(n, 0), values[k] * strength)
    return out


def genre_pair(a, b, concepts):
    # Same specific-style availability gate as the frozen frontend scorer.
    if not a['specificStyleIds'] or not b['specificStyleIds']:
        return 0., 0.
    x, y = a['canonical'], b['canonical']
    keys = sorted(set(x) | set(y))
    rx = {k: x.get(k, 0) - min(x.get(k, 0), y.get(k, 0)) for k in keys if x.get(k, 0) > y.get(k, 0)}
    ry = {k: y.get(k, 0) - min(x.get(k, 0), y.get(k, 0)) for k in keys if y.get(k, 0) > x.get(k, 0)}
    return jaccard(x, y), jaccard(project(rx, concepts), project(ry, concepts))


def build(root):
    from ..genre_force_export import canonical_profile
    from ..genre_registry_review import mapper
    from .development_audio import vector_ok
    from .development_profiles import DevelopmentRunner

    plan, run = load(root), root / RUN
    corpus = corpus_from_plan(plan)
    # Replay verifies every raw response, schema and source-profile linkage without API calls.
    DevelopmentRunner(root).freeze_profiles()
    profiles = json.loads((run / 'gemini/profiles_frozen.json').read_text())['profiles']
    require(set(profiles) == set(corpus.by_id), 'common-population profiles incomplete')
    config = json.loads((run / 'audio_config.json').read_text())
    require(config['plan_sha256'] == digest(plan), 'audio plan mismatch')
    audio, hashes = {}, {}
    for t in plan['tracks']:
        path = run / 'audio' / (t['request_id'] + '.json')
        row = json.loads(path.read_text())
        require(row['configuration_sha256'] == digest(config) and row['source_sha256'] == t['source_sha256'], 'audio cache linkage mismatch')
        require(file_hash(root / t['source_path']) == t['source_sha256'], 'retained source changed')
        require(all(vector_ok(row[k]) for k in ('C_center30', 'C_method_c', 'M')), 'invalid pooled vector')
        audio[t['request_id']] = row
        hashes[str(path.relative_to(root))] = file_hash(path)
    engine = mapper(root)
    force_path = root / 'configs/genre_force_v1/genre-force-explorer-v1.json'
    force = json.loads(force_path.read_text())
    concepts = {c['id']: {'kind': c['kind'], 'neighborhoods': {
        n: engine.config['membership_proposal'][rel + '_relation_strength'] for n, rel in c['neighborhoods'].items()}}
        for c in engine.config['concepts'] if not c['mapping_review_required'] and c['kind'] in force['representations']['canonical']['eligible']}
    ids = tuple(r.recording_id for r in corpus.recordings)
    mapped = {k: canonical_profile(profiles[k], engine, force) for k in ids}
    matrices = {}
    for key in ('C_center30', 'C_method_c', 'M'):
        vectors = np.asarray([audio[k][key] for k in ids], dtype=np.float64)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        matrices[key] = np.clip(vectors @ vectors.T, -1, 1)
    jc, jnr = np.zeros((len(ids), len(ids))), np.zeros((len(ids), len(ids)))
    for i, a in enumerate(ids):
        for j in range(i, len(ids)):
            x, y = genre_pair(mapped[a], mapped[ids[j]], concepts)
            jc[i, j] = jc[j, i] = x
            jnr[i, j] = jnr[j, i] = y
    matrices.update(Jc=jc, Jnr=jnr, R=(1-jc)*jnr)
    # Extend the pinned M3 recipe to NEW recordings, then supply its frozen matrix.
    # This is not a claim that new corpus scores were in the historical frozen100.
    matrices['M3'] = .7172981519 * matrices['C_method_c'] + .2827018481 * matrices['M']
    provenance_paths = [run / 'plan.private.json', run / 'audio_config.json', run / 'gemini/execution_manifest.json',
        run / 'gemini/profiles_frozen.json', force_path, root / 'configs/genre_registry_v1/genre-neighborhood-map-v1.json',
        root / 'configs/genre_registry_v1/mapper_reference.py', Path(__file__).resolve(),
        root / 'src/audio_similarity/genre_force_export.py', root / 'src/audio_similarity/stage5e3_materialize.py']
    hashes.update({str(p.relative_to(root)): file_hash(p) for p in provenance_paths})
    freeze_json(run / 'bundle_inputs.json', hashes)
    gm = json.loads((run / 'gemini/execution_manifest.json').read_text())
    na = digest({'not_applicable': 'no genre ontology provided to Gemini'})
    identities = {}
    for key, rep in FEATURE_IDS.items():
        checkpoint = (config['models']['clap']['sha256'] if key.startswith('C_') else
                      config['models']['muq']['pytorch_model.bin']['sha256'] if key == 'M' else digest(config['models']))
        identities[key] = FeatureIdentity(key, rep, checkpoint, digest([config, rep]), file_hash(Path(__file__)),
            digest({'audio': config, 'gemini': gm['environment']}), digest(tuple(r.source_sha256 for r in corpus.recordings)),
            digest(ids), matrix_hash(matrices[key]), file_hash(provenance_paths[5]), gm['prompt_sha256'],
            gm['base_schema_sha256'], na, digest(hashes))
    features = PairFeatures(corpus, ids, matrices, identities, np.asarray([bool(mapped[k]['specificStyleIds']) for k in ids]))
    features.save(run / 'features')
    freeze_json(run / 'mapped_profiles.json', mapped)
    result = {'status': 'DEVELOPMENT_FEATURES_READY', 'tracks': len(ids), 'playlists': len(corpus.playlists),
        'bundle_id': features.identity, 'genre_available': sum(features.genre_available),
        'source_permission_status': 'PENDING', 'formal_confirmation': False,
        'm3_provenance': 'Pinned .7172981519 C + .2827018481 centered30 MuQ recipe, newly frozen on this corpus; historical matrix unchanged.'}
    freeze_json(run / 'bundle_report.json', result)
    return result
