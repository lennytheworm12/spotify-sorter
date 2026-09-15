#!/usr/bin/env python3
# Generate the combined-corpus split following the retained protocol rule.
# Rule: protocol v11 SS9 + realized partitions in calibration_corpus_audit_v1.
# Families (curator / duplicate overlap) never split across fit and evaluation.
import json, hashlib
from pathlib import Path
from itertools import combinations

R = Path('/home/bphan944/PersonalProjects/spotifyProject/ml/audio_similarity')
AUD = R / '.research_audio'
ORIG = json.loads((AUD / 'playlist_calibration_method_c_full_v1/corpus.json').read_text())
EXT_DEV = json.loads((AUD / 'playlist_calibration_extension_preparation_v1/role_catalogs_v3/development_candidates/catalog.private.json').read_text())
EXT_CONF = json.loads((AUD / 'playlist_calibration_extension_preparation_v1/role_catalogs_v3/confirmation_candidates/catalog.private.json').read_text())
OUT = R / 'reports/playlist_weight_calibration/v1/combined_corpus'

EVIDENCE_ONLY = {'mix_or_radio_source_review_required', 'single_artist_excluded'}
SEED = 'combined-split-v1'
TARGET_EVAL_FRACTION = 0.25

# ---- original playlists: usable candidates vs evidence-only
usable, evidence_only = [], []
for s in ORIG['source_playlists']:
    recs = set(s.get('request_ids') or [])
    entry = {
        'playlist_id': s['playlist_id'],
        'intent': s.get('declared_intent'),
        'curator': s.get('curator'),
        'cohort': s.get('cohort'),
        'recordings': sorted(recs),
        'n_recordings': len(recs),
    }
    (evidence_only if s.get('cohort') in EVIDENCE_ONLY else usable).append(entry)

# ---- family clustering over the usable playlists
def fam_key(e):
    return (e['curator'] or f"__unattributed__{e['playlist_id']}").strip().lower()

def related(a, b):
    if fam_key(a) == fam_key(b):
        return True
    A, B = set(a['recordings']), set(b['recordings'])
    if not A or not B:
        return False
    inter = len(A & B)
    smaller_containment = inter / min(len(A), len(B))
    jaccard = inter / len(A | B)
    return jaccard >= 0.8 or smaller_containment >= 0.9

parent = {e['playlist_id']: e['playlist_id'] for e in usable}
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[rb] = ra
for a, b in combinations(usable, 2):
    if related(a, b):
        union(a['playlist_id'], b['playlist_id'])

clusters = {}
for e in usable:
    clusters.setdefault(find(e['playlist_id']), []).append(e)

ordered = sorted(clusters.values(), key=lambda c: (-sum(e['n_recordings'] for e in c), sorted(e['playlist_id'] for e in c)[0]))
total_recs = sum(e['n_recordings'] for c in ordered for e in c)
target = TARGET_EVAL_FRACTION * total_recs

eval_clusters, fit_clusters, acc = [], [], 0
for c in ordered:
    size = sum(e['n_recordings'] for e in c)
    if acc < target:
        eval_clusters.append(c); acc += size
    else:
        fit_clusters.append(c)

fit_playlists = [e for c in fit_clusters for e in c]
eval_playlists = [e for c in eval_clusters for e in c]
fit_recs = {r for e in fit_playlists for r in e['recordings']}
eval_recs = {r for e in eval_playlists for r in e['recordings']}
ext_fit = set(EXT_DEV['recording_ids'])
ext_lock = set(EXT_CONF['recording_ids'])
ev_only_recs = {r for e in evidence_only for r in e['recordings']}

# leaked = appear in both a fit group and an evaluation/lockbox group -> purge from fit
leaked = sorted((fit_recs & eval_recs) | (fit_recs & ext_lock))
fit_recs -= set(leaked)

