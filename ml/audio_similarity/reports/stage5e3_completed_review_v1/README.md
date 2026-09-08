# Completed Stage 5E.3 human review

Start with [ratings and notes](playlist-review-ratings-and-notes.csv) and
[verification](verification.json). All 98 packets and 419 unique review pairs
were submitted. All 419 exported answers and all 6 notes match the server ledger
exactly. Ratings: 1 = 11, 2 = 44, 3 = 113, 4 = 191, 5 = 60; no UNSURE.

The CSV is the owner's original export, preserved byte-for-byte. Row order is
its frozen blinded packet/candidate order. Notes retain the owner's wording.
The rubric asks whether the songs belong in the same coherent playlist group:
1 definitely not, 2 probably not, 3 borderline, 4 probably, 5 definitely.

The [frozen label snapshot](../stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/post_review_rating_snapshot.json)
contains the original hash-chained submission events, notes, revisions, and
historical labels. Its 1,011 labels include historical evidence beyond the 419
new judgments; this is not 1,011 new reviews. Live mutable review state and audio
are not included. The CSV and snapshot are verified by artifact_manifest.json.

Reviewer checks:

- Confirm CSV identities, notes, counts and ratings against the frozen snapshot.
- Read the six notes about mismatched listening character, particularly lo-fi
  candidates for Shoota, Wet Dreamz, and boys dont cry. These are qualitative
  observations, not evidence of which method wins.
- Review the [revision-2 design](../../docs/designs/stage5e3_revision2.md) and
  [engineering handoff](../stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/handoff.json).
- Scientific method comparison has NOT run. No method winner, final scientific
  verdict, fusion change, or production activation is claimed in this handoff.

After review, the existing post-review commands from ml/audio_similarity are:

```bash
.venv/bin/python -m audio_similarity.cli.stage5e3 analyze
.venv/bin/python -m audio_similarity.cli.stage5e3 closeout
```

Labels are now frozen; the UI cannot accept further submissions to this run.
Further corrections require a separately versioned reviewed workflow.
