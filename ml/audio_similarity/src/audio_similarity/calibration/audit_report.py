"""Draft execution settings and concise readiness report; no performance outputs."""
from .contracts import Clap, digest
from .ranking import RHO, WC, ETA, grid, M3_RHO


def draft_manifest(capture, audit):
    return {
        'schema': 'playlist-calibration-execution-draft-v1', 'status': 'DRAFT_NOT_FROZEN',
        'calibration_authorized_by_this_artifact': False,
        'capture_sha256': digest(capture), 'audit_sha256': digest(audit),
        'owner_clarification': audit.get('owner_clarification'),
        'protocols': capture['protocols'], 'implementation_hashes': capture['implementation_hashes'],
        'corpus': {'initial_run': 'example_playlist_batches_v1', 'requests': audit['initial_requests'],
            'source_membership_snapshot_hash': digest(audit['playlists']),
            'recording_purge_groups_hash': digest(audit['recording_group_links']),
            'eligibility': ['Original multi-artist genre-focused sources only, classified by source notes before scoring.',
                'Source-use and curator provenance must be resolved; copied lists retain original curator.',
                'Exclude single-artist catalogs from Layer A; ambiguous Mix/radio candidates stay pending/diagnostic.',
                'Sample up to 30 from the entire source in hash order, maximum three per primary artist and minimum ten primary artists.',
                'Keep failed/unresolved sampled requests visible; do not replace based on feature availability.',
                'Missing genre is a visible no-op, not an exclusion. Missing audio requires common-population attrition.'],
            'sampling_seed': 'calibration-audit-v1/sample/{playlist_id}',
            'minimum_usable_recordings': {'main_target': 30, 'harness_query_minimum': 2,
                'status': 'UNRESOLVED_WHEN_POSSIBLE_EXCEPTION_POLICY; min2 is not main-cohort eligibility'},
            'extension': 'Separate source snapshot; not fitting data and not automatically an untouched lockbox.',
            'personal_library': 'Not added as challengers; separate transfer cohort under the protocol.'},
        'features': {'status': 'WAITING_FOR_FEATURES', 'frozen_feature_bundle_sha256': None,
            'audited_feature_rows_sha256': digest(audit['feature_rows']),
            'verified_counts': audit['verified_features'],
            'representation_choices': [c.value for c in Clap], 'muq': 'fixed centered30; never full-song M4',
            'C_checkpoint': 'Stage5E1 C HTSAT-base music_audioset_epoch_15_esc_90.14.pt; not Arm D HTSAT-tiny',
            'identity': 'Exact retained source bytes + recording identity + checkpoint/config + sampling plan + feature hash.',
            'Gemini': 'Reuse existing frozen free-genre prompt/config and canonical-first registry; missing stays no-op.',
            'historical_alternatives': 'Documented only; neither stale queue links nor original artifacts replaced.'},
        'splits': {'status': 'DRAFT_CONDITIONAL_ONLY', 'approved_split_manifest_sha256': None,
            'conditional_preflight_sha256': digest(audit['conditional_splits']),
            'source_grouping': 'Same credited curator plus transitive full-playlist duplicate groups; unknown curator not independent.',
            'duplicate_thresholds': {'jaccard': .8, 'smaller_containment': .9},
            'version_purge': 'Purge evaluation recording/version groups from all fitting seeds, positives and challengers.',
            'outer_folds': 3, 'inner_folds': 2, 'seed': 'calibration-audit-v1/outer',
            'lockbox': {'assigned': False, 'performance_read': False,
                'reason': 'Source identity/roles unresolved; do not force full confirmation from eight provisional groups.'},
            'inspected_frozen100': 'development-only; future lockbox must exclude its recording/version groups',
            'artist_sensitivity': 'Report overlap; do not claim artist disjointness from track purging.'},
        'candidate_catalog': {'status': 'DRAFT_NOT_FROZEN',
            'policy': 'All distinct evaluation-partition recordings, minus seeds and duplicate versions; identical for every arm.',
            'conditional_catalog_hashes': [p['candidate_catalog_sha256'] for p in audit['conditional_splits']['partitions']],
            'nonmembers': 'UNLABELED; relevance zero only for observed-membership metrics'},
        'scoring': {'F': '(1-rho)*C_h + rho*M + w_c*Jc + w_n*(1-Jc)*Jnr',
            'Q': 'mean(top min(3, seed_count) complete F values)', 'top_k_tunable': False},
        'grid': {'h': [c.value for c in Clap], 'rho': RHO, 'w_c': WC, 'eta': ETA,
            'w_n': 'w_c*eta', 'nominal': 880, 'eta_deduplicated': 792,
            'unique_joint': len(grid()), 'exact_M3_additional_controls': 36},
        'recall_guardrail': {'status': 'DRAFT_RECOMMENDATION_MATCHES_EXISTING_HARNESS',
            'comparator': 'Same h, rho and audio base as each candidate, with w_c=w_n=0. For M3 additions use exact frozen M3.',
            'threshold': 'inner macro Recall@20 >= corresponding comparator Recall@20 - 0.02',
            'separately_tuned_audio_winner': 'Report as refitted ablation; not substituted into this guardrail.'},
        'masks': {'repetitions': 8, 'hidden_fraction': .2, 'rounding': 'max(1, ceil(0.2*n_unique))',
            'schedule': 'existing hash_order using partition.seed/playlist_id/repeat',
            'independent_units': 'curator/duplicate groups, never repeated masks'},
        'uncertainty': {'status': 'DRAFT_EXECUTION_DEFAULT_NOT_RUN', 'bootstrap_draws': 2000,
            'seed': 1701, 'unit': 'curator/duplicate cluster; retain all playlist masks together',
            'interval': 'paired percentile 95%; recompute hierarchical macro in each resample',
            'one_SE': 'sample standard deviation ddof=1 of cluster-bootstrap inner macro NDCG@20',
            'fewer_than_two_clusters': 'INSUFFICIENT_DATA; no interval or selection claim'},
        'ties': {'candidate_ranking': 'descending unrounded Q, ascending stable recording ID',
            'selection': ['within one cluster SE of best Recall-eligible inner NDCG',
                'fewest nonzero signals', 'lowest w_c', 'lowest w_n',
                f'closest rho to original {M3_RHO}', 'rho', 'eta', 'CLAP representation ID', 'audio base ID'],
            'float_guard_tolerance': 1e-12},
        'unresolved': ['Source-use records; external playlist membership preservation is owner-confirmed in the captured clarification.'
                       if audit.get('owner_clarification') else 'Owner-versus-captured external provenance and source-use records.',
            'Independent curator identities, source descriptions and acquisition/remote-use provenance.',
            'Complete recording/version adjudication and the two stale feature links.',
            'Main min30 when-possible policy versus explicitly scoped smaller development pilot.',
            'Final source strata, development/lockbox/output-policy role allocation and feature bundle.',
            'Approve/freeze draft execution defaults before real inner selection; no results inspected.'],
        'production_activation': False,
    }


