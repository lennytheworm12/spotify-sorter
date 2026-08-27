from __future__ import annotations
import argparse,json
from audio_similarity.stage4a_cache import encode

def main():
 p=argparse.ArgumentParser();p.add_argument('--config',default='configs/holistic_stage4a_fma30.yaml');p.add_argument('--limit',type=int);p.add_argument('--track-id',type=int,action='append');p.add_argument('--validate-only',action='store_true');a=p.parse_args()
 if a.validate_only:
  from pathlib import Path
  import yaml
  from audio_similarity.stage4a_cache import Cache
  c=yaml.safe_load(Path(a.config).read_text());print(json.dumps(Cache(Path(a.config).parent.parent/c['paths']['artifacts']/'segments.sqlite').manifest(),indent=2));return
 print(json.dumps(encode(a.config,a.limit,a.track_id),indent=2))
if __name__=='__main__':main()
