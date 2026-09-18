"""Read-only Chromium checks. Run with the ML venv against the configured Vite bridge.
Usage: python frontend/tests/browser_song_space.py --output /tmp/song-space-browser
Screenshots contain the local library; keep the output directory out of Git.
"""
import argparse
import json
import time
from io import BytesIO
from PIL import Image
from pathlib import Path
from playwright.sync_api import sync_playwright, expect, TimeoutError

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:5173')
parser.add_argument('--output', type=Path, default=Path('/tmp/song-space-browser'))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
checks = []

def check(name, condition=True):
    assert condition, name
    checks.append(name)
    print('PASS', name, flush=True)

def upload(page, data):
    page.locator('input[type=file]').set_input_files({'name': 'test-map.json', 'mimeType': 'application/json', 'buffer': json.dumps(data).encode()})

def fixture():
    return {'schemaVersion': 'song-space-v1', 'id': 'browser-fixture', 'name': 'Synthetic browser fixture', 'description': 'Isolated UI test, no human labels',
            'scorer': {'id': 'test-distance', 'label': 'Test distance', 'description': 'Lower means closer', 'scoreRange': [0, 10], 'higherIsCloser': False},
            'neighborhoodSize': 2, 'communities': [{'id': 'one', 'label': 'First area'}, {'id': 'two', 'label': 'Second area'}],
            'songs': [{'id': 'a', 'title': 'Alpha', 'artists': ['One'], 'community': 'one', 'x': 0, 'y': 0},
                      {'id': 'b', 'title': 'Beta', 'artists': ['Two'], 'community': 'one', 'x': 10, 'y': 10},
                      {'id': 'c', 'title': 'Gamma', 'artists': ['Three'], 'community': 'two', 'x': 30, 'y': 0}],
            'links': [{'source': 'a', 'target': 'b', 'score': 1, 'sourceRank': 1, 'targetRank': 1},
                      {'source': 'a', 'target': 'c', 'score': 5, 'sourceRank': 2, 'targetRank': 1}]}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
    errors, mutations, responses = [], [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: mutations.append(r.url) if r.method not in ['GET', 'HEAD'] else None)
    page.on('response', lambda r: responses.append((r.url, r.status, r.headers)))
    started = time.monotonic()
    page.goto(args.url)
    try:
        page.wait_for_load_state('networkidle', timeout=5000)
    except TimeoutError:
        pass  # Vite worker/HMR can prevent networkidle; the rendered graph is the readiness gate.
    page.locator('.space-renderer canvas').first.wait_for(timeout=65000)
    check('actual library graph loads')
    load_seconds = time.monotonic() - started
    library = page.request.get(args.url + '/__song-space/data/library').json()
    check('complete 1257-track cached library', len(library['songs']) == 1257)
    check('rendered library count', '1,257 songs' in page.locator('.space-sidebar-intro').inner_text())
    page.screenshot(path=str(args.output / 'desktop.png'))
    page.get_by_role('tab', name='Songs', exact=True).click()
    check('song list starts with bounded rendering', page.locator('.space-song-list li').count() == 200)
    page.get_by_role('button', name='Show more songs', exact=False).click()
    check('all songs remain reachable through list pagination', page.locator('.space-song-list li').count() == 400)
    search = page.get_by_role('textbox', name='Find a song or artist')
    search.fill('Wet Dreamz'); search.press('Enter')
    expect(page.get_by_role('heading', name='Wet Dreamz', exact=True)).to_be_visible()
    check('search and keyboard selection')
    song = next(s for s in library['songs'] if s['title'] == 'Wet Dreamz')
    neighbors = sorted([(e['sourceRank'] if e['source'] == song['id'] else e['targetRank'], e['score']) for e in library['links'] if song['id'] in [e['source'], e['target']] and (e['sourceRank'] if e['source'] == song['id'] else e['targetRank']) is not None])
    check('displayed ranked scores exactly match snapshot', page.locator('.space-score').all_text_contents() == [f'{score:.3f}' for _, score in neighbors])
    page.get_by_role('button', name='Locate song', exact=True).click()
    page.screenshot(path=str(args.output / 'selected.png'))
    audio = page.locator('audio')
    audio.evaluate('(a) => a.play()')
    page.wait_for_function('document.querySelector("audio").currentTime > 0.1')
    audio.evaluate('(a) => { a.currentTime = 60 }')
    page.wait_for_function('document.querySelector("audio").currentTime >= 60 && !document.querySelector("audio").seeking')
    check('Chromium audio plays and seeks to 60 seconds')
    audio.evaluate('(a) => a.pause()')
    response = page.request.get(args.url + song['audioUrl'], headers={'Range': 'bytes=1024-2047'})
    check('HTTP Range returns exact bytes', response.status == 206 and len(response.body()) == 1024 and response.headers['content-range'].startswith('bytes 1024-2047/'))
    check('invalid Range is explicit 416', page.request.get(args.url + song['audioUrl'], headers={'Range': 'bytes=999999999999-'}).status == 416)
    check('cross-origin local bridge denied', page.request.get(args.url + '/__song-space/catalog', headers={'Origin': 'https://example.com'}).status == 403)
    check('malformed origin handled', page.request.get(args.url + '/__song-space/catalog', headers={'Origin': 'bad'}).status == 403)
    page.locator('.space-neighbors button').first.click()
    check('neighbor navigation', page.locator('.space-inspector h2').inner_text() != 'Wet Dreamz')
    page.get_by_role('button', name='Close inspector').click()
    page.get_by_role('tab', name='Areas', exact=True).click()
    page.locator('.space-communities button').first.click()
    check('community focus', page.locator('.space-filter-tag').count() == 1)
    page.get_by_role('checkbox', name='Bridges only').check()
    check('bridges mode clears incompatible area filter', page.locator('.space-filter-tag').count() == 0)
    page.locator('.space-communities button').first.click()
    check('area focus restores its internal connections', not page.get_by_role('checkbox', name='Bridges only').is_checked())
    page.get_by_role('button', name='Show all communities').click()
    page.get_by_role('tab', name='Bridges', exact=True).click()
    page.locator('.space-bridge-list button').first.click()
    expect(page.get_by_role('complementary', name='Connection details')).to_be_visible()
    check('bridge inspection and exact connection details')
    page.get_by_role('checkbox', name='Bridges only').check()
    page.get_by_role('button', name='Locate connection', exact=True).click()
    page.screenshot(path=str(args.output / 'bridge.png'))
    page.get_by_role('button', name='Close inspector').click()
    page.get_by_role('combobox', name='Map source').select_option('clap-c')
    expect(page.locator('.space-sidebar-intro')).to_contain_text('100 songs', timeout=65000)
    check('frozen full-song C is distinct and has 100 songs')
    page.screenshot(path=str(args.output / 'frozen-c.png'))
    page.set_viewport_size({'width': 390, 'height': 844})
    page.get_by_role('button', name='Browse songs', exact=False).click()
    search.fill('Wet Dreamz'); search.press('Enter')
    expect(page.get_by_role('heading', name='Wet Dreamz', exact=True)).to_be_visible()
    check('mobile inspector and accessible search')
    check('no horizontal mobile overflow', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
    page.screenshot(path=str(args.output / 'mobile-selected.png'))
    page.get_by_role('button', name='Locate song', exact=True).click()
    page.get_by_role('button', name='Close inspector').click()
    page.screenshot(path=str(args.output / 'mobile-map.png'))
    page.set_viewport_size({'width': 1440, 'height': 1000})
    upload(page, fixture())
    expect(page.locator('.space-sidebar-intro')).to_contain_text('3 songs', timeout=65000)
    # Find the unique second-community node in the actual rendered pixels,
    # then click/hover it through Chromium rather than invoking internal handlers.
    viewport = page.locator('.space-viewport')
    img = Image.open(BytesIO(viewport.screenshot())).convert('RGB')
    pixels = [(x, y) for y in range(img.height) for x in range(img.width) if img.getpixel((x, y)) == (179, 162, 213)]
    assert pixels, 'Second-community node must be rendered'
    x = sum(a for a, _ in pixels) / len(pixels)
    y = sum(b for _, b in pixels) / len(pixels)
    box = viewport.bounding_box()
    page.mouse.move(box['x'] + x, box['y'] + y)
    expect(page.locator('.space-tooltip')).to_contain_text('Gamma')
    page.mouse.click(box['x'] + x, box['y'] + y)
    expect(page.get_by_role('heading', name='Gamma', exact=True)).to_be_visible()
    check('real WebGL node hover and click select the correct song')
    page.get_by_role('button', name='Close inspector').click()
    page.emulate_media(reduced_motion='reduce')
    before = viewport.screenshot()
    page.get_by_role('button', name='Zoom in', exact=True).click()
    assert viewport.screenshot() != before
    page.get_by_role('button', name='Fit entire map', exact=True).click()
    viewport.focus(); viewport.press('+'); viewport.press('Home')
    check('zoom, reset and keyboard controls with reduced motion')
    page.emulate_media(reduced_motion='no-preference')
    search.fill('Alpha'); search.press('Enter')
    expect(page.locator('.space-inspector')).to_contain_text('lower is closer')
    check('local import preserves non-CLAP score direction and supplied communities')
    page.screenshot(path=str(args.output / 'synthetic.png'))
    revised = fixture(); revised['songs'][0]['title'] = 'Updated Alpha'
    upload(page, revised)
    search.fill('Updated'); search.press('Enter')
    expect(page.get_by_role('heading', name='Updated Alpha', exact=True)).to_be_visible()
    check('same-ID reimport replaces stale layout')
    invalid = fixture(); invalid['songs'].append(invalid['songs'][0])
    upload(page, invalid)
    expect(page.get_by_role('alert')).to_contain_text('Duplicate song ID')
    check('invalid import retains current map')
    page.get_by_role('button', name='Dismiss import error').click()
    empty=fixture(); empty['songs']=[]; empty['links']=[]
    upload(page, empty)
    expect(page.get_by_role('heading', name='This map has no songs yet')).to_be_visible()
    check('empty snapshot state')
    page.route('**/__song-space/data/library', lambda route: route.fulfill(status=503, body='Unavailable'))
    page.reload()
    expect(page.get_by_role('heading', name='This map couldn’t be opened')).to_be_visible()
    check('source failure is explicit')
    page.unroute('**/__song-space/data/library')
    page.get_by_role('button', name='Try again').click()
    expect(page.locator('.space-sidebar-intro')).to_contain_text('1,257 songs', timeout=65000)
    check('retry recovers source')
    page.route('**/auth/me', lambda route: route.fulfill(status=401, content_type='application/json', body='{"message":"Not connected"}'))
    page.get_by_role('link', name='Organizer', exact=False).click()
    expect(page.get_by_role('heading', name='Spotify Playlist Organizer')).to_be_visible()
    page.get_by_role('link', name='Back to song space', exact=False).click()
    expect(page.locator('.space-sidebar-intro')).to_contain_text('1,257 songs', timeout=65000)
    check('existing organizer and return navigation preserved')
    # Independent pages use synthetic snapshots to exercise exceptional states.
    fallback = browser.new_page()
    fallback.add_init_script("""const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function(type, ...args) {
        return type.includes('webgl') ? null : original.call(this, type, ...args);
      };""")
    fallback.route('**/__song-space/data/library', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps(fixture())))
    fallback.goto(args.url)
    expect(fallback.get_by_role('alert')).to_contain_text('The graph needs WebGL', timeout=30000)
    fallback.get_by_role('textbox', name='Find a song or artist').fill('Alpha')
    fallback.get_by_role('textbox', name='Find a song or artist').press('Enter')
    expect(fallback.get_by_role('heading', name='Alpha', exact=True)).to_be_visible()
    check('WebGL failure preserves usable song-list inspection')
    fallback.close()
    blank = browser.new_page()
    blank.route('**/__song-space/catalog', lambda route: route.fulfill(status=200, content_type='application/json', body='[]'))
    blank.goto(args.url)
    expect(blank.get_by_role('button', name='Open a local map', exact=True)).to_be_visible()
    check('unconfigured provider offers file import')
    blank.close()
    check('no uncaught browser errors', not errors)
    check('no review or Spotify mutations', not mutations)
    summary={'checks':checks,'count':len(checks),'initial_load_seconds':round(load_seconds,2),'page_errors':errors,'mutations':mutations,'browser_audio_partial_responses':sum(1 for url,status,_ in responses if '/audio/' in url and status==206)}
    (args.output/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    browser.close()
