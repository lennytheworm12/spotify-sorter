"""Prepare and execute the separately authorized frozen-100 free-form extension."""
import argparse
from pathlib import Path

from .prepare import prepare_inventory, freeze_manifest
from .runner import Frozen100Runner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare-audio', 'freeze-manifest', 'next', 'run', 'replay', 'freeze', 'export'])
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--limit', type=int, default=84, help='Maximum new attempts this invocation, at most 84.')
    args = parser.parse_args()
    root, run = Path.cwd(), args.run.resolve()
    if args.action == 'prepare-audio':
        prepare_inventory(root, run)
        return
    if args.action == 'freeze-manifest':
        m = freeze_manifest(root, run)
        print({'status': 'MANIFEST_FROZEN', 'new_attempt_cap': m['max_attempts'], 'cached_profiles': len(m['cached_profiles'])})
        return
    runner = Frozen100Runner(root, run)
    if args.action in ('next', 'run'):
        if not 1 <= args.limit <= 84:
            parser.error('--limit must be within 1..84')
        for _ in range(1 if args.action == 'next' else args.limit):
            result = runner.next()
            print(result, flush=True)
            if not result['new_generation_calls']:
                break
    elif args.action == 'replay':
        print(runner.replay())
    elif args.action == 'freeze':
        print({k: v for k, v in runner.freeze_profiles().items() if k != 'files'})
    else:
        if not args.report:
            parser.error('export requires --report')
        from .export import export
        print(export(runner, args.report.resolve()))


if __name__ == '__main__':
    main()
