"""Check every displayed frozen-100 pair against the independent numeric oracle."""
import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dev'))
from genre_mechanical_audit import reference_pairs, reference_score, read, digest, freeze


def fixed(value, places=6):
    # JS toFixed rounds the IEEE754 value; -0 prints as 0. Numeric equality and
    # reconstruction are checked at full precision separately by the oracle.
    if value == 0:
        value = 0
    return str(Decimal.from_float(float(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def run(url, source, qa, output):
    packet = read(source / 'explorer.json')
    with urlopen(url + '/__song-space/genre/data') as response:
        assert json.load(response) == packet, 'Live packet differs from frozen source'
    expected = reference_pairs(packet)
    contract = read(qa / 'contract.json')
    scenarios = [s for s in contract['scenarios'] if ':alpha' in s['id']]
    manifest_files = list(read(source / 'artifact_manifest.json')['files']) + ['artifact_manifest.json']
    snapshot = lambda: {n: {'sha256': digest(source / n), 'mtime_ns': (source / n).stat().st_mtime_ns} for n in manifest_files}
    before = snapshot()
    failures, errors, writes = [], [], []
    row_checks = inspector_checks = topk_checks = 0
    graph_checks = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--enable-webgl', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        page = browser.new_page(viewport={'width': 1500, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        def readonly(route):
            request = route.request
            if request.method not in ('GET', 'HEAD') or not request.url.startswith(url + '/'):
                writes.append({'method': request.method, 'url': request.url})
                route.abort()
            else:
                route.continue_()
        page.route('**/*', readonly)
        page.goto(url + '/#/genre', wait_until='networkidle')
        expect(page.get_by_role('heading', name='All 99 neighbors')).to_be_visible()
        coordinates = page.locator('.gf-map').get_attribute('data-coordinate-signature')
        assert json.loads(coordinates) == [[s['id'], s['x'], s['y']] for s in packet['baseLayout']['songs']]
        for scenario in scenarios:
            settings = scenario['settings']
            page.get_by_label('Genre source', exact=True).select_option(settings['genreMode'])
            page.get_by_label('Force mode', exact=True).select_option(settings['forceMode'])
            page.get_by_role('slider', name='Genre strength alpha').focus()
            page.keyboard.press('Home' if settings['alpha'] == 0 else 'End')
            for song in packet['songs']:
                page.get_by_label('Genre anchor', exact=True).select_option(song['id'])
                expect(page.locator('.gf-anchor h2')).to_have_text(song['title'])
                relevant = {b if a == song['id'] else a: p for (a, b), p in expected.items() if song['id'] in (a, b)}
                original = sorted(relevant, key=lambda k: (-relevant[k]['audio'], k))
                ranks = {key: i + 1 for i, key in enumerate(original)}
                scores = {key: reference_score(value, settings) for key, value in relevant.items()}
                ordered = sorted(relevant, key=lambda key: (-scores[key]['adjusted'], key))
                actual = page.locator('.gf-ranking tbody tr').evaluate_all('(rows) => rows.map(r => ({id:r.dataset.songId,cells:Array.from(r.cells).slice(1).map(c=>c.innerText)}))')
                if [r['id'] for r in actual] != ordered:
                    failures.append({'check': 'display_order', 'anchor': song['id'], 'scenario': scenario['id'], 'expected': ordered, 'actual': [r['id'] for r in actual]})
                for index, row in enumerate(actual):
                    key = row['id']
                    score = scores[key]
                    cells = [fixed(relevant[key]['audio']), fixed(score['adjusted']),
                             f'{ranks[key]} → {ordered.index(key) + 1}',
                             ('+' if score['delta'] >= 0 else '') + fixed(score['delta']), fixed(score['genre'], 4)]
                    if row['cells'] != cells:
                        failures.append({'check': 'display_score_cells', 'pair': [song['id'], key], 'scenario': scenario['id'], 'expected': cells, 'actual': row['cells']})
                    row_checks += 1
                if settings['alpha'] == 0:
                    for k in (5, 10, 12, 20, 99):
                        if [r['id'] for r in actual[:k]] != original[:k]:
                            failures.append({'check': 'display_top_' + str(k), 'anchor': song['id'], 'scenario': scenario['id']})
                        topk_checks += 1
                key = ordered[0]
                pair, score = relevant[key], scores[key]
                facts = page.locator('.gf-facts div').evaluate_all('(rows)=>Object.fromEntries(rows.map(r=>[r.querySelector("dt").innerText,r.querySelector("dd").innerText]))')
                expected_facts = {'Original audio': fixed(pair['audio']), 'Adjusted score': fixed(score['adjusted']),
                                  'Original → adjusted rank': f'{ranks[key]} → 1',
                                  'Genre delta': ('+' if score['delta'] >= 0 else '') + fixed(score['delta']),
                                  'Jc': fixed(pair['jc']), 'Jnr': fixed(pair['jnr']),
                                  'Full-neighborhood J (diagnostic)': fixed(pair['jn']),
                                  'Final G': fixed(score['genre']), 'G_force': fixed(score['force'])}
                for field, value in expected_facts.items():
                    if facts.get(field) != value:
                        failures.append({'check': 'inspector_' + field, 'pair': [song['id'], key], 'scenario': scenario['id'], 'expected': value, 'actual': facts.get(field)})
                inspector_checks += 1
                if page.locator('.gf-map').get_attribute('data-coordinate-signature') != coordinates:
                    failures.append({'check': 'off_coordinates_changed', 'anchor': song['id'], 'scenario': scenario['id']})
            if settings['alpha'] == 1:
                move = page.get_by_label('Move graph', exact=True)
                move.check()
                expect(page.get_by_text('Temporary adjusted layout', exact=True)).to_be_visible(timeout=30000)
                first = page.locator('.gf-map').get_attribute('data-coordinate-signature')
                move.uncheck()
                restored = page.locator('.gf-map').get_attribute('data-coordinate-signature') == coordinates
                move.check()
                expect(page.get_by_text('Temporary adjusted layout', exact=True)).to_be_visible(timeout=30000)
                second = page.locator('.gf-map').get_attribute('data-coordinate-signature')
                move.uncheck()
                graph_checks.append({'scenario': scenario['id'], 'repeated_coordinates_exact': first == second, 'restored': restored})
                if first != second or not restored:
                    failures.append({'check': 'temporary_graph_replay_restore', 'scenario': scenario['id']})
            print(json.dumps({'scenario': scenario['id'], 'display_rows_checked': row_checks, 'failures': len(failures)}), flush=True)
        page.get_by_role('button', name='Reset to original settings', exact=True).click()
        page.screenshot(path=str(output / 'desktop.png'))
        browser.close()
    after = snapshot()
    if before != after:
        failures.append({'check': 'frozen_artifact_mutation', 'expected': before, 'actual': after})
    if errors or writes:
        failures.append({'check': 'browser_errors_or_nonlocal_write', 'errors': errors, 'requests': writes})
    freeze(output / 'failures_browser.json', failures)
    report = {'status': 'FAIL' if failures else 'PASS', 'url': url, 'packet_sha256': digest(source / 'explorer.json'),
              'scenarios': len(scenarios), 'directed_display_rows_checked': row_checks,
              'unordered_pairs_per_scenario': 4950, 'inspector_pairs_checked': inspector_checks,
              'alpha_zero_topk_checks': topk_checks, 'failure_count': len(failures),
              'display_precision': 'score/audio/delta/Jc/Jnr/G_force 6 decimals; table G 4 decimals; exact toFixed-equivalent strings checked against independent unrounded components',
              'rounded_display_values_are_not_full_precision_inputs': True,
              'graph_checks': graph_checks, 'frozen_before': before, 'frozen_after': after,
              'errors': errors, 'write_or_external_requests': writes}
    freeze(output / 'browser_checks.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:5174')
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--qa', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = run(args.url, args.run, args.qa, args.output)
    print(json.dumps({k: v for k, v in report.items() if not k.startswith('frozen_')}))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)
