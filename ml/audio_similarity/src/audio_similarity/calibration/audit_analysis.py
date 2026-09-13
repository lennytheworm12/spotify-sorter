"""Model-blind attrition and hypothetical split preflight over captured evidence."""
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
import re
from types import SimpleNamespace
import unicodedata

from .contracts import Layer, Role, digest
from .splits import grouped_folds, hash_order, source_clusters


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


class Groups:
    def __init__(self, keys):
        self.parents = {k: k for k in keys}

    def find(self, key):
        while self.parents[key] != key:
            key = self.parents[key]
        return key

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        self.parents[max(a, b)] = min(a, b)


def recording_groups(tracks, sources):
    """Conservative purge groups, not an adjudication of recording equivalence."""
    groups = Groups(tracks)
    seen = {}
    links = []
    for key in sorted(tracks):
        t = tracks[key]
        tokens = [('exact_title_credits', normalized(t['title']), tuple(sorted(normalized(a) for a in t['artists'])))]
        if key in sources:
            s = sources[key]
            tokens += [('source_hash', s['actual_source_sha256']),
                       ('stored_identity', s['result']['representation']['stable_track_id'])]
            video = s['provenance'].get('youtube_video_id')
            if video:
                tokens.append(('video_id', video))
        for token in tokens:
            if token in seen:
                groups.union(key, seen[token])
                links.append({'a': key, 'b': seen[token], 'basis': token[0]})
            else:
                seen[token] = key
    return {k: groups.find(k) for k in sorted(tracks)}, links


def sample_members(keys, tracks, versions, seed):
    ordered = hash_order(keys, seed)
    selected, artists, used = [], Counter(), set()
    # Whole-list deterministic order with a cap, never replace failed sampled members.
    for k in ordered:
        artist = normalized(tracks[k]['artists'][0])
        if versions[k] in used or artists[artist] >= 3:
            continue
        selected.append(k)
        used.add(versions[k])
        artists[artist] += 1
        if len(selected) == 30:
            break
    return selected


def classify_source(text, title, primary_artists):
    match = re.search(r'curated by ([^\n]+?)(?:\.\s*)?$', text, re.M)
    curator = match.group(1) if match else None
    if curator and normalized(curator) == 'unknown':
        curator = None
    source = re.search(r'https://open\.spotify\.com/playlist/([A-Za-z0-9]+)', text)
    warnings = []
    if not curator:
        warnings.append('CURATOR_UNRESOLVED')
    kind = 'externally_attributed_capture' if source else 'PROVENANCE_UNRESOLVED'
    if len(primary_artists) == 1:
        cohort, layer = 'single_artist_excluded', None
    elif re.search(r'\b(mix|radio)\b', title, re.I):
        cohort, layer = 'mix_or_radio_source_review_required', 'C_candidate'
        warnings.append('TITLE_DOES_NOT_PROVE_PERSONALIZED_ALGORITHM_OR_HUMAN_MIX')
    else:
        cohort, layer = 'genre_focused_candidate', 'A_candidate'
    return {'curator': curator, 'source_url': source.group(0) if source else None,
            'provenance_kind': kind, 'cohort': cohort, 'layer': layer, 'warnings': warnings}


def source_stratum(text):
    """Read the original capture tags only, never model classifications."""
    tags = {'alt-rnb': 'R1', 'neo-soul': 'R2', 'rnb': 'R3', 'hip-hop': 'H1',
            'modern-rap': 'H2', 'lofi': 'B1', 'downtempo': 'E1', 'indie-pop': 'P1'}
    return next((value for tag, value in tags.items() if re.search(r'^\s*- ' + re.escape(tag) + r'\s*$', text, re.M)),
                'STRATUM_REVIEW_REQUIRED')


