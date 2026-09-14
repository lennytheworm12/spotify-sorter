"""Prepare frozen-corpus Gemini/genre features. No calibration or audio inference."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'prepare', 'audio-cache', 'freeze-execution',
                                        'run', 'replay', 'build', 'verify', 'publish', 'status'])
    parser.add_argument('--approval', type=Path, help='Preserved explicit owner batch/upload and numeric cap approval')
    args = parser.parse_args()
    root = Path.cwd()
    if args.action == 'preflight':
        from ..calibration.gemini_full_inputs import inventory
        result = inventory(root)
    elif args.action == 'prepare':
        from ..calibration.gemini_full_prepare import prepare
        result = prepare(root)
    elif args.action == 'audio-cache':
        from ..calibration.gemini_full_features import prepare_audio_features
        result = prepare_audio_features(root)
    elif args.action == 'freeze-execution':
        if args.approval is None:
            parser.error('--approval is required before freezing execution')
        from ..calibration.gemini_full_manifest import freeze_execution
        result = freeze_execution(root, args.approval)
    elif args.action == 'run':
        from ..calibration.gemini_full_runner import run_all
        result = run_all(root)
    elif args.action == 'replay':
        from ..calibration.gemini_full_recovery import freeze_profiles
        frozen = freeze_profiles(root)
        result = {'status': 'PROFILES_VERIFIED', 'profiles': len(frozen['profiles']), 'new_api_calls': 0}
    elif args.action == 'build':
        from ..calibration.gemini_full_features import build
        result = build(root)
    else:
        from ..calibration import gemini_full_verify
        result = getattr(gemini_full_verify, args.action)(root)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
