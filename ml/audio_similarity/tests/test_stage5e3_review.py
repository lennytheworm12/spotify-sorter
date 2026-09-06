import json
import shutil
import threading
import wave
from pathlib import Path
import numpy as np
import pytest
from audio_similarity.stage5e3_retrieval import rank_tracks,build_packets
from audio_similarity.stage5e3_inputs import eligible
from audio_similarity.stage5e3_artifacts import freeze_json,digest,hashes
from audio_similarity.stage5e3_review import PlaylistReviewStore,handler,ReviewHTTPServer
from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5c2_analysis import canonical_pair_id
from audio_similarity.playlist_compatibility_eval import METHODS


def setup_fixture(tmp_path):
    root=tmp_path;run=root/'reports/fixture';state=root/'.research_audio/review';media=root/'.research_audio/tone.wav';media.parent.mkdir(parents=True)
    # Synthetic local audio only; every rating stays under this disposable root.
    with wave.open(str(media),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000)
        f.writeframes((np.sin(np.arange(24000*14)*2*np.pi*440/24000)*2000).astype('<i2').tobytes())
    tracks=[{'spotify_track_id':f't{i:02d}','title':f'Synthetic {i}','artists':['Fixture'],
             'source_sha256':file_sha256(media),'retained_source_path':str(media.relative_to(root)),
             'youtube_video_id':f'v{i}'} for i in range(10)]
    # Retrieval identities are synthetic unique recordings; playback points at fixture WAV.
    ranking_tracks=[t|{'source_sha256':t['spotify_track_id']} for t in tracks]
    matrix=np.full((10,10),.5);np.fill_diagonal(matrix,1)
    rows=rank_tracks(ranking_tracks,{m:matrix for m in METHODS})
    pairs={canonical_pair_id(a['spotify_track_id'],b['spotify_track_id']):[a['spotify_track_id'],b['spotify_track_id']] for a in tracks for b in tracks if a!=b}
    original={'labels':{},'pairs':pairs,'conflicts':{},'semantic_tags':{}}
    payload,probes,assign,counts=build_packets(ranking_tracks,rows,original)
    freeze_json(run/'source_manifest.json',{'tracks':tracks})
    freeze_json(run/'pre_review_rating_snapshot.json',original)
    freeze_json(run/'review_blind_payload.json',payload)
    freeze_json(run/'review_manifest.json',{'payload_hash':digest(payload),'scientific_hashes':hashes([run/'review_blind_payload.json',run/'pre_review_rating_snapshot.json'],run),'assignments':assign,'counts':counts})
    static=Path(__file__).parents[1]/'evaluation/static/stage5e3_review.html'
    return PlaylistReviewStore(root,run,state),static,rows,ranking_tracks


def test_retrieval_dedup_and_probes(tmp_path):
    store,static,rows,tracks=setup_fixture(tmp_path)
    labels={canonical_pair_id('t00','t09'):5,canonical_pair_id('t01','t08'):1}
    original=read_snapshot= json.loads((store.run/'pre_review_rating_snapshot.json').read_text())
    original['labels']=labels
    a=build_packets(tracks,rows,original);b=build_packets(tracks,list(reversed(rows)),original)
    assert a==b
    payload,probes,hidden,counts=a
    pair_ids=[c['pair_id'] for p in payload['packets'] for c in p['candidates']]
    assert len(pair_ids)==len(set(pair_ids))
    assert counts['drift_repeat_pairs']>0
    assert all(p['candidate'] not in {r['candidate'] for r in rows if r['query']==p['query']} for p in probes)
    forbidden=('method_id','score','rank','probe_type','known_rating','retrieved_by_methods')
    assert all(k not in json.dumps(payload) for k in forbidden)
    duplicate=tracks[1]|{'source_sha256':tracks[0]['source_sha256']}
    assert not eligible(tracks[0],duplicate)
    assert not eligible(tracks[0],tracks[1]|{'youtube_video_id':tracks[0]['youtube_video_id']})


def submit_all(store):
    for packet in store.payload['packets']:
        store.submit_packet({'packet_id':packet['packet_id'],'answers':[{'pair_id':c['pair_id'],'label':'UNSURE'} for c in packet['candidates']]})


