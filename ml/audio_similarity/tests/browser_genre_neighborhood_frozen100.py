"""Isolated Chromium check of all frozen100 rows, audio and durable feedback."""
import argparse
import csv
import io
import json
from pathlib import Path
from urllib.request import urlopen, Request
from playwright.sync_api import sync_playwright, expect

p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8799');p.add_argument('--output',required=True)
a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
def get(path):
    with urlopen(a.url+path) as r:return json.load(r)
assert get('/api/ping')['mode']=='gemini_style_disposable'
s=get('/api/neighborhood/session');assert len(s['tracks'])==100
assert all(t['answer']['revision']==0 for t in s['tracks'])
errors=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1200,'height':1000})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
    page.goto(a.url+'/neighborhood',wait_until='networkidle')
    for i,t in enumerate(s['tracks']):
        page.locator('#jump').select_option(str(i))
        expect(page.locator('#song-title')).to_have_text(t['title'])
        page.wait_for_function('()=>document.querySelector("#player").readyState>=1')
        assert abs(page.locator('#player').evaluate('(a)=>a.duration')-t['duration_seconds'])<.1
        for k in ('primary_family','primary_style'):
            assert t['mapping']['raw_genre_labels'][k] in page.locator('#raw').inner_text()
        with urlopen(Request(a.url+t['audio_url'],headers={'Range':'bytes=0-63'})) as r:
            assert r.status==206 and len(r.read())==64
    page.locator('#player').click(position={'x':20,'y':20})
    page.wait_for_function('()=>document.querySelector("#player").currentTime>.1')
    width=page.locator('#player').bounding_box()['width']
    page.locator('#player').click(position={'x':width*.6,'y':21})
    page.wait_for_function('()=>document.querySelector("#player").currentTime>20')
    page.locator('#mapping [data-value=not_sure]').click()
    page.locator('#classification [data-value=not_sure]').click()
    page.locator('#notes').fill('Disposable test only — frozen100 autosave')
    expect(page.locator('#status')).to_have_text('Saved to disk.')
    page.reload(wait_until='networkidle');page.locator('#jump').select_option('99')
    expect(page.locator('#notes')).to_have_value('Disposable test only — frozen100 autosave')
    page.screenshot(path=str(out/'desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(out/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    with page.expect_download() as dl:page.locator('#export').click()
    rows=list(csv.DictReader(Path(dl.value.path()).read_text(encoding='utf-8-sig').splitlines()))
    assert len(rows)==100 and rows[-1]['notes']=='Disposable test only — frozen100 autosave'
    browser.close()
assert not errors,errors
(out/'verification.json').write_text(json.dumps({'status':'PASS','tracks':100,'duration_checks':100,'http_range_checks':100,
 'raw_labels_preserved':True,'playback_and_seek':True,'autosave_reload_export':True,'mobile_overflow':False,
 'console_errors':errors,'real_owner_answers_written':0},indent=2)+'\n')
print('PASS: 100 songs, audio Range/durations, labels, playback/seek, save/reload/export, mobile')
