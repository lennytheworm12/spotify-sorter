"""Serve the blinded Representative Library V4 review queue."""
from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.cli.stage5b1b_review_server import serve
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b5_representative_v4 import load_v4_config
from audio_similarity.stage5b5_review import (
    Stage5B5ReviewStore,
    write_human_review_artifacts,
)


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(root / "reports/stage5b5_representative_v4/benchmark_config.json"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        config = load_v4_config(args.config)
        _, review_path = write_human_review_artifacts(config)
        store = Stage5B5ReviewStore(
            review_path,
            config.output_dir / "automated_selector_decisions.json",
        )
    except (FileNotFoundError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    serve(
        store,
        args.host,
        args.port,
        open_browser=not args.no_browser,
        mode="stage5b5_representative_v4_review",
        export_filename="stage5b5-representative-v4-human-review.csv",
        server_name="Stage 5B.5 Representative V4 reviewer",
    )


if __name__ == "__main__":
    main()
