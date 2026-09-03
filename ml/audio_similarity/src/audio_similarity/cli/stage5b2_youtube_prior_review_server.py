"""Serve the adaptive Stage 5B.2 raw YouTube-ranking human review."""
from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.cli.stage5b1b_review_server import serve
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b2_youtube_prior import load_youtube_prior_config
from audio_similarity.stage5b2_youtube_prior_review import (
    YoutubePriorReviewStore,
    write_human_review_artifacts,
)


MODE = "stage5b2_youtube_prior_review"
EXPORT_FILENAME = "stage5b2-youtube-prior-human-review.csv"


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(root / "reports/stage5b_youtube_prior_v1/benchmark_config.json"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        config = load_youtube_prior_config(args.config)
        _, review_path = write_human_review_artifacts(config)
        store = YoutubePriorReviewStore(review_path)
    except (FileNotFoundError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    serve(
        store,
        args.host,
        args.port,
        open_browser=not args.no_browser,
        mode=MODE,
        export_filename=EXPORT_FILENAME,
        server_name="Stage 5B.2 raw YouTube-ranking reviewer",
    )


if __name__ == "__main__":
    main()
