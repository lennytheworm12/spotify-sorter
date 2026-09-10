"""Isolated browser checks; synthetic mode until an audio baseline is confirmed."""
import argparse,json
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright,expect
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:5180');p.add_argument('--output',required=True);p.add_argument('--real',action='store_true');a=p.parse_args()
out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
with urlopen(a.url+'/__song-space/genre/data') as r:packet=json.load(r)
assert bool(packet['provenance'].get('synthetic')) != a.real
errors=[];requests=[]
with sync_playwright() as pw:
 b=pw.chromium.launch(args=['--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']);page=b.new_page(viewport={'width':1500,'height':1100})
 page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None);page.on('request',lambda r:requests.append((r.method,r.url)))
 page.goto(a.url+'/#/genre',wait_until='networkidle');expect(page.get_by_role('heading',name='All 99 neighbors')).to_be_visible();assert page.locator('.gf-ranking tbody tr').count()==99
 coords=page.locator('.gf-map').get_attribute('data-coordinate-signature')
 original=page.locator('.gf-ranking tbody').inner_text();assert page.get_by_role('slider',name='Genre strength alpha').input_value()=='0'
 slider=page.get_by_role('slider',name='Genre strength alpha');slider.focus();page.keyboard.press('End');expect(slider).to_have_value('1');assert coords==page.locator('.gf-map').get_attribute('data-coordinate-signature')
 assert page.locator('.gf-ranking tbody').inner_text()!=original
 page.get_by_role('button',name='Original audio · α = 0').click();assert page.locator('.gf-ranking tbody').inner_text()==original
 slider.focus();page.keyboard.press('End');page.get_by_label('Genre source',exact=True).select_option('canonical_only');page.get_by_label('Genre source',exact=True).select_option('neighborhood_only_diagnostic');page.get_by_label('Genre source',exact=True).select_option('canonical_plus_residual')
 page.get_by_label('Force mode',exact=True).select_option('signed_experimental');expect(page.get_by_text('Experimental: low overlap subtracts')).to_be_visible();page.get_by_label('Force mode',exact=True).select_option('pull_only')
 page.get_by_label('Genre beta',exact=True).fill('0.10');page.get_by_label('Residual eta',exact=True).fill('0.50');assert coords==page.locator('.gf-map').get_attribute('data-coordinate-signature')
 page.get_by_label('Move graph',exact=True).check();expect(page.get_by_text('Temporary adjusted layout',exact=True)).to_be_visible(timeout=20000);assert coords!=page.locator('.gf-map').get_attribute('data-coordinate-signature')
 page.get_by_label('Move graph',exact=True).uncheck();assert coords==page.locator('.gf-map').get_attribute('data-coordinate-signature')
 page.locator('.gf-ranking tbody tr').nth(3).get_by_role('button').click();expect(page.get_by_role('heading',name='Canonical union',exact=True)).to_be_visible()
 for song in packet['songs']:
  page.get_by_label('Genre anchor',exact=True).select_option(song['id']);assert page.locator('.gf-ranking tbody tr').count()==99
 page.get_by_label('Genre anchor',exact=True).select_option(packet['songs'][0]['id'])
 audio=page.locator('.gf-anchor audio');page.wait_for_function('()=>document.querySelector(".gf-anchor audio").readyState>=1');audio.click(position={'x':20,'y':20});page.wait_for_function('()=>!document.querySelector(".gf-anchor audio").paused');audio.click(position={'x':audio.bounding_box()['width']*.65,'y':21});page.wait_for_function('()=>document.querySelector(".gf-anchor audio").currentTime>10')
 page.locator('.gf-anchor h2').click();page.keyboard.press('Space');page.wait_for_function('()=>document.querySelector(".gf-anchor audio").paused');page.keyboard.press('ArrowRight');expect(page.get_by_label('Genre anchor',exact=True)).to_have_value(packet['songs'][1]['id']);page.keyboard.press('ArrowLeft')
 page.get_by_label('Find genre explorer song').fill(packet['songs'][3]['title']);assert any(packet['songs'][3]['title'] in s for s in page.locator('[aria-label="Genre anchor"] option').all_text_contents());page.get_by_label('Find genre explorer song').fill('')
 page.screenshot(path=str(out/'desktop.png'),full_page=True);page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(out/'mobile.png'),full_page=True);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');b.close()
assert not errors,errors
assert all(method in ['GET','HEAD'] for method,url in requests),requests
with urlopen(Request(a.url+packet['songs'][0]['audioUrl'],headers={'Range':'bytes=0-63'})) as r:assert r.status==206 and len(r.read())==64
try:
 urlopen(Request(a.url+'/__song-space/genre/data',data=b'{}',headers={'Content-Type':'application/json'}));raise AssertionError('Write accepted')
except HTTPError as e:assert e.code==405
result={'status':'PASS','synthetic':not a.real,'tracks':100,'neighbors_per_anchor':99,'all_modes':True,'parameter_controls':True,'alpha_zero_restores':True,'fixed_coordinates_unchanged':True,'temporary_graph_changes_and_restores':True,'keyboard_search_audio_seek':True,'http_range':True,'write_rejected':True,'console_errors':errors,'review_writes':0}
(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
