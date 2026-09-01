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

## Stage 5B.1A2 recording-match review

Review the frozen 25-track yt-dlp discovery experiment in the local browser UI:

```bash
uv run python -m audio_similarity.cli.stage5b1a2_review_server
# http://127.0.0.1:8767
```

The page opens each of the five ordered candidates on YouTube and saves explicit
rank/`NOT_IN_TOP_5`/`UNCERTAIN` judgments plus optional notes directly to
`reports/stage5b1a_ytdlp/ytdlp_review.csv`. Watching a candidate never labels
it. Saves are atomic and resume from the existing CSV; use **Export CSV** for a
portable copy. No audio or video is downloaded by the review server.

## Stage 5B.1B held-out candidate review

Stage 5B.1B exposes hierarchical recording-identity and source-quality evidence
without selecting a final AUTO_MATCH threshold. Verify or reproduce the
metadata-only artifacts from `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.cli.stage5b1b verify
.venv/bin/python -m audio_similarity.cli.stage5b1b dev
.venv/bin/python -m audio_similarity.cli.stage5b1b artifacts --overwrite
```

The frozen held-out discovery is already complete. Review each candidate in
`reports/stage5b1b/heldout_review.csv` by filling
`candidate_review_label` with `IDEAL`, `ACCEPTABLE`, `WRONG`, or `UNCERTAIN`;
optional candidate and track notes have dedicated columns. Multiple candidates
may be IDEAL or ACCEPTABLE, and a track need not have an IDEAL candidate. Do
not regenerate the review after labels are entered.

## Stage 2B balanced holistic fusion benchmark

Stage 2B is a stage-gated corrective benchmark over the frozen 40-query
universe. It compares CLAP, MERT-5120, and MuQ using identical `center5_v1`
evidence, encoder-neutral identity duplicate rules, and new multi-rater labels.
Stage 1A and Stage 2A remain immutable.

```bash
# Validate frozen inputs and deterministically regenerate the 16/8/16 split.
uv run python -m audio_similarity.cli.stage2b_contract

# Build the balanced disagreement trials from validated local embeddings/audio.
uv run python -m audio_similarity.cli.build_stage2b_trials

# Focused contract/trial tests (retrieval tests are network-free).
uv run pytest tests/test_stage2b_contract.py tests/test_stage2b_trials.py
```

The Stage 2B contract and split must be committed and pushed before disagreement
retrieval. Collect independent ratings only through the isolated exact-PCM mode:

```bash
uv run python -m audio_similarity.cli.stage2b_eval_server
# http://127.0.0.1:8620 — requires a stable non-empty rater ID
```

The server plays raw little-endian float32 `center5_v1` samples and maintains
append-only authoritative, TRAIN/VALIDATION-only, and TEST-only blinded exports.
The approved `single_reviewer_v2` analysis amendment narrows conclusions to the
designated reviewer's preferences while preserving the selection/TEST lock:

```bash
uv run python -m audio_similarity.cli.freeze_stage2b_ratings \
  --config configs/holistic_stage2b_fusion_single_reviewer.yaml
uv run python -m audio_similarity.cli.build_stage2b_dataset \
  --config configs/holistic_stage2b_fusion_single_reviewer.yaml
uv run python -m audio_similarity.cli.select_stage2b_model \
  --config configs/holistic_stage2b_fusion_single_reviewer.yaml
```

TEST scoring remains locked until a pushed train/validation selection artifact
exists. After that checkpoint is tracked, clean, committed, and pushed, reveal
TEST exactly once (the command refuses an existing output):

```bash
uv run python -m audio_similarity.cli.evaluate_stage2b_test \
  --config configs/holistic_stage2b_fusion_single_reviewer.yaml

# After reveal, verify existing hashes without rerunning selection or TEST.
uv run python -m audio_similarity.cli.evaluate_stage2b_test \
  --config configs/holistic_stage2b_fusion_single_reviewer.yaml --verify
```

Stage 2B closed under `single_reviewer_v2` as **`SINGLE_ENCODER_WINS`**.
LAION-CLAP achieved 0.7719 held-out query-macro accuracy versus 0.7594 for
the validation-preselected CLAP+MuQ fusion (difference -0.0125; paired 95%
query-bootstrap CI [-0.1260, 0.0969]). This is personal perceptual-alignment
evidence for the designated reviewer, not a population-level claim.

## Stage 2A residual signal screen

Stage 1 is closed as a constrained preliminary pilot. Stage 2A is an
**exploratory, unfitted** screen over the frozen labels—not a final encoder,
population, production, or inter-rater study. It independently checks tonal,
rhythm, timbre, and MERIT component margins against provisional CLAP and
MERT-5120 baselines. It does not train a reranker or select fusion weights.

