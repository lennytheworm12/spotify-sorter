# Append-only chart catalog expansion

The initial 534-recording cohort and Batches 0001–0002 remain frozen. Expansion
does not repack Batch 0002 or change either batch's runtime state.

From `ml/audio_similarity`, finish all unattempted Spotify queries in the existing
collected chart input, then freeze newly matched recordings:

```sh
.venv/bin/python -m audio_similarity.chart_catalog_complete
```

This performs Spotify metadata work only. Each pass has at most 500 searches,
uses existing serial request pacing, and reuses successful checkpoints. Provider
errors (including 429 and active cooldown) abort immediately. Rerun to resume;
do not bypass the persisted cooldown. No YouTube discovery, downloads, or model
inference is started.

The current 3,429 literal-song input bounds the number of passes. Completion means
zero `PENDING` queries in that input, **not** complete global chart coverage or a
match for every song. No-exact-match/ambiguous outcomes remain excluded. Existing
market/year/source gaps are preserved explicitly; matching does not repair them.

New immutable `extension_XXXX/` directories pin the expanded matching snapshot
and preceding artifact inventories. Previously scheduled recording editions are
excluded by Spotify identity and the existing recording comparator. New tracks
retain seeded ordering and receive batches of at most 500, starting at Batch 3.
Repeated expansion with unchanged input is a no-op. Every batch uses the same
provider circuit/cooldown directory, so changing batch cannot bypass a block.

Runtime metadata progress lives in the ignored
`.research_audio/chart_catalog_v1/expansion_progress.json`; final expansion results
are in `expansion_result.json`. Matching reports are content-addressed.

After the command finishes, inspect the reported batch range. Run a new download
batch only by explicit command, for example:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m audio_similarity.cli.stage5d0a resume --batch 3
```

There is no automatic next-batch execution.
