"""Isolated OAuth-error/history regression. Requires a running Vite frontend."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import json
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url',default='http://127.0.0.1:5173')
parser.add_argument('--output',type=Path,default=Path('/tmp/song-space-auth-check.json'))
args=parser.parse_args()
checks=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 page=b.new_page()
 page.route('**/__song-space/catalog',lambda r:r.fulfill(status=200,content_type='application/json',body='[]'))
 page.route('**/auth/me',lambda r:r.fulfill(status=401,content_type='application/json',body='{"message":"Not connected"}'))
 page.goto(args.url+'/?auth=error&reason=test#/')
 expect(page.get_by_role('heading',name='Spotify Playlist Organizer')).to_be_visible()
 page.get_by_role('link',name='Back to song space',exact=False).click()
 expect(page.get_by_role('button',name='Open a local map',exact=True)).to_be_visible()
 assert 'auth=' not in page.url
 checks.append('OAuth error can return to song space even when hash is already root')
 page.get_by_role('link',name='Organizer',exact=False).click()
 expect(page.get_by_role('heading',name='Spotify Playlist Organizer')).to_be_visible()
 page.go_back()
 expect(page.get_by_role('button',name='Open a local map',exact=True)).to_be_visible()
 checks.append('browser Back restores song-space route')
 args.output.write_text(json.dumps({'checks':checks,'count':len(checks)},indent=2)+'\n')
 print(checks)
 b.close()
