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

## Licensing boundary

- MERIT code: MIT
- MERT-v1-330M model card: CC BY-NC 4.0
- MERIT training data / heads: non-commercial (CC BY-NC-SA 4.0 derivatives)
- FMA audio: Creative Commons source audio, track-specific licensing varies

Phase 1 is a non-commercial research/resume experiment. Do not redistribute
derived embedding corpora without license review.
