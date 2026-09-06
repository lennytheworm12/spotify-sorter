"""Stage 5E.3 pre-review pipeline and separately gated scientific closeout."""
import argparse
import json
from pathlib import Path
from audio_similarity.stage5e3_prepare import REPORT,prepare,verify_prepared
from audio_similarity.stage5e3_materialize import embed,build_similarities,build_review
from audio_similarity.stage5e3_review import PlaylistReviewStore,serve_review
from audio_similarity.stage5e3_closeout import analyze,closeout
from audio_similarity.stage5e3_handoff import handoff


def main():
    root=Path(__file__).resolve().parents[3]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','embed-full-muq','build-similarities','build-review','review','snapshot-labels','analyze','closeout','verify','handoff','run-all'])
    parser.add_argument('--run',type=Path,default=root/REPORT)
    parser.add_argument('--state',type=Path,default=root/'.research_audio/stage5e3_frozen100_v3_review')
    parser.add_argument('--port',type=int,default=8785)
    args=parser.parse_args();run=args.run.resolve()
    commands={'prepare':lambda:prepare(root,run),'embed-full-muq':lambda:embed(root,run),
              'build-similarities':lambda:build_similarities(root,run),'build-review':lambda:build_review(root,run),
              'analyze':lambda:analyze(root,run),'closeout':lambda:closeout(root,run),'verify':lambda:verify_prepared(root,run),'handoff':lambda:handoff(root,run)}
    if args.command in ('review','snapshot-labels'):
        verify_prepared(root,run)
        store=PlaylistReviewStore(root,run,args.state)
        result=serve_review(store,args.port) if args.command=='review' else store.freeze_labels()
    elif args.command=='run-all':
        result={}
        for name in ('prepare','embed-full-muq','build-similarities','build-review'):result[name]=commands[name]()
        result['status']='AWAITING_ENGINEERING_VERIFICATION_AND_HUMAN_REVIEW'
    else:result=commands[args.command]()
    print(json.dumps(result,sort_keys=True,allow_nan=False))

if __name__=='__main__':main()
