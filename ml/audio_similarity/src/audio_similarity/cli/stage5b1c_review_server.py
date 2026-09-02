"""Serve the 11-case blinded Stage 5B.1C Tier-2 safety audit."""
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


MODE = "stage5b1c_tier2_human_audit"
EXPORT_FILENAME = "stage5b1c-tier2-human-review.csv"
SHUFFLE_SALT = "stage5b1c-tier2-human-audit-v1"


def handler_for(store: Stage5B1BChallengeReviewStore):
    return make_review_handler(store, mode=MODE, export_filename=EXPORT_FILENAME)


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(root / "configs" / "stage5b1b_fresh_challenge.json"),
    )
    parser.add_argument(
        "--queue",
        default=str(root / "reports" / "stage5b1c_b" / "tier2_human_audit_queue.json"),
    )
    parser.add_argument(
        "--review",
        default=str(root / "reports" / "stage5b1c_b" / "tier2_human_review.csv"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        config = load_challenge_config(args.config)
        manifest = load_challenge_manifest(
            config.manifest_path, expected_sha256=config.manifest_sha256
        )
        store = Stage5B1BChallengeReviewStore(
            manifest,
            Path(args.queue).resolve(),
            Path(args.review).resolve(),
            session_mode=MODE,
            export_filename=EXPORT_FILENAME,
            shuffle_salt=SHUFFLE_SALT,
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
        server_name="Stage 5B.1C Tier-2 reviewer",
    )


if __name__ == "__main__":
    main()