def split_preflight(playlists, tracks, versions, available, *, collapse_owner=False):
    """Reuse production-free grouping/purging helpers; no source is marked cleared."""
    eligible = [p for p in playlists if p['layer'] == 'A_candidate' and p['curator'] is not None
                and p['sample_primary_artists'] >= 10 and len(p['sample_request_ids']) == 30]
    records = {k: SimpleNamespace(version_group_id=versions[k],
               artist_group_ids=tuple(normalized(a) for a in t['artists'])) for k, t in tracks.items()}
    sources = [SimpleNamespace(playlist_id=p['playlist_id'], recording_ids=tuple(p['sample_request_ids']),
                curator_group_id='owner' if collapse_owner else p['curator'],
                duplicate_group_id=p['playlist_id'], parent_playlist_ids=(), layer=Layer.ORIGINAL,
                source_ready=False) for p in eligible]
    curators = sorted({p.curator_group_id for p in sources})
    corpus = SimpleNamespace(playlists=tuple(sources), by_id=records,
        groups=tuple(SimpleNamespace(group_id=k, curator_id=k) for k in curators),
        identity=digest({'samples': eligible, 'version_groups': versions, 'owner_sensitivity': collapse_owner}))
    if not sources:
        return {'status': 'INSUFFICIENT_DATA', 'source_groups': 0, 'partitions': []}
    # Duplicate groups are computed on full source membership, then inherited by samples.
    original = corpus.playlists
    full = {p['playlist_id']: p['request_ids'] for p in playlists}
    corpus.playlists = tuple(SimpleNamespace(**(vars(p) | {'recording_ids': tuple(full[p.playlist_id])})) for p in original)
    cluster_map = source_clusters(corpus)
    corpus.playlists = tuple(SimpleNamespace(**(vars(p) | {'duplicate_group_id': cluster_map[p.playlist_id]})) for p in original)
    group_count = len(set(source_clusters(corpus).values()))
    result = {'status': 'CONDITIONAL_GEOMETRY_ONLY', 'cleared_sources': 0,
              'source_groups': group_count, 'curator_labels': curators,
              'candidate_playlists': len(sources), 'sample_requests': len({k for p in sources for k in p.recording_ids}),
              'cluster_map': source_clusters(corpus), 'partitions': [], 'lockbox_reserved': False,
              'qualification': 'No permissions/curator identity or version adjudication inferred; not a runnable evaluation corpus.'}
    by_id = {p.playlist_id: p for p in corpus.playlists}

    def describe(partition):
        sides = {}
        for side, pids, keys in [('fit', partition.fit_playlists, partition.fit_recordings),
                                 ('evaluation', partition.evaluation_playlists, partition.evaluation_recordings)]:
            rows = []
            for pid in pids:
                ids = set(by_id[pid].recording_ids) & set(keys)
                unique = {versions[k] for k in ids}
                rows.append({'playlist_id': pid, 'recordings': len(unique),
                    'query_usable_min2': len(unique) >= 2, 'main_target_min30': len(unique) >= 30,
                    'primary_artists': len({normalized(tracks[k]['artists'][0]) for k in ids})})
            sides[side] = {'playlists': rows, 'surviving_playlists_min2': sum(r['query_usable_min2'] for r in rows),
                          'main_target_playlists_min30': sum(r['main_target_min30'] for r in rows),
                          'curators': len({by_id[r['playlist_id']].curator_group_id for r in rows if r['query_usable_min2']}),
                          'tracks': len(keys), 'version_groups': len({versions[k] for k in keys})}
        sides['artist_overlap'] = len({a for k in partition.fit_recordings for a in records[k].artist_group_ids} &
                                     {a for k in partition.evaluation_recordings for a in records[k].artist_group_ids})
        sides['purged_requests'] = len(partition.purged_recordings)
        sides['partition'] = asdict(partition)
        sides['candidate_catalog_sha256'] = digest(partition.evaluation_recordings)
        return sides

    try:
        outer = grouped_folds(corpus, list(by_id), 3, Role.OUTER, 'calibration-audit-v1/outer', available)
        for i, p in enumerate(outer):
            row = describe(p)
            try:
                inner = grouped_folds(corpus, p.fit_playlists, 2, Role.INNER,
                                      f'calibration-audit-v1/outer/{i}/inner', p.fit_recordings)
                row['inner'] = [describe(q) for q in inner]
            except ValueError as exc:
                row['inner_error'] = str(exc)
            result['partitions'].append(row)
        result['status'] = 'CONDITIONAL_DEVELOPMENT_GEOMETRY_FEASIBLE' if all('inner_error' not in r for r in result['partitions']) else 'INSUFFICIENT_DATA'
    except ValueError as exc:
        result.update(status='INSUFFICIENT_DATA', reason=str(exc))
    return result


