"""Serve the unified Stage 5C.2 similarity-review workspace."""
from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.cli.stage5b1b_review_server import serve
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5c2_amended_100 import migrate_review_labels
from audio_similarity.stage5c2_review import Stage5C2ReviewStore


DEFAULT_REPORT_DIRECTORY = "reports/stage5c2_representative_100_amended_v2"


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    report = root / DEFAULT_REPORT_DIRECTORY
    default_queue = report / "review_queue.json"
    default_review = report / "human_similarity_review.csv"
    default_selected = report / "selected_sources.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default=str(default_queue))
    parser.add_argument("--review", default=str(default_review))
    parser.add_argument(
        "--selected-sources", default=str(default_selected)
    )
    parser.add_argument(
        "--playback-source", choices=("local", "youtube"), default="local"
    )
    parser.add_argument(
        "--local-audio-index", default=str(root / ".research_audio/index.json")
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8782)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    static = root / "evaluation/static/stage5c2_similarity_review.html"
    try:
        using_amended_defaults = (
            Path(args.queue).resolve() == default_queue.resolve()
            and Path(args.review).resolve() == default_review.resolve()
            and Path(args.selected_sources).resolve() == default_selected.resolve()
        )
        if using_amended_defaults:
            migrate_review_labels(
                root / "reports/stage5c2_representative_100/human_similarity_review.csv",
                Path(args.review),
            )
        store = Stage5C2ReviewStore(
            args.queue,
            args.review,
            selected_sources_path=args.selected_sources,
            local_audio_index_path=(
                args.local_audio_index if args.playback_source == "local" else None
            ),
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
        frame_sources=(
            ("https://www.youtube-nocookie.com",)
            if args.playback_source == "youtube"
            else ()
        ),
    )


if __name__ == "__main__":
    main()
