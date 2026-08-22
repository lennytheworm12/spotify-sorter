"""Export the listening-test UI as a static bundle for GitHub Pages.

    python -m audio_similarity.cli.export_static_site \
        --sheets reports/human_eval \
        --manifest data/manifests/fma_small.parquet \
        --output site

Produces:
    site/index.html    the dual-mode evaluator UI
    site/session.json  rater-safe payload (no representation names, no ids)

On Pages the UI runs in offline mode: ratings/notes live in the reviewer's
browser (localStorage) and can be exported as JSON and merged back via
`POST /api/import` on any machine running the eval server, or via ⚙ Import
in server mode. Audio playback from Pages requires a reachable audio server
(see README phone/mixed-content notes).
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from audio_similarity.eval_store import SheetStore

_STATIC_DIR = Path(__file__).resolve().parents[3] / "evaluation" / "static"


def export(sheets_dir: str | Path, manifest_path: str | Path, output_dir: str | Path) -> Path:
    manifest_path = Path(manifest_path)
    store = SheetStore(sheets_dir, manifest_path, manifest_path.parent / "fma_small")
    # build_session only needs the manifest for titles; audio existence checks
    # are skipped by pointing audio_root at a path we don't verify here.
    session = store.build_session()
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "format": "listening-test-session-v1",
        "factor_cells": session["factor_cells"],
        "ab_trials": session["ab_trials"],
        "progress": session["progress"],
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(_STATIC_DIR / "index.html", out / "index.html")
    with open(out / "session.json", "w") as fh:
        json.dump(payload, fh, indent=1)

    n = len(payload["factor_cells"])
    m = len(payload["ab_trials"])
    print(f"static bundle written to {out.resolve()} ({n} factor cells, {m} A/B trials)")
    print("audio is NOT bundled — reviewers configure an audio server URL in ⚙ Settings")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheets", default="reports/human_eval")
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--output", default="site")
    args = parser.parse_args()
    export(args.sheets, args.manifest, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