def analyze(capture):
    run = capture['runs']['example_playlist_batches_v1']
    tracks = {t['local_recording_id']: t for b in run['manifest']['batches'] for t in b['tracks']}
    sources = {s['request_id']: s for s in capture['sources']}
    versions, links = recording_groups(tracks, sources)
    verified = {r['recording_id'] for r in capture['inventory']['recordings'] if r['centered30'] and r['muq']}
    members = defaultdict(list)
    for key, t in tracks.items():
        for m in t['memberships']:
            members[m['source_key']].append(key)
    c_by_hash = defaultdict(list)
    for row in capture['method_c']:
        if row['verified']:
            c_by_hash[row['source_sha256']].append(row)
    g_by_hash = defaultdict(list)
    for row in capture['profiles']:
        if row['gemini_verified'] and row['mapped_verified']:
            g_by_hash[row['source_sha256']].append(row)
    features = []
    for key in sorted(tracks):
        source = sources.get(key, {})
        sha = source.get('actual_source_sha256')
        stable = source.get('result', {}).get('representation', {}).get('stable_track_id')
        # Matching bytes alone can reveal an alias, but identity must also align for enrollment.
        cs = [r for r in c_by_hash[sha] if r['spotify_track_id'] == stable]
        gs = [r for r in g_by_hash[sha] if r['spotify_track_id'] == stable]
        features.append({'request_id': key, 'source_sha256': sha, 'cache_recording_id': stable,
            'centered30': key in verified, 'muq': key in verified,
            'method_c': len(cs) == 1, 'gemini_canonical': len(gs) == 1,
            'method_c_evidence': cs, 'gemini_evidence': gs,
            'same_hash_other_identity_C': len(c_by_hash[sha]) - len(cs),
            'same_hash_other_identity_Gemini': len(g_by_hash[sha]) - len(gs),
            'recording_identity_status': 'HASH_LINKED_AUTO_SELECTED_NOT_OWNER_ADJUDICATED' if source else 'UNRESOLVED',
            'purge_group': versions[key]})
    by_feature = {r['request_id']: r for r in features}
    playlists = []
    for p in capture['intakes']['589be5ae1ef5']['playlists']:
        path = '.research_audio/playlist_reference_intake/589be5ae1ef5/vault_sources/' + Path(p['vault_path']).name
        text = capture['files'][path]['text']
        keys = sorted(set(members[p['vault_path']]))
        artists = {normalized(tracks[k]['artists'][0]) for k in keys}
        info = classify_source(text, p['title'], artists)
        sample = sample_members(keys, tracks, versions, 'calibration-audit-v1/sample/' + p['playlist_id'])
        playlists.append({'playlist_id': p['playlist_id'], 'title': p['title'], 'source_path': p['vault_path'],
            'source_note_sha256': p['sha256'], **info, 'request_ids': keys, 'sample_request_ids': sample,
            'stratum': source_stratum(text),
            'sample_primary_artists': len({normalized(tracks[k]['artists'][0]) for k in sample}),
            'original_table_rows': len(p['tracks']), 'captured_declared_slots': p['membership_slots'],
            'distinct_requests': len(keys), 'primary_artists': len(artists),
            'queue_states': dict(Counter(run['states'].get(k, {}).get('state', 'NOT_STARTED') for k in keys)),
            'verified_features': {f: sum(by_feature[k][f] for k in keys) for f in ('centered30','muq','method_c','gemini_canonical')},
            'sample_verified_audio': sum(k in verified for k in sample),
            'membership_use_permission': p['membership_use_permission'],
            'audio_use_permission': p['audio_use_permission'],
            'remote_processing_permission': p['remote_processing_permission'],
            'redistribution_permission': 'permission_pending',
            'source_description': None, 'declared_intent': p['title'], 'intent_basis': 'source_title_only',
            'actual_eligibility': 'SOURCE_NOT_READY',
            'provenance_conflict': None if capture.get('owner_clarification') else
                'queue says owner-declared; captured source names external curator/Spotify URL',
            'provenance_resolution': capture.get('owner_clarification', {}).get('interpretation')})
    initial_paths = {p['source_path'] for p in playlists}
    extension = []
    for p in capture['intakes']['15127df33fca']['playlists']:
        if p['vault_path'] in initial_paths:
            continue
        text = capture['files']['.research_audio/playlist_reference_intake/15127df33fca/vault_sources/' + Path(p['vault_path']).name]['text']
        extension.append({'source_path': p['vault_path'], 'source_note_sha256': p['sha256'], 'table_rows': len(p['tracks']),
            **classify_source(text, Path(p['vault_path']).stem, {r['artists_text'].split(',')[0] for r in p['tracks']}),
            'eligibility': 'NOT_AUDITED_FOR_INITIAL_CORPUS', 'source_use_status': 'UNRESOLVED'})
    totals = {f: sum(r[f] for r in features) for f in ('centered30','muq','method_c','gemini_canonical')}
    duplicate_edges = []
    for i, a in enumerate(playlists):
        av = {versions[k] for k in a['request_ids']}
        for b in playlists[i + 1:]:
            bv = {versions[k] for k in b['request_ids']}
            jaccard = len(av & bv) / len(av | bv)
            containment = len(av & bv) / min(len(av), len(bv))
            if jaccard >= .8 or containment >= .9:
                duplicate_edges.append({'a': a['playlist_id'], 'b': b['playlist_id'],
                    'jaccard': jaccard, 'containment': containment})
    overlays = []
    corrected = {r['expected_old_source_sha256']: r for r in capture['corrections']['corrections']}
    quarantined = {r['source_sha256']: r for r in capture['quarantines']['tracks']}
    for row in features:
        sha = row['source_sha256']
        if sha in corrected or sha in quarantined:
            overlays.append({'request_id': row['request_id'], 'source_sha256': sha,
                'status': 'CORRECTION_REVIEW_REQUIRED' if sha in corrected else 'QUARANTINED',
                'record': corrected.get(sha) or quarantined[sha]})
    if overlays:
        # Never admit known superseded audio to a conditional feature population.
        verified -= {r['request_id'] for r in overlays}
    return {'schema': 'real-calibration-corpus-audit-v1', 'source_readiness': 'SOURCE_NOT_READY',
        'owner_clarification': capture.get('owner_clarification'),
        'feature_readiness': 'WAITING_FOR_FEATURES', 'full_evaluation_feasibility': 'NOT_ESTABLISHED',
        'initial_requests': len(tracks), 'initial_playlists': len(playlists),
        'initial_membership_slots': sum(p['original_table_rows'] for p in playlists),
        'invalid_metadata_exclusions': run['manifest']['excluded'],
        'initial_queue_states': dict(Counter(s['state'] for s in run['states'].values())),
        'verified_features': totals, 'all_four_features': sum(all(r[f] for f in totals) for r in features),
        'provenance_counts': dict(Counter(p['cohort'] for p in playlists)),
        'primary_candidate_strata': sorted({p['stratum'] for p in playlists if p['layer'] == 'A_candidate'}),
        'cleared_playlists': 0, 'confirmed_owner_authored': 0, 'confirmed_pooled': 0,
        'version_group_count': len(set(versions.values())), 'recording_group_links': links,
        'duplicate_playlist_edges': duplicate_edges, 'source_overlay_conflicts': overlays,
        'playlists': playlists, 'feature_rows': features,
        'conditional_splits': split_preflight(playlists, tracks, versions, verified),
        'single_owner_sensitivity': split_preflight(playlists, tracks, versions, verified, collapse_owner=True),
        'extension': {'new_source_notes': extension, 'new_requests': capture['runs']['example_playlist_batches_v2']['manifest']['track_count'],
            'queue_states': dict(Counter(s['state'] for s in capture['runs']['example_playlist_batches_v2']['states'].values())),
            'role': 'SEPARATE_UNASSIGNED_COHORT_NOT_AUTOMATIC_LOCKBOX'},
        'hash_mismatches': capture['mismatches'],
        'limitations': ['Exact-title/credit, stored-ID, source-hash and video groups are conservative purge links, not complete version adjudication.',
            'No independent curator identities or source-use clearance inferred from copied tables.',
            'Sampled failures remain explicit; no replacement according to model outputs or feature availability.',
            'No selected weights, scores, lockbox performance, or suitability labels were evaluated.']}
