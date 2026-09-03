"""Serve the representative library benchmark human-review workbench."""
from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.cli.stage5b1b_review_server import serve
from audio_similarity.stage5b_representative_review_store import (
    RepresentativeBenchmarkReviewStore,
)


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review",
        default=str(root / "reports/stage5b_representative_library_v1/human_review.csv"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    store = RepresentativeBenchmarkReviewStore(args.review)
    serve(
        store,
        args.host,
        args.port,
        open_browser=not args.no_browser,
        mode="stage5b_representative_library_review",
        export_filename="stage5b-representative-library-v1-human-review.csv",
        server_name="Stage 5B representative library reviewer",
    )


if __name__ == "__main__":
    main()
