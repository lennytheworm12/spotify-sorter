"""Evaluate the Stage 5B.1C-C strong-metadata fallback offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1c_strong_metadata import write_strong_metadata_artifacts


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "configs/stage5b1b_fresh_challenge.json",
    )
    parser.add_argument(
        "--tier2a-dir", type=Path, default=root / "reports/stage5b1c_a"
    )
    parser.add_argument(
        "--source-neutral-dir", type=Path, default=root / "reports/stage5b1c_b"
    )
    parser.add_argument(
        "--diagnostic",
        type=Path,
        default=root
        / "reports/stage5b1c_c_diagnostic/remaining_tail_diagnostic.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "reports/stage5b1c_c_strong_metadata",
    )
    args = parser.parse_args()
    artifacts = write_strong_metadata_artifacts(
        args.config.resolve(),
        tier2a_dir=args.tier2a_dir.resolve(),
        source_neutral_dir=args.source_neutral_dir.resolve(),
        diagnostic_path=args.diagnostic.resolve(),
        output_dir=args.output_dir.resolve(),
    )
    print(
        json.dumps(
            {
                "status": "STAGE5B1C_C_STRONG_METADATA_EVALUATED",
                **artifacts["summary"],
                "artifacts": {
                    name: {"path": str(path), "sha256": file_sha256(path)}
                    for name, path in artifacts.items()
                    if isinstance(path, Path)
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
