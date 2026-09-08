"""Seal the frozen Stage 5G.1 result; no fitting, inference, or production writes."""
from pathlib import Path
import hashlib
import numpy as np
from .stage5e3_artifacts import read,freeze,freeze_json,hashes,verify_hashes


def closeout(root):
    run=root/'reports/stage5g1_clap_similarity/v1'
    verify_hashes(root,read(run/'input_hashes.json'))
    config=read(run/'protocol.json');inventory=read(run/'supervision_inventory.json')
    audit=read(run/'supplemental_audit.json');validation=read(run/'verification/validation.json')
    if audit['status']!='PASS' or validation['status']!='PASS':raise ValueError('validation incomplete')
    c=read(run/'comparison.json');curves=read(run/'learning_curves.json')
    def gain(name):
        v=c['comparisons'][name]
        return v['delta'] is not None and v['delta']>=config['evaluation']['material_gain'] and v['low']>0
    outcome=('DATA_INSUFFICIENT' if not inventory['gate_passes'] else 'SUPPORTED' if gain('M1_vs_B1') else
             'COVERAGE_ONLY' if gain('B1_vs_B0') else 'REPRESENTATION_LIMITED')
    if outcome!=c['outcome']:raise ValueError('outcome differs from frozen predicate')
    original=read(run/'extraction_ledger_000.json');replay=read(run/'extraction_ledger_001.json')
    assert replay['replay'] and replay['forward_passes']==0 and replay['cache_hits']==1927
    for fraction in [.25,.5,1.0]:
        a=read(run/f'training_ledger_{fraction}_000.json');b=read(run/f'training_ledger_{fraction}_001.json')
        assert a['epochs']==b['epochs'] and a['selected_epoch']==b['selected_epoch']
        curve=next(v for v in curves if v['fraction']==fraction)
        assert hashlib.sha256((run/f'model_{fraction}.npz').read_bytes()).hexdigest()==curve['checkpoint_sha256']
    summary={'outcome':outcome,'production_activation':False,'primary_gate_passes':inventory['gate_passes'],
             'trainable_parameters':c['trainable_parameters'],'frozen_clap_parameters':original['frozen_parameter_count'],
             'materialized_tracks':len(original['tracks']),'segments':original['forward_passes'],
             'cache_replay_forward_passes':replay['forward_passes'],'deterministic_training_replay':True,
             'final_checkpoint_sha256':curves[-1]['checkpoint_sha256'],
             'limitations':['Only 16 test anchors / 58 correlated preferences; exploratory intervals are wide.',
                            'Artist-disjoint sensitivity fails its predeclared evidence gate.',
                            'Validation selects epoch 1 in all training fractions; the learner is not demonstrated to exploit all available CLAP information.',
                            'Representation-limited means no credible gain in this small model/aggregation experiment, not proof of information absence.',
                            'Historical similarity supervision is not the newer playlist-compatibility target.'],
             'decision_rule':config['evaluation'],'comparisons':c['comparisons']}
    freeze_json(run/'closeout.json',summary)
    report=f'''# Stage 5G.1 scientific closeout: {outcome}

Neither full-segment mean/cosine nor the small learned scorer demonstrates a
credible held-out improvement under the frozen 5-percentage-point plus positive
lower-95%-bound rule. This outcome is **limited to this experiment**. It does not
prove that CLAP lacks human-relevant information, or that a different learner
could not recover it. No production behavior is activated.

## Supervision and split

740 unique compatible numeric whole-song similarity pairs involve 100 tracks
and 107 credited artists. There are 7,680 strict anchor-based preferences and
3,827 tied candidate comparisons; ties do not enter training. No numeric
conflicts or uncertain pairs were found in the accepted similarity evidence.
The 419 Stage 5E.3 playlist judgments use a different rubric and are inventoried
separately. Stage 2B excerpt/FMA labels and source-identity reviews are excluded.
Unrated pairs remain unknown. Copies of evidence are not independent labels.

The one frozen source-grouped split contains 60 train, 20 validation and 20 test
tracks. Only within-partition human pairs generate constraints. The 410 crossing
pairs are excluded. Track IDs, preference lists, per-track degrees and artist
reuse are published in split.json, human_evidence.json and the inventory/audit.

| Partition | Rated pairs | Informative anchors | Strict preferences | Strong (gap >=2) |
|---|---:|---:|---:|---:|
'''
    for part in ['train','validation','test']:
        v=inventory['primary_split'][part];report+=f"| {part} | {v['rated_pairs']} | {v['anchors']} | {v['preferences']} | {v['strong_preferences']} |\n"
    report+='''
The primary exploratory gate passes. Artist grouping is transitive across every
credited artist and source/video alias. Its test split has only 10 informative
anchors / 27 preferences, below the frozen 15/50 floor; no artist-disjoint model
claim is made. Artist names are used only for split auditing, never prediction.
The gate is an exploratory adequacy floor, not a power guarantee for small gains.

## Representations and model

B0 is exact historical Arm-D d_clap. B1 and M1 share the same 1,927 normalized
512-D segments over all 100 retained sources. Every window is 480,000 samples at
48 kHz; the tail cyclically repeats its own samples. Arm D's HTSAT-tiny
630k-audioset-fusion-best.pt checkpoint, quantization, mel extraction, and
independent-view forward path are reused. Checkpoint SHA-256:
`fb171dd9b608aebdac3d89286cd7615c5100af4cc7dc37797c7fb8d3cc15e3a5`.
No trimming, loudness normalization, new audio, or CLAP training.

B1 uses L2(equal mean of normalized segments) cosine. M1 uses a shared 512-to-16
tanh projection, mean all-section absolute differences/products, a 32-to-1 head
and sigmoid. It is symmetric and permutation-invariant; no Transformer or
metadata/other-model inputs. Arm D already has a full-song resized global view,
so B0-to-B1 tests construction/local coverage, not simply access to more seconds.
B1-to-M1 isolates this learned scorer on identical frozen segment inputs.

The 8,241-parameter model uses torch default seeded Linear initialization,
AdamW (lr 0.001, weight decay 0.001), full-batch anchor-macro logistic preference
loss, seed 20260908, deterministic single-thread CPU training, at most 200 epochs,
and patience 20 on validation loss. Validation chooses the earliest improvement
exceeding 1e-6. CLAP's 158,348,809 parameters remain frozen. No scaler is fitted.

## Held-out and split results

Preference score ties within 1e-6 receive half credit. Primary agreement is
anchor-macro, not a raw-row average. Test contains 16 informative anchors and
58 preferences, supported by 30 human pair labels.

| Method | Train macro | Validation macro | Test macro | Test micro |
|---|---:|---:|---:|---:|
'''
    for m in ['B0','B1','M1']:
        report+=f"| {m} | {c['metrics']['train'][m]['anchor_macro']:.2%} | {c['metrics']['validation'][m]['anchor_macro']:.2%} | {c['metrics']['test'][m]['anchor_macro']:.2%} | {c['metrics']['test'][m]['preference_micro']:.2%} |\n"
    report+='\n| Comparison | Test macro delta (percentage points) | Paired 95% interval |\n|---|---:|---:|\n'
    for name,v in c['comparisons'].items():report+=f"| {name} | {100*v['delta']:+.2f} | [{100*v['low']:+.2f}, {100*v['high']:+.2f}] |\n"
    report+='''
Intervals resample paired test anchors, 2,000 PCG64 replicates at seed 20260908,
with sorted IDs and linear percentiles. They are conditional on this selected
corpus and do not fully model shared-candidate dependence. Strong-preference
results, per-method absolute intervals and per-anchor values are in
supplemental_audit.json. Wide intervals preclude equivalence or absence claims.

## Learning curves and overfitting

| Training fraction | Preferences | Train macro | Validation macro | Selected epoch |
|---|---:|---:|---:|---:|
'''
    for v in curves:report+=f"| {v['fraction']:.0%} | {v['training_constraints']} | {v['train']['anchor_macro']:.2%} | {v['validation']['anchor_macro']:.2%} | {v['selected_epoch']} |\n"
    full=read(run/'training_ledger_1.0_000.json')
    report+=f'''
All three runs stop after 21 epochs and select epoch 1. Later fitting does not
improve validation loss, an overfitting/weak-generalization warning. Training
loss and validation loss for every epoch are preserved in the execution ledgers.
The final model is the predeclared 100% fraction, not a test-selected curve point.
Its training runtime was {full['runtime_seconds']:.3f} seconds; scoring 5,050 unordered
pairs including self pairs took {full['inference_matrix_seconds']:.3f} seconds on CPU.
CLAP extraction took {original['seconds']:.3f} seconds after identity checks, with
1,927 forwards. Replay made zero forwards and reproduced exact NPZ/JSON artifacts.
All three real training runs replayed identical epoch histories and checkpoint
hashes. Final checkpoint SHA-256: `{summary['final_checkpoint_sha256']}`.

## Interpretation and next research boundary

The modest +1.71-point learned-versus-B1 difference is below the fixed +5-point
margin and has a wide interval spanning negative and positive effects. B1 also
does not improve B0. Thus the required outcome is REPRESENTATION_LIMITED under
this frozen operational rule, with no broad information-theoretic conclusion.
Validation selected almost-untrained models; model inadequacy and sparse
supervision remain plausible explanations alongside representation limitations.

Known Wet Dreamz, Shoota and boys dont cry cases are listed only where a real
compatible similarity label exists, marked as research-influencing diagnostics.
Their newer playlist ratings are not substituted, and an unrated suggested
comparison is not assigned a label. This stage does not tune those cases away.
A later reviewed experiment may test complementary MuQ information or stronger
evidence; this stage creates no new review queue and activates nothing.

## Reproduction and verification

Use the commands in docs/stage5g1.md with the locked environment and retained
local audio/checkpoint. Replay never invokes the CLAP forward path on a cache
miss; it fails explicitly. Original ledgers are create-once; later executions
append numbered ledgers. The final artifact_manifest.json inventories all run
files except itself. Input hashes protect historical artifacts, raw sources,
label provenance, protocol and fitting/extraction implementation.

Focused suite: 11 passed. Full non-heavy suite: 1,261 passed, 12 deselected,
11 warnings, 121.30 seconds. verification/audit_outputs.py checks isolation,
human-only preferences, timestamps, normalization, cache replay, finite symmetric
scores, all reported split metrics, and historical hashes. Supporting evidence
and exact test output are in verification/. No network downloads, MuQ/MIR inputs,
CLAP tuning, new judgments, Spotify writes, or production changes occurred.
'''
    freeze(run/'experiment_report.md',report.encode())
    freeze_json(run/'artifact_manifest.json',hashes([p for p in run.rglob('*') if p.is_file() and p.name!='artifact_manifest.json'],run))
    verify_hashes(run,read(run/'artifact_manifest.json'))
    return summary

if __name__=='__main__':
    import json
    print(json.dumps(closeout(Path(__file__).resolve().parents[2]),sort_keys=True))
