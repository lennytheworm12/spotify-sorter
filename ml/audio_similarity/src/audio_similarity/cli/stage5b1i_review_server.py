"""Serve the Stage 5B.1I all-candidate human-oracle review workbench."""
from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.cli.stage5b1b_review_server import serve
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b1i_human_oracle import (
    load_stage5b1i_config,
    replay_human_oracle_universe,
)
from audio_similarity.stage5b1i_review_store import Stage5B1IReviewStore


MODE = "stage5b1i_human_oracle_tail"
EXPORT_FILENAME = "stage5b1i-human-oracle-tail-review.csv"


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default=str(root / "configs/stage5b1i_human_oracle_tail.json")
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8774)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        config = load_stage5b1i_config(Path(args.config))
        store = Stage5B1IReviewStore(
            config.artifacts["human_review_queue"],
            config.artifacts["human_review"],
            replay_human_oracle_universe(config),
        )
    except (FileNotFoundError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    serve(
        store,
        args.host,
        args.port,
        open_browser=not args.no_browser,
        mode=MODE,
        export_filename=EXPORT_FILENAME,
        server_name="Stage 5B.1I human-oracle reviewer",
    )


if __name__ == "__main__":
    main()
