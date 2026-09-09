# Gemini style pilot — contract received, source identity pending

Status: **PREPARED_NOT_RUN_SOURCE_IDENTITY_BLOCKED**. This is a tested preparation
milestone, not a completed pilot. The earlier [preflight report](gemini-style-pilot-preflight.md)
and its frozen artifacts remain unchanged.

The owner supplied `style-pilot-v1-design-contract.md` on September 9, 2026.
It contains all 16 candidate Spotify IDs, the operational ontology, and the exact
response schema. No design files are missing now. All 16 retained recordings
resolve locally and have complete, metadata-stripped FLAC copies. Original audio,
representation caches, correction/quarantine indexes, and map exports pass their
protected hash checks. No audio inference, source replacement, graph change,
rating mutation, or production activation occurred.

**Gemini generation requests: 0. Audio uploads: 0. Model metadata calls: 1
(from the earlier preflight). Generation spend: $0.**

## Remaining identity question

`C04`, **boys dont cry**, Spotify `1ON9XudZFxwu43tQXBszIX`, has the catalog credit
**sysmint**. Its actual retained source is [this ericdoaVault upload](https://www.youtube.com/watch?v=3jTMJRKqR_I),
credited to **ericdoa**. The supplied draft confirms the public Spotify credit,
but it does not establish that this differently attributed recording is the same
audio. Hashes establish which bytes were retained; they do not settle attribution.

The existing owner listening copy is:

```text
C:\Users\bphan\Downloads\Gemini Song Diagnostics\B - Hyperpop and lo-fi\00 - boys dont cry - sysmint.mp3
```

Its SHA-256 is `5674648c0a5a0f29ac94a6b60301f25d9dad49aef27fd28b36f55e10ebf5e92f`.
The diagnostic-copy manifest links it to the same retained source SHA-256,
`91747896537a183bb6aac8dbb486963677a8ac7d5f39c412edb77f9ffaa1d3dc`.
Owner confirmation must concern the **actual recording**, not just approval of a
metadata label. If confirmed, retain both catalog and uploader credits and record
owner-confirmed audio equivalence separately. If it is wrong, resolve an exact
source without substituting a different song or quietly reducing the pilot to 15.

`C05`, **The Peace**, is now resolved under the supplied instruction to use the
exact known corpus recording by stable ID. The source is [underscores' official
video](https://www.youtube.com/watch?v=Gf-fCJ6TkRU), with 173.302 seconds of decoded
audio. This is explicitly the retained video recording, not an asserted byte match
to the 169.500-second Spotify album master, and not the Frost Children remix.

Other documented recording differences include the official video for **The Hills**
(234.185 retained seconds versus 242.253 catalog seconds), **GET IT** (158.708 versus
151.301), and **Perfect Night**'s official choreography video (162.133 versus 159.080).
The complete retained audio is preserved; this does not establish complete album
master coverage. **Shouldn't Be** remains the historical third-party lyric upload,
with matching title/artist and near-matching duration. Official-master equivalence
has not been independently established for that upload.

## Frozen inputs and blinding audit

The complete supplied note was displayed during inspection before predictions.
It combines design, hypotheses and six cited ratings, so the assistant has seen
those expectations. This deviation is explicitly recorded in
`contract_exposure.json`; it must not be described as an assistant-blinded study.
No historical rating inventory was opened to construct model profiles.

Model input construction extracts only the supplied prompt, Section 3 ontology,
and exact JSON schema. The candidate table, hypotheses, controls, owner notes and
rating sections remain outside the request. Track-specific provider text contains
only a neutral `N###` ID and the complete prepared duration. Spotify IDs, titles,
artists and provenance are stored locally. No prompt or taxonomy was tuned after
reading the expectations, and all eventual results remain selected development
diagnostics rather than confirmatory evidence.

| Input | SHA-256 |
| --- | --- |
| Supplied design | `451ccfccb5a3a667b58dad7df904e7d19a2e8b33fa4f88392f131f2843be2c8c` |
| Prompt | `f9f1f530b34a055580e2d58dea5a0eea0c5ea400b2bb10605fd7a91b8dfee4bb` |
| Ontology extraction | `47fe7163378561495b049746d7300d88c4ff10e2ef3b9226e43983c018208dff` |
| Exact response schema | `4cdea0d10f22580fd971c1fd081d56dcf23f6e064ac1ce446c9e60e987acc672` |

## Implementation and verification

The isolated `gemini_style_pilot` package now adds strict contract extraction,
source inventory/preparation, identity-free request construction, content-addressed
profile cache keys, and no-repair schema/semantic validation. It preserves unknown
styles, vocabulary gaps, tentative classifications and non-music as legitimate
outcomes. Invalid JSON, duplicate fields, illegal style/family combinations,
out-of-range timestamps, duplicate assignments and overlong observations fail
validation rather than changing classifications.

The earlier budget guard remains unchanged: no more than 20 generation attempts,
no more than $2, bounded combined thinking/output, immutable attempt reservations,
and fail-closed token accounting. The actual upload/generation orchestration,
smoke gate, validated profile cache replay, repeated requests, owner style review
and post-profile pair join are **not implemented/executed by this milestone**.
An execution manifest has not been falsely declared ready.

Validation passed: **26 focused tests**, and **1,335 full non-heavy tests passed,
12 deselected, 11 warnings** in 126.38 seconds. The initial full-suite run was
interrupted by the sandbox blocking a local HTTP test; the completed rerun had
loopback access. Test output and verification are stored with the public artifacts.
All 16 preparation receipts replay identically with subprocess calls disabled:
zero conversions, identical inventory and protected historical hashes. This is
audio-preparation replay, not a claim of completed Gemini profile-cache replay.
All 31 files in the original frozen preflight artifact manifest also verify
unchanged. All 16 offline request-body checks pass; those use an explicit
placeholder Files API URI and are not provider requests or simulated results.

## Artifacts and continuation

Public review package:
`ml/audio_similarity/reports/gemini_style_pilot/v1/contract_readiness/`.
It contains `source_inventory.json`, `readiness.json`, exact safe `model_inputs/`,
test verification and an artifact hash manifest. It contains no key or raw signed
provider media URLs.

Private run:
`ml/audio_similarity/.research_audio/gemini_style_pilot/style-pilot-v1/`.
New `contract/` and `source_checks/` files preserve the earlier preflight ledger.
`prepared/N001.flac` through `N016.flac` and their receipts pin complete prepared
audio, original/prepared hashes, sample counts and conversion commands. Neutral IDs
are stable preparation identifiers; the local inventory maps them to A01–C06.

After source equivalence is resolved, finish and test paid transport, freeze the
execution manifest, run only the two engineering smokes first, and enforce the
remaining attempt/cost allowance. Freeze every real profile before the historical
rating inventory join or owner style comparison. No scientific conclusion is yet
available.
