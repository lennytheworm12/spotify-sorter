"""Serve the Stage 5B.1E natural-query targeted human review."""
from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.cli.stage5b1b_review_server import make_review_handler, serve
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b1b_challenge import load_challenge_config, load_challenge_manifest
from audio_similarity.stage5b1e_queries import load_stage5b1e_config
from audio_similarity.stage5b1e_review import Stage5B1EReviewStore


MODE = "stage5b1e_natural_query_human_audit"
EXPORT_FILENAME = "stage5b1e-natural-query-human-review.csv"


def handler_for(store: Stage5B1EReviewStore):
    return make_review_handler(store, mode=MODE, export_filename=EXPORT_FILENAME)


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default=str(root / "configs/stage5b1e_natural_query_evaluation.json")
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8773)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        config = load_stage5b1e_config(args.config)
        challenge = load_challenge_config(config.challenge_config_path)
        manifest = load_challenge_manifest(
            challenge.manifest_path, expected_sha256=challenge.manifest_sha256
        )
        store = Stage5B1EReviewStore(
            manifest,
            config.artifacts["audit_queue"],
            config.artifacts["human_review"],
            export_filename=EXPORT_FILENAME,
        )
    except (FileNotFoundError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    serve(
        store, args.host, args.port,
        open_browser=not args.no_browser,
        mode=MODE,
        export_filename=EXPORT_FILENAME,
        server_name="Stage 5B.1E natural-query reviewer",
    )


if __name__ == "__main__":
    main()
