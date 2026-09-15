#!/usr/bin/env python3
"""Resolve the inputs the combined 3,059-recording build needs. Read-only.

Checks the three gates from reports/playlist_weight_calibration/v1/combined_corpus/DESIGN.md
and inventories the per-recording inputs for both corpora.
"""
import json, sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root / 'src'))
from audio_similarity.calibration.contracts import file_hash, digest

EXT_RUN = root / '.research_audio/playlist_calibration_extension_preparation_v1'
EXT_SNAP = root / '.research_audio/playlist_calibration_extension_recovery_03/feature_snapshot_v2'
ORIG = root / '.research_audio/playlist_calibration_gemini_full_v1'
ORIG_BUNDLE = ORIG / 'masked_bundle_v1'

report = {}

# --- inventories
orig_ids = json.loads((root / 'reports/playlist_weight_calibration/v1/method_c_full/recording_ids.json').read_text())
ext_ids = json.loads((EXT_SNAP / 'recording_ids.json').read_text())
report['inventory'] = {'original': len(orig_ids), 'extension': len(ext_ids), 'combined': len(set(orig_ids) | set(ext_ids))}

# --- gate 2: inter-corpus overlap on recording id
id_overlap = sorted(set(orig_ids) & set(ext_ids))
report['gate_2_id_overlap'] = {'count': len(id_overlap), 'sample': id_overlap[:5]}

# audio sha overlap
def audio_hashes(path, key_candidates):
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    recs = data if isinstance(data, list) else data.get('recordings', [])
    hashes = {}
    for r in recs:
        if not isinstance(r, dict):
            continue
        for k in key_candidates:
            if r.get(k):
                hashes[r.get('recording_id')] = r[k]
                break
    return hashes

ext_checks = EXT_SNAP / 'source_checks.json'
ext_h = audio_hashes(ext_checks, ['source_sha256', 'audio_sha256']) or {}
orig_track = root / 'reports/playlist_weight_calibration/v1/method_c_full/track_status.json'
orig_h = {}
ts = json.loads(orig_track.read_text())
recs = ts if isinstance(ts, list) else ts.get('tracks', ts.get('recordings', []))
for r in (recs if isinstance(recs, list) else []):
    if isinstance(r, dict) and r.get('audio_sha256'):
        orig_h[r.get('recording_id')] = r['audio_sha256']
sha_overlap = sorted(set(orig_h.values()) & set(ext_h.values()))
report['gate_2_audio_sha_overlap'] = {'original_hashes': len(orig_h), 'extension_hashes': len(ext_h),
                                      'overlap_count': len(sha_overlap), 'sample': [h[:12] for h in sha_overlap[:5]]}

# --- gate 1: role catalogs
ext_cat = {r: (EXT_RUN / f'role_catalogs_v3/{r}_candidates/catalog.private.json').exists()
           for r in ('development', 'confirmation')}
report['gate_1_extension_catalogs'] = ext_cat
orig_cat_hits = [str(p.relative_to(root)) for p in root.rglob('*catalog*.json')
                 if 'original' in str(p).lower() or 'lockbox' in str(p).lower()][:8]
report['gate_1_original_catalog_candidates'] = orig_cat_hits
report['gate_1_status'] = 'OPEN' if not orig_cat_hits else 'REVIEW'

# --- per-recording input availability
ext_feat = EXT_RUN / 'features'
report['inputs'] = {
    'extension_method_c_features_dir': {'path': str(ext_feat.relative_to(root)), 'exists': ext_feat.exists(),
                                        'count': len(list(ext_feat.glob('*.json'))) if ext_feat.exists() else 0},
    'extension_profiles': {'path': str((EXT_SNAP / 'profile_snapshot.private.json').relative_to(root)),
                           'exists': (EXT_SNAP / 'profile_snapshot.private.json').exists()},
    'original_profiles': {'path': str((ORIG / 'profiles_frozen.json').relative_to(root)),
                          'exists': (ORIG / 'profiles_frozen.json').exists()},
    'original_bundle_matrices': {n: (ORIG_BUNDLE / n).exists() for n in ('Jc.npy', 'Jnr.npy', 'R.npy', 'genre_pair_valid.npy')},
}
# original per-recording Method C vectors?
cand = []
for pat in ('features', '*features*', '*vectors*'):
    cand += [str(p.relative_to(root)) for p in root.glob(f'.research_audio/playlist_calibration_*/{pat}')][:3]
report['inputs']['original_per_recording_vectors'] = sorted(set(cand))[:6]

report['gate_3_deferred_profiles'] = {'original_expected': 2,
                                      'original_manifest_missing': json.loads((ORIG_BUNDLE / 'manifest.json').read_text()).get('missing_profiles'),
                                      'extension_missing': json.loads((EXT_SNAP / 'manifest.json').read_text()).get('missing_profiles')}

out = root / 'reports/playlist_weight_calibration/v1/combined_corpus/input_readiness_v1.json'
out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps(report, indent=1)[:2600])
print('\nwritten:', out.relative_to(root))
