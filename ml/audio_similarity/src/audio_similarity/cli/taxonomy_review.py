"""Prepare, launch/resume, or explicitly freeze the 16-pair taxonomy audit."""
import argparse
import json
from pathlib import Path
from audio_similarity.taxonomy_packet import REPORT, prepare
from audio_similarity.taxonomy_review_store import TaxonomyReviewStore
from audio_similarity.cli.stage5b1b_review_server import serve
from audio_similarity.stage5e3_artifacts import read, verify_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'review', 'freeze'])
    parser.add_argument('--port', type=int, default=8791)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--state-dir', help='Separate disposable directory for browser tests or another audit session')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.command == 'prepare':
        print(json.dumps(prepare(root), indent=2))
        return
    verify_hashes(root / REPORT, read(root / REPORT / 'artifact_manifest.json'))
    production_state = root / 'artifacts/stage5g1b_taxonomy_review/v1'
    state = Path(args.state_dir) if args.state_dir else production_state
    if args.state_dir and state.resolve() == production_state.resolve():
        raise ValueError('A disposable override must not target the real review state.')
    store = TaxonomyReviewStore(root / REPORT / 'packet.json', state, root)
    try:
        if args.command == 'freeze':
            print(json.dumps(store.freeze(), indent=2))
        else:
            serve(store, '127.0.0.1', args.port, open_browser=not args.no_browser,
                  static=root / 'evaluation/static/taxonomy_review.html',
                  mode='taxonomy_audit_disposable' if args.state_dir else 'taxonomy_audit',
                  export_filename='taxonomy-answers.csv', server_name='Musical identity review')
    finally:
        store.close()


if __name__ == '__main__':
    main()
