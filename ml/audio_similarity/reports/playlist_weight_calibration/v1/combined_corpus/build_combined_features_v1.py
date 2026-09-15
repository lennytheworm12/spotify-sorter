#!/usr/bin/env python3
# Build combined pairwise artifacts for the union corpus (original 1,924 + extension 1,135).
# Reuses the audited builders. No API calls, no new audio inference.
import json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, 'src')
from audio_similarity.calibration.contracts import file_hash, digest, freeze_json, require
from audio_similarity.calibration.gemini_full_inputs import read
from audio_similarity.calibration.gemini_full_features import mapper_inputs, genre_matrices, freeze_array
from audio_similarity.calibration.gemini_full_masked import expand
from audio_similarity.calibration.method_c_full_readiness import cosine_matrix
from audio_similarity.calibration.method_c_full_cache import load_feature
from audio_similarity.calibration.audit_capture import read_db
from audio_similarity.calibration.development_audio import cached_vector, vector_ok

root = Path.cwd()
AUD = root / '.research_audio'
O = AUD / 'playlist_calibration_method_c_gpu_v1'
O_FEAT = AUD / 'playlist_calibration_method_c_gpu_v1/features'
E = AUD / 'playlist_calibration_extension_preparation_v1'
OUT = AUD / 'playlist_calibration_combined_v1/feature_snapshot_v1'
GEN = 'genre_shards'

o_corpus = read(O / 'corpus.json'); o_conf = read(O / 'configuration.json'); o_comp = read(O / 'companion_features.json')
e_corpus = read(E / 'corpus.json'); e_conf = read(E / 'configuration.json'); e_comp = read(E / 'companion_features.json')

o_ids = [t['recording_id'] for t in o_corpus['recordings']]
e_ids = [t['recording_id'] for t in e_corpus['recordings']]
require(o_ids == sorted(set(o_ids)), 'original ids unordered')
require(e_ids == sorted(set(e_ids)), 'extension ids unordered')
require(not (set(o_ids) & set(e_ids)), 'inter-corpus id overlap')
ids = sorted(set(o_ids) | set(e_ids))
require(len(ids) == 3059, f'union size {len(ids)} != 3059')
print(f'union: {len(ids)} recordings ({len(o_ids)} original + {len(e_ids)} extension)')

# ---- audio vectors: method_c from feature files, center30/muq from the vector DB
audio = {'C_method_c': [], 'C_center30': [], 'M': []}
source_rows = []
for corpus, feat_dir, conf, comp in ((o_corpus, O_FEAT, o_conf, o_comp), (e_corpus, E, e_conf, e_comp)):
    require([r['recording_id'] for r in comp['recordings']] == [t['recording_id'] for t in corpus['recordings']],
            'companion order differs')
    for t, proof_row in zip(corpus['recordings'], comp['recordings']):
        rid = t['recording_id']
        feature = feat_dir / 'features' / (rid + '.json') if (feat_dir / 'features').is_dir() else feat_dir / (rid + '.json')
        require(feature.exists(), f'missing method_c feature {rid}')
        audio['C_method_c'].append(load_feature(feature, t, conf)['vector'])
        for key, encoder in (('C_center30', 'laion_clap'), ('M', 'muq_mulan_large')):
            proof = proof_row[key]
            require(proof is not None, f'missing companion {key} for {rid}')
            rel = str(proof['path'])
            if rel.endswith('.sqlite'):
                db = read_db(root / rel)
                try:
                    vec, origin = cached_vector(db, 'pooled',
                        "stable_track_id=? AND source_audio_sha256=? AND encoder_id=? AND status='SUCCESS'",
                        (rid, t['audio_sha256'], encoder))
                finally:
                    db.close()
                require(vec is not None, f'no cached {key} for {rid}')
            else:
                doc = read(root / rel)
                require(doc['source_sha256'] == t['audio_sha256'], f'json audio proof source differs {rid}')
                require(vector_ok(doc[key]), f'json pooled vector invalid {rid} {key}')
                vec = np.asarray(doc[key], dtype='<f4')
            require(digest(np.asarray(vec).tolist()) == proof['vector_sha256'], f'companion proof differs {rid} {key}')
            audio[key].append(vec)
        source_rows.append({'recording_id': rid, 'source_sha256': t['audio_sha256'],
                            'method_c_feature_sha256': file_hash(feature)})
require(len(audio['C_method_c']) == 3059, 'vector coverage')
print('vectors collected: 3059 x 3')

