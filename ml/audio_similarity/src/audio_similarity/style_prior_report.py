"""Produce readable pilot evidence without changing frozen analysis rules."""
from pathlib import Path
from .stage5e3_artifacts import read, freeze, freeze_json, hashes, verify_hashes
from .style_prior import RUN


def format_interval(value):
    if value['point'] is None:
        return 'not estimable'
    return f"{value['point']:.3f} [{value['low']:.3f}, {value['high']:.3f}]"


def main(root):
    run = root / RUN
    verify_hashes(root, read(run / 'input_hashes.json'))
    result = read(run / 'results.json')
    config = read(run / 'protocol.json')
    tracks = {t['spotify_track_id']: t for t in read(run / 'tracks.json')}
    rows = [p for p in read(run / 'pair_results.json') if p['rubric'] == 'playlist']
    def label(pair):
        return ' / '.join(tracks[t]['title'].replace('|', '/') for t in pair['tracks'])
    def table(pairs):
        lines = ['| Pair | Human | D cosine | C cosine | Style distance |', '|---|---:|---:|---:|---:|']
        lines += [f"| {label(p)} | {p['rating']}/5 | {p['D_cosine']:.3f} | {p['C_cosine']:.3f} | {p['style_distance']:.3f} |" for p in pairs]
        return '\n'.join(lines)
    high_good = sorted((p for p in rows if p['rating'] >= 4), key=lambda p: (-p['style_distance'], p['pair_id']))[:10]
    low_bad = sorted((p for p in rows if p['rating'] <= 2), key=lambda p: (p['style_distance'], p['pair_id']))[:10]
    controls = [('sit around', 'risk'), ('m o v i e', 'uncertainty'), ('heart', '2080'), ('ever2late', 'the peace'),
                ('wet dreamz', 'sit around'), ('wet dreamz', 'cloudy thoughts'), ('shoota', 'stay with me'), ('boys dont cry', 'sit around')]
    diagnostics = []
    for first, second in controls:
        candidates = [p for p in rows if any(first in tracks[a]['title'].casefold() and second in tracks[b]['title'].casefold() for a, b in [p['tracks'], p['tracks'][::-1]])]
        diagnostics.extend(candidates)
    if not result['signal_gate_passes']:
        diagnosis = 'STYLE_SIGNAL_NOT_ESTABLISHED'
        next_step = 'Inspect a small blinded sample of classifier profiles against human descriptions before changing the distance rule or collecting more similarity labels. This outcome does not establish that musical style itself is unhelpful.'
    else:
        cv = result['penalty']['D']
        delta = cv.get('paired_anchor_delta', {})
        if delta.get('point') is not None and delta['point'] >= config['material_improvement'] and delta['low'] > 0:
            diagnosis = 'SOFT_PRIOR_PROMISING_DEVELOPMENT_ONLY'
            next_step = 'Use a small blinded new-pair review to test predicted improvements and accepted-match damage before any larger reranker experiment. Do not tune using the named examples.'
        else:
            diagnosis = 'STYLE_OBSERVABLE_RERANKING_NOT_ESTABLISHED'
            next_step = 'Review a bounded set of high-distance accepted matches and low-distance rejected matches to identify whether the detector is wrong or the musical difference is acceptable. Do not promote a penalty from overall separation alone.'
    lines = ['# Dedicated style prior pilot', '', f'**Diagnosis: {diagnosis}.**', '', next_step, '',
             'This is a single-reviewer development experiment on previously exposed frozen evidence. No production winner or independent confirmatory result is declared.', '',
             '## Signal separation', '', 'AUC asks whether a rejected pair has a larger style distance than an accepted pair sharing its anchor. Chance is 0.5. Intervals are descriptive anchor bootstraps; shared candidates limit their independence.', '',
             '| Rubric / slice | Anchors | AUC [95% interval] |', '|---|---:|---:|']
    for rubric in ('playlist', 'holistic'):
        for key in ('all', 'high_D_top10', 'cosine_caliper', 'exclude_diagnostic_artists', 'C_cosine_caliper'):
            value = result[rubric][key]
            lines.append(f"| {rubric} / {key} | {value['anchors']} | {format_interval(value['macro_auc'])} |")
    lines += ['', f"Frozen signal gate passed: **{result['signal_gate_passes']}**.", '', '## Conditional penalty', '']
    if result['signal_gate_passes']:
        for baseline in ('D', 'C'):
            cv = result['penalty'][baseline]
            lines += [f"### {baseline} {'primary' if baseline == 'D' else 'sensitivity'}", '', f"Status: {cv['status']}.", '']
            if 'folds' not in cv:
                continue
            lines += ['| Fold | Lambda | Training accuracy | Baseline held-out | Penalty held-out | Preferences / anchors |', '|---|---:|---:|---:|---:|---:|']
            for f in cv['folds']:
                lines.append(f"| {f['fold']} | {f['lambda']} | {f['training']['macro']:.3f} | {f['baseline']['macro']:.3f} | {f['penalty']['macro']:.3f} | {f['baseline']['preferences']} / {f['baseline']['anchors']} |")
            lines += ['', f"Paired held-out anchor-macro change: {format_interval(cv['paired_anchor_delta'])}.", '']
    else:
        lines += ['Not run: the predeclared signal gate failed. No lambda was fitted.', '']
    lines += ['## Known diagnostic pairs', '', 'These influenced the research direction and are not untouched validation. A difference can coexist with a valid 4/5 match. Exact D and C differ substantially for some controls.', '', table(diagnostics), '',
              '## Accepted matches with largest style distance', '', table(high_good), '',
              '## Rejected matches with smallest style distance', '', table(low_bad), '',
              '## Reproduction and limitations', '',
              'See `docs/style_prior_pilot.md` for exact commands and the engineering decoding amendment. Raw patch sigmoid arrays are in the content-addressed local cache; raw song means, normalized distributions, all rated-pair results, extractor identity, folds and protocol accompany this report.', '',
              'There is one fixed 400-style classifier and one fixed distance. No similarity model was trained. The normalized sigmoid distribution is a comparison device, not a calibrated probability of mutually exclusive styles. Unknown pretraining overlap, one reviewer, small artist folds and purposefully selected historical neighbors limit generalization claims. A positive global AUC does not prove incremental ranking value or causal identity recognition.', '',
              'Execution counts, test results and historical-integrity checks are recorded in `verification.json`. The manifest hashes every final report artifact. Existing CLAP/MuQ/fusion, human labels, historical verdicts and production behavior remain unchanged.', '']
    freeze(run / 'report.md', '\n'.join(lines).encode())
    freeze_json(run / 'diagnosis.json', {'diagnosis': diagnosis, 'next_step': next_step, 'production_activated': False, 'new_human_judgments': 0})
    freeze_json(run / 'counterexamples.json', {'accepted_high_distance': high_good, 'rejected_low_distance': low_bad, 'known_development_diagnostics': diagnostics})
    print(diagnosis)


if __name__ == '__main__':
    main(Path.cwd())
