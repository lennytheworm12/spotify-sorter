# Combined corpus redesign — run the next stage on all processed audio

**Status:** DESIGN · supersedes the extension-only scope of `execution_contract_v4.json`
**Owner:** Bi Phan · **Date:** 2026-09-15

## 1. Goal

Today the authorized run covers only the **extension** (1,135 recordings / 14 development playlists). The
redesign makes the next stage — the weight search — run over **all processed audio**: the original corpus
and the extension as one combined corpus.

| | Playlists | Recordings | Valid profiles | Pairwise artifacts |
|---|---|---|---|---|
| Original corpus | 28 | **1,924** | 1,922 (2 deferred) | `masked_bundle_v1/` Jc, Jnr, R, mask |
| Extension | 17 | **1,135** | 1,135 (0 missing) | `feature_snapshot_v2/` Jc, Jnr, R, M, C_center30, C_method_c, mask |
| **Combined** | **45** | **3,059** | 3,057 (2 deferred) | to be built (this design) |

3,059 recordings matches the "about 3k" target. The two corpora are currently **separate by design** — the
extension README states the extension "remains separate from the original corpus" — and that separation is
what this redesign removes.

## 2. Why this is feasible

Every input needed is already **per-recording**, so the union can be assembled locally:

- Method C per-recording vectors (`features/<recording_id>.json` + the verified Method C matrix)
- Companion cached vectors per recording (laion_clap → C_center30, muq_mulan_large → M) in the audited vector DB
- Per-recording Gemini profiles (1,922 + 1,135) and their unchanged canonical mappings
- The unchanged mapper (138-concept / 29-neighborhood)

**No new API calls, no new audio inference.** The build is matrix assembly: cosine matrices over per-recording
vectors plus the genre-side pair matrices.

## 3. Build plan

```
combined/feature_snapshot_v1/
  recording_ids.json          ordered; original ids ∪ extension ids, sorted, deduped
  C_method_c.npy              cosine matrix over 3,059 per-recording Method C vectors
  C_center30.npy              cosine matrix over companion laion_clap vectors
  M.npy                       cosine matrix over companion muq_mulan_large vectors
  Jc.npy  Jnr.npy  R.npy      genre-side matrices, combined
  genre_pair_valid.npy        false where either member lacks a valid profile
  profile_status.json         per-recording: VALID_SPECIFIC_STYLE | VALID_NONINFORMATIVE
                              | UPLOAD_QUOTA_BLOCKED_NO_PROFILE (the 2 deferred)
  manifest.json               counts, hashes, invariants, cost accounting
  roles/development_candidates/  combined development split  (submatrix)
  roles/confirmation_candidates/ combined confirmation split (submatrix)
```

Invariants preserved exactly as the existing artifacts define them:

- explicit recording order; matrices symmetric; audio cells finite and bounded
- genre cells valid only where `genre_pair_valid` is true; `R = (1-Jc)*Jnr` exact
- missing profiles are **NaN plus a false validity mask** — never zero, never valid-unknown
- confirmation membership-recovery results stay uncomputed and uninspected

## 4. Gates before the build runs

1. **Pin the original corpus role catalog.** The extension split is available
   (`role_catalogs_v3/{development,confirmation}_candidates/catalog.private.json`, 14 / 5 playlists). The
   original corpus's development/confirmation assignment must be located and pinned by path+hash first —
   without it the combined split cannot be defined. *(Not found in `reports/playlist_weight_calibration/v1/`
   or the extension run dirs during this design pass; it lives with the original calibration work.)*
2. **Re-verify zero overlap** between the corpora on three axes: recording ID, audio SHA-256, and
   conservatively linked version families. The extension README asserts zero for ID/hash/version overlap
   with the original corpus; the build recipe must re-assert it as a hard gate rather than trusting the prose.
3. **Confirm the 2 deferred profiles stay deferred.** They mask out; the combined corpus runs with
   3,057 valid rather than silently dropping rows.

## 5. Cost and compute

