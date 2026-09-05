"""Prepare, review, and score the artifact-only Stage 5E.2 evaluation."""
import argparse
import json
from pathlib import Path

from audio_similarity.stage5e2 import REPORT, PRIOR, STATE, read, run, evaluate
from audio_similarity.stage5e1_review import Stage5E1ReviewStore
from audio_similarity.cli.stage5b1b_review_server import serve
from audio_similarity.stage5b1b_artifacts import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'review', 'metrics'])
    parser.add_argument('--export', action='append', default=[])
    parser.add_argument('--port', type=int, default=8784)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.command == 'prepare':
        result = run(root, args.export)
        print(json.dumps({k: result[k] for k in ('verdict','total_D_pairs','covered_D_pairs','covered_percent','new_judgments')}, indent=2))
    elif args.command == 'review':
        store = Stage5E1ReviewStore(root/REPORT/'review_queue.json', root/STATE, root)
        serve(store, '127.0.0.1', args.port, open_browser=not args.no_browser,
              static=root/'evaluation/static/stage5e1_blinded_review.html',
              mode='stage5e2_blinded_pair_review', export_filename='stage5e2-human-review.csv',
              server_name='Stage 5E.2 similarity reviewer')
    else:
        # Validate queue, local source hashes, pair identities, and rating values.
        store = Stage5E1ReviewStore(root/REPORT/'review_queue.json', root/STATE, root)
        labels = read(root/REPORT/'reused_labels.json')
        for row in store._read_rows():
            if row['human_label'] in {'1','2','3','4','5'}:
                labels[row['pair_id']] = int(row['human_label'])
        _, metrics = evaluate(read(root/PRIOR/'nearest_neighbors.json'), labels)
        metrics['verdict'] = 'HUMAN_EVIDENCE_FOR_OWNER_REVIEW_NO_AUTOMATIC_ACTIVATION'
        atomic_json(root/STATE.parent/'current_metrics.json', metrics)
        print(json.dumps(metrics, indent=2))


if __name__ == '__main__':
    main()
