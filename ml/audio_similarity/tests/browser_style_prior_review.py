import argparse
import csv
import io
import json
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright, expect

parser=argparse.ArgumentParser(description='Browser tests: refuses to write to a real review server.')
parser.add_argument('--url',default='http://127.0.0.1:8793')
parser.add_argument('--output-dir',required=True)
args=parser.parse_args()
root=Path.cwd();run=root/'reports/style_prior_pilot/review_v1'
output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=True)
url=args.url
with urllib.request.urlopen(url+'/api/ping') as response:
    assert json.load(response)['mode']=='style_audit_disposable','Refusing to write test answers to the real reviewer'
with urllib.request.urlopen(url+'/api/session') as response:session=json.load(response)
assert session['completed']==0 and session['total']==12
def keys(value):
    if isinstance(value,dict):
        return set(value).union(*(keys(v) for v in value.values()))
    if isinstance(value,list):
        return set().union(*(keys(v) for v in value))
    return set()
raw=keys(session)
for forbidden in ('selection_stratum','distance','source_sha256','retained_source_path','rating','probe','score'):
    assert forbidden not in raw,forbidden
request=urllib.request.Request(url+session['pairs'][0]['left']['audio_url'],headers={'Range':'bytes=0-63'})
with urllib.request.urlopen(request) as response:
    assert response.status==206 and len(response.read())==64 and response.headers['Content-Range'].startswith('bytes 0-63/')
errors=[]
console_errors=[]
expected_console_errors=[]
intentional_failure=False
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(viewport={'width':1200,'height':1100},accept_downloads=True)
    page=context.new_page()
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('console',lambda message:(expected_console_errors if intentional_failure else console_errors).append(message.text) if message.type=='error' else None)
    page.goto(url,wait_until='networkidle')
    expect(page.locator('.choice')).to_have_count(9)
    for i in range(12):
        page.locator('#jump').select_option(str(i))
        for selector in ('#left audio','#right audio'):
            page.wait_for_function("s=>{const a=document.querySelector(s);return a.readyState>=1&&a.duration>0}",arg=selector)
    page.locator('#jump').select_option('0')
    page.wait_for_function("()=>document.querySelector('#left audio').readyState>=1")
    page.screenshot(path=str(output/'desktop.png'),full_page=True)
    page.locator('#left audio').evaluate('(a)=>a.play()')
    page.wait_for_function("()=>document.querySelector('#left audio').currentTime>0.15")
    page.locator('#right audio').evaluate('(a)=>a.play()')
    page.wait_for_function("()=>document.querySelector('#left audio').paused && !document.querySelector('#right audio').paused")
    for selector in ('#left audio','#right audio'):
        target=page.locator(selector).evaluate('(a)=>Math.min(45,a.duration/2)')
        page.locator(selector).evaluate('(a,t)=>{a.currentTime=t}',target)
        page.wait_for_function("({s,t})=>{const a=document.querySelector(s);return !a.seeking&&Math.abs(a.currentTime-t)<3}",arg={'s':selector,'t':target})
    page.locator('[data-value="VOCALS"]').click()
    page.locator('#note').fill('Browser fixture: voice texture, with a comma\nand a newline.')
    expect(page.locator('#status')).to_have_text('Saved to disk.')
    page.reload(wait_until='networkidle');page.locator('#jump').select_option('0')
    expect(page.locator('[data-value="VOCALS"]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('#note')).to_have_value('Browser fixture: voice texture, with a comma\nand a newline.')
    intentional_failure=True
    page.route('**/api/review',lambda route:route.abort())
    page.locator('#note').fill('Browser fixture draft survives failed save')
    expect(page.locator('#status')).to_contain_text('Not saved to disk.')
    page.reload(wait_until='networkidle');page.locator('#jump').select_option('0')
    expect(page.locator('#note')).to_have_value('Browser fixture draft survives failed save')
    expect(page.locator('#status')).to_contain_text('Not saved to disk.')
    with page.expect_download() as download:
        page.locator('#export').click()
    draft_rows=list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig'))))
    assert any(r['note']=='Browser fixture draft survives failed save' and r['save_status']=='LOCAL_DRAFT' for r in draft_rows)
    page.unroute('**/api/review')
    page.locator('#retry').click()
    expect(page.locator('#status')).to_have_text('Saved to disk.')
    other=context.new_page();other.goto(url,wait_until='networkidle');other.locator('#jump').select_option('0')
    other.locator('[data-value="TEXTURE"]').click();expect(other.locator('#status')).to_have_text('Saved to disk.')
    page.locator('[data-value="FAMILY"]').click();expect(page.locator('#status')).to_contain_text('Another tab changed')
    page.locator('#reload').click();expect(page.locator('[data-value="TEXTURE"]')).to_have_attribute('aria-pressed','true')
    other.close()
    intentional_failure=False
    for i in range(1,12):
        page.locator('#jump').select_option(str(i));page.locator('[data-value="NONE"]').click()
        expect(page.locator('#status')).to_have_text('Saved to disk.')
    expect(page.locator('#completion')).to_be_visible()
    with page.expect_download() as download:
        page.locator('#export').click()
    rows=list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig'))))
    assert len(rows)==12 and all(r['save_status']=='SAVED' for r in rows)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(output/'mobile.png'),full_page=True)
    assert page.evaluate('()=>document.documentElement.scrollWidth<=window.innerWidth')
    assert not errors,errors
    assert not console_errors,console_errors
    browser.close()
with urllib.request.urlopen(url+'/api/session') as response:assert json.load(response)['completed']==12
from audio_similarity.stage5e3_artifacts import read,verify_hashes
verify_hashes(root,read(run/'input_hashes.json'))
result={'status':'PASS','pairs':12,'browser':'real isolated Chromium via Playwright','all_24_audio_metadata_loaded':True,'playback_and_seeking_both_players':True,'HTTP_range_206':True,'mutually_exclusive_playback':True,'autosave_reload':True,'offline_draft_reload_and_csv_export':True,'multi_tab_conflict_detection':True,'completion_and_export':True,'mobile_no_horizontal_overflow':True,'page_errors':errors,'unexpected_console_errors':console_errors,'intentional_failure_console_events':len(expected_console_errors),'historical_inputs_unchanged':True,'test_server_mode':'style_audit_disposable','real_review_answers_written':0}
(output/'browser_verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
