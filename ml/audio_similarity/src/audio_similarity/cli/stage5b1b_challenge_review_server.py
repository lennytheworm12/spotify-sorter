"""Serve the blinded Stage 5B.1B fresh-challenge human-audit workbench."""
from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.cli.stage5b1b_review_server import make_review_handler, serve
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b1b_challenge import (
    load_challenge_config,
    load_challenge_manifest,
)
from audio_similarity.stage5b1b_challenge_review_store import (
    Stage5B1BChallengeReviewStore,
)


MODE = "stage5b1b_fresh_challenge_human_audit"
EXPORT_FILENAME = "stage5b1b-fresh-challenge-human-review.csv"


def handler_for(store: Stage5B1BChallengeReviewStore):
    """Create the configured handler while keeping HTTP tests concise."""

    return make_review_handler(store, mode=MODE, export_filename=EXPORT_FILENAME)


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(root / "configs" / "stage5b1b_fresh_challenge.json"),
    )
    parser.add_argument(
        "--review",
        help="optional review CSV override for a disposable or exported copy",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        config = load_challenge_config(args.config)
        manifest = load_challenge_manifest(
            config.manifest_path,
            expected_sha256=config.manifest_sha256,
        )
        store = Stage5B1BChallengeReviewStore(
            manifest,
            config.artifacts["audit_queue"],
            Path(args.review).resolve()
            if args.review
            else config.artifacts["human_review"],
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
    )


if __name__ == "__main__":
    main()
