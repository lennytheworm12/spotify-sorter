import json, hashlib
import numpy as np
from pathlib import Path

R = Path('/home/bphan944/PersonalProjects/spotifyProject/ml/audio_similarity')
AUD = R / '.research_audio'
S = AUD / 'playlist_calibration_combined_v1/feature_snapshot_v1'
CC = R / 'reports/playlist_weight_calibration/v1/combined_corpus'
out = {}

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

# 1) snapshot completeness
need = ['Jc', 'Jnr', 'R', 'M', 'C_center30', 'C_method_c', 'genre_pair_valid']
files = {f'{k}.npy': (S / f'{k}.npy').exists() for k in need}
man = json.loads((S / 'manifest.json').read_text())
ids = json.loads((S / 'recording_ids.json').read_text())
out['snapshot'] = {'all_matrices_present': all(files.values()), 'missing': [k for k, v in files.items() if not v],
                   'n_recordings': len(ids), 'manifest_n': man.get('n', man.get('recordings', None)),
                   'matrices': len(need)}

# 2) invariant re-verification on disk
Jc = np.load(S / 'Jc.npy'); Jnr = np.load(S / 'Jnr.npy'); Rm = np.load(S / 'R.npy')
mask = np.load(S / 'genre_pair_valid.npy').astype(bool)
sym = bool(np.array_equal(Jc, Jc.T, equal_nan=True) and np.array_equal(Jnr, Jnr.T, equal_nan=True))
with np.errstate(invalid='ignore'):
    expect = (1 - Jc) * Jnr
ok = np.nan_to_num(Rm - expect, nan=0.0)
finite = np.isfinite(Jc) | np.isnan(Jc)
out['invariants'] = {
    'symmetric': sym,
    'R_equals_1_minus_Jc_times_Jnr_exact': bool(np.abs(ok).max() == 0.0),
    'bounded': bool(np.nanmin(Jc) >= 0 and np.nanmax(Jc) <= 1 and np.nanmin(Jnr) >= 0 and np.nanmax(Jnr) <= 1),
    'mask_symmetric': bool(np.array_equal(mask, mask.T)),
    'nan_cells': int(np.isnan(Jc).sum()),
    'mask_false_cells': int((~mask).sum()),
}

# 3) lockbox isolation: lockbox recordings must not be in the learn set
sp = json.loads((CC / 'split_manifest_v1.private.json').read_text())
groups = {k: set(v['recordings']) for k, v in sp['roles'].items()} if 'roles' in sp else {}
if groups:
    fit = groups.get('learn_and_train', set())
    lock = groups.get('lockbox_reserved', set())
    heavy = groups.get('held_out_validation', set())
    out['split'] = {'roles': {k: len(v) for k, v in groups.items()},
                    'lockbox_disjoint_from_fit': not (fit & lock),
                    'heldout_disjoint_from_fit': not (fit & heavy),
                    'all_roles_cover_union': len(set().union(*groups.values()))}

# 4) artifact chain
chain = {}
for name in ['execution_contract_v8.json', 'readiness_report_v12.json', 'split_manifest_v1.private.json',
             'split_summary_v1.json']:
    p = CC / name
    chain[name] = sha(p) if p.exists() else None
out['artifacts'] = chain
out['github'] = None

print(json.dumps(out, indent=1))
(S / 'sanitation_check_v1.json').write_text(json.dumps(out, indent=1) + '\n')
