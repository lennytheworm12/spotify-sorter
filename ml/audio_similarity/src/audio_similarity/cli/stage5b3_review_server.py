"""Serve the nine-case Stage 5B.3 targeted human review."""
from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.cli.stage5b1b_review_server import serve
from audio_similarity.stage5b3_review_store import Stage5B3ReviewStore


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review",
        default=str(root / "reports/stage5b3_minimal_selector/human_review.csv"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8778)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    store = Stage5B3ReviewStore(args.review)
    serve(
        store,
        args.host,
        args.port,
        open_browser=not args.no_browser,
        mode="stage5b3_minimal_selector_review",
        export_filename="stage5b3-minimal-selector-human-review.csv",
        server_name="Stage 5B.3 minimal-selector reviewer",
    )


if __name__ == "__main__":
    main()
