"""Real Chromium checks. Refuses real state; all answers are disposable fixtures."""
import argparse
import csv
import io
import json
from pathlib import Path
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright, expect

csv.field_size_limit(1_048_576)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:8795')
parser.add_argument('--output-dir', required=True)
args = parser.parse_args()
url, output = args.url, Path(args.output_dir)
output.mkdir(parents=True, exist_ok=True)


def get(path):
    with urllib.request.urlopen(url + path) as response:
        return json.load(response)


assert get('/api/ping')['mode'] == 'gemini_style_disposable', 'Refusing to write test answers to the real owner review'
session = get('/api/session')
assert session['phase'] == 'listen' and session['listening_completed'] == 0 and session['total'] == 16
assert not any(key in json.dumps(session) for key in ('primary_family', 'primary_style', 'audio_evidence', 'original_c_similarity', 'human_playlist_rating'))
try:
    get('/api/profile/A01')
    raise AssertionError('Profile disclosed before independent pass')
except urllib.error.HTTPError as error:
    assert error.code == 409
request = urllib.request.Request(url + '/api/answer', data=b'{}', headers={'Content-Type': 'application/json', 'Origin': 'http://different-origin.invalid'})
try:
    urllib.request.urlopen(request)
    raise AssertionError('Cross-origin mutation accepted')
except urllib.error.HTTPError as error:
    assert error.code == 400
audio_url = url + session['tracks'][0]['audio_url']
for byte_range, status, size in [('bytes=0-63', 206, 64), ('bytes=-32', 206, 32)]:
    with urllib.request.urlopen(urllib.request.Request(audio_url, headers={'Range': byte_range})) as response:
        assert response.status == status and len(response.read()) == size
        assert response.headers['Content-Type'] == 'audio/flac'
try:
    urllib.request.urlopen(urllib.request.Request(audio_url, headers={'Range': 'bytes=999999999999-'}))
    raise AssertionError('Invalid range accepted')
except urllib.error.HTTPError as error:
    assert error.code == 416

