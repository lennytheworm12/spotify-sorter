import argparse,json,yaml
from pathlib import Path
from audio_similarity.stage4a_cache import Cache
from audio_similarity.stage4a_dual_cache import encode
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',default='configs/holistic_stage4a_dual.yaml');p.add_argument('--limit',type=int);p.add_argument('--track-id',type=int,action='append');p.add_argument('--validate-only',action='store_true');a=p.parse_args()
 if a.validate_only:
  c=yaml.safe_load(Path(a.config).read_text());print(json.dumps(Cache(Path(a.config).parent.parent/c['paths']['muq_cache']).manifest(),indent=2));return
 print(json.dumps(encode(a.config,a.limit,a.track_id),indent=2))
if __name__=='__main__':main()
