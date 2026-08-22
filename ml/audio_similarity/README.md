# audio_similarity — Phase 1 (MERIT + FMA)

Phase 1 of the Spotify audio-representation project: evaluate whether **frozen MERIT**
melody/rhythm/timbre embeddings are useful enough to become the foundational audio
representation for the Spotify organizer.

Authoritative design documents live in the Obsidian vault under
`Projects/Spotify Sorter/`:

- `Spotify Audio Representation Phase 1 MERIT FMA Design.md` (primary contract)
- `Spotify Multimodal Song Representation System Design.md` (parent context)

This package is deliberately isolated from the Node/React production application.

## Architecture (published MERIT inference path — do not change casually)

```text
audio -> 24 kHz mono -> truncate/pad to 30 s
  -> MERT-v1-330M [frozen] (ONE shared forward pass)
  -> hidden layers 3, 4, 5, 6, 23
  -> mean-pool each layer over time, concatenate -> 5120-D
  -> head_mel / head_rhy / head_tim   (Linear 5120->512, ReLU, Linear 512->128, L2 norm)
  -> three 128-D unit vectors
```

The expensive MERT backbone forward pass is shared across all three heads.
The pooled 5120-D general-MERT vector is also preserved as Baseline A.

## Setup

Requires `uv` and an NVIDIA GPU is optional but strongly recommended
(MERT-v1-330M runs comfortably in ~2 GB VRAM at fp32).

```bash
cd ml/audio_similarity
uv sync            # creates .venv + uv.lock from pinned sources
```

Torch is pulled from the CUDA 12.4 wheel index (see `pyproject.toml`).
For CPU-only environments, replace the `[tool.uv.sources]` torch/torchaudio
entries with the default PyPI index.

## Model provenance

Pinned artifacts (recorded per-run into experiment metadata):

| Artifact | Value |
|---|---|
| Backbone | `m-a-p/MERT-v1-330M` (exact revision recorded at runtime) |
| Heads | `amaai-lab/merit`: `head_mel/best_head.pt`, `head_rhy/best_head.pt`, `head_tim/best_head.pt` |
| Head integrity | SHA-256 of each `.pt` recorded before loading |

## Tests

```bash
# fast suite (no model downloads; heavy tests deselected by default)
uv run pytest

# deliberate heavy end-to-end smoke test (downloads MERT ~1.3 GB + heads ~33 MB)
uv run pytest -m heavy -o addopts=""
```

The heavy suite is the Stage A gate: 3/3 clips must decode, encode, satisfy the
128-D unit-norm contract, repeat deterministically on the same stack, and give
~1.0 factor cosine for duplicate waveforms.

## Workflow (Phase 1 stages)

```bash
# Stage B: build the frozen manifest
uv run python -m audio_similarity.cli.build_manifest \
    --audio-dir data/fma/fma_small \
    --metadata-csv data/fma/fma_metadata/tracks.csv \
    --output data/manifests/fma_small.parquet

# Freeze the human-eval query set BEFORE inspecting neighbors
uv run python -m audio_similarity.cli.freeze_queries \
    --manifest data/manifests/fma_small.parquet \
    --output reports/phase1_queries.csv

# Stage C/G: resumable batch encode (safe to interrupt and re-run)
uv run python -m audio_similarity.cli.encode_fma \
    --config configs/phase1_fma_small.yaml \
    --audio-root data/fma/fma_small \
    --output-dir artifacts/phase1_full

# Automatic metrics (genre overlap, Jaccard, correlations, latency)
uv run python -m audio_similarity.cli.run_automatic_metrics \
    --embeddings artifacts/phase1_full/embeddings.parquet \
    --features data/fma/fma_metadata/features.csv \
    --manifest data/manifests/fma_small.parquet \
    --output reports/automatic_metrics.json

# Human-eval sheets (blinded; keys kept separate)
uv run python -m audio_similarity.cli.build_eval_sheets \
    --embeddings artifacts/phase1_full/embeddings.parquet \
    --queries reports/phase1_queries.csv \
    --output-dir reports/human_eval

# Listening-test evaluator UI (plays the real MP3s; autosaves ratings)
uv run python -m audio_similarity.cli.eval_server \
    --sheets reports/human_eval \
    --audio-root data/fma/fma_small
# add --host 0.0.0.0 to rate from a phone on the same network
# -> http://127.0.0.1:8616  (Factor Utility tab: 0/1/2/3/X per cell;
#    A/B Compare tab: A/B/Tie/Neither; keyboard: space/Q play, 0-3/X rate,
#    A/B/T/N choose, Enter next unrated)

# Public Pages UI (offline mode): https://lennytheworm12.github.io/spotify-sorter/
# Regenerate its bundle after sheets change (auto-deploys on push):
uv run python -m audio_similarity.cli.export_static_site \
    --sheets reports/human_eval \
    --manifest data/manifests/fma_small.parquet \
    --output site

# After rating: aggregate into the predeclared gates
uv run python -m audio_similarity.cli.summarize_human_eval \
    --sheets reports/human_eval --output reports/human_eval_summary.json
```

