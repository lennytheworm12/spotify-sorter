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