Listeners heard full FMA clips, while all Stage 2A baseline/residual inputs use
the exact deterministic centered five-second `center5_v1` excerpt at 24 kHz
mono. The decision report preserves this stimulus/input limitation.

```bash
# MIR extraction is network-free and resumable; this deliberately leaves MERIT absent
uv run python -m audio_similarity.cli.extract_stage2_residuals \
  --config configs/holistic_stage2a_residual_screen.yaml

# Required real experiment: opt-in heavy MERT/MERIT inference.
# Cached Hugging Face weights make this offline; uncached weights require deliberate acquisition.
uv run python -m audio_similarity.cli.extract_stage2_residuals \
  --config configs/holistic_stage2a_residual_screen.yaml --enable-heavy

# Build the canonical 136-trial feature table and run 50,000 query bootstraps
uv run python -m audio_similarity.cli.score_stage2_residual_screen \
  --config configs/holistic_stage2a_residual_screen.yaml
```

Scoring is deterministic and network-free. Local feature/model caches remain
ignored; only lightweight config, canonical table, summaries, and reports are
versioned under `reports/holistic_stage2a/`.

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

## Phase 2 pre-gate framework (encoder-agnostic)

While the Phase 1 human gate is open, these pieces are safe to build and use
(design sections 9, 29, 47, 50):

| Module | Purpose |
|---|---|
| `sampling.py` | Deterministic versioned segment strategies: first30, center30, three20, three30, five20, dense30_hop15 (terminal-anchor rule) |
| `aggregation.py` | MeanL2 v1 song embedding + typed failures |
| `encoder.py` | Minimal `AudioEncoder` protocol + deterministic `FakeEncoder` (no models) |
| `signal_views.py` | Deterministic waveform / linear-STFT / log-mel PNG renderers with full provenance; no metadata inputs exist |
| `ox_alpha.py` | Strict comparison schema (A/B/Tie/Abstain), versioned prompt, fake client, JSONL resume cache, request budget guardrail |
| `cli/ox_alpha_smoke.py` | Live-gated smoke runner — refuses without `--live` **and** `OPENROUTER_API_KEY`; prints model/prompt/renderer/planned-count/cap/cache before any request |

Fast tests never download models or call providers:

```bash
uv run pytest
```

Optional live smoke (spends requests; requires credentials):

```bash
export OPENROUTER_API_KEY=...
uv run python -m audio_similarity.cli.ox_alpha_smoke --live \
    --model <model-id> --cases 6 --max-requests 54
```

Phase 2 config: `configs/phase2_full_song_sampling.yaml`. The full sampling
matrix waits for the Phase 1 human gate; see the vault Phase 2 design doc.

## Holistic encoder benchmark (Stage 1A — active)

Benchmarking MuQ-MuLan-large vs MERT variants vs LAION-CLAP on identical
frozen 5-s excerpts, selected by blinded human overall-similarity preference.

```bash
# encode corpus per encoder (resumable)
uv run python -m audio_similarity.cli.encode_holistic --encoder all

# rebuild retrieval unions + blinded A/B sheets
uv run python -m audio_similarity.cli.build_holistic_sheets

# serve rating UI with both MERIT and holistic sheets live
mkdir -p reports/live_sheets && cp reports/human_eval/*.csv reports/live_sheets/ \
  && cp reports/holistic_stage1a/holistic_*.csv reports/holistic_stage1a/holistic_trial_keys.json reports/live_sheets/
uv run python -m audio_similarity.cli.eval_server --sheets reports/live_sheets --host 0.0.0.0
```

No tunnel is required for local rating: use `http://127.0.0.1:8616` on the
host, or `http://<host-LAN-IP>:8616` from a device on the same network. The
active constrained pilot tracks coverage of all 136 available blinded trials
with at least one judgment each; additional independent judgments remain
useful. Use **⬇ Export overall ratings** in the toolbar to download the
authoritative CSV, including reviewer attribution and append-only choice logs.

Report: `reports/holistic_encoder_stage1a.md`. Model licenses: MuQ weights
CC-BY-NC-4.0 (code MIT); CLAP/MERT research use. Heavy model deps (`muq`,
`laion-clap`) are only needed for encoding/rating, not for fast tests.

## Licensing boundary

- MERIT code: MIT
- MERT-v1-330M model card: CC BY-NC 4.0
- MERIT training data / heads: non-commercial (CC BY-NC-SA 4.0 derivatives)
- FMA audio: Creative Commons source audio, track-specific licensing varies

Phase 1 is a non-commercial research/resume experiment. Do not redistribute
derived embedding corpora without license review.
