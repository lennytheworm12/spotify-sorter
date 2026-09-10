"""Real Chromium tests against a fresh disposable session only."""
import argparse
import csv
import io
import json
from pathlib import Path
import urllib.request
import urllib.error

from playwright.sync_api import sync_playwright, expect

csv.field_size_limit(1_048_576)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url',default='http://127.0.0.1:8796')
parser.add_argument('--output-dir',required=True)
a=parser.parse_args();url=a.url;out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
def get(path):
    with urllib.request.urlopen(url+path) as r:return json.load(r)
assert get('/api/ping')['mode']=='gemini_style_disposable', 'Never test-write the real review'
session=get('/api/neighborhood/session');old=get('/api/session')
assert session['review_kind']=='genre-neighborhood-owner-review-v1' and len(session['tracks'])==16
assert all(t['answer']['revision']==0 for t in session['tracks']), 'Use fresh disposable state'
with urllib.request.urlopen(urllib.request.Request(url+session['tracks'][0]['audio_url'],headers={'Range':'bytes=0-63'})) as r:
    assert r.status==206 and len(r.read())==64 and r.headers['Content-Type']=='audio/flac'
try:
    urllib.request.urlopen(urllib.request.Request(url+'/api/neighborhood/answer',data=b'{}',headers={'Content-Type':'application/json','Origin':'http://different.invalid'}))
    raise AssertionError('Cross-origin save allowed')
except urllib.error.HTTPError as e:assert e.code==400
errors=[];console=[];expected_console=[];offline=False
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(viewport={'width':1150,'height':1100},accept_downloads=True)
    page=context.new_page()
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda m:(expected_console if offline else console).append(m.text) if m.type=='error' else None)
    page.goto(url,wait_until='networkidle')
    page.get_by_role('link',name='Open genre-neighborhood review').click()
    expect(page.locator('#song-title')).to_have_text(session['tracks'][0]['title'])
    for i,t in enumerate(session['tracks']):
        page.locator('#jump').select_option(str(i))
        page.wait_for_function('()=>document.querySelector("#player").readyState>=1')
        assert abs(page.locator('#player').evaluate('(a)=>a.duration')-t['duration_seconds'])<.1
        assert all(str(v) in page.locator('#raw').inner_text() for v in [t['mapping']['raw_genre_labels']['primary_family'],t['mapping']['raw_genre_labels']['primary_style']])
    page.locator('#jump').select_option('0')
    page.wait_for_function('()=>document.querySelector("#player").readyState>=1')
    page.locator('#player').click(position={'x':20,'y':20})
    page.wait_for_function('()=>document.querySelector("#player").currentTime>.1')
    width=page.locator('#player').bounding_box()['width']
    page.locator('#player').click(position={'x':width*.53,'y':21})
    page.wait_for_function('()=>document.querySelector("#player").currentTime>20&&!document.querySelector("#player").seeking')
    page.locator('#mapping [data-value=fits]').click()
    page.locator('#classification [data-value=does_not_fit]').click()
    note='Synthetic only, "quotes"\n音楽🎵 '+('long note '*6000)
    page.locator('#notes').fill(note)
    expect(page.locator('#status')).to_have_text('Saved to disk.')
    assert get('/api/neighborhood/session')['tracks'][0]['answer']['fields']['notes']==note
    page.reload(wait_until='networkidle');page.locator('#jump').select_option('0')
    expect(page.locator('#notes')).to_have_value(note)
    page.screenshot(path=str(out/'desktop.png'),full_page=True)
    offline=True;context.set_offline(True)
    draft=note+' OFFLINE DRAFT'
    page.locator('#notes').fill(draft)
    expect(page.locator('#recovery')).to_be_visible()
    with page.expect_download() as download:page.locator('#export').click()
    path=download.value.path()
    with Path(path).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    assert rows[0]['notes']==draft and rows[0]['save_status']=='LOCAL_DRAFT'
    context.set_offline(False);offline=False
    page.reload(wait_until='networkidle');page.locator('#jump').select_option('0')
    expect(page.locator('#status')).to_have_text('Saved to disk.')
    expect(page.locator('#notes')).to_have_value(draft)
    other=context.new_page();other.goto(url+'/neighborhood',wait_until='networkidle');other.locator('#jump').select_option('0')
    page.locator('#notes').fill('FIRST TAB SAVED')
    expect(page.locator('#status')).to_have_text('Saved to disk.')
    other.locator('#notes').fill('SECOND TAB STALE DRAFT')
    expect(other.locator('#recovery')).to_be_visible()
    other.locator('#reload').click()
    expect(other.locator('#notes')).to_have_value('FIRST TAB SAVED')
    other.close()
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#jump').select_option('2')
    expect(page.locator('#warnings')).to_contain_text('Heterogeneous')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(out/'mobile.png'),full_page=True)
    for i in range(16):
        page.locator('#jump').select_option(str(i))
        page.locator('#mapping [data-value=not_sure]').click()
        page.locator('#classification [data-value=not_sure]').click()
        expect(page.locator('#status')).to_have_text('Saved to disk.')
    expect(page.locator('#finish')).to_be_enabled()
    page.locator('#finish').click()
    expect(page.locator('#completion')).to_be_visible()
    expect(page.locator('#notes')).to_be_disabled()
    with page.expect_download() as download:page.locator('#export').click()
    with Path(download.value.path()).open(encoding='utf-8-sig',newline='') as f:final=list(csv.DictReader(f))
    assert len(final)==16 and all(r['save_status']=='SAVED' for r in final)
    assert get('/api/session')==old, 'Earlier review changed during mapping feedback'
    assert not errors and not console,(errors,console)
    browser.close()
result={'status':'PASS','tracks':16,'full_flac_duration_checks':16,'native_playback_and_seek':True,'range_206':True,'cross_origin_rejected':True,'autosave_and_reload':True,'long_notes':True,'offline_draft_export_and_recovery':True,'multi_tab_conflict':True,'complete_and_export':True,'mobile_overflow':False,'old_review_unchanged':True,'page_errors':errors,'unexpected_console_errors':console,'expected_offline_console_errors':len(expected_console),'real_review_answers_written':0}
(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
