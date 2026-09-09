"""Deterministic human-readable closeout from frozen style-band results."""
from pathlib import Path
import csv
import io

from .stage5e3_artifacts import read, freeze, freeze_json, hashes, verify_hashes, digest
from .style_band_experiment import RUN
from .style_band_metrics import correction_summary, key


def ci(value):
    if value['point'] is None:
        return 'not estimable'
    return f"{value['point']:.4f} [{value['low']:.4f}, {value['high']:.4f}]"


def csv_bytes(rows, columns):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def report(root):
    run = root / RUN
    verify_hashes(root, read(run / 'input_hashes.json'))
    result = read(run / 'results.json')
    config = read(run / 'protocol.json')
    tracks = {t['spotify_track_id']: t for t in read(run / 'tracks.json')}
    bands = read(run / 'track_bands.json')
    pairs = {key(*p['tracks']): p for p in read(run / 'pair_results.json')}
    events = read(run / 'preference_changes.json')
    rows = []
    for event in events:
        if event['transition'] == 'unchanged':
            continue
        row = dict(event)
        for role in ('anchor', 'preferred', 'other'):
            track = tracks[row[role]]
            row[role + '_title'] = track['title']
            row[role + '_artist'] = track['artist_credit']
        for role in ('preferred', 'other'):
            pair = pairs[key(row['anchor'], row[role])]
            for field in ('C', 'adjusted_C', 'band_distance', 'rating'):
                row[role + '_' + field] = pair[field]
        rows.append(row)
    columns = ['fold', 'anchor', 'anchor_title', 'anchor_artist', 'preferred', 'preferred_title', 'preferred_artist',
               'other', 'other_title', 'other_artist', 'gap', 'before', 'after', 'delta', 'good_bad', 'transition']
    columns += [role + '_' + field for role in ('preferred', 'other') for field in ('C', 'adjusted_C', 'band_distance', 'rating')]
    freeze(run / 'changed_orderings.csv', csv_bytes(rows, columns))
    top_summary = {}
    for name in ('top5_grouped', 'top5_all_candidates_diagnostic'):
        top = read(run / (name + '.json'))
        summary = {}
        for transition in ('kept', 'added', 'removed'):
            for label in ('bad', 'middle', 'good', 'unknown'):
                selected = [r for r in top if r['transition'] == transition and (
                    'unknown' if r['rating'] is None else 'bad' if r['rating'] <= 2 else 'good' if r['rating'] >= 4 else 'middle') == label]
                summary[transition + '_' + label] = {'directed': len(selected), 'unique_pairs': len({key(r['anchor'], r['candidate']) for r in selected})}
        top_summary[name] = summary
    freeze_json(run / 'top5_summary.json', top_summary)
    region_events = {field: {name: correction_summary([r for r in events if bands[r['anchor']][field] == name])
                            for name in sorted({b[field] for b in bands.values()})} for field in ('band', 'parent')}
    freeze_json(run / 'region_corrections.json', region_events)
    lines = ['# Coarse hierarchical style-band prior on frozen CLAP C', '',
             f"Outcome: **{result['decision']['outcome']}**. Development-only; no production activation.", '',
             'This tests one predefined taxonomy and one bounded soft-penalty family. It does not test all possible style priors, '
             'and previously inspected ratings do not constitute fresh confirmation.', '',
             '## Inputs and protocol', '',
             f"100 frozen tracks; 419 existing playlist-compatibility pairs (55 bad, 113 middle, 251 good). "
             f"The exact grouped evaluation contains {result['preferences']} strict preferences over {result['anchors']} anchors. "
             'Holistic ratings and taxonomy-review answers were not used as extra training labels.', '',
             f"Configuration SHA-256: `{digest(config)}`. `input_hashes.json` locks every implementation/configuration and protected input; "
             '`mapping.json` lists all 400 exact style assignments. `band_features.npz` retains raw masses, band/parent profiles, '
             'known-signal fractions, distance, identities and unchanged C scores.', '',
             'Thirteen informative bands plus unknown; eight parent neighborhoods. Sum raw full-track sigmoid means through the '
             'fixed mapping, smooth informative band masses by 1e-8, normalize, and sum into parents. '
             'Distance = known fractions × (half band JS + half parent JS), in bits. '
             '`adjusted C = C - lambda * distance`; no hard rejection. Multi-label mass is not calibrated genre probability; '
             'correlated tag counts can bias the aggregation.', '',
             '## Grouped ranking agreement', '', '| Method | Anchor-macro agreement, descriptive 95% interval |', '| --- | --- |']
    for name in ('C', 'band', 'raw_style_control'):
        lines.append(f"| {name} | {ci(result['performance'][name])} |")
    lines += ['', f"Band-minus-C paired delta: **{ci(result['paired_delta'])}**. Artist/source-cluster sensitivity: "
              f"{ci(result['clustered_paired_delta'])}, {result['clustered_paired_delta']['groups']} connected groups.", '',
              f"Strong-preference delta: {ci(result['strong_delta'])}. Diagnostic-artist exclusion delta: "
              f"{ci(result['exclude_diagnostic_artists_delta'])}. Neither sensitivity refits the selected lambdas.", '',
              '| Fold | Selected band lambda | Raw-style control lambda | C held-out | Band held-out |', '| --- | --- | --- | --- | --- |']
    for fold in result['folds']:
        lines.append(f"| {fold['fold']} | {fold['lambda']} | {fold['raw_control_lambda']} | {fold['metrics']['C']['macro']:.4f} | {fold['metrics']['band']['macro']:.4f} |")
    lines += ['', 'Selection uses only training preferences on tracks disjoint from that fold’s evaluation tracks, including credited '
              'artist and source/video groups. Grid: 0, .025, .05, .10; smallest maximizing strength wins. All training grid scores '
              'and per-anchor evaluation scores are in `results.json`. No taxonomy or strength was changed after inspecting results.', '',
              '## Corrections and damage', '']
    summary = result['corrections']
    lines += [f"Among {summary['good_bad_constraints']} good-versus-bad preferences, C had {summary['baseline_strict_errors']} strict errors "
              f"and {summary['baseline_strict_correct']} strict correct orderings. The prior strictly corrected **{summary['corrected_orderings']}** "
              f"orderings involving **{summary['corrected_unique_pairs']} unique bad pairs**, and broke **{summary['broken_orderings']}** "
              f"orderings involving **{summary['broken_unique_pairs']} unique good pairs**. "
              f"There were {summary['good_bad_tie_changes']} tie transitions. Net good/bad ranking credit: {summary['good_bad_net_credit']:+g}.", '',
              'These are observed relative-order changes, not playlist admission decisions. A unique pair can be affected in multiple '
              'anchor comparisons. `changed_orderings.csv` identifies every changed ordering with song titles, artists, ratings and '
              'before/after scores; `preference_changes.json` also includes unchanged orderings.', '',
              '| Top-5 scope | Removed bad | Removed good | Added good | Added bad | Added unknown |', '| --- | --- | --- | --- | --- | --- |']
    for scope, counts in top_summary.items():
        cells = [str(counts[name]['directed']) for name in ('removed_bad', 'removed_good', 'added_good', 'added_bad', 'added_unknown')]
        lines.append('| ' + scope + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', 'Top-5 counts above are directed query/candidate slots; `top5_summary.json` also provides global pair deduplication '
              'and all good/middle/bad/unknown kept/added/removed categories. Grouped candidate pools contain only held-out tracks. '
              'The all-candidate diagnostic includes training candidates and is not held-out generalization evidence. '
              'Removing a bad match does not establish benefit when its replacement is unknown.', '',
              '## Breadth and complementary signal', '',
              '| Dominant predicted parent | Anchors | Paired delta, 95% interval | Corrected / broken good-bad orderings |', '| --- | --- | --- | --- |']
    for name, region in result['parent_breakdown'].items():
        counts = region_events['parent'][name]
        lines.append(f"| {name} | {region['anchors']} | {ci(region['delta'])} | {counts['corrected_orderings']} / {counts['broken_orderings']} |")
    lines += ['', 'The same breakdown at fine band resolution is in `results.json`, with correction counts in `region_corrections.json`. '
              'These regions are classifier-derived, not verified genres. Empty or tiny regions cannot demonstrate broad generalization.', '',
              '| Distance signal | All-pair good/bad macro AUC | Within C cosine .05 caliper | Either-direction C Top-5 |', '| --- | --- | --- | --- |']
    for name, diagnostics in result['distance_diagnostics_all_development'].items():
        lines.append('| ' + name + ' | ' + ' | '.join(ci(diagnostics[k]['macro_auc']) for k in ('all', 'C_caliper', 'either_direction_C_top5')) + ' |')
    lines += ['', 'Caliper and Top-5 diagnostics test whether distance distinguishes good/bad pairs in similar C-score neighborhoods. '
              'They are descriptive, may involve few anchors, and cannot override the grouped ranking verdict.', '',
              '## Frozen decision and next step', '']
    for name, passed in result['decision']['checks'].items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    lines += ['', f"Largest eligible parent: `{result['decision']['largest_parent_region']}`; excluding it gives "
              f"{ci(result['decision']['without_largest_parent_delta'])}.", '']
    if result['decision']['outcome'].startswith('COMPLEMENTARY'):
        lines.append('The smallest justified next experiment is one prospectively frozen evaluation of this same soft prior, '
                     'with independent playlist-compatibility supervision and explicit good-match damage accounting. Do not activate it.')
    else:
        lines.append('Close this coarse genre-band shortcut as not established. Return to the learned playlist-compatibility scorer / '
                     'supervision path: first audit grouped-data sufficiency for frozen CLAP C and the actual playlist rubric, then '
                     'design one small regularized scorer if evidence permits. Do not expand taxonomy rules or retune this result.')
    lines += ['', '## Verification and limitations', '',
              '100 existing cached track outputs (18,823 classifier patches) were validated and reused; **zero new audio inference**. '
              '`replay.json` records exact-byte replay of seven numerical/analysis artifacts. Historical source and artifact hashes '
              'are checked before execution and on replay. No historical verdict, representation, rating or ledger is overwritten.', '',
              '`validation.json` records actual focused/full-suite results and any publication-dependent check timing. '
              '`artifact_manifest.json` covers all final artifacts except itself; verify it with the canonical `verify_hashes` helper. '
              'Commands and complete frozen interpretation rules are in `docs/style_band_prior.md`.', '',
              'Limits: one reviewer, sparse candidate-union-selected ratings, reused development folds, small correlated evaluation '
              'groups, approximate musically authored hierarchy, uncalibrated style outputs, and classifier-derived regions. '
              'Neither success nor failure establishes universal human perception or fresh test-set performance.', '']
    freeze(run / 'report.md', '\n'.join(lines).encode())
    freeze_json(run / 'decision.json', result['decision'])


def manifest(root):
    run = root / RUN
    verify_hashes(root, read(run / 'input_hashes.json'))
    required = ['report.md', 'replay.json', 'validation.json', 'decision.json', 'changed_orderings.csv']
    if any(not (run / name).is_file() for name in required):
        raise ValueError('closeout artifacts missing')
    freeze_json(run / 'artifact_manifest.json', hashes([p for p in run.iterdir() if p.name != 'artifact_manifest.json'], run))
    verify_hashes(run, read(run / 'artifact_manifest.json'))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['report', 'manifest'])
    args = parser.parse_args()
    {'report': report, 'manifest': manifest}[args.command](Path.cwd())
