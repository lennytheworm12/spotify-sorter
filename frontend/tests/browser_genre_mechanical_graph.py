"""Compare browser worker coordinates to independently invoked adjusted layouts."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:5174')
parser.add_argument('--qa', type=Path, required=True)
args = parser.parse_args()
expected = json.loads((args.qa / 'expected_graphs.json').read_text())
failures, errors, checks = [], [], []
with sync_playwright() as pw:
    browser = pw.chromium.launch(args=['--enable-webgl', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport={'width': 1500, 'height': 1000})
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(args.url + '/#/genre', wait_until='networkidle')
    expect(page.get_by_role('heading', name='All 99 neighbors')).to_be_visible()
    for layout in expected['layouts']:
        settings = layout['settings']
        page.get_by_label('Genre source', exact=True).select_option(settings['genreMode'])
        page.get_by_label('Force mode', exact=True).select_option(settings['forceMode'])
        page.get_by_role('slider', name='Genre strength alpha').focus()
        page.keyboard.press('End')
        page.get_by_label('Move graph', exact=True).check()
        expect(page.get_by_text('Temporary adjusted layout', exact=True)).to_be_visible(timeout=30000)
        actual = json.loads(page.locator('.gf-map').get_attribute('data-coordinate-signature'))
        for wanted, observed in zip(layout['coordinates'], actual, strict=True):
            if wanted != observed:
                failures.append({'scenario': layout['id'], 'track': wanted[0], 'expected': wanted, 'actual': observed})
        checks.append({'scenario': layout['id'], 'tracks': len(actual), 'exact_adjusted_coordinates': actual == layout['coordinates']})
        page.get_by_label('Move graph', exact=True).uncheck()
    browser.close()
result = {'status': 'FAIL' if failures or errors else 'PASS', 'checks': checks, 'failures': failures, 'browser_errors': errors}
path = args.qa / 'browser_graph_correspondence.json'
text = json.dumps(result, indent=2, sort_keys=True) + '\n'
if path.exists():
    assert path.read_text() == text, 'Browser graph correspondence replay differs'
else:
    path.write_text(text)
print(json.dumps(result))
raise SystemExit(0 if result['status'] == 'PASS' else 1)