Reviewer flow (both modes): enter your name top-right so ratings are
attributed; optional ✎ note per item for later LLM/human review; status
filters (unrated / unrated-by-me / rated-by-me). In offline/Pages mode,
ratings live in the browser — send them back via ☁️ Save to Drive,
📤 Share (native share sheet on phones), ⬇ Export file, or 📋 Copy JSON;
merge locally with ⚙ Import into CSVs (`/api/import`).

Google Drive export (offline mode, works on iPhone Safari): requires a
one-time OAuth Client ID. Steps:

1. <https://console.cloud.google.com> → create/select a project
2. APIs & Services → Library → enable **Google Drive API**
3. APIs & Services → Credentials → Create credentials → **OAuth client
   ID** → type *Web application* → Authorized JavaScript origins:
   `https://lennytheworm12.github.io` and `http://localhost:8616`
4. Paste the client ID (`….apps.googleusercontent.com`) into ⚙ Settings

Uploads land in the reviewer's own Drive as
`listening-test-<name>-<date>.json`; they share it with the maintainer
from the Drive app. Scope is `drive.file` (only files this app created).
If Google auth is blocked (popup blockers etc.), the UI falls back to the
share sheet / clipboard paths.

Phone setup: simplest is opening the LAN-served UI directly
(`http://YOUR-PC-IP:8616` with `--host 0.0.0.0`). The HTTPS Pages site
cannot play HTTP audio directly (browser mixed-content rules), but can
still be used for rating + notes with export/import.

The evaluator is deliberately reusable: it serves whatever blinded sheets +
key files sit in `--sheets`, so future human-input gates (Phase 2 sampling
comparisons, cluster-label checks) can reuse it by generating new sheets.

## Hosting on Fly.io (friends on other networks)

The Pages site can't stream audio from your home machine, so for remote
reviewers deploy the evaluator itself:

```bash
# one-time bundle build (only the ~455 MB of referenced clips, full quality)
uv run python -m audio_similarity.cli.build_deploy_bundle \
    --sheets reports/human_eval \
    --manifest data/manifests/fma_small.parquet \
    --queries reports/phase1_queries.csv \
    --audio-root data/fma/fma_small \
    --output deploy_bundle \
    --app-name your-unique-app-name

cd deploy_bundle
fly launch --no-deploy     # creates the app (needs a fly.io account)
fly deploy                 # builds the image (~455 MB) and ships it
fly status                 # gives you https://your-unique-app-name.fly.dev
```

The container runs the same evaluator in server mode: audio streams from
the VM and ratings persist to the CSVs **inside the running machine**.
Two caveats:

1. **Ratings live on the VM** — copy them back with
   `fly ssh sftp get /app/reports/human_eval/judgments_factor.csv`
   (same for `judgments_ab.csv`) after reviewers finish, or have reviewers
   use the export/import flow. Rebuilding from a fresh bundle wipes VM
   state; `fly ssh sftp put` restored sheets before redeploys that matter.
2. **Licensing**: ATTRIBUTION.csv ships inside the image. Keep the app
   URL unlisted among friends; public promotion of CC-audio hosting needs
   a per-track attribution review.

## Licensing boundary

- MERIT code: MIT
- MERT-v1-330M model card: CC BY-NC 4.0
- MERIT training data / heads: non-commercial (CC BY-NC-SA 4.0 derivatives)
- FMA audio: Creative Commons source audio, track-specific licensing varies

Phase 1 is a non-commercial research/resume experiment. Do not redistribute
derived embedding corpora without license review.