| Item | Value |
|---|---|
| Matrices | ~7 × 3,059² × 8 B ≈ **525 MB** total |
| Cosine matrices | trivial (single matmul over 3,059 vectors) |
| Genre matrices | the heavy part — sharded CPU pass over 3,059 profiles |
| API spend | **$0** (no new calls) |
| Audio inference | **0** (all vectors cached) |

## 6. Risks, stated plainly

1. **Cross-corpus pairs are new evidence.** 1,924 × 1,135 ≈ 2.18 M pairs have never been evaluated. They are
   mechanically valid (same representations, same mapper) but they were not part of either corpus's prior
   validation. The combined run's results are therefore not a superset of previous findings — they are a new
   measurement.
2. **Version-family links may cross corpora.** The extension's conservative version grouping was computed
   within the extension. Combining may surface cross-corpus version families that neither corpus's purge
   logic saw. Gate 2 covers the overlap check; any new cross-corpus family must be retained conservatively
   (never adjudicated during the search).
3. **Split geometry changes what "development" means.** Fitting on the combined development split is a
   different experiment from fitting on the extension's 14 playlists. The original corpus's own confirmation/
   lockbox set must not be inspected to make this work.
4. **Permission status is unchanged.** `permission_supported=false`; approval to run is an owner
   authorization, not a clearance. Nothing here changes that, and results must not be represented as
   permission-cleared.

## 7. What changes in the contract

`execution_contract_v4.json` authorized the search on the extension's development split. The redesign
(superseding `execution_contract_v5.json`) will:

- widen `accepted_scope` to the combined corpus (45 playlists / 3,059 recordings / 3,057 valid)
- keep `weight_search_approved=true`, `permission_supported=false`, and every retained condition
- add `combined_build` authorization with the three gates above as preconditions
- keep the confirmation set reserved: combined confirmation = original confirmation ∪ extension confirmation,
  still uninspected

---

## Split definition (added 2026-09-15 — gate 1 resolved)

Generated by `make_combined_split_v1.py` from the retained protocol rule
(protocol v11 §9 "Split design: what is actually held out", plus the realized
partitions in `calibration_corpus_audit_v1`). This replaces the open gate 1.

**Rule applied:** candidates are the curated `genre_focused_candidate` sources;
generated Mixes (`mix_or_radio_source_review_required`) and single-artist sources
(`single_artist_excluded`) are evidence-only and enter neither fitting nor
evaluation. Playlists are clustered by curator / duplicate overlap
(same curator OR recording-set Jaccard ≥ 0.8 OR smaller-list containment ≥ 0.9)
and **clusters are never split across fit and evaluation**.

| Role | Playlists | Recordings | What it means |
|---|---|---|---|
| **learn_and_train** | 20 | 1641 | the fit set: original fit clusters + extension development candidates |
| **held_out_validation** | 3 | 319 | model selection only, never fitted on |
| **lockbox_reserved** | 5 | 485 | extension confirmation candidates — opened **once**, after the procedure is locked |
| **evidence_only** | 17 | 855 | generated Mixes + single-artist sources; excluded by cohort rule |

Leaked recordings (present in both a fit group and an evaluation/lockbox group):
**20 purged** from the fit set. Clusters formed: **9**.

Recording counts are membership-weighted (playlists overlap — 3300 across groups
vs 3167 unique, i.e. 117 multi-playlist overlaps).

- `split_id`: `3a147d5dd4f721225c7c670ab06e13c3e0b902a28d532c65c12c7f5d6171ba5b`
- `split_manifest_v1.private.json` sha256: `2163f0be994246e75fa3de22e428692d40d6d319ab6f81c853030493f255467d`
- seed: `combined-split-v1` (deterministic; re-running reproduces the same split)

**Gate status after this step:** gate 1 RESOLVED · gate 2 PASS (0 overlap) · gate 3 CONFIRMED
(3,057 valid / 2 deferred) · **gate 4 OPEN** — the combined pairwise build itself.
