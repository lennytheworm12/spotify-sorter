"""Build the canonical Stage 2A table and run the deterministic unfitted screen."""
from __future__ import annotations
import argparse
import hashlib

from audio_similarity.stage2_residuals import build_trial_table, load_config, validate_input_hashes
from audio_similarity.stage2_screen import score_table, write_outputs


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--config", required=True); args = p.parse_args()
    cfg, root = load_config(args.config); checked = validate_input_hashes(cfg, root)
    table, raw = build_trial_table(cfg, root); result = score_table(table, cfg)
    manifest = write_outputs(table, raw, result, cfg, root, checked)
    print(f"canonical={len(table)} raw_judgments={len(raw)} primary_ab={result['denominators']['primary_ab']}")
    for family, decision in result["family_decisions"].items(): print(f"{family}: {decision['status']}")
    print(f"table_sha256={manifest['table_sha256']}")
    print(f"metrics_sha256={manifest['metrics_sha256']}")
    print(f"report_sha256={manifest['report_sha256']}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
