"""Freeze the pre-rating Stage 2B collection bundle hash manifest."""

from __future__ import annotations

import argparse

from audio_similarity.stage2b_collection import freeze_collection_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    payload = freeze_collection_bundle(args.root)
    print(f"froze {len(payload['immutable_sha256'])} immutable collection files")


if __name__ == "__main__":
    main()
