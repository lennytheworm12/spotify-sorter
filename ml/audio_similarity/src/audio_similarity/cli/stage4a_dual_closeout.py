"""Generate or verify the frozen Stage 4A closeout artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage4a_dual_closeout import CloseoutError, build_closeout


def render(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


def write_or_verify(path: Path, content: str, verify: bool) -> None:
    if verify:
        if not path.exists():
            raise CloseoutError(f"missing closeout artifact: {path}")
        if path.read_text() != content:
            raise CloseoutError(f"closeout verification failed: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    metrics, artifact = build_closeout(root)
    report_dir = root / "reports/holistic_stage4a_dual"
    write_or_verify(report_dir / "final_metrics.json", render(metrics), args.verify)
    write_or_verify(
        report_dir / "audio_representation_v1.json",
        render(artifact),
        args.verify,
    )
    print(render(artifact), end="")


if __name__ == "__main__":
    main()
