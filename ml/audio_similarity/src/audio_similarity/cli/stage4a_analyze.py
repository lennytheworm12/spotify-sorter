import argparse,json
from audio_similarity.stage4a_analysis import run

def main():
 p=argparse.ArgumentParser();p.add_argument('--config',default='configs/holistic_stage4a_fma30.yaml');p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(run(a.config,a.validate_only),indent=2))
if __name__=='__main__':main()