# ---- order vectors to the sorted union
order = {rid: i for i, rid in enumerate(ids)}
all_ids_unsorted = o_ids + e_ids
vecs = {k: np.array([v for _, v in sorted(zip(all_ids_unsorted, vals), key=lambda kv: order[kv[0]])])
        for k, vals in audio.items()}
matrices = {k: cosine_matrix(v.tolist()) for k, v in vecs.items()}
print('audio matrices built:', {k: m.shape for k, m in matrices.items()})

# ---- cross-check against the two existing verified bundles (within-corpus blocks)
o_idx = [order[i] for i in o_ids]; e_idx = [order[i] for i in e_ids]
mb = AUD / 'playlist_calibration_gemini_full_v1/masked_bundle_v1'
bundle_ids = read(mb / 'recording_ids.json')
require(bundle_ids == o_ids, 'masked bundle id order differs')
checks = {}
for name, key in (('Jc', 'Jc'), ('Jnr', 'Jnr'), ('R', 'R')):
    pass
# block comparison happens after genre matrices are built (below)
print('original block order verified against masked bundle')

# ---- mapped profiles: reuse both existing mapped sets (mapper unchanged) + the repair
o_cache = read(AUD / 'playlist_calibration_gemini_full_v1/validated_mapping_cache.json')
o_mapped = o_cache['mapped']
e_mapped = read(AUD / 'playlist_calibration_extension_recovery_03/feature_snapshot_v2/mapped_profiles.private.json')
repair = read(AUD / 'playlist_calibration_gemini_full_v1/repair_01_radio_edit/mapped_profile.json')
repair_id = repair['recording_id']
mapped, provenance = {}, {}
for rid in ids:
    if rid in o_mapped:
        mapped[rid] = o_mapped[rid]; provenance[rid] = 'original_audit'
    elif rid == repair_id:
        mapped[rid] = repair['mapped']; provenance[rid] = 'repair_01_radio_edit_substituted_audio'
    elif rid in e_mapped:
        mapped[rid] = e_mapped[rid]; provenance[rid] = 'extension_snapshot_v2'
    else:
        mapped[rid] = None; provenance[rid] = 'missing'
valid_ids = sorted(r for r, v in mapped.items() if v is not None)
repaired = [r for r, p in provenance.items() if p == 'repair_01_radio_edit_substituted_audio']
print(f'mapped profiles: {len(valid_ids)} of {len(ids)} (missing {len(ids) - len(valid_ids)}; repaired {len(repaired)})')
require(len(valid_ids) == 3058, f'expected 3058 valid profiles, got {len(valid_ids)}')

# ---- genre matrices over the union
engine, force, concepts, canonical_profile, mapper_hashes = mapper_inputs(root)
inputs = {'mapper_hashes': mapper_hashes, 'recording_ids_sha256': digest(ids)}
valid = genre_matrices(OUT / GEN, valid_ids, {k: mapped[k] for k in valid_ids}, concepts, inputs,
                       shard_size=32, recompute=True)
available, mask, genre = expand(ids, valid_ids, valid)
matrices.update(genre)
print('genre matrices built:', {k: m.shape for k, m in genre.items()})
print('mask: valid pairs', int(mask.sum()), 'of', mask.size)

# ---- cross-check the rebuilt within-corpus blocks against the frozen bundles
problems = []
for key in ('Jc', 'Jnr', 'R'):
    mine = np.asarray(matrices[key])
    theirs = np.load(mb / (key + '.npy'), allow_pickle=False)
    sub = mine[np.ix_(o_idx, o_idx)]
    same = np.allclose(sub, theirs, rtol=0, atol=0, equal_nan=True)
    checks['original_block_' + key] = 'MATCH' if same else 'DIFFERS'
    if not same:
        problems.append(f'original block {key} differs (max abs delta {np.nanmax(np.abs(sub - theirs)):.3e})')
    e_snap = AUD / 'playlist_calibration_extension_recovery_03/feature_snapshot_v2'
    theirs_e = np.load(e_snap / (key + '.npy'), allow_pickle=False)
    e_ordered = sorted(e_ids)
    e_idx2 = [order[i] for i in e_ordered]
    sub_e = mine[np.ix_(e_idx2, e_idx2)]
    same_e = np.allclose(sub_e, theirs_e, rtol=0, atol=0, equal_nan=True)
    checks['extension_block_' + key] = 'MATCH' if same_e else 'DIFFERS'
    if not same_e:
        problems.append(f'extension block {key} differs (max abs delta {np.nanmax(np.abs(sub_e - theirs_e)):.3e})')
