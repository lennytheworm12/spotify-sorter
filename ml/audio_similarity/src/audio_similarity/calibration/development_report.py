"""Publish compact development evidence without audio or provider upload receipts."""
import csv
import gzip
import io
import json
from pathlib import Path

import numpy as np

from .contracts import file_hash, freeze_json, require
from .development_evaluation import bootstrap_weights
from .development_inputs import RUN, load
from .development_validation import usage
from .search import summaries

PUBLIC = 'reports/playlist_weight_calibration/v1/development_run'


def freeze_report_protocol(root):
    value = {'schema': 'development-report-protocol-v1', 'baseline': 'frozen_m3',
        'comparisons': 'Every predeclared arm versus fixed M3; descriptive paired outer-query deltas.',
        'bootstrap': 'Same 2000 curator/duplicate-cluster draws and seed 1701 as frozen search.',
        'decision': 'No outer-result model-family selection, no production winner, no threshold fitting.',
        'implementation_sha256': file_hash(Path(__file__))}
    freeze_json(root / RUN / 'report_protocol.json', value)
    return value


def publish(root):
    run, public, plan = root / RUN, root / PUBLIC, load(root)
    protocol = json.loads((run / 'report_protocol.json').read_text())
    require(protocol['implementation_sha256'] == file_hash(Path(__file__)), 'report implementation changed')
    result = json.loads((run / 'search/results.json').read_text())
    rows = result['arm_summaries']
    baseline = rows['frozen_m3']['summary']['per_query']
    keys = [r['query_id'] for r in baseline]
    comparisons = {}
    weights = bootstrap_weights(baseline, draws=plan['bootstrap_draws'], seed=plan['bootstrap_seed'])
    for arm, evidence in sorted(rows.items()):
        values = {r['query_id']: r for r in evidence['summary']['per_query']}
        require(set(values) == set(keys), 'outer comparison populations differ')
        delta_rows = [r | {k: values[r['query_id']][k]-r[k] for k in ('ndcg20','recall20','recall10')} for r in baseline]
        bootstrap = weights @ np.asarray([r['ndcg20'] for r in delta_rows]) if weights is not None else None
        comparisons[arm] = {'metrics': evidence['summary']['macro'], 'ndcg20_uncertainty': evidence['uncertainty'],
            'delta_vs_fixed_m3': summaries(delta_rows)['macro'],
            'paired_ndcg20_delta_interval95': [float(x) for x in np.quantile(bootstrap, [.025,.975])] if bootstrap is not None else None,
            'per_stratum': evidence['summary']['per_stratum'],
            'selected_by_outer_fold': [f['outer_estimates'][arm].get('model') for f in result['folds']]}
    calls = usage(root)
    audio = json.loads((run / 'audio_receipt.json').read_text())
    summary = {'status': result['status'], 'tracks': sum(t['in_sample'] for t in plan['tracks']),
        'playlists': len(plan['playlists']), 'independent_groups': len(set(plan['source_clusters'].values())),
        'excluded_sampled_requests': len(plan['exclusions']), 'gemini': calls,
        'audio': {k: v for k,v in audio.items() if k != 'files'}, 'comparisons': comparisons,
        'source_permission_status': 'PENDING', 'limitations': result['limitations'],
        'production_activation': False, 'suitability_status': 'LABELS_REQUIRED', 'strictness_status': 'NOT_CALIBRATED'}
    freeze_json(public / 'results.json', summary)
    # Preserve the full numeric search ledger in deterministic compressed JSON.
    ledgers = [json.loads((run / f'search/outer_{i}/inner/search_ledger.json').read_text()) for i in range(plan['outer_folds'])]
    raw = (json.dumps(ledgers, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
    compressed = gzip.compress(raw, mtime=0)
    target = public / 'inner_search_ledgers.json.gz'
    if target.exists():
        require(target.read_bytes() == compressed, 'public ledger replay differs')
    else:
        target.write_bytes(compressed)
    lines = ['# Development comparison closeout', '',
        f"Completed {summary['tracks']} songs across {summary['playlists']} playlists / {summary['independent_groups']} curator groups.",
        f"Gemini: {calls['generation_attempts']} new calls, ${calls['actual_cost_usd']}; one prior compatible profile reused.",
        '', 'These are grouped development estimates. They do not select a production winner or admission cutoff.', '',
        '| Predeclared procedure | NDCG@20 | Recall@20 | Recall@10 | NDCG delta vs M3 | Paired 95% interval |',
        '|---|---:|---:|---:|---:|---|']
    for arm, v in comparisons.items():
        m, interval = v['metrics'], v['paired_ndcg20_delta_interval95']
        ci = f"[{interval[0]:+.4f}, {interval[1]:+.4f}]" if interval else 'insufficient groups'
        lines.append(f"| {arm} | {m['ndcg20']:.4f} | {m['recall20']:.4f} | {m['recall10']:.4f} | {v['delta_vs_fixed_m3']['ndcg20']:+.4f} | {ci} |")
    lines += ['', 'Inspect `results.json` for each fold’s selected settings and per-stratum results. '
        '`inner_search_ledgers.json.gz` retains every configuration’s metrics and selection reasons.', '',
        'Limitations: small source-selected development sample; missing recordings are listed without replacements; '
        'source-use documentation remains pending; catalog nonmembers are unlabeled. No untouched lockbox, '
        'suitability calibration, or playlist writes were used. Repeated masks are not independent curators.', '']
    text = '\n'.join(lines).encode()
    report = public / 'REPORT.md'
    if report.exists():
        require(report.read_bytes() == text, 'public report replay differs')
    else:
        report.write_bytes(text)
    return summary
