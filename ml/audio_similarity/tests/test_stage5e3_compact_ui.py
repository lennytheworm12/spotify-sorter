import threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from tests.test_stage5e3_review import setup_fixture
from audio_similarity.stage5e3_review import ReviewHTTPServer, handler


def test_compact_drafts_playback_submit_and_blinding(tmp_path):
    store, _, _, _ = setup_fixture(tmp_path)
    static = Path(__file__).parents[1] / 'evaluation/static/stage5e3_compact_review.html'
    server = ReviewHTTPServer(('127.0.0.1', 0), handler(store, static))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            url = f'http://127.0.0.1:{server.server_port}'
            page.goto(url)
            page.wait_for_load_state('networkidle')
            assert page.locator('#jump option').count() == len(store.packets)
            page.locator('article').first.locator('[data-label="4"]').click()
            assert store.events() == []
            page.reload()
            page.wait_for_load_state('networkidle')
            assert page.locator('article').first.locator('[data-label="4"]').get_attribute('aria-pressed') == 'true'
            page.locator('article').first.locator('.play').click()
            page.wait_for_function('() => document.querySelector("#shared-audio").currentTime > .05')
            page.locator('#shared-audio').evaluate('(a) => {a.pause();a.currentTime=8}')
            page.wait_for_function('() => !document.querySelector("#shared-audio").seeking')
            page.locator('#next').click()
            page.locator('#prev').click()
            assert page.locator('article').first.locator('[data-label="4"]').get_attribute('aria-pressed') == 'true'
            page.locator('#submit').click()
            assert 'every candidate' in page.locator('#status').inner_text()
            for button in page.locator('article [data-label="4"]').all():
                button.click()
            page.locator('#submit').click()
            page.wait_for_function('() => document.querySelector("#status").textContent === "Complete packet saved."')
            assert len(store.events()) == 1
            assert page.locator('#next').is_enabled()
            page.reload()
            page.wait_for_load_state('networkidle')
            assert page.locator('article').first.locator('[data-label="4"]').get_attribute('aria-pressed') == 'true'
            assert page.request.get(url + '/api/reveal').status == 404
            payload = page.request.get(url + '/api/session').text()
            assert not any(key in payload for key in ('method_id', 'score', 'rank', 'probe_type', 'known_rating'))
            # Recover drafts left by the earlier UI without submitting test data to the real run.
            page.evaluate("""() => {
                for(const p of packets.filter(p=>!p.submitted)) {
                    const values=Object.fromEntries(p.candidates.map(c=>[c.pair_id,
                        {pair_id:c.pair_id,label:'3',note:'=note, "quoted"\\nsecond line'}]));
                    sessionStorage.setItem(draftKey(p),JSON.stringify(values));
                }
            }""")
            page.reload()
            page.wait_for_load_state('networkidle')
            with page.expect_download() as download_info:
                page.locator('#export').click()
            import csv
            with open(download_info.value.path(), encoding='utf-8-sig', newline='') as stream:
                exported=list(csv.DictReader(stream))
            drafts=[r for r in exported if r['save_status']=='DRAFT']
            assert drafts and all(r['note'].startswith("'=note") for r in drafts)
            assert all('method_id' not in r and 'score' not in r for r in exported)
            page.locator('#save-all').click()
            page.wait_for_function('() => packets.every(p=>p.submitted) && !busy')
            assert len(store.events()) == len(store.packets)
            assert all(a['note'].startswith('=note') for event in store.events()[1:] for a in event['answers'])
            assert page.locator('#save-all').is_disabled()
            page.screenshot(path='/tmp/stage5e3-compact-desktop.png', full_page=True)
            page.set_viewport_size({'width':390, 'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path='/tmp/stage5e3-compact-mobile.png', full_page=True)
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