print('block checks:', json.dumps(checks, indent=1))
# diagnostic: where do the original blocks differ, and does it involve the repaired profile?
rep_idx = [order[r] for r in repaired]
diag = {}
for key in ('Jc', 'Jnr', 'R'):
    mine = np.asarray(matrices[key]); theirs = np.load(mb / (key + '.npy'), allow_pickle=False)
    sub = mine[np.ix_(o_idx, o_idx)]
    diff = ~np.isclose(sub, theirs, rtol=0, atol=0, equal_nan=True)
    n_diff = int(diff.sum())
    if n_diff and rep_idx:
        rows = set(np.where(diff[:, rep_idx[0]])[0]) | set(np.where(diff[rep_idx[0], :])[0])
        confined = n_diff == len(rows) * 2 - 1
        diag[key] = {'differing_cells': n_diff, 'confined_to_repaired_index': bool(confined),
                     'repaired_index': rep_idx[0]}
    else:
        diag[key] = {'differing_cells': n_diff, 'confined_to_repaired_index': None}
print('block diagnostics:', json.dumps(diag, indent=1))

# ---- invariants on the union matrices
Jc = np.asarray(matrices['Jc']); Jnr = np.asarray(matrices['Jnr']); R = np.asarray(matrices['R'])
require(np.array_equal(Jc, Jc.T, equal_nan=True), 'Jc not symmetric')
require(np.array_equal(Jnr, Jnr.T, equal_nan=True), 'Jnr not symmetric')
require(np.array_equal(R, R.T, equal_nan=True), 'R not symmetric')
require(np.array_equal(mask, mask.T), 'mask not symmetric')
finite = np.isfinite(Jc[~np.isnan(Jc)])
require(finite.size == 0 or (finite.min() >= -1e-9 and finite.max() <= 1 + 1e-9), 'Jc out of bounds')
expect = (1 - Jc) * Jnr
require(np.allclose(np.nan_to_num(R, nan=0.0), np.nan_to_num(expect, nan=0.0), atol=0, rtol=0, equal_nan=True),
        'R != (1-Jc)*Jnr')
print('invariants: symmetric, bounded, R=(1-Jc)*Jnr exact')

# ---- freeze outputs
files = {k: freeze_array(OUT / (k + '.npy'), np.asarray(v)) for k, v in matrices.items()}
files['genre_pair_valid'] = freeze_array(OUT / 'genre_pair_valid.npy', mask)
freeze_json(OUT / 'recording_ids.json', ids)
freeze_json(OUT / 'source_checks.json', source_rows)
manifest = {
    'schema': 'combined-feature-snapshot-v1',
    'recordings': len(ids), 'original_recordings': len(o_ids), 'extension_recordings': len(e_ids),
    'valid_profiles': len(valid_ids), 'missing_profiles': len(ids) - len(valid_ids),
    'profile_provenance': {k: sum(1 for p in provenance.values() if p == k)
                           for k in sorted(set(provenance.values()))},
    'repaired_profiles': {'count': len(repaired), 'recording_ids': repaired,
                          'note': 'profile obtained from a substituted radio-edit audio (see gemini_repair_01/REPORT.md); not equivalent to the original recording measurement'},
    'files': files, 'recording_order_sha256': digest(ids),
    'original_corpus_sha256': digest(o_corpus), 'extension_corpus_sha256': digest(e_corpus),
    'mapper_input_hashes': mapper_hashes,
    'within_corpus_block_checks': checks,
    'within_corpus_blocks_exact': all(v == 'MATCH' for v in checks.values()),
    'matrix_validation': 'explicit sorted-union order; symmetric; bounded; exact R=(1-Jc)*Jnr; NaN + false mask for missing profiles',
    'missing_semantics': 'NaN plus false validity mask; never zero or valid unknown',
    'new_api_calls': 0, 'new_audio_inference_calls': 0,
    'implementation_sha256': file_hash(Path(__file__)),
}
freeze_json(OUT / 'manifest.json', manifest)
print(json.dumps({'recordings': manifest['recordings'], 'valid_profiles': manifest['valid_profiles'],
                  'missing_profiles': manifest['missing_profiles'],
                  'within_corpus_blocks_exact': manifest['within_corpus_blocks_exact']}, indent=1))
if problems:
    print('PROBLEMS:'); [print('  -', p) for p in problems]
