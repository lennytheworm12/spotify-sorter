"""Read-only Chromium inspection of old/new frozen100 mapper comparison."""
import json
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright,expect
url='http://127.0.0.1:8800';out=Path('/tmp/registry-compare-browser-v1');out.mkdir(exist_ok=True)
def get(path):
 with urlopen(url+path) as r:return json.load(r)
assert get('/api/ping')['mode']=='gemini_style_disposable'
before=get('/api/neighborhood/session');data=get('/api/registry-comparison');errors=[]
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1400,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
 page.goto(url+'/neighborhood',wait_until='networkidle');page.get_by_role('link',name='Compare old mapper / new vault mapper').click();expect(page.locator('#title')).to_have_text(data['tracks'][0]['title'])
 for i,t in enumerate(data['tracks']):
  page.locator('#jump').select_option(str(i));expect(page.locator('#title')).to_have_text(t['title']);assert t['raw_profile']['primary_style'] in page.locator('#raw').inner_text();assert 'undefined' not in page.locator('#new-content').inner_text()
 page.locator('[data-view=new]').click();expect(page.locator('#old')).to_be_hidden();expect(page.locator('#new')).to_be_visible();page.locator('[data-view=old]').click();expect(page.locator('#new')).to_be_hidden();page.locator('[data-view=both]').click()
 page.locator('#search').fill('Wet Dreamz');opts=page.locator('#jump option').all_text_contents();assert any('Wet Dreamz' in s for s in opts);page.locator('#search').fill('');page.locator('#jump').select_option('0');page.wait_for_function('()=>document.querySelector("#player").readyState>=1');page.locator('#player').click(position={'x':20,'y':20});page.wait_for_function('()=>document.querySelector("#player").currentTime>.1')
 page.screenshot(path=str(out/'desktop.png'),full_page=True);page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(out/'mobile.png'),full_page=True);b.close()
assert not errors,errors
assert before==get('/api/neighborhood/session')
(out/'verification.json').write_text(json.dumps({'status':'PASS','tracks':100,'views':['old','new','both'],'search':True,'playback':True,'mobile_overflow':False,'console_errors':errors,'review_unchanged':True,'feedback_writes':0},indent=2)+'\n')
print('PASS: 100 tracks, old/new/both, search, playback, mobile, zero review writes')
