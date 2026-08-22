"""Build a self-contained Fly.io deployment bundle for the listening test.

    python -m audio_similarity.cli.build_deploy_bundle \
        --sheets reports/human_eval \
        --manifest data/manifests/fma_small.parquet \
        --queries reports/phase1_queries.csv \
        --audio-root data/fma/fma_small \
        --output deploy_bundle [--app-name my-listening-test]

Only the tracks actually referenced by the sheets (queries + neighbors +
A/B sides) are bundled — typically ~450 MB, not all 8k clips. The bundle
is a complete deploy context: Dockerfile, fly.toml, app source, sheets,
manifest, audio subset, and an attribution CSV (FMA is Creative Commons;
public hosting requires keeping attribution available).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

from audio_similarity.manifest import load_manifest

_DOCKERFILE = """\
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir "pandas>=2.2,<3" "pyarrow>=18"
COPY src ./src
COPY evaluation ./evaluation
COPY reports ./reports
COPY data ./data
ENV PYTHONPATH=/app/src
EXPOSE 8080
CMD ["python", "-m", "audio_similarity.cli.eval_server", \\
     "--host", "0.0.0.0", "--port", "8080", "--no-browser"]
"""

_FLY_TOML = """\
# deploy with: fly launch --no-deploy  then  fly deploy
app = "{app_name}"
primary_region = "iad"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 1

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
"""


def referenced_track_ids(sheets_dir: Path, queries_csv: Path | None) -> set[int]:
    ids: set[int] = set()
    kf = pd.read_csv(sheets_dir / "key_factor.csv")
    ids |= set(kf["neighbor_track_id"].astype(int))
    ka = pd.read_csv(sheets_dir / "key_ab.csv")
    ids |= set(ka["a_track_id"].astype(int)) | set(ka["b_track_id"].astype(int))
    if queries_csv and Path(queries_csv).exists():
        q = pd.read_csv(queries_csv)
        if "track_id" in q.columns:
            ids |= set(q["track_id"].astype(int))
    return ids


def build_bundle(
    sheets_dir: str | Path,
    manifest_path: str | Path,
    queries_csv: str | Path | None,
    audio_root: str | Path,
    output_dir: str | Path,
    app_name: str = "listening-test",
) -> Path:
    root = Path(__file__).resolve().parents[3]
    out = Path(output_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    manifest = load_manifest(manifest_path).set_index("track_id")
    ids = referenced_track_ids(Path(sheets_dir), queries_csv)
    missing = [tid for tid in sorted(ids) if tid not in manifest.index]

    # audio subset preserving relative layout (audio_root-relative paths)
    copied = 0
    for tid in sorted(ids & set(manifest.index)):
        rel = manifest.at[tid, "relative_audio_path"]
        src = Path(audio_root) / rel
        if not src.exists():
            continue
        dst = out / "data" / "fma" / "fma_small" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    # manifest trimmed to the subset (keeps schema + evaluation-only metadata)
    subset = manifest.loc[sorted(ids & set(manifest.index))].reset_index()
    manifest_dst = out / "data" / "manifests" / "fma_small.parquet"
    manifest_dst.parent.mkdir(parents=True, exist_ok=True)
    subset.to_parquet(manifest_dst, index=False)

    # sheets + keys (keys stay server-side inside the image; not exposed via routes)
    sheet_dst = out / "reports" / "human_eval"
    sheet_dst.mkdir(parents=True, exist_ok=True)
    for csv in Path(sheets_dir).glob("*.csv"):
        shutil.copy2(csv, sheet_dst / csv.name)

    # source + UI (eval_server resolves its static dir relative to this layout)
    shutil.copytree(root / "src", out / "src")
    shutil.copytree(root / "evaluation", out / "evaluation")

    # attribution: FMA is Creative Commons — keep credits shipped with any public host
    attrib_cols = ["track_id", "title", "artist", "album", "top_genre"]
    attrib_cols = [c for c in attrib_cols if c in subset.columns]
    if "license" in manifest.columns:
        attrib_cols.append("license")
    subset[attrib_cols].to_csv(out / "ATTRIBUTION.csv", index=False)

    (out / "Dockerfile").write_text(_DOCKERFILE)
    (out / "fly.toml").write_text(_FLY_TOML.format(app_name=app_name))

    size_mb = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"bundle: {out.resolve()}")
    print(f"tracks: {copied}/{len(ids)} ({len(missing)} missing from manifest)")
    print(f"total size: {size_mb:.0f} MB")
    print("next: cd into the bundle and run `fly launch --no-deploy` then `fly deploy`")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheets", default="reports/human_eval")
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--queries", default="reports/phase1_queries.csv")
    parser.add_argument("--audio-root", default="data/fma/fma_small")
    parser.add_argument("--output", default="deploy_bundle")
    parser.add_argument("--app-name", default="listening-test",
                        help="Fly app name (must be globally unique)")
    args = parser.parse_args()

    build_bundle(args.sheets, args.manifest, args.queries, args.audio_root, args.output, args.app_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
