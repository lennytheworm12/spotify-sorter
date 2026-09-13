"""Isolated, owner-authorized development inputs. Historical artifacts stay read-only."""
from collections import Counter
import json
from pathlib import Path

from .contracts import digest, file_hash, freeze_json, require

RUN = '.research_audio/playlist_calibration_development_v1'
AUDIT = '.research_audio/calibration_corpus_audits/20260913_owner_confirmed'


def prepare(root):
    run = root / RUN
    audit = json.loads((root / AUDIT / 'audit.private.json').read_text())
    capture = json.loads((root / AUDIT / 'capture.private.json').read_text())
    plans = audit['conditional_splits']
    pids = set(plans['cluster_map'])
    playlists = [p for p in audit['playlists'] if p['playlist_id'] in pids]
    requests = {r for p in playlists for r in p['sample_request_ids']}
    source_by_id = {r['request_id']: r for r in capture['sources']}
    tracks = {t['local_recording_id']: t for b in capture['runs']['example_playlist_batches_v1']['manifest']['batches'] for t in b['tracks']}
    repairs = {r['request_id'] for r in capture['mismatches']}
    usable, excluded = [], []
    for key in sorted(requests | repairs):
        if key not in source_by_id:
            excluded.append({'request_id': key, 'reason': 'SAMPLED_SOURCE_UNAVAILABLE',
                'queue_state': capture['runs']['example_playlist_batches_v1']['states'][key]['state']})
            continue
        source = source_by_id[key]
        require(file_hash(root / source['source_path']) == source['actual_source_sha256'], 'retained source changed')
        usable.append({'request_id': key, 'stable_track_id': source['result']['representation']['stable_track_id'],
            'source_path': source['source_path'], 'source_sha256': source['actual_source_sha256'],
            'title': tracks[key]['title'], 'artists': tracks[key]['artists'],
            'prior_representation': source['result']['representation'], 'repair_required': key in repairs,
            'in_sample': key in requests, 'purge_group': next(r['purge_group'] for r in audit['feature_rows'] if r['request_id'] == key)})
    settings = {
        'schema': 'owner-authorized-playlist-development-v1', 'status': 'FROZEN_DEVELOPMENT_PLAN',
        'owner_authorization': 'what are the stael cache links? also the two fixed samples can be whatever you decide Im not too particular can you run steps 1-4?',
        'scope': 'Small personal development experiment; not a source-cleared formal confirmation or production activation.',
        'source_use_documentation': 'PENDING_OWNER_REPORTS_NO_LICENSE',
        'development_exception': 'Owner explicitly requests execution after the source-use gap was reported. Preserve pending status; do not assert legal clearance.',
        'formal_confirmation': False, 'production_activation': False, 'lockbox': None,
        'source_audit_sha256': file_hash(root / AUDIT / 'audit.private.json'),
        'tracks': usable, 'playlists': playlists, 'exclusions': excluded,
        'source_clusters': plans['cluster_map'],
        'sampling': 'Keep audited whole-source hash samples; no replacements for unavailable samples. Repair both named stale links even if outside sample.',
        'minimum_samples': 'Development exception: retain sampled playlists below 30 after documented attrition; at least 20 required.',
        'outer_folds': 3, 'inner_folds': 2, 'split_seed': 'calibration-development-v1',
        'mask_repetitions': 8, 'bootstrap_draws': 2000, 'bootstrap_seed': 1701,
        'grid': {'rho': [i/10 for i in range(11)], 'w_c': [0,.005,.010,.020,.035,.050,.075,.100],
                 'eta': [0,.25,.5,.75,1], 'representations': ['centered30_v1','method_c_full_song']},
        'recall_comparator': 'same representation/rho/audio base with genre coefficients zero; tolerance .02',
        'selection': 'existing one-SE simplicity policy; selection inside inner folds only',
        'genre': 'unchanged frozen free-genre point prompt, gemini-3.8-flash LOW, existing canonical-first residual mapper',
        'gemini_run_cap_usd': '5', 'gemini_attempt_cap': len(usable), 'automatic_retries': 0,
        'audio_device': 'cpu', 'audio_threads': 2,
        'no_downloads': True,
    }
    freeze_json(run / 'plan.private.json', settings)
    return settings


def load(root):
    return json.loads((root / RUN / 'plan.private.json').read_text())