def markdown(audit, manifest):
    counts = audit['verified_features']
    splits = audit['conditional_splits']
    lines = ['# Real playlist corpus readiness audit', '',
        '**Source readiness: SOURCE_NOT_READY. Feature readiness: WAITING_FOR_FEATURES.**', '',
        'No calibration, model inference, downloads, lockbox performance inspection, or production changes occurred.', '',
        f"Initial scope: {audit['initial_playlists']} captured lists, {audit['initial_requests']} requests; "
        f"{audit['initial_queue_states'].get('COMPLETE', 0)} queue completions, "
        f"{audit['initial_queue_states'].get('MANUAL_TAIL', 0)} manual tails, "
        f"{audit['initial_queue_states'].get('ACQUISITION_FAILED', 0)} acquisition failures. "
        'The extension remains separate.', '',
        '## Provenance and eligibility', '',
        ('Owner confirms that each table preserves one external playlist track list. The queue wording '
         'owner-declared means owner-collected here, not independently owner-authored. ' if audit.get('owner_clarification') else
         'Captured notes name external curators and Spotify URLs. The queue says owner-declared reference groupings; '
         'that does not establish independent authorship. ') + 'No source-use status is upgraded by this audit. '
        'Original source descriptions, curator account IDs, and discovery details are incomplete.', '',
        f"Source-only screen: {audit['provenance_counts']}. Zero sources are cleared for calibration. "
        'Mix/radio titles are review flags, not proof of an algorithmic or heterogeneous playlist. '
        'The single-artist source is outside primary Layer A. Unknown curator stays unresolved.', '',
        '## Feature verification', '', '| Feature | Exact source/identity matches |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in counts.items()]
    lines += ['', f"Common four-feature population: {audit['all_four_features']} requests. "
        'Counts refer to inspected compatible artifacts, not title matches. Missing genre remains a no-op; '
        'this tiny coverage cannot test whether genre helps the broader corpus.', '',
        'Thirsty (aespa) and Sour Grapes (LE SSERAFIM) have queue feature links to a different source hash '
        'than the retained audio. Retained bytes agree with acquisition provenance. Thirsty has exact-source '
        'historical A/C/MUQ alternatives; these are documented, not silently substituted. Sour Grapes has no '
        'matching alternate in the inspected representation caches. No source or cache was overwritten.', '',
        '## Conditional split feasibility', '',
        f"Treating the credited curators as provisional groups gives {splits.get('candidate_playlists', 0)} candidate "
        f"playlists in {splits.get('source_groups', 0)} groups. These are not independently verified curator identities. "
        'Three outer/two inner folds can be simulated without fitting, but this does not establish a full confirmation design. '
        'If all lists are genuinely authored by the owner, one source group remains and grouped evaluation is infeasible.', '',
        'Samples are drawn from complete membership before feature attrition, capped at three tracks per primary artist. '
        'Unavailable sampled tracks remain visible and are not replaced. The table reports query-feasible playlists '
        '(at least two recordings); the private audit separately reports those still meeting the main 30-recording target.', '',
        '| Outer fold | Fit playlists / curators / tracks | Evaluation playlists / curators / tracks | Purged fit requests |',
        '|---|---|---|---:|']
    for i, p in enumerate(splits['partitions']):
        vals = [f"{p[s]['surviving_playlists_min2']} / {p[s]['curators']} / {p[s]['tracks']}" for s in ('fit','evaluation')]
        lines.append(f'| {i + 1} | {vals[0]} | {vals[1]} | {p["purged_requests"]} |')
    lines += ['', 'All inner partitions, recording lists, purge lists, artist overlap and candidate hashes are retained '
        'in `audit.private.json`. These are conditional metadata-only plans. No lockbox was allocated or scored.', '',
        '## Draft and next action', '',
        'The draft retains the documented 880 nominal / 756 unique joint configurations plus 36 exact-M3 controls. '
        'It proposes eight masks, 2,000 cluster bootstrap draws, and the existing same-h/rho audio comparator '
        'with genre coefficients zero. These settings have not been fitted or scientifically selected.', '',
        'Resolve source provenance first. If that passes, a small development-only pilot may be possible after '
        'feature parity and identity checks; a full grouped confirmation is not currently established. '
        'The draft feature bundle and split freeze hashes remain null.', '',
        ('Owner input still needed: point to any existing source-use permission/license records. ' if audit.get('owner_clarification') else
         'Owner input needed: clarify copied versus independently authored membership (which lists, if mixed), '
         'and point to any existing source-use permission/license records. ') + 'Remaining execution details have '
        'explicit draft defaults or stay blocked on this factual clarification.', '',
        f"Capture hash: `{manifest['capture_sha256']}`. Audit hash: `{manifest['audit_sha256']}`."]
    if audit.get('owner_clarification'):
        lines += ['', '## Owner clarification', '',
            audit['owner_clarification']['interpretation'], '',
            'The attributed external curators are retained. These are copies of individual external playlist '
            'memberships, not new independent owner-authored playlists or pooled lists. Source-use status remains pending.']
    return '\n'.join(lines) + '\n'
