"""Extract resumable center5_v1 MIR and opt-in MERIT residual caches."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from audio_similarity.stage2_residuals import (
    extract_track,
    load_config,
    required_track_ids,
    validate_input_hashes,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--enable-heavy", action="store_true", help="load MERT/MERIT and require all three MERIT heads")
    args = p.parse_args()
    cfg, root = load_config(args.config); validate_input_hashes(cfg, root)
    import pandas as pd
    manifest = pd.read_parquet(root / cfg["inputs"]["manifest"]).set_index("track_id")
    ids = required_track_ids(cfg, root); cache_dir = root / cfg["paths"]["cache_dir"]
    encoder = None
    if args.enable_heavy:
        from audio_similarity.merit_encoder import MeritEncoder
        encoder = MeritEncoder.from_pretrained()
    counts = {"EXTRACTED": 0, "EXISTING": 0}; failures = []
    for i, tid in enumerate(ids, 1):
        row = manifest.loc[tid]
        try:
            status = extract_track(root / cfg["paths"]["audio_root"] / row.relative_audio_path,
                                   str(row.audio_sha256), cfg, cache_dir, encoder)
            counts[status] += 1
        except Exception as exc:
            failures.append({"track_id": int(tid), "error": f"{type(exc).__name__}: {exc}"})
        if i % 20 == 0 or i == len(ids): print(f"[{i}/{len(ids)}] extracted={counts['EXTRACTED']} existing={counts['EXISTING']} failures={len(failures)}")
    out = root / cfg["paths"]["report_dir"]; out.mkdir(parents=True, exist_ok=True)
    summary = {"tracks_required": len(ids), "enable_heavy": args.enable_heavy, "counts": counts, "failures": failures}
    (out / "extraction_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if failures: raise RuntimeError(f"residual extraction failed for {len(failures)} tracks; see {out / 'extraction_summary.json'}")
    if not args.enable_heavy: print("MIR complete; MERIT remains intentionally absent until --enable-heavy is supplied.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
