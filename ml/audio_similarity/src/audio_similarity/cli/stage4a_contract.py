from __future__ import annotations
import argparse
from pathlib import Path
from audio_similarity.stage4a_contract import freeze,validate

def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','validate']);p.add_argument('--root',default='.');p.add_argument('--config',default='configs/holistic_stage4a_fma30.yaml');p.add_argument('--validate-only',action='store_true');a=p.parse_args();root=Path(a.root).resolve();config=root/a.config
 result=validate(root,config) if a.command=='validate' or a.validate_only else freeze(root,config);print(result['contract_sha256'])
if __name__=='__main__':main()
