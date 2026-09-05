"""Serve the Stage 5E.1 consolidated blinded pair reviewer."""
from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.cli.stage5b1b_review_server import serve
from audio_similarity.stage5e1_contract import REPORT_DIRECTORY
from audio_similarity.stage5e1_review import Stage5E1ReviewStore


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default=str(root / REPORT_DIRECTORY / "review_queue.json"))
    parser.add_argument("--review", default=str(root / ".research_audio/stage5e1_review/human_similarity_review.csv"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8783)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    store = Stage5E1ReviewStore(args.queue, args.review, root)
    serve(
        store,
        args.host,
        args.port,
        open_browser=not args.no_browser,
        static=root / "evaluation/static/stage5e1_blinded_review.html",
        mode="stage5e1_blinded_pair_review",
        export_filename="stage5e1-human-similarity-review.csv",
        server_name="Stage 5E.1 blinded similarity reviewer",
    )


if __name__ == "__main__":
    main()
