# Sixteen-pair musical identity review

Open **http://localhost:8791** while the local reviewer is running. Listen to the two full songs, select the main difference that matters for playlist compatibility, and optionally explain it. “No meaningful mismatch” and “Not sure” are valid answers. “Another difference” needs a short note to count as complete.

Choices save immediately; notes save automatically after a short typing pause. Wait for **Saved to disk** before closing. Unsent drafts also persist in this browser, including after a reload. CSV export includes notes and marks any unsaved browser drafts explicitly. No packet-by-packet Submit button is needed.

To launch or resume from `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.cli.taxonomy_review review --port 8791 --no-browser
```

The default state is `artifacts/stage5g1b_taxonomy_review/v1/answers.sqlite`. It contains answers and an append-only revision ledger. `taxonomy-answers.csv` alongside it is regenerated from the database. The frontend's **Export answers & notes CSV** button also includes browser drafts if a save fails. Old similarity ratings and Stage 5G.1B artifacts are never rewritten.

The packet is frozen at `reports/stage5g1b_taxonomy_review/v1/packet.json`. It contains 16 pairs, 32 distinct tracks, and 46 credited artists with no artist reused across pairs. Four selection strata each contribute four pairs: historical good/bad crossed with higher/lower probe evidence. A separate private artifact records the selection. The browser receives only song identities, local playback URLs, taxonomy choices, and this review's answers—no old ratings, model scores, flags, or strata. This is a deliberately selected development audit, not a sample for estimating library-wide mismatch prevalence.

After completing the review, an explicit freeze command creates a read-only label snapshot and prevents further edits:

```bash
.venv/bin/python -m audio_similarity.cli.taxonomy_review freeze
```

Freezing is optional until you are satisfied with all answers; it does not run analysis or declare a scientific outcome.

## Validation

```bash
.venv/bin/python -m pytest tests/test_taxonomy_review.py -q
.venv/bin/python -m pytest -q
```

`tests/browser_taxonomy_review.py` exercises the real frontend using Playwright. Start a separate server with `--state-dir /tmp/a-fresh-disposable-directory --port 8793 --no-browser`, then run:

```bash
.venv/bin/python tests/browser_taxonomy_review.py --output-dir /tmp/taxonomy-browser-artifacts
```

The browser test requires an empty disposable review session and refuses servers marked as the real reviewer. It checks all 32 audio sources, seeking/HTTP Range, one-at-a-time playback, persistence, offline draft recovery and export, revision conflicts, completion, console errors, and mobile layout. Test answers must stay in the disposable directory. Browser screenshots and verification records accompany the frozen packet.
