from __future__ import annotations
import argparse,json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from audio_similarity.stage4a_store import Store,StoreError
STATIC=Path(__file__).resolve().parents[3]/'evaluation/static/stage4a.html'
def handler(store):
 class H(BaseHTTPRequestHandler):
  def send(self,status,body,kind='application/json',headers=None):
   if isinstance(body,str):body=body.encode()
   self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
   for k,v in (headers or {}).items():self.send_header(k,v)
   self.end_headers();self.wfile.write(body)
  def json(self,status,payload):self.send(status,json.dumps(payload).encode())
  def do_GET(self):
   try:
    parsed=urlparse(self.path)
    if parsed.path=='/':return self.send(200,STATIC.read_bytes(),'text/html; charset=utf-8')
    if parsed.path=='/api/session':return self.json(200,store.session(parse_qs(parsed.query).get('reviewer',[''])[0]))
    if parsed.path=='/api/export':return self.send(200,store.export_bytes(),'text/csv',{'Content-Disposition':'attachment; filename=stage4a-ratings.csv'})
    parts=parsed.path.strip('/').split('/')
    if len(parts)==3 and parts[0]=='trial':
     body,digest=store.audio(parts[1],parts[2]);return self.send(200,body,'audio/wav',{'X-Canonical-PCM-SHA256':digest,'Cache-Control':'private, max-age=3600'})
    self.json(404,{'error':'not found'})
   except (StoreError,KeyError,ValueError) as exc:self.json(400,{'error':str(exc)})
  def do_POST(self):
   try:
    size=int(self.headers.get('Content-Length','0'));payload=json.loads(self.rfile.read(size) or b'{}')
    if self.path=='/api/rating':return self.json(200,store.submit(payload.get('trial_id'),payload.get('reviewer_id'),payload.get('choice')))
    if self.path=='/api/import':return self.json(200,store.import_rows(payload.get('rows',[])))
    self.json(404,{'error':'not found'})
   except (StoreError,KeyError,ValueError,json.JSONDecodeError) as exc:self.json(400,{'error':str(exc)})
  def log_message(self,*args):pass
 return H
def main():
 p=argparse.ArgumentParser();p.add_argument('--reports',default='reports/holistic_stage4a');p.add_argument('--audio-root',default='data/fma/fma_small');p.add_argument('--manifest',default='reports/holistic_stage4a/fma_small_candidate_manifest.parquet');p.add_argument('--reviewer',required=True);p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8766);a=p.parse_args();store=Store(a.reports,a.audio_root,a.manifest,a.reviewer);server=ThreadingHTTPServer((a.host,a.port),handler(store));print(f'http://{a.host}:{a.port}',flush=True);server.serve_forever()
if __name__=='__main__':main()