errors, console_errors, expected_console_errors = [], [], []
intentional_failure = False
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1150, 'height': 1100}, accept_downloads=True)
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: (expected_console_errors if intentional_failure else console_errors).append(message.text) if message.type == 'error' else None)
    page.goto(url, wait_until='networkidle')
    expect(page.locator('#comparison')).to_be_hidden()
    expect(page.locator('#advance')).to_be_disabled()
    for i in range(16):
        page.locator('#jump').select_option(str(i))
        page.wait_for_function('()=>{const a=document.querySelector("#player");return a.readyState>=1&&a.duration>0}')
        duration = page.locator('#player').evaluate('(a)=>a.duration')
        assert abs(duration - session['tracks'][i]['duration_seconds']) < 0.1
    page.locator('#jump').select_option('0')
    page.wait_for_function('()=>document.querySelector("#player").readyState>=1')
    page.screenshot(path=str(output / 'desktop-listen.png'), full_page=True)
    page.locator('#player').click(position={'x': 20, 'y': 20})
    page.wait_for_function('()=>document.querySelector("#player").currentTime>0.15')
    page.locator('#player').evaluate('(a)=>{a.currentTime=45}')
    page.wait_for_function('()=>{const a=document.querySelector("#player");return !a.seeking&&a.currentTime>=44}')
    page.locator('#jump').select_option('1')
    assert page.locator('#player').evaluate('(a)=>a.paused')
    page.locator('#jump').select_option('0')
    page.locator('#identity [data-value="yes"]').click()
    note = 'SYNTHETIC BROWSER FIXTURE ONLY: commas, "quotes", and\na newline 音楽🎵.'
    page.locator('#owner_family_or_style_words').fill(note)
    expect(page.locator('#status')).to_have_text('Saved to disk.')
    page.reload(wait_until='networkidle');page.locator('#jump').select_option('0')
    expect(page.locator('#owner_family_or_style_words')).to_have_value(note)

    intentional_failure = True
    oversized = 'x' * 250_001
    page.locator('#owner_family_or_style_words').fill(oversized)
    expect(page.locator('#status')).to_contain_text('exceeds 250,000')
    expect(page.locator('#owner_family_or_style_words')).to_have_value(oversized)
    with page.expect_download() as download:
        page.locator('#export').click()
    oversized_rows = list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig'))))
    assert len(oversized_rows[0]['owner_family_or_style_words']) == 250_001
    assert oversized_rows[0]['save_status'] == 'LOCAL_DRAFT'
    page.locator('#reload').click()
    expect(page.locator('#owner_family_or_style_words')).to_have_value(note)
    page.route('**/api/answer', lambda route: route.abort())
    draft = 'SYNTHETIC OFFLINE DRAFT ONLY — recover after a disconnected save.'
    page.locator('#owner_family_or_style_words').fill(draft)
    expect(page.locator('#status')).to_contain_text('Not saved to disk.')
    page.reload(wait_until='networkidle');page.locator('#jump').select_option('0')
    expect(page.locator('#owner_family_or_style_words')).to_have_value(draft)
    expect(page.locator('#status')).to_contain_text('Not saved to disk.')
    with page.expect_download() as download:
        page.locator('#export').click()
    rows = list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig'))))
    assert any(r['owner_family_or_style_words'] == draft and r['save_status'] == 'LOCAL_DRAFT' for r in rows)
    page.unroute('**/api/answer')
    page.locator('#retry').click()
    expect(page.locator('#status')).to_have_text('Saved to disk.')
    other = context.new_page();other.goto(url, wait_until='networkidle');other.locator('#jump').select_option('0')
    other.locator('#identity [data-value="not_sure"]').click()
    expect(other.locator('#status')).to_have_text('Saved to disk.')
    page.locator('#owner_family_or_style_words').fill('SYNTHETIC STALE TAB NOTE')
    expect(page.locator('#status')).to_contain_text('Another tab changed')
    page.locator('#reload').click()
    expect(page.locator('#identity [data-value="not_sure"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#owner_family_or_style_words')).to_have_value(draft)
    other.close();intentional_failure = False
    for i in range(1, 16):
        page.locator('#jump').select_option(str(i))
        page.locator('#identity [data-value="not_sure"]').click()
        page.locator('#owner_family_or_style_words').fill(f'SYNTHETIC LISTENING FIXTURE {i}, not a real owner judgment.')
        expect(page.locator('#status')).to_have_text('Saved to disk.')
    expect(page.locator('#progress')).to_contain_text('16 / 16 described')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path=str(output / 'mobile-listen.png'), full_page=True)
    assert page.evaluate('()=>document.documentElement.scrollWidth<=window.innerWidth')
    page.set_viewport_size({'width': 1150, 'height': 1100})
    page.locator('#advance').click()
    expect(page.locator('#comparison')).to_be_visible()
    expect(page.locator('#model-output h3')).to_contain_text(['Gemini’s original description', 'Same audio, repeated request'])
    expect(page.locator('#listening')).to_be_hidden()
    page.screenshot(path=str(output / 'desktop-compare.png'), full_page=True)
    page.locator('.timestamp').first.click()
    page.wait_for_function('()=>!document.querySelector("#player").paused')
    first_notes = get('/api/session')['tracks'][0]['answer']['fields']['owner_family_or_style_words']
    assert first_notes == draft
    for i in range(16):
        page.locator('#jump').select_option(str(i))
        expect(page.locator('#model-output > article h3')).to_have_text('Gemini’s original description')
        page.locator('#verdict [data-value="not_sure"]').click()
        page.locator('#certainty [data-value="not_sure"]').click()
        if i == 0:
            page.locator('#notes').fill('SYNTHETIC comparison note,\nwith unicode 音楽🎵 and a long explanation. ' * 200)
        expect(page.locator('#status')).to_have_text('Saved to disk.')
    expect(page.locator('#progress')).to_contain_text('16 / 16 reviewed')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path=str(output / 'mobile-compare.png'), full_page=True)
    assert page.evaluate('()=>document.documentElement.scrollWidth<=window.innerWidth')
    page.locator('#advance').click()
    expect(page.locator('#completion')).to_be_visible()
    expect(page.locator('#notes')).to_be_disabled()
    page.reload(wait_until='networkidle')
    expect(page.locator('#completion')).to_be_visible()
    with page.expect_download() as download:
        page.locator('#export').click()
    rows = list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig'))))
    assert len(rows) == 16 and all(r['save_status'] == 'SAVED' and r['phase'] == 'complete' for r in rows)
    assert rows[0]['owner_family_or_style_words'] == draft and len(rows[0]['notes']) > 10_000
    assert not errors, errors
    assert not console_errors, console_errors
    browser.close()

assert get('/api/session')['phase'] == 'complete'
result = {'status': 'PASS', 'browser': 'isolated real Chromium via Playwright', 'tracks': 16,
          'all_full_FLAC_metadata_and_durations_verified': True, 'playback_and_seeking': True,
          'HTTP_range_206_and_416': True, 'model_profiles_server_gated_before_first_pass': True,
          'autosave_reload': True, 'offline_draft_recovery_and_export': True, 'multi_tab_conflicts': True,
          'immutable_independent_pass': True, 'two_pass_completion_reload_export': True,
          'long_unicode_notes_preserved': True, 'mobile_no_horizontal_overflow': True,
          'oversized_paste_preserved_and_exported_without_truncation': True,
          'page_errors': errors, 'unexpected_console_errors': console_errors,
          'intentional_failure_console_events': len(expected_console_errors), 'real_owner_answers_written': 0}
(output / 'browser_verification.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, sort_keys=True))
