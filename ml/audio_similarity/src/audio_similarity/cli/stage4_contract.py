from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.stage4_contract import freeze_readiness_contract, validate_frozen_contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze or validate the Stage 4 corpus/implementation contract; never downloads or encodes audio")
    parser.add_argument("command", choices=("freeze", "validate"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/holistic_stage4_full_song.yaml")
    parser.add_argument("--output", default="reports/holistic_stage4/corpus_provenance.json")
    parser.add_argument("--validate-only", action="store_true", help="alias for validate; never writes experiment outputs")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    config = root / args.config
    output = root / args.output
    if args.command == "validate" or args.validate_only:
        payload = validate_frozen_contract(root, config, output)
    else:
        payload = freeze_readiness_contract(root, config, output)
    print(payload["contract_sha256"])


if __name__ == "__main__":
    main()
