# Real corpus audit — September 13, 2026

This is an audit and draft execution handoff, not a calibration result. See
[REPORT.md](REPORT.md) and [draft_execution_manifest.json](draft_execution_manifest.json).
The existing calibration harness remains unchanged and synthetic-only.

From `ml/audio_similarity`, capture a fresh audit in a **new** directory:

```bash
.venv/bin/python -m audio_similarity.cli.playlist_calibration_audit capture \
  --output .research_audio/calibration_corpus_audits/NEW_RUN \
  --owner-statement reports/playlist_weight_calibration/v1/corpus_audit/owner_clarification.json \
  --vault-git-dir /tmp/spotify-vault-review
```

The vault argument points to an existing local Git object store containing pinned
commit `1be145263f0e6405a68b3d9a0949ce7218ddc6a4`. This command performs no fetch,
network requests, downloads, decoding, inference, parameter search, or playlist
writes. It requires the original queue to be finished. The active extension is
read once for queue metadata, never used to fit or evaluate anything.

Replay the delivered captured evidence, without rereading the changing queues:

```bash
.venv/bin/python -m audio_similarity.cli.playlist_calibration_audit replay \
  --snapshot .research_audio/calibration_corpus_audits/20260913_owner_confirmed/capture.private.json \
  --output .research_audio/calibration_corpus_audits/REPLAY_RUN
```

Replay verifies the capture hash and implementation hashes, then regenerates the
same audit, draft, source CSV, report and artifact manifest. Existing differing
files fail closed. It does not recheck live source bytes; use a new capture for
that. A new capture may report different extension progress.

Private evidence remains in `.research_audio/calibration_corpus_audits/20260913_owner_confirmed/`:

- `capture.private.json`: source notes, completed queue snapshots, source hashes,
  cache validation receipts, correction overlays and immutable protocol texts.
- `audit.private.json`: per-playlist attrition, sampled request IDs, conservative
  recording groups, every outer/inner partition and candidate catalog, five
  same-audio/different-ID Method C candidates, and both cache-link investigations.
- `source_inventory.private.csv`: 28-row source/curator/eligibility review table.
- `capture_hash.json` and `artifact_manifest.json`: verification identities.

Do not commit private membership/audio. Only aggregate findings and the draft are
published here. Earlier private captures without the `owner_confirmed` suffix
predate the final owner clarification and are not the handoff.

The owner confirmed that each table preserves one external playlist's track list.
Markdown is the manual capture mechanism; no Spotify API is required by this audit.
Original curator attribution remains intact. Self-added genre labels remain discovery
annotations rather than proof of external source intent. The single-owner collapse
is retained as a sensitivity check, not as the owner-confirmed provenance model.

Validation:

```bash
.venv/bin/python -m pytest tests/calibration tests/test_stage5a_cache.py \
  tests/test_reference_batches.py tests/test_reference_dedupe.py -q
```

The source screen uses captured titles, credits and artist counts only. It does
not infer that every “Mix” is algorithmic, infer independent curators from distinct
playlist names, or promote permission-pending metadata to cleared evidence.
Identical title/credits across durations is a conservative purge rule, not a claim
that the recordings are identical. Unrecognized version aliases remain a limitation.

The conditional split audit uses the existing `source_clusters` and
`grouped_folds` machinery with an explicitly non-cleared metadata adapter. It does
not produce a validated `Corpus` that could be used to fit. Full-source duplicate
groups are inherited by sampled playlists, and all seeds/positives/challengers
are subject to recording purges. No lockbox assignment or performance is generated.

Method C verification reads the exact Stage 5E.1 C configuration, source manifest,
sampling plans, pooled vector and every cached view; hashes, normalization,
boundaries and pooled mean must agree. Arm D and full-song MuQ are not substitutes.
Gemini overlap is limited to the existing frozen100 free-genre producer and its
matching registry output; prepared audio, profile and source hashes are checked.
Historical A/MUQ alternatives for Thirsty are reported for later review, not enrolled
by rewriting the original queue. Future reuse still needs a complete aligned bundle.

The protocol's “at least 30 ... when possible” remains an explicit draft question
about eligibility after attrition. Only three of the ten provisional known-curator
samples currently retain 30 usable audio recordings. The harness's two-recording
query minimum is not substituted for the main cohort requirement. Eight credited
groups also fall well short of the reference's 30-group planning target; that target
is not asserted to be a statistical power guarantee.
