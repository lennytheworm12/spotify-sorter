"""Atomic anchor submissions and global reveal lock using the local audio server."""
import fcntl
import json
import math
import mimetypes
import os
import threading
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from .stage5e3_artifacts import read,freeze_json,digest,verify_hashes
from .stage5b1a_models import file_sha256
from .stage5e1_review import Stage5E1ReviewStore
from .cli.stage5b1b_review_server import make_review_handler,ReviewHTTPServer
from .stage5e3_retrieval import RUBRIC


class PlaylistReviewStore:
    local_audio_for_request=Stage5E1ReviewStore.local_audio_for_request

    def __init__(self,root,run,state):
        self.root=Path(root).resolve();self.run=Path(run).resolve();self.state=Path(state).resolve()
        self.payload=read(self.run/'review_blind_payload.json')
        self.manifest=read(self.run/'review_manifest.json')
        verify_hashes(self.run,self.manifest['scientific_hashes'])
        if digest(self.payload)!=self.manifest['payload_hash']:raise ValueError('review payload hash mismatch')
        self.packets={p['packet_id']:p for p in self.payload['packets']}
        self.state.mkdir(parents=True,exist_ok=True)
        self.review_path=self.state/'review_submissions.jsonl'
        self.review_path.touch(exist_ok=True)
        self.lock=threading.RLock();self._local_audio={}
        for t in read(self.run/'source_manifest.json')['tracks']:
            p=(self.root/t['retained_source_path']).resolve()
            if not p.is_relative_to(self.root/'.research_audio') or not p.is_file() or file_sha256(p)!=t['source_sha256']:raise ValueError('invalid local playback source')
            mime={'.webm':'audio/webm','.m4a':'audio/mp4','.opus':'audio/ogg'}.get(p.suffix) or mimetypes.guess_type(p.name)[0]
            if not mime or not mime.startswith('audio/'):raise ValueError('unsupported local media')
            self._local_audio[t['spotify_track_id']]=(p,mime)
        freeze_json(self.state/'run_identity.json',{'run':str(self.run),'manifest_hash':digest(self.manifest)})
        self.events()

    def events(self):
        with self.lock, (self.state/'review.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_SH)
            return self._events_unlocked()

    def _events_unlocked(self):
        records=[json.loads(line) for line in self.review_path.read_text().splitlines() if line]
        previous=''
        for i,event in enumerate(records):
            body={k:v for k,v in event.items() if k!='event_hash'}
            if event.get('sequence')!=i or event.get('previous_hash')!=previous or event.get('event_hash')!=digest(body):raise ValueError('submission ledger chain mismatch')
            if event['packet_id'] not in self.packets:raise ValueError('unknown packet in ledger')
            previous=event['event_hash']
        return records

    def session_page(self,offset=0,limit=1,review_filter='all'):
        events=self.events();latest={e['packet_id']:e for e in events}
        packets=self.payload['packets']
        if review_filter=='unreviewed': packets=[p for p in packets if p['packet_id'] not in latest]
        if offset<0 or not 1<=limit<=10:raise ValueError('invalid pagination')
        public=[]
        for packet in packets[offset:offset+limit]:
            prior=latest.get(packet['packet_id'])
            public.append(packet|{'submitted':prior is not None,'answers':prior['answers'] if prior else []})
        return {'question':self.payload['question'],'rubric':RUBRIC,'packets':public,'total':len(packets),
                'submitted_packets':len(latest),'all_packets':len(self.packets),
                'frozen':(self.run/'post_review_rating_snapshot.json').exists()}

    def submit_packet(self,payload):
        if not isinstance(payload,dict):raise ValueError('expected packet object')
        with self.lock, (self.state/'review.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if (self.run/'post_review_rating_snapshot.json').exists():raise ValueError('review already frozen')
            packet=self.packets.get(payload.get('packet_id'))
            if packet is None:raise ValueError('unknown packet')
            answers=payload.get('answers');expected={c['pair_id'] for c in packet['candidates']}
            if not isinstance(answers,list) or len(answers)!=len(expected):raise ValueError('complete packet required')
            cleaned=[]
            for answer in answers:
                if not isinstance(answer,dict) or answer.get('pair_id') not in expected or answer.get('label') not in RUBRIC:raise ValueError('invalid pair or label')
                note=answer.get('note','')
                if not isinstance(note,str) or len(note)>2000:raise ValueError('invalid note')
                cleaned.append({'pair_id':answer['pair_id'],'label':answer['label'],'note':note})
            if len({a['pair_id'] for a in cleaned})!=len(expected):raise ValueError('duplicate pair')
            cleaned.sort(key=lambda a:a['pair_id'])
            events=self._events_unlocked();prior=next((e for e in reversed(events) if e['packet_id']==packet['packet_id']),None)
            if prior and prior['answers']==cleaned:return {'saved':True,'duplicate':True}
            reason=payload.get('revision_reason','')
            if not isinstance(reason,str) or len(reason)>2000:raise ValueError('invalid revision reason')
            if prior and not reason.strip():raise ValueError('explicit revision reason required')
            playback=payload.get('playback',[])
            if not isinstance(playback,list) or len(playback)>200:raise ValueError('invalid playback diagnostics')
            allowed_tracks={packet['anchor']['spotify_track_id']}|{c['track']['spotify_track_id'] for c in packet['candidates']}
            for item in playback:
                if not isinstance(item,dict) or set(item)!={'track_id','played_seconds','seek_count'} or item['track_id'] not in allowed_tracks:raise ValueError('invalid playback record')
                if any(type(item[k]) not in (int,float) or not math.isfinite(item[k]) or item[k]<0 for k in ('played_seconds','seek_count')):raise ValueError('invalid playback values')
            event={'sequence':len(events),'previous_hash':events[-1]['event_hash'] if events else '',
                   'packet_id':packet['packet_id'],'answers':cleaned,'previous_answers':prior['answers'] if prior else None,
                   'revision_reason':reason,'timestamp':datetime.now(timezone.utc).isoformat(),
                   'session_id':payload.get('session_id','local-review'),'playback':playback,
                   'semantic_tag':'PLAYLIST_COMPATIBILITY_V1'}
            if not isinstance(event['session_id'],str) or len(event['session_id'])>100:raise ValueError('invalid session ID')
            event['event_hash']=digest(event)
            encoded=(json.dumps(event,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode()
            with self.review_path.open('ab') as stream:
                stream.write(encoded);stream.flush();os.fsync(stream.fileno())
            return {'saved':True,'duplicate':False}

    def freeze_labels(self):
        with self.lock, (self.state/'review.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            events=self._events_unlocked();latest={e['packet_id']:e for e in events}
            if set(latest)!=set(self.packets):raise ValueError('AWAITING_HUMAN_REVIEW: entire queue must be submitted')
            original=read(self.run/'pre_review_rating_snapshot.json');labels=dict(original['labels']);tags=dict(original['semantic_tags'])
            revisions=[]
            for event in events:
                for answer in event['answers']:
                    p=answer['pair_id'];value=int(answer['label']) if answer['label']!='UNSURE' else 'UNSURE'
                    old=labels.get(p)
                    revisions.append({'pair_id':p,'old_value':old,'new_value':value,'reason':event['revision_reason'] or 'blinded review submission/repeat',
                                      'timestamp':event['timestamp'],'session_id':event['session_id'],'event_hash':event['event_hash']})
                    labels[p]=value;tags[p]='PLAYLIST_COMPATIBILITY_V1'
            snapshot={'labels':labels,'semantic_tags':tags,'events':events,'revisions':revisions,
                      'review_complete':True,'manifest_hash':digest(self.manifest),'ledger_sha256':file_sha256(self.review_path)}
            freeze_json(self.run/'post_review_rating_snapshot.json',snapshot)
            # Derived append-only revision evidence is frozen with the completed ledger.
            from .stage5e3_artifacts import freeze
            freeze(self.state/'rating_revision_ledger.jsonl',b''.join((json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n').encode() for r in revisions))
            return {'status':'LABELS_FROZEN','judgments':len(labels)}


def handler(store,static):
    base=make_review_handler(store,static=static,mode='playlist_review')
    class Handler(base):
        def do_GET(self):
            path=urlparse(self.path).path
            if path not in ('/','/index.html','/api/session','/api/ping') and not path.startswith('/audio/track/'):
                return self._json({'error':'not found'},404)
            return super().do_GET()
        def do_POST(self):
            if urlparse(self.path).path!='/api/review':return self._json({'error':'not found'},404)
            try:
                origin=self.headers.get('Origin');host=self.headers.get('Host')
                if origin and origin!=f'http://{host}':raise ValueError('cross-origin request rejected')
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=131072:raise ValueError('invalid request size')
                return self._json(store.submit_packet(json.loads(self.rfile.read(size))))
            except (ValueError,TypeError,KeyError) as exc:
                return self._json({'error':str(exc)},400)
    return Handler


def serve_review(store,port=8785):
    static=store.root/'evaluation/static/stage5e3_review.html'
    server=ReviewHTTPServer(('127.0.0.1',port),handler(store,static))
    print(f'Playlist review: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
