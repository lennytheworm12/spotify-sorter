"""Offline synthetic calibration proof and read-only corpus readiness commands."""
import argparse
import json
from pathlib import Path

from audio_similarity.calibration.contracts import freeze_json
from audio_similarity.calibration.readiness import summarize_inventory, write_readiness
from audio_similarity.calibration.synthetic import run_demo

ROOT = Path(__file__).resolve().parents[3]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['synthetic', 'readiness', 'replay-readiness'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, action='append', default=[])
    parser.add_argument('--inventory', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'synthetic':
        result = run_demo(args.output)
    elif args.command == 'replay-readiness':
        if args.inventory is None:
            parser.error('--inventory is required')
        result = summarize_inventory(json.loads(args.inventory.read_text()))
        freeze_json(args.output / 'readiness.json', result)
    else:
        runs = args.run_dir or [Path('.research_audio/example_playlist_batches_v1'),
                               Path('.research_audio/example_playlist_batches_v2')]
        result = write_readiness(ROOT, tuple((ROOT / p).resolve() for p in runs), args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
