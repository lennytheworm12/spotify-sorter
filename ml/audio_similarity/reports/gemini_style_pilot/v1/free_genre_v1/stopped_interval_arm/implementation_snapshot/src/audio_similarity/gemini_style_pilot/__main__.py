"""Explicit preparation, single-attempt execution, and offline replay commands."""
import argparse
import json
from pathlib import Path

from .manifest import make_manifest
from .runner import PilotRunner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['freeze-manifest', 'run-next', 'replay', 'freeze-profiles'])
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--run', type=Path, default=Path('.research_audio/gemini_style_pilot/style-pilot-v1'))
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--duration-revision', type=Path, help='explicit owner-approved continuation record')
    args = parser.parse_args()
    root = args.root.resolve()
    run = args.run if args.run.is_absolute() else root / args.run
    if args.command == 'freeze-manifest':
        if not args.inventory:
            parser.error('--inventory is required; unresolved source identities must not be overridden')
        inventory = args.inventory if args.inventory.is_absolute() else root / args.inventory
        revision = args.duration_revision
        if revision and not revision.is_absolute():
            revision = root / revision
        make_manifest(root, run, inventory, duration_revision=revision)
        result = {'status': 'EXECUTION_MANIFEST_FROZEN', 'new_api_calls': 0}
    else:
        runner = PilotRunner(root, run)
        if args.command == 'run-next':
            result = runner.next()
        elif args.command == 'replay':
            result = runner.replay()
        else:
            frozen = runner.freeze_profiles()
            result = {'status': frozen['status'], 'new_api_calls': 0}
    # Never print style classifications until all real profiles are frozen.
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
