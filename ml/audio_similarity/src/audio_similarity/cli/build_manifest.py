"""Build the frozen FMA manifest.

    python -m audio_similarity.cli.build_manifest \
        --audio-dir data/fma/fma_small \
        --metadata-csv data/fma/fma_metadata/tracks.csv \
        --output data/manifests/fma_small.parquet
"""

from __future__ import annotations

import argparse

from audio_similarity.manifest import build_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-dir", required=True)
    parser.add_argument("--metadata-csv", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    frame = build_manifest(args.audio_dir, args.metadata_csv, args.output)
    total = len(frame)
    ok = int((frame["decode_status"] == "SUCCESS").sum())
    print(f"manifest rows: {total} ({ok} decodable, {total - ok} decode-failed)")
    print(f"written to {args.output}")


if __name__ == "__main__":
    main()
