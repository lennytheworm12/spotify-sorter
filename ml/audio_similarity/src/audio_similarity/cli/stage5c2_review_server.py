"""Serve the unified Stage 5C.2 similarity-review workspace."""
from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.cli.stage5b1b_review_server import serve
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5c2_review import Stage5C2ReviewStore


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    report = root / "reports/stage5c2_representative_100"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default=str(report / "review_queue.json"))
    parser.add_argument("--review", default=str(report / "human_similarity_review.csv"))
    parser.add_argument(
        "--selected-sources", default=str(report / "selected_sources.json")
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8782)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    static = root / "evaluation/static/stage5c2_similarity_review.html"
    try:
        store = Stage5C2ReviewStore(
            args.queue, args.review, selected_sources_path=args.selected_sources
        )
    except (FileNotFoundError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    serve(
        store,
        args.host,
        args.port,
        open_browser=not args.no_browser,
        static=static,
        mode="stage5c2_similarity_review",
        export_filename="stage5c2-human-similarity-review.csv",
        server_name="Stage 5C.2 unified similarity reviewer",
        frame_sources=("https://www.youtube-nocookie.com",),
    )


if __name__ == "__main__":
    main()