def test_atomic_revision_resume_and_freeze(tmp_path):
    store,_,_,_=setup_fixture(tmp_path);packet=store.payload['packets'][0]
    with pytest.raises(ValueError):store.freeze_labels()
    with pytest.raises(ValueError):store.submit_packet({'packet_id':packet['packet_id'],'answers':[]})
    assert store.events()==[]
    payload={'packet_id':packet['packet_id'],'answers':[{'pair_id':c['pair_id'],'label':'4'} for c in packet['candidates']]}
    store.submit_packet(payload);before=store.review_path.read_bytes();store.submit_packet(payload)
    assert before==store.review_path.read_bytes()
    resumed=PlaylistReviewStore(store.root,store.run,store.state)
    assert resumed.session_page()['packets'][0]['submitted']
    payload['answers'][0]['label']='2'
    with pytest.raises(ValueError):resumed.submit_packet(payload)
    resumed.submit_packet(payload|{'revision_reason':'fixture correction'})
    assert resumed.review_path.read_bytes().startswith(before)
    assert resumed.events()[-1]['previous_answers'][0]['label']=='4'
    for packet in resumed.payload['packets'][1:]:resumed.submit_packet({'packet_id':packet['packet_id'],'answers':[{'pair_id':c['pair_id'],'label':'UNSURE'} for c in packet['candidates']]})
    resumed.freeze_labels();resumed.freeze_labels()
    with pytest.raises(ValueError):resumed.submit_packet(payload)
    assert 'UNSURE' in json.loads((store.run/'post_review_rating_snapshot.json').read_text())['labels'].values()


def test_chromium_playback_range_blinding_submission_resume(tmp_path):
    from playwright.sync_api import sync_playwright
    store,static,_,_=setup_fixture(tmp_path)
    server=ReviewHTTPServer(('127.0.0.1',0),handler(store,static));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    errors=[];responses=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            page=browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('response',lambda r:responses.append((r.url,r.status)))
            page.goto(url);page.wait_for_load_state('networkidle')
            assert page.locator('article').count()>0
            assert page.locator('audio').first.evaluate('(a)=>a.paused && a.currentTime===0')
            page.locator('audio').first.evaluate('(a)=>a.play()')
            page.wait_for_function('() => document.querySelector("audio").currentTime>0.1')
            page.locator('audio').first.evaluate('(a)=>{a.pause();a.currentTime=8}')
            page.wait_for_function('() => Math.abs(document.querySelector("audio").currentTime-8)<0.1 && !document.querySelector("audio").seeking')
            response=page.request.get(url+'/audio/track/t00',headers={'Range':'bytes=100-199'})
            assert response.status==206 and len(response.body())==100
            assert response.headers['content-range'].startswith('bytes 100-199/')
            assert page.request.get(url+'/audio/track/t00',headers={'Range':'bytes=999999999-'}).status==416
            for route in ('/api/export','/api/reveal','/review_manifest.json','/retrieval_top5.parquet','/../review_manifest.json'):
                assert page.request.get(url+route).status==404
            assert not any(k in page.request.get(url+'/api/session').text() for k in ('method_id','score','rank','probe_type','known_rating'))
            page.locator('#submit').click();assert 'every candidate' in page.locator('#message').inner_text()
            for select in page.locator('article select').all():select.select_option('4')
            page.locator('#submit').click();page.wait_for_function('() => document.querySelector("#message").textContent==="Complete packet saved."')
            page.reload();page.wait_for_load_state('networkidle')
            assert all(s.input_value()=='4' for s in page.locator('article select').all())
            page.locator('#next').click();page.wait_for_function('() => document.querySelector("#progress").textContent.startsWith("Packet 2 ")')
            assert page.request.get(url+'/api/reveal').status==404
            page.screenshot(path='/tmp/stage5e3-browser-fixture.png',full_page=True)
            assert not errors
            browser.close()
        restarted=PlaylistReviewStore(store.root,store.run,store.state)
        assert restarted.session_page()['submitted_packets']==1
        assert restarted.events()[0]['playback']
    finally:
        server.shutdown();server.server_close();thread.join()
