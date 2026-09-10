# Gemini pilot owner review

Open **http://127.0.0.1:8794** while the local review server is running.
The interface follows the earlier dark, compact review workbench: full-song
playback, Previous/Next, a song selector, visible saving status, long notes and
CSV export. It contains the same 16 recordings from the completed pilot.

First, listen and describe each song in your own words. Choose whether it is the
intended recording and add a short sound/style description. Vocals, instruments
and section notes are optional; “not sure” is a valid answer. Changes save as you
type. There is no per-song Submit button.

After all 16 are covered, **Save listening pass & compare** preserves those notes
and reveals Gemini's saved descriptions. Review the overall description, its
certainty, any acceptable alternative labels and specific errors. Timestamp
buttons seek within the same recording. Repeated requests, where available,
appear separately; the original profile is never replaced by a repeat.

**Finish review** saves the final snapshot after all comparison answers are
complete. Answers are already saved before that button is pressed. You can tell
the assistant when you are done; an export is optional.

## Saving and recovery

SQLite stores every saved revision. A CSV mirror updates after each save. Browser
drafts also survive reloads and temporarily failed connections. If saving fails,
the page says so and keeps the local draft. Export includes unsaved drafts with
`LOCAL_DRAFT` status. Multi-tab conflicts require an explicit choice between
retrying your draft and reloading the saved answer.

Each note supports 250,000 characters. Oversized content is rejected explicitly,
never silently truncated. CSV export preserves commas, quotes, Unicode and
newlines and escapes spreadsheet formula prefixes.

Your initial listening notes become read-only when you start comparing model
descriptions. Add later corrections in the comparison notes. The browser review
does not change the original Downloads CSV, any earlier human ratings, Gemini
profiles, source audio, representation caches or historical reports.

## Launch or resume

From `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.cli.gemini_style_review --port 8794
```

The server binds only to `127.0.0.1`. Stop it with Ctrl+C; the same command resumes
the saved state. It makes no model/API calls and uses the existing local FLACs.

State lives in `artifacts/gemini_style_pilot_review/duration_v3/`:

- `answers.sqlite`: authoritative answers, revision events and phase snapshots.
- `owner-review-answers.csv`: current saved answers, regenerated from SQLite.
- `independent_snapshot.json`: listening notes saved before model disclosure.
- `owner_snapshot.json`: completed owner review after **Finish review**.

The packet is pinned to the original pilot artifact manifest and profile freeze.
Gemini profile data is withheld by the server until the listening snapshot
exists. This controls disclosure through this frontend; the earlier report and
conversation already discussed some model outputs, so it does not establish an
untouched or naive review. These are owner audio-description judgments, not new
numeric playlist-compatibility labels.

## Verification

```bash
.venv/bin/python -m pytest tests/test_gemini_style_review.py tests/test_taxonomy_review.py tests/test_gemini_style_runner.py -q
.venv/bin/python -m pytest -q
```

For a browser test, use a fresh disposable directory and a separate port:

```bash
.venv/bin/python -m audio_similarity.cli.gemini_style_review --state-dir /tmp/gemini-review-test-fresh --port 8795
.venv/bin/python tests/browser_gemini_style_review.py --output-dir /tmp/gemini-review-browser-evidence
```

The browser test refuses the real review mode and requires an empty disposable
session. It exercises all 16 full FLAC durations, playback and seeking, HTTP Range,
server-side profile withholding, autosave, reload, offline recovery/export,
multi-tab conflicts, long notes, both review passes, final freeze, CSV export,
mobile layout and console errors. No synthetic answers enter the real dataset.

Verification output and screenshots are recorded separately in
`reports/gemini_style_pilot_review/v1/`; the frozen inference package remains
unchanged.

## Genre-neighborhood inspection

Open **http://127.0.0.1:8794/neighborhood**, or choose **Open genre-neighborhood
review** on the earlier review page. The same launch command serves both views.
This view contains only the original 16 songs and their frozen free-form Gemini
labels. It shows canonical concepts, broad families, overlapping neighborhoods,
separate scene/context labels, warnings and every raw-label mapping trace.
Vocal, arrangement and texture descriptions are context only.

Answer two separate questions: whether the mapping is reasonable given the raw
labels, and whether those original labels fit the audio. Optional notes autosave;
CSV export and offline recovery work as in the earlier review. No per-song Submit
is needed. Finish freezes the answers when both questions are covered for all 16.

This review saves separately to `artifacts/genre_neighborhood_review/pilot16/`
(`answers.sqlite`, `owner-review-answers.csv`, and completed `owner_snapshot.json`).
It does not change the earlier listening answers, frozen mapping, Gemini outputs,
playlist ratings or rankings, and makes no model calls.

For isolated browser verification, start the server with a fresh `--state-dir`
and run `tests/browser_genre_neighborhood_review.py --url http://127.0.0.1:8796
--output-dir /tmp/neighborhood-browser-evidence` against that disposable port.

## Frozen 100 with unchanged mapper v1

Open **http://127.0.0.1:8798/neighborhood**. This separate instance uses the exact
100 saved Gemini classifications and prepared full-recording FLACs, without new
API calls. Its source is `reports/gemini_style_pilot/frozen100_free_genre_v1/`;
its frozen mapping packet is `reports/genre_neighborhood_map/v1/frozen100/`.
The original 16-song instance and answers remain separate. Prior answers are not
silently treated as decisions about this expanded review.

```sh
.venv/bin/python -m audio_similarity.genre_neighborhood_frozen100 --serve --port 8798
```

Answers autosave to `artifacts/genre_neighborhood_review/frozen100/`, with the
same CSV export and finish behavior. To reproduce the offline mapping artifacts:

```sh
.venv/bin/python -m audio_similarity.genre_neighborhood_frozen100 --output /tmp/neighborhood100-replay
```

Mapper v1 is unchanged. Unknown/ambiguous labels stay review-required; this run
measures mapping coverage for manual inspection, not musical accuracy or ranking
improvement. No genre penalties, reranking or production changes are enabled.

## Compare the larger vault registry

Open **http://127.0.0.1:8798/compare**, or choose **Compare old mapper / new vault
mapper** in the 100-song review. Old, New vault and Side by side views preserve
the selected song. Search, original Gemini labels, audio, coverage counts and
per-label contribution traces are available. This is read-only; existing answers
remain in the existing review section.

The vault's 138-concept / 29-neighborhood registry and reference implementation
are pinned verbatim in `configs/genre_registry_v1/`, separately from the old
41-concept mapper. The reference mapper uses explicit aliases/composites,
field/relation weights and coordinatewise maximum. Broad concepts, facets,
contexts and gated concepts have no sonic vote. Unknowns are retained.

```sh
.venv/bin/python -m audio_similarity.genre_registry_review
.venv/bin/python -m audio_similarity.genre_neighborhood_frozen100 --serve --port 8798
```

Derived outputs live in `reports/genre_registry_review/v1/frozen100/`. Repeat
mapping verifies existing outputs; use `--output /tmp/registry-replay` for a
separate replay. No API calls, score adjustment, graph movement or reranking
are implemented. Membership weights are not similarity or probability values.