manifest = {
    'schema': 'combined-corpus-split-v1',
    'seed': SEED,
    'target_eval_fraction': TARGET_EVAL_FRACTION,
    'rule': {
        'source': 'protocol v11 SS9 (split design) + calibration_corpus_audit_v1 realized partitions',
        'candidates': 'cohort=genre_focused_candidate (curated, genre-focused, curator boundary defined)',
        'evidence_only_excluded': sorted(EVIDENCE_ONLY),
        'family_rule': 'same curator OR recording-set jaccard>=0.8 OR smaller-list containment>=0.9; clusters never split across fit/eval',
        'lockbox': 'extension confirmation_candidates, opened once after the procedure is locked',
    },
    'fit': {
        'role': 'learn_and_train',
        'playlists': sorted(e['playlist_id'] for e in fit_playlists),
        'recordings': sorted(fit_recs),
        'n_playlists': len(fit_playlists),
        'n_recordings': len(fit_recs),
    },
    'outer_validation': {
        'role': 'held_out_for_model_selection',
        'playlists': sorted(e['playlist_id'] for e in eval_playlists),
        'recordings': sorted(eval_recs),
        'n_playlists': len(eval_playlists),
        'n_recordings': len(eval_recs),
        'cluster_sizes': [sum(e['n_recordings'] for e in c) for c in eval_clusters],
    },
    'lockbox_reserved': {
        'role': 'one_time_confirmation_after_lock',
        'playlists': sorted(EXT_CONF['playlist_ids']),
        'recordings': sorted(ext_lock),
        'n_playlists': len(EXT_CONF['playlist_ids']),
        'n_recordings': len(ext_lock),
    },
    'extension_development': {
        'role': 'learn_and_train',
        'playlists': sorted(EXT_DEV['playlist_ids']),
        'recordings': sorted(ext_fit),
        'n_playlists': len(EXT_DEV['playlist_ids']),
        'n_recordings': len(ext_fit),
    },
    'evidence_only': {
        'playlists': sorted(e['playlist_id'] for e in evidence_only),
        'cohorts': sorted({e['cohort'] for e in evidence_only}),
        'n_playlists': len(evidence_only),
        'n_recordings': sum(e['n_recordings'] for e in evidence_only),
    },
    'purged_leaked_recordings': {
        'n': len(leaked),
        'sha256': hashlib.sha256('\n'.join(leaked).encode()).hexdigest(),
    },
    'clusters': [
        {'members': sorted(e['playlist_id'] for e in c),
         'curators': sorted({(e['curator'] or 'unattributed') for e in c})}
        for c in (fit_clusters + eval_clusters)
    ],
}
manifest['split_id'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()

OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'split_manifest_v1.private.json').write_text(json.dumps(manifest, indent=1, sort_keys=True))

combined_fit = len(fit_recs) + len(ext_fit)
combined_eval = len(eval_recs)
combined_lock = len(ext_lock)
summary = {
    'schema': 'combined-corpus-split-summary-v1',
    'split_id': manifest['split_id'],
    'seed': SEED,
    'learn_and_train_recordings': combined_fit,
    'held_out_validation_recordings': combined_eval,
    'lockbox_reserved_recordings': combined_lock,
    'evidence_only_excluded_recordings': manifest['evidence_only']['n_recordings'],
    # NOTE: playlists overlap, so group sizes sum above the unique corpus size.
    'sum_of_group_recordings': combined_fit + combined_eval + combined_lock + manifest['evidence_only']['n_recordings'],
    'unique_recordings_across_all_groups': len(fit_recs | ext_fit | eval_recs | ext_lock | ev_only_recs),
    'unique_recordings_in_any_fit_or_eval_group': len(fit_recs | ext_fit | eval_recs),
    'multi_playlist_overlap_recordings': (len(fit_recs) + len(ext_fit) + len(eval_recs) + len(ext_lock) + len(ev_only_recs)) - len(fit_recs | ext_fit | eval_recs | ext_lock | ev_only_recs),
    'learn_and_train_playlists': manifest['fit']['n_playlists'] + manifest['extension_development']['n_playlists'],
    'held_out_playlists': manifest['outer_validation']['n_playlists'],
    'lockbox_playlists': manifest['lockbox_reserved']['n_playlists'],
    'evidence_only_playlists': manifest['evidence_only']['n_playlists'],
    'purged_leaked': len(leaked),
    'clusters': len(manifest['clusters']),
}
(OUT / 'split_summary_v1.json').write_text(json.dumps(summary, indent=1, sort_keys=True))
print(json.dumps(summary, indent=1))
