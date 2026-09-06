import sys,json,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright
from audio_similarity.stage5e3_prepare import REPORT,verify_prepared
from audio_similarity.stage5e3_review import PlaylistReviewStore,ReviewHTTPServer,handler
from audio_similarity.stage5e3_artifacts import read
root=Path.cwd();run=root/REPORT
verify_prepared(root,run)
store=PlaylistReviewStore(root,run,root/'.research_audio/stage5e3_frozen100_v3_review')
before=store.review_path.read_bytes()
assert before==b'', 'real review has already started; do not run this pre-review verifier'
server=ReviewHTTPServer(('127.0.0.1',0),handler(store,root/'evaluation/static/stage5e3_review.html'))
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
url=f'http://127.0.0.1:{server.server_port}'
errors=[];console=[];tracks=[];requests=[]
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  page=browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('console',lambda m:console.append({'type':m.type,'text':m.text}) if m.type in ('error','warning') else None)
  page.on('response',lambda r:requests.append({'url':r.url,'status':r.status}) if r.status>=400 else None)
  page.goto(url);page.wait_for_load_state('networkidle')
  assert page.locator('article').count()>0
  payload=page.request.get(url+'/api/session').json()
  text=json.dumps(payload)
  for key in ('method_id','score','rank','probe_type','known_rating','retrieved_by_methods','source_sha256'):
   assert key not in text,key
  assert page.locator('audio').first.evaluate('(a)=>a.paused&&a.currentTime===0')
  page.screenshot(path='/tmp/stage5e3-real-review.png',full_page=True)
  for track in read(run/'source_manifest.json')['tracks']:
   tid=track['spotify_track_id'];audio_url=url+'/audio/track/'+tid
   r=page.request.get(audio_url,headers={'Range':'bytes=0-1023'})
   assert r.status==206 and len(r.body())==1024
   assert r.headers['accept-ranges']=='bytes'
   result=page.locator('audio').first.evaluate('''async (a,src)=>{
    a.pause();a.src=src;a.load();
    await new Promise((resolve,reject)=>{a.onloadedmetadata=resolve;a.onerror=()=>reject(Error('audio metadata error'));setTimeout(()=>reject(Error('metadata timeout')),10000)});
    const duration=a.duration;await a.play();await new Promise((resolve,reject)=>{const began=performance.now();const timer=setInterval(()=>{if(a.currentTime>0.05){clearInterval(timer);resolve()}else if(performance.now()-began>8000){clearInterval(timer);reject(Error('playback clock did not advance'))}},25)});
    const played=a.currentTime;a.pause();const target=duration*.6;
    await new Promise((resolve,reject)=>{a.onseeked=resolve;a.currentTime=target;setTimeout(()=>reject(Error('seek timeout')),10000)});
    return {duration,played,current:a.currentTime,target,error:a.error?.message||null};
   }''',audio_url)
   print(json.dumps({'track_id':tid,**result}),flush=True)
   assert result['duration']>0 and result['played']>0 and abs(result['current']-result['target'])<.2 and result['error'] is None
   tracks.append({'track_id':tid,'range_status':r.status,**result})
  # Navigation/resume is read-only on this real dataset.
  page.locator('#next').click();page.wait_for_load_state('networkidle')
  page.reload();page.wait_for_load_state('networkidle')
  assert store.review_path.read_bytes()==before
  browser.close()
finally:
 server.shutdown();server.server_close();thread.join()
report={'passed':not errors and not console,'tracks_tested':len(tracks),'tracks':tracks,'page_errors':errors,'console':console,
        'failed_requests':requests,'real_rating_bytes_before':len(before),'real_rating_bytes_after':store.review_path.stat().st_size,
        'synthetic_ratings_written_to_real_dataset':0}
Path('/tmp/stage5e3-real-browser-result.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='tracks'}))
assert report['passed']
