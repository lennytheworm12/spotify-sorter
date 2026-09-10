---
title: Spotify Genre Mapping v1 — Research and Design
project: Spotify Sorter
status: proposed-not-production-validated
mapping_version: genre-neighborhood-v1-draft
source_commit: 190a12596968ed84245aa1a880cdfae97214fe94
---

# Spotify Genre Mapping v1 — Research and Design

## Decision

Keep Gemini's raw genre labels and audio descriptions immutable. Add a **typed, versioned concept registry** that resolves spelling variants, preserves meaningful style distinctions, and derives **overlapping musical neighborhoods**. Use those neighborhoods as candidate evidence for a later small CLAP adjustment—not as playlist membership, a new audio classifier, or a canonical truth about every song.

This draft specifies 12 broad background families, 29 narrower overlapping neighborhoods and 138 concepts (styles, broad families, contexts and modifiers). These counts are implementation scope, not a claim about how many genres exist. The larger registry includes extension vocabulary; only supported, observed concepts need to participate in the first experiment. No API inference, playlist changes, embedding changes, live graph changes or reranking were performed for this design.

**The JSON is the machine-readable source of the proposed mapping. This note explains its meaning.** Source references support terminology and qualitative relationships, not the numerical membership defaults or proof of playlist usefulness. All definitions are project-authored operational scopes; none is an exhaustive musicological definition.

## 1. Research findings that change the design

AllMusic distinguishes broad genres from narrower styles and separately distinguishes moods and activity-related themes [S01]. Discogs explicitly permits combined genres and separates broad genres from styles [S02]. MusicBrainz uses subjective community genre tags with an expandable vocabulary [S03]. Research on the AcousticBrainz Genre Dataset deliberately retains multiple taxonomies and hierarchy levels rather than assuming different communities use identical labels [S05]. These sources support a multi-label design, not a universal numeric genre-distance table.

Three consequences follow for this project:

1. **Alias equality, genre relationship and playlist compatibility are different.** `rnb` and `R&B` can resolve to the same family. Alternative R&B and neo-soul should remain distinct concepts connected to the same neighborhood. Their shared neighborhood does not prove two specific recordings belong together.
2. **Production, vocal role, cultural scene and musical style must not be silently merged.** A low-fidelity texture is not automatically lo-fi hip-hop; a soundtrack is not automatically classical; K-pop can contain multiple sonic styles [S01, S16, S19]. Context can matter in a later playlist-intent model, but the first sonic prior must state when it uses it.
3. **Shared ancestry does not dictate pairwise playlist distances.** Boom bap and lo-fi hip-hop share musical vocabulary [S06–S08, S21]. A useful system should preserve this overlap, not falsify their history to force separation. Different vocals and arrangements may require separate evidence.

### Important corrections to the earlier proposal

- Keep `electronic` broad; do not rename every electronic recording `electronic_dance`. Downtempo/downbeat includes electronic listening music that is not organized around a dance-floor role [S12].
- Do not make `ambient_experimental` one all-purpose family. Ambient and generic experimental orientation are different kinds of evidence [S13].
- Give hyperpop its own retained concept and a digital-pop neighborhood. Do not automatically map it into ambient or require uninterrupted speed/loudness [S14].
- Do not force `lo-fi`, `instrumental hip-hop`, `chillhop` and `lo-fi hip-hop` into one alias. Some sources use chillhop and lo-fi hip-hop interchangeably; preserving separate canonical IDs while allowing a shared neighborhood is the conservative choice [S07, S08, S21].
- Do not collapse Afrobeat and Afrobeats. MusicBrainz explicitly lists them as different concepts [S04]. Do not create a single sonic bucket for all African, Asian or Latin music.
- An album-level label does not verify every track or every retained audio source. City Girl's own album page supplies a multi-tag view of *Goddess of the Hollow*, but does not authenticate a Gemini description of the local *Pray* recording [S18].

## 2. Architecture

`original model profile → alias/composite resolution → typed concepts → overlapping neighborhoods → separate compatibility experiment`

The registry records four principal kinds of information:

| Kind | Examples | Effect in the first sonic-neighborhood experiment |
|---|---|---|
| Broad family | electronic, pop, hip-hop, R&B/soul | Background context and coverage, not a blanket attraction rule |
| Specific style | boom bap, neo-soul, future bass, minimal techno | Can contribute to defined neighborhoods |
| Cultural/scene context | K-pop, K-R&B, Mandopop, K-indie | Preserve for inspection; zero geographic/scene penalty or bonus by default |
| Facet / broad modifier | lo-fi, acoustic, experimental, singer-songwriter, cinematic | Preserve separately; no hidden genre classification |

The few `style_context` and `style_umbrella` registry entries preserve mixed or broad uses without pretending they carry specific acoustic information. An unresolved compound such as `African Dancehall and Reggae` remains visible with a review-required result. It does not become a fictional universal genre.

Concept types are determined by the resolved term, **not solely by Gemini's field name**. Gemini can place a specific style such as Ambient in `primary_family`; the mapper recognizes its specific concept while retaining the original field and label.

## 3. Broad families

These are background navigation/lineage groupings, not equidistant playlist classes. They are not exhaustive; unrepresented traditions are preserved as unmapped/contextual labels until explicitly modeled. No `other` or `unknown` family creates similarity between unrelated unknown songs.

| ID | Operational scope |
|---|---|
| `hip_hop` | Hip-hop-derived musical styles, including vocal rap and instrumental forms. Never infer foreground rapping from this family alone. |
| `rnb_soul` | R&B and soul traditions, including contemporary, alternative and neo-soul branches. Not all singing is R&B. |
| `pop` | Pop songwriting and its established stylistic branches. Does not mean every popular recording. |
| `electronic` | Electronic musical traditions. A synthesizer or electronic production tag alone does not make a song a genre member; electronic does not imply dance-floor function. |
| `rock` | Rock and related stylistic branches. Guitar presence alone is insufficient. |
| `folk` | Explicitly identified folk traditions or folk styles. Acoustic timbre alone is insufficient; do not collapse unrelated traditions into one usable playlist. |
| `jazz` | Jazz-derived musical styles. A jazz sample alone need not make an entire recording jazz. |
| `blues` | Explicit blues styles and traditions, distinct from generic sad mood. |
| `funk` | Funk-derived groove styles. Keep separate from generic R&B; cross-memberships are allowed. |
| `classical` | Classical and explicitly identified contemporary classical styles. Soundtrack use and piano instrumentation alone are insufficient. |
| `country` | Country and country-derived styles. Acoustic guitar alone is insufficient. |
| `reggae` | Reggae-derived styles, with explicit substyles retained rather than one Caribbean bucket. |


For Afrobeats, Afrobeat, bossa nova and reggaeton, the registry keeps named style concepts and separate neighborhoods. Their listed background family associations are project retrieval associations, not a complete historical genealogy. No whole-continent or whole-language sonic equality is introduced.

## 4. The overlapping neighborhoods

A neighborhood is a small set of related **styles**, not a current Song Space Louvain community and not a playlist. Its ID must stay independent of whichever artists happen to lead a displayed region. Broad family names can be useful explanations, but an arbitrary root-to-root path length must not become a musical distance.

The first ten entries cover the central R&B, rap, lo-fi, pop and hyperpop use cases. More specific electronic neighborhoods avoid collapsing everything from ambient to hard techno into one equal membership. The remaining entries preserve coherent scope for other observed or anticipated labels. Sparse extension regions are not claimed to be evaluated.

| ID | Neighborhood | Scope |
|---|---|---|
| `rnb_soul` | R&B / soul | Contemporary R&B, alternative R&B, neo-soul and explicit R&B/soul hybrids; preserves a common neighborhood across substyles. |
| `boom_bap_jazz_hop` | Boom bap / jazz-hop | Sample-oriented hip-hop and jazz-rap stylistic territory. Does not require or forbid lead rap. |
| `lofi_chillhop` | Lo-fi / chillhop | Explicit lo-fi-beat and chillhop styles. Not a synonym for all hip-hop instrumentals or all low-fidelity audio. |
| `instrumental_hip_hop` | Instrumental hip-hop | Explicit beat-led instrumental hip-hop styles, potentially energetic or experimental; not inherently lo-fi. |
| `trap_cloud_rap` | Trap / cloud-rap styles | Trap and related cloud/melodic/emo rap territory. Retains each fine label; no assumption all such songs belong together. |
| `downtempo_trip_hop` | Downtempo / trip-hop | Downtempo, trip-hop and chillout stylistic territory; related to but not identical to lo-fi beats or ambient. |
| `pop_song` | Pop songwriting | Specific pop-song styles. Raw broad Pop alone does not activate this neighborhood in the conservative mapping. |
| `indie_dream_pop` | Indie / dream / bedroom pop | Indie-pop, dream-pop and bedroom-pop stylistic territory; distinct fine labels survive. |
| `synthetic_pop` | Synth / dance-pop | Synth-pop, electropop and dance-pop; no automatic house/techno classification. |
| `hyperpop_digital_pop` | Hyperpop / digital pop | Explicit hyperpop and reviewed digital-pop neighbors. Not generic ambient, fast music, electronic music, or all processed vocals. |
| `house_disco` | House / nu-disco | House variants and related contemporary disco production; full subtype identities retained. |
| `techno` | Techno | Techno variants, with minimal, dub, industrial and hard variants retained. This is not all electronic music. |
| `trance` | Trance | Explicit trance styles. Not implied by atmospheric synthesizers. |
| `dnb_jungle` | Drum-and-bass / jungle | Drum-and-bass/jungle styles with fine subtypes such as neurofunk retained. |
| `dubstep_bass` | Dubstep / bass styles | Explicit dubstep, future-bass and related bass styles. Broad Bass Music alone is too ambiguous for a confident fine relationship. |
| `ambient_drone` | Ambient / drone | Explicit ambient/drone music, rather than every atmospheric recording. |
| `experimental_electronic` | Experimental electronic | Specific glitch/IDM/deconstructed electronic styles. Generic Experimental is a modifier and does not activate a universal cluster. |
| `rock_alternative` | Rock / alternative rock | Explicit rock-derived styles, with punk/metal/shoegaze labels retained, not collapsed into identical songs. |
| `folk_acoustic_song` | Folk / acoustic songwriting | Explicit acoustic-pop and folk-songwriter styles, not any recording that contains acoustic instruments. |
| `jazz` | Jazz styles | Explicit jazz styles; broad-only Jazz is display metadata until supported by more specific evidence. |
| `blues` | Blues styles | Explicit blues substyles; reserve until present in the corpus. |
| `funk_disco` | Funk / disco | Specific funk/disco styles; not a synonym for danceable or soulful. |
| `classical` | Classical styles | Explicit classical substyles. Soundtrack and cinematic alone are excluded. |
| `country_americana` | Country / Americana | Explicit country and Americana styles, with finer identities preserved. |
| `reggae_dancehall` | Reggae / dancehall | Explicit reggae, dub and dancehall styles; not all Caribbean music. |
| `afrobeats` | Afrobeats | Contemporary Afrobeats vocabulary. Distinct from Afrobeat, Afro house and the continent of Africa. |
| `afrobeat` | Afrobeat | Explicit Afrobeat tradition; retain separately from contemporary Afrobeats. |
| `bossa_nova` | Bossa nova | Explicit bossa nova style. Not all Latin music or all jazz. |
| `reggaeton` | Reggaeton | Explicit reggaeton style. Not any Spanish-language song. |


## 5. Key mappings

**Core** and **related** are proposed membership relations, not confidence or calibrated genre probabilities. Exact canonical labels survive alongside the neighborhood vector.

| Canonical style | Core neighborhoods | Additional related neighborhoods | Deliberately not inferred |
|---|---|---|---|
| contemporary R&B | R&B/soul | — | Pop, trap or acoustic style solely because these are common influences |
| alternative R&B | R&B/soul | — | Ambient/indie rock without additional explicit labels |
| neo-soul | R&B/soul | — | Jazz genre solely from harmonic color |
| pop-R&B / pop-soul | R&B/soul | Pop songwriting | That the two canonical terms are exact synonyms |
| trap soul / trap R&B | R&B/soul | Trap/cloud rap | That all trap with singing is R&B |
| boom bap | Boom-bap/jazz-hop | — | Rap-led vocal role or lo-fi membership |
| lo-fi hip-hop | Lo-fi/chillhop | Boom-bap/jazz-hop; downtempo/trip-hop | No vocals, or maximum separation from rap |
| chillhop | Lo-fi/chillhop | Boom-bap/jazz-hop; downtempo/trip-hop | Identical production fidelity to every lo-fi track |
| instrumental hip-hop | Instrumental hip-hop | — | Lo-fi, chill, boom bap or low energy |
| trap | Trap/cloud rap | — | EDM trap, R&B or ambient |
| trip-hop | Downtempo/trip-hop | Boom-bap/jazz-hop | Synonymy with lo-fi hip-hop |
| dream pop | Indie/dream pop | — | Ambient music merely because it is atmospheric |
| ambient pop | Indie/dream pop | Ambient/drone | Purely ambient or beatless |
| hyperpop | Hyperpop/digital pop | Synthetic pop | Ambient, fixed BPM, unbroken loudness |
| future bass | Dubstep/bass styles | Synthetic pop | Hard techno or generic hip-hop trap |
| minimal techno | Techno | — | Generic sparse music or downtempo |
| nu-disco | House/nu-disco | Funk/disco; synthetic pop | Every dance-pop recording is nu-disco |

The quantitative JSON includes provisional extensions such as pluggnb, rage rap and digicore. Entries marked `mapping_review_required` produce no sonic membership until their mapping is reviewed. Recognition of a label is different from authorization to use its numerical effect. In particular, adding Hyperpop to the registry does not reclassify any existing sysmint or underscores track by artist identity.

### Why related styles need not be aliases

`Alt-R&B → alternative_rnb` is alias normalization. `alternative_rnb → rnb_soul` is neighborhood membership. `alternative_rnb ↔ neo_soul` is a relationship between different styles. Keeping the three operations separate prevents expanding the vocabulary from silently rewriting evidence.

### Worked example: dispersed R&B

Synthetic profile A: Alternative R&B + Ambient Pop. Synthetic profile B: Neo-soul + Pop-soul.

Both acquire a core R&B/soul membership, but A also retains its ambient-pop/indie-pop relationship and B its pop-soul identity. This gives a later prior a common semantic signal without requiring the two recordings to have identical CLAP neighborhoods. The result is **shared evidence**, not an automatic accepted pairing.

### Worked example: boom bap and lo-fi

A boom-bap label has core membership in the boom-bap/jazz-hop neighborhood. A lo-fi-hip-hop label has core membership in lo-fi/chillhop and related membership in boom-bap/jazz-hop. Thus they overlap, but their derived profiles are not identical.

Do not hardcode that boom bap must always be closer to trap than to lo-fi. That universal ordering does not follow from genre history and could reject compatible pairs. The proposed relative memberships are a testable prior, not a musicological theorem.

**Limit:** two recordings with the same labels receive the same genre profile. A genre-only method cannot distinguish a vocal boom-bap recording from a boom-bap instrumental when the supplied labels are identical. If the important difference is foreground rap versus beat-led listening, test the existing `vocal_role` and `arrangement_focus` as a separately named genre-plus-attributes variant. Do not quietly smuggle those attributes into genre-only results.

## 6. Alias, composite and ambiguity policy

Normalization is deliberately mechanical: Unicode NFKC; casefold; replace hyphen variants and underscores with spaces; translate `&` into the word `and`; collapse whitespace. Then resolve only against an explicit alias table.

Do not strip every punctuation character, stem words, fuzzy-match unknown labels, or ask an LLM to make up a fresh mapping at comparison time. The final `s` in Afrobeats matters. Slashes can indicate a real compound or an ambiguity, not necessarily synonyms.

| Input | Result |
|---|---|
| `R&B`, `rnb`, `RnB` | Same broad R&B/soul concept |
| `Alt-R&B`, `alternative_rnb` | Same alternative-R&B concept |
| `DnB`, `D&B`, `Drum and Bass` | Same drum-and-bass concept |
| `Soul` vs `R&B` | Distinct retained concepts, connected to the same broad family |
| `Electronica` vs `Electronic` | Preserve the separate umbrella term, not exact synonymy |
| `Dance/Electronic` | Electronic family + broad dance context; no automatic house/techno membership |
| `K-Pop` + `Contemporary R&B` | K-pop context retained; the explicit R&B style contributes to R&B/soul |
| `Korean Ballad` | Scene/context + ballad form; no inferred R&B or acoustic arrangement |
| `Lo-fi` | Production facet only; no automatic lo-fi-hip-hop genre |
| `Afrobeat` vs `Afrobeats` | Separate canonical style concepts |
| `Hard Techno` vs `Future Bass` | Separate styles and neighborhoods even though both can be electronic |
| `Ambient/Shoegaze` | Unmapped unless that exact compound is explicitly added; do not guess |
| `African Dancehall and Reggae` | Review-required ambiguous compound, no sonic vote |

Unknown labels remain verbatim with an unresolved status. Unresolved items do not enter a shared Unknown cluster and must not cause repulsion from every known song.

## 7. Derived profile and aggregation

The included `mapper_reference.py` is a local reference normalizer. It preserves every original genre string, records field-level mapping traces, and emits canonical concepts, background families, overlapping neighborhood memberships and unresolved labels. It does **not** classify audio, map artist names, change scores or assign playlists.

Proposed defaults, explicitly not learned or calibrated:

- Specific label appearing in primary style: weight 1.0; secondary style: 0.5.
- Specific style appearing in primary family: 0.5; secondary family: 0.25. This handles mixed hierarchy levels without promoting broad words.
- Core membership multiplier: 1.0; related membership: 0.5.
- Combine duplicate contributions with coordinatewise maximum, not addition.
- Broad-family concepts, scene tags, generic modifiers and unresolved labels contribute zero to the sonic neighborhood vector.
- Self-reported Gemini certainty is retained, not treated as a numerical probability.

Formally, for known specific concepts c contributing to neighborhood n:

`g_n(x) = max_c [field_strength(c, x) × relation_strength(c, n)]`.

The coordinates need not sum to one. They represent overlapping support, not a probability distribution. No automatic transitive propagation is allowed: hyperpop related to electronic does not make it a member of every electronic subgenre.

Keeping canonical fine labels alongside g matters: house and microhouse may share a neighborhood without being identical styles. Later comparisons should inspect fine-label agreement, broader-neighborhood overlap, specificity and missingness separately, rather than throwing away the fine layer.

## 8. Scoring boundary

The mapping is specified; a validated ranking adjustment is not. Keep the agreed interface:

`S_adjusted(a,b) = S_CLAP_C(a,b) + lambda × r_style(a,b)`.

Requirements: symmetry, bounded adjustment, exact zero-weight baseline, explicit unknown no-op, and preservation of original scores. Neither shared genre nor map adjacency constitutes an admission threshold. The adjusted value is a ranking score, not raw cosine or a calibrated playlist probability.

Do not use `negative adjustment = no shared genre`. A missing association may mean unknown, mixed granularity, a rare style, or a legitimate cross-style pairing. The draft intentionally supplies **no hardcoded incompatibility matrix**. Negative adjustment requires a separately specified and evaluated mismatch rule.

First compute descriptive candidate features: fine-style overlap; neighborhood overlap; specific mapped coverage; broad-only coverage; context-only status. A bounded overlap statistic, such as weighted Jaccard, can describe relatedness; its value does not by itself justify either a boost or a penalty. The sign/strength calibration belongs to the experiment contract.

Broad-only R&B, Pop or Electronic evidence is initially too coarse for a sonic adjustment. Specific R&B styles still share the R&B neighborhood, so the cross-subtype use case is preserved without a generic broad-word attractor. A broad-family fallback can be a separately reported ablation rather than silently introduced.

## 9. Evidence audit and evaluation before activation

The existing frozen100 Gemini export is explicitly unreviewed model output. Schema-valid is not musically correct. Its source identity relies on previously retained recordings, not a new listening audit [R01]. The older Discogs-derived experiment also used a hierarchical soft prior; it did not establish a ranking gain. It had unchanged held-out orderings, unrated replacements for apparent bad-neighbor removals, and known-good losses in an all-candidate diagnostic [R02]. Changing the label source does not erase that result.

### Stage A — map and inspect, without scores

Run the mapper on the complete local CSV. Report every raw label, canonical result, counts, aliases, unresolved concepts, and neighborhood occupancy. Report mapping coverage separately from audio classification accuracy. Audit possible source/classification errors without replacing labels based on artist reputation or existing pair outcomes. Preserve original profiles and source hashes; any later corrections require a separate versioned evidence layer.

Check whether a better broad mapping is hiding a wrong specific label. The *Pray* example is illustrative: collapsing Hard Techno and downtempo into Electronic would hide their distinction, not solve the classification issue. Artist-supplied album tags can motivate an audio check, not authorize silently relabeling the local recording [S18].

### Stage B — development-only ranking study

Use the existing playlist-compatibility rubric, not pooled audio-description or holistic-similarity labels. Keep the same CLAP C scores, candidate identities and candidate budget. Compare unchanged CLAP, exact canonical-label features, and neighborhood features. Any genre-plus-vocals/arrangement variant is separate. Keep duplicate/source groups together and report artist grouping/overlap. Freeze the normalization table before selecting score strengths; choose any strength only within development and include zero.

Count wrong good-versus-bad orderings corrected, correct orderings broken, tie transitions, affected anchors and unique pairs. At fixed Top-K, count good retained/lost/added, bad removed/added, intermediate entries and unknown replacements separately. A bad-to-unknown replacement is not a verified improvement. Protect accepted cross-style pairs and inspect same-style bad pairs. Report concentration by artist/region and sensitivity after excluding the motivating cases.

### Stage C — fresh confirmation

The repeatedly inspected 100-song set is development evidence. Repartitioning it does not make it fresh. Freeze the ontology, mapping and score procedure before a track/source-disjoint confirmatory review, preferably artist-disjoint when practical. Require benefit beyond one motivating pair or artist and a predeclared tolerance for good-match damage. Set those numerical acceptance criteria using development goals, not after seeing confirmatory results. No new review queue or paid inference is created by this document.

## 10. Astra handoff

> Implement only the immutable genre-label mapper from genre-neighborhood-map-v1.json and its coverage report against the pinned frozen100 classifications. Preserve raw labels and descriptions. Maintain typed concepts, exact alias resolution, explicit composite rules, overlapping memberships, field-level traces, and unresolved/no-op behavior. Use the supplied tests as engineering fixtures, not music truth. Inspect all unmapped or review-required labels; do not invent track- or artist-specific exceptions. Report mapping coverage, neighborhood occupancy, and classification/source concerns separately. Do not change CLAP/MuQ embeddings, candidate rankings, map coordinates, or playlist behavior. Then propose one bounded score-adjustment experiment with unchanged CLAP C control, corrected-vs-damaged accounting, cross-style protection, development-only parameter selection and fresh-evaluation requirements. Do not execute that ranking experiment as part of the mapping stage.

Suggested location in the project: `ml/audio_similarity/configs/genre_neighborhood_v1.json`. Suggested vault note: `Projects/Spotify Sorter/Spotify Genre Mapping v1 — Research and Design.md`. These are proposed destinations, not paths already written in your local repository or vault.

## 11. Verification performed here

Forty synthetic engineering tests passed: alias consistency, concept/source references, immutable inputs, duplicate handling, unknown no-op, specificity/type rules, ambiguity handling, deterministic replay and bounded membership values. The tests verify the mapper matches the draft design—not that the draft musical relationships improve recommendations.

The complete raw 100-song CSV is not bundled. It was available as connector-returned text, not mounted as a local file. Therefore this package does not claim a freshly computed full-corpus coverage percentage or listening accuracy. The CLI produces the exact coverage audit when run on the user's local CSV. No real Gemini outputs have been relabeled by this package.

From this package directory:

```bash
python -m unittest -v test_mapping
python mapper_reference.py   --input /path/to/spotifyProject/ml/audio_similarity/reports/gemini_style_pilot/frozen100_free_genre_v1/classifications.csv   --output /path/to/new-derived-report/mapped_profiles.json
```

The CLI refuses to overwrite an existing output. It records the input and mapping hashes and preserves Spotify identities. It reports `classification_accuracy: not_assessed` and `score_adjustment: null`.

## Appendix A — Complete concept registry

The following definitions and memberships are project-authored design decisions. Source IDs identify terminology/relationship references, not claimed validation of weights. Empty neighborhoods are intentional for broad, contextual or insufficiently specific concepts. Review-required entries must not generate sonic votes until reviewed.

| ID | Kind | Definition | Neighborhood memberships | Review first? | Sources |
|---|---|---|---|---|---|
| `family:hip_hop` | family | Hip-hop-derived musical styles, including vocal rap and instrumental forms. Never infer foreground rapping from this family alone. | — | No | S01, S02, S04 |
| `family:rnb_soul` | family | R&B and soul traditions, including contemporary, alternative and neo-soul branches. Not all singing is R&B. | — | No | S01, S02, S04 |
| `family:pop` | family | Pop songwriting and its established stylistic branches. Does not mean every popular recording. | — | No | S01, S02, S04 |
| `family:electronic` | family | Electronic musical traditions. A synthesizer or electronic production tag alone does not make a song a genre member; electronic does not imply dance-floor function. | — | No | S01, S02, S04 |
| `family:rock` | family | Rock and related stylistic branches. Guitar presence alone is insufficient. | — | No | S01, S02, S04 |
| `family:folk` | family | Explicitly identified folk traditions or folk styles. Acoustic timbre alone is insufficient; do not collapse unrelated traditions into one usable playlist. | — | No | S01, S02, S04 |
| `family:jazz` | family | Jazz-derived musical styles. A jazz sample alone need not make an entire recording jazz. | — | No | S01, S02, S04 |
| `family:blues` | family | Explicit blues styles and traditions, distinct from generic sad mood. | — | No | S01, S02, S04 |
| `family:funk` | family | Funk-derived groove styles. Keep separate from generic R&B; cross-memberships are allowed. | — | No | S01, S02, S04 |
| `family:classical` | family | Classical and explicitly identified contemporary classical styles. Soundtrack use and piano instrumentation alone are insufficient. | — | No | S01, S02, S04 |
| `family:country` | family | Country and country-derived styles. Acoustic guitar alone is insufficient. | — | No | S01, S02, S04 |
| `family:reggae` | family | Reggae-derived styles, with explicit substyles retained rather than one Caribbean bucket. | — | No | S01, S02, S04 |
| `style:contemporary_rnb` | style | Modern R&B stylistic umbrella; retain alternatives and hybrids. | rnb_soul (core) | No | S09 |
| `style:alternative_rnb` | style | Left-field R&B; no automatic indie-rock, electronic or ambient membership without additional evidence. | rnb_soul (core) | No | S09 |
| `style:neo_soul` | style | R&B/soul with explicit classic-soul-oriented identity; not every warm keyboard sound. | rnb_soul (core) | No | S10 |
| `style:pop_rnb` | style | Explicit pop/R&B hybrid, retained separately from pop-soul. | rnb_soul (core); pop_song (related) | No | S09, S04 |
| `style:pop_soul` | style | Explicit pop/soul hybrid. | rnb_soul (core); pop_song (related) | No | S09 |
| `style:trap_soul` | style | Explicit R&B/trap hybrid label; not all trap with singing. | rnb_soul (core); trap_cloud_rap (related) | No | S04, S08 |
| `style:trap_rnb` | style | Explicit trap/R&B composite; related to trap soul but not silently rewritten as an exact synonym. | rnb_soul (core); trap_cloud_rap (related) | No | S04, S08 |
| `style:indie_rnb` | style | Loose independent/alternative R&B label; does not itself establish acoustic indie-pop similarity. | rnb_soul (core) | Yes | S04, S09 |
| `style:quiet_storm` | style | Explicit quiet-storm R&B style, not just low energy. | rnb_soul (core) | No | S09 |
| `style:boom_bap` | style | Hip-hop style/production centered on emphatic kick-snare patterns and sampling traditions; vocals remain separate. | boom_bap_jazz_hop (core) | No | S06 |
| `style:jazz_rap` | style | Explicit jazz/hip-hop fusion; vocal role must come from the recording rather than inferred from name alone. | boom_bap_jazz_hop (core); jazz (related) | No | S04, S06 |
| `style:jazzhop` | style | Jazz-influenced beat/hip-hop term with variable usage; not automatically a jazz-rap synonym. | boom_bap_jazz_hop (core); instrumental_hip_hop (related) | Yes | S04, S21 |
| `style:lofi_hip_hop` | style | Explicit lo-fi hip-hop style. Production aesthetic is not an automatic no-vocals rule. | lofi_chillhop (core); boom_bap_jazz_hop (related); downtempo_trip_hop (related) | No | S07, S08, S21 |
| `style:lofi_beats` | style | Beat-oriented lo-fi descriptor. Related to lo-fi hip-hop but preserve the broader wording. | lofi_chillhop (core); instrumental_hip_hop (related); downtempo_trip_hop (related) | No | S07, S21 |
| `style:chillhop` | style | Chill hip-hop/beat style; preserve separately from lo-fi hip-hop because fidelity need not be identical. | lofi_chillhop (core); boom_bap_jazz_hop (related); downtempo_trip_hop (related) | No | S08, S21 |
| `style:instrumental_hip_hop` | style | Hip-hop instrumental style, including non-lofi and non-chill examples. | instrumental_hip_hop (core) | No | S04 |
| `style:trap` | style | Hip-hop trap style; distinguish explicit EDM trap when supplied. | trap_cloud_rap (core) | No | S08 |
| `style:melodic_trap` | style | Melody-forward trap label; not identical to all melodic rap or R&B. | trap_cloud_rap (core) | No | S04, S08 |
| `style:melodic_rap` | style | Melodically delivered rap style. Does not force trap production or R&B membership. | trap_cloud_rap (core) | No | S04 |
| `style:emo_rap` | style | Explicit emo-rap style; emotional lyrics alone are insufficient. | trap_cloud_rap (core) | No | S04 |
| `style:cloud_rap` | style | Explicit cloud-rap label; atmospheric production does not make it ambient music. | trap_cloud_rap (core) | No | S04 |
| `style:pop_rap` | style | Explicit pop/rap crossover. | trap_cloud_rap (core); pop_song (related) | No | S04 |
| `style:plugg` | style | Explicit plugg trap-related style; preserve separately from pluggnb. | trap_cloud_rap (core) | No | S04 |
| `style:pluggnb` | style | Explicit plugg/R&B-related hybrid; provisional overlap, not an exact alias of plugg or contemporary R&B. | trap_cloud_rap (core); rnb_soul (related) | Yes | S04 |
| `style:rage_rap` | style | Explicit synth-forward rage-rap style; loudness alone is insufficient. | trap_cloud_rap (core); hyperpop_digital_pop (related) | Yes | S04, S14 |
| `style:drill` | style | Explicit drill styles; preserve regional subtypes when supplied. | trap_cloud_rap (core) | No | S04 |
| `style:conscious_hip_hop` | style | Lyrical/thematic hip-hop designation. Supplies hip-hop context but no automatic boom-bap similarity. | — | No | S04 |
| `style:east_coast_hip_hop` | style_context | Regional hip-hop designation; does not imply boom bap in every recording. | — | No | S04, S06 |
| `style:chopped_and_screwed` | style | Explicit slowed/reworked hip-hop style and technique; not every pitched vocal. | trap_cloud_rap (core) | No | S04 |
| `style:phonk` | style | Phonk hip-hop vocabulary; not automatically drift phonk or phonk house. | trap_cloud_rap (core) | No | S17 |
| `style:drift_phonk` | style | Specific drift-phonk variant; preserve rather than collapse to all phonk. | trap_cloud_rap (core); dubstep_bass (related) | Yes | S17 |
| `style:dance_pop` | style | Pop style oriented around dance rhythms; not identical to house or techno. | synthetic_pop (core); pop_song (core) | No | S01, S04 |
| `style:synth_pop` | style | Synth-led pop style; distinct from electro and synthwave. | synthetic_pop (core); pop_song (related) | No | S01, S04 |
| `style:electropop` | style | Electronic pop style; related to synth-pop but retained separately. | synthetic_pop (core); pop_song (related) | No | S01, S04 |
| `style:indie_pop` | style | Explicit indie-pop stylistic label, not every independent release. | indie_dream_pop (core); pop_song (related) | No | S01, S04 |
| `style:bedroom_pop` | style | Bedroom-pop aesthetic/scene label; no assumption of a particular recording venue. | indie_dream_pop (core); pop_song (related) | No | S01, S04 |
| `style:dream_pop` | style | Atmospheric pop/rock style; not automatically ambient music. | indie_dream_pop (core) | No | S01, S04 |
| `style:alternative_pop` | style | Broad alternative-pop style, retained separately from indie pop and art pop. | pop_song (core); indie_dream_pop (related) | No | S01, S04 |
| `style:art_pop` | style | Explicit art-pop designation; not synonymous with all experimental music. | pop_song (core) | No | S01, S04 |
| `style:bubblegum_pop` | style | Explicit bright hook-oriented bubblegum-pop label. | pop_song (core); synthetic_pop (related) | No | S01, S04 |
| `style:pop_rock` | style | Explicit pop/rock hybrid. | pop_song (core); rock_alternative (related) | No | S01, S04 |
| `style:piano_pop` | style | Explicit piano-pop style, distinct from solo piano classical music. | pop_song (core); folk_acoustic_song (related) | No | S01, S04 |
| `style:acoustic_pop` | style | Explicit acoustic-pop style, not a rule based only on instrument presence. | folk_acoustic_song (core); pop_song (related) | No | S01, S04 |
| `style:ambient_pop` | style | Pop with ambient-oriented identity; retain both song and atmospheric aspects. | indie_dream_pop (core); ambient_drone (related) | No | S01, S04 |
| `style:downtempo_pop` | style | Explicit pop/downtempo hybrid, not all slow pop. | pop_song (core); downtempo_trip_hop (related) | No | S01, S04 |
| `style:hyperpop` | style | Explicit exaggerated/digitally processed pop style. Active-section density may matter, but speed, constant loudness and ambient membership are not requirements. | hyperpop_digital_pop (core); synthetic_pop (related) | No | S14 |
| `style:digicore` | style_context | Distinct internet music/scene term. Preserve as a concept; review its sonic mapping before activation instead of treating it as a hyperpop synonym. | — | Yes | S04 |
| `style:bubblegum_bass` | style | Explicit digital pop/bass style; not generic bubblegum pop. | hyperpop_digital_pop (core); synthetic_pop (related) | Yes | S04, S14 |
| `style:downtempo` | style | Electronic listening-style umbrella; not a measured tempo adjective. | downtempo_trip_hop (core) | No | S12 |
| `style:trip_hop` | style | Downtempo experimental electronic/hip-hop-related style. | downtempo_trip_hop (core); boom_bap_jazz_hop (related) | No | S11 |
| `style:chillout` | style | Loose chillout stylistic label. Not all calming music, and not necessarily lo-fi. | downtempo_trip_hop (core) | No | S12 |
| `style:chillwave` | style | Specific hazy electronic-pop style; not a chillhop alias. | indie_dream_pop (core); synthetic_pop (related); downtempo_trip_hop (related) | No | S04, S02 |
| `style:house` | style | Explicit house music. | house_disco (core) | No | S04, S02 |
| `style:deep_house` | style | Specific house branch. | house_disco (core) | No | S04, S02 |
| `style:microhouse` | style | Minimal/detail-focused house branch; related to but not synonymous with minimal techno. | house_disco (core) | No | S04, S02 |
| `style:afro_house` | style | Specific house style; neither a synonym for Afrobeats nor all African electronic music. | house_disco (core) | No | S04, S02 |
| `style:amapiano` | style | Specific South African house-related style; do not normalize to Afrobeats. | house_disco (core) | No | S04, S02 |
| `style:nu_disco` | style | Contemporary disco-oriented style. | house_disco (core); funk_disco (related); synthetic_pop (related) | No | S04, S02 |
| `style:techno` | style | Explicit techno style. | techno (core) | No | S04, S02 |
| `style:minimal_techno` | style | Specific techno branch; do not equate with generic minimal electronic. | techno (core) | No | S04, S02 |
| `style:dub_techno` | style | Techno with dub-oriented techniques, not ordinary reggae dub. | techno (core); ambient_drone (related) | No | S04, S02 |
| `style:hard_techno` | style | Specific harder techno style, distinct from future bass and downtempo. | techno (core) | No | S04, S02 |
| `style:industrial_techno` | style | Techno with industrial textures. | techno (core); experimental_electronic (related) | No | S04, S02 |
| `style:schranz` | style | Specific hard-techno vocabulary, not an electronic umbrella synonym. | techno (core) | No | S04, S02 |
| `style:trance` | style | Explicit trance style. | trance (core) | No | S04, S02 |
| `style:drum_and_bass` | style | Specific electronic breakbeat/bass style. | dnb_jungle (core) | No | S04, S02 |
| `style:jungle` | style | Jungle breakbeat tradition; related to DnB but retained distinctly. | dnb_jungle (core) | No | S04, S02 |
| `style:neurofunk` | style | Specific drum-and-bass branch; not funk merely because the name contains funk. | dnb_jungle (core) | No | S04, S02 |
| `style:dubstep` | style | Specific electronic bass style; not a dub-reggae alias. | dubstep_bass (core) | No | S04, S02 |
| `style:future_bass` | style | Synth-heavy bass music with trap/dubstep influences; not hard techno. | dubstep_bass (core); synthetic_pop (related) | No | S15 |
| `style:uk_garage` | style | Specific garage rhythmic tradition; not garage rock. | house_disco (core); dubstep_bass (related) | No | S04, S02 |
| `style:breakbeat` | style | Breakbeat genre umbrella; exact rhythm patterns alone should be stored as a facet. | dubstep_bass (core); dnb_jungle (related) | No | S04, S02 |
| `style:edm_trap` | style | Explicit dance/bass-music sense of trap, separate from hip-hop trap. | dubstep_bass (core); trap_cloud_rap (related) | No | S04, S02 |
| `style:ambient` | style | Explicit texture-focused ambient style; not a synonym for atmospheric. | ambient_drone (core) | No | S13 |
| `style:drone` | style | Explicit drone style. | ambient_drone (core) | No | S13 |
| `style:idm` | style | Intelligent dance music / experimental electronic style umbrella. | experimental_electronic (core) | No | S04, S02 |
| `style:glitch` | style | Glitch as a named musical style; glitchy timbre alone remains a texture facet. | experimental_electronic (core) | No | S04, S02 |
| `style:deconstructed_club` | style | Explicit experimental-club style, not an automatic synonym for hyperpop. | experimental_electronic (core); dubstep_bass (related) | No | S04, S02 |
| `style:experimental_electronic` | style | Explicit experimental-electronic style; narrower than Experimental alone. | experimental_electronic (core) | No | S04, S02 |
| `style:indie_rock` | style | Explicit indie-rock style; not all independent music. | rock_alternative (core) | No | S04 |
| `style:alternative_rock` | style | Explicit alternative-rock style. | rock_alternative (core) | No | S04 |
| `style:shoegaze` | style | Specific layered guitar-derived rock style; not every hazy song. | rock_alternative (core); indie_dream_pop (related) | No | S04 |
| `style:punk` | style | Specific punk stylistic umbrella. | rock_alternative (core) | No | S04 |
| `style:metal` | style | Specific metal stylistic umbrella; retain substyles for later expansion. | rock_alternative (core) | No | S04 |
| `style:indie_folk` | style | Explicit indie-folk style. | folk_acoustic_song (core) | No | S04 |
| `style:contemporary_folk` | style | Explicit contemporary-folk style; not a universal traditional-music bucket. | folk_acoustic_song (core) | No | S04 |
| `style:folk_pop` | style | Explicit folk/pop hybrid. | folk_acoustic_song (core); pop_song (related) | No | S04 |
| `style:vocal_jazz` | style | Jazz style with a vocal designation; details of voice remain separate. | jazz (core) | No | S04 |
| `style:jazz_funk` | style | Explicit jazz/funk fusion. | jazz (core); funk_disco (related) | No | S04 |
| `style:bossa_nova` | style | Specific Brazilian style. Its jazz relationship does not make all Latin music one style. | bossa_nova (core); jazz (related) | No | S04 |
| `style:disco` | style | Explicit disco style; distinct from every dance rhythm. | funk_disco (core); house_disco (related) | No | S04 |
| `style:modern_classical` | style | Named contemporary classical music label; not all cinematic or instrumental music. | classical (core) | No | S04 |
| `style:chamber_music` | style | Explicit chamber-music classification. | classical (core) | No | S04 |
| `style:americana` | style | Named American roots style; not a nationality tag. | country_americana (core); folk_acoustic_song (related) | No | S04 |
| `style:alternative_country` | style | Explicit alternative-country style. | country_americana (core) | No | S04 |
| `style:dancehall` | style | Named reggae-derived style, not merely music for a dance hall. | reggae_dancehall (core) | No | S04 |
| `style:dub` | style | Reggae-derived dub style; not equivalent to dubstep or dub techno. | reggae_dancehall (core) | No | S04 |
| `style:afrobeats` | style | Specific contemporary Afrobeats umbrella; preserve the final s. | afrobeats (core) | No | S04 |
| `style:afrobeat` | style | Specific Afrobeat tradition; preserve separately from Afrobeats. | afrobeat (core); funk_disco (related) | No | S04 |
| `style:reggaeton` | style | Specific reggaeton style; not any Spanish-language music. | reggaeton (core) | No | S04 |
| `context:k_pop` | context | Preserve scene, cultural or broad regional descriptor. No regional match bonus or penalty in the audio-style experiment; explicit sonic labels are mapped separately. | — | No | S16, S19 |
| `context:k_rnb` | context | Preserve scene, cultural or broad regional descriptor. No regional match bonus or penalty in the audio-style experiment; explicit sonic labels are mapped separately. | — | No | S16, S19 |
| `context:j_pop` | context | Preserve scene, cultural or broad regional descriptor. No regional match bonus or penalty in the audio-style experiment; explicit sonic labels are mapped separately. | — | No | S16, S19 |
| `context:mandopop` | context | Preserve scene, cultural or broad regional descriptor. No regional match bonus or penalty in the audio-style experiment; explicit sonic labels are mapped separately. | — | No | S16, S19 |
| `context:cantopop` | context | Preserve scene, cultural or broad regional descriptor. No regional match bonus or penalty in the audio-style experiment; explicit sonic labels are mapped separately. | — | No | S16, S19 |
| `context:k_indie` | context | Preserve scene, cultural or broad regional descriptor. No regional match bonus or penalty in the audio-style experiment; explicit sonic labels are mapped separately. | — | No | S16, S19 |
| `context:asian_pop` | context | Preserve scene, cultural or broad regional descriptor. No regional match bonus or penalty in the audio-style experiment; explicit sonic labels are mapped separately. | — | No | S16, S19 |
| `context:latin` | context | Preserve scene, cultural or broad regional descriptor. No regional match bonus or penalty in the audio-style experiment; explicit sonic labels are mapped separately. | — | No | S16, S19 |
| `context:african_traditional` | context | Preserve scene, cultural or broad regional descriptor. No regional match bonus or penalty in the audio-style experiment; explicit sonic labels are mapped separately. | — | No | S16, S19 |
| `context:west_african_folk` | context | Preserve scene, cultural or broad regional descriptor. No regional match bonus or penalty in the audio-style experiment; explicit sonic labels are mapped separately. | — | No | S16, S19 |
| `facet:lofi` | facet | Low-fidelity aesthetic without an explicit genre. Do not infer lo-fi hip-hop. | — | No | S01, S19 |
| `facet:acoustic` | facet | Acoustic timbre/production descriptor, not automatically folk. | — | No | S01, S19 |
| `facet:experimental` | facet | Experimental orientation; no single homogeneous sonic family. | — | No | S01, S19 |
| `facet:indie` | facet | Independent/alternative descriptor without sufficient sonic specification. | — | No | S01, S19 |
| `facet:singer_songwriter` | facet | Creator/songwriting context, not necessarily acoustic or folk. | — | No | S01, S19 |
| `facet:ballad` | facet | Song-form/style modifier; not automatically R&B, pop or acoustic. | — | No | S01, S19 |
| `facet:piano_ballad` | facet | Piano/ballad descriptor; not a classical assignment. | — | No | S01, S19 |
| `facet:minimalism` | facet | Ambiguous between compositional tradition and sparse aesthetic unless context resolves it. | — | No | S01, S19 |
| `facet:easy_listening` | facet | Broad listening-use/style umbrella; no automatic ambient, classical or lo-fi assignment. | — | No | S01, S19 |
| `facet:cinematic` | facet | Cinematic character/use descriptor; no automatic classical assignment. | — | No | S01, S19 |
| `facet:soundtrack` | facet | Release/use context, not a sonic genre. | — | No | S01, S19 |
| `facet:dance` | facet | Insufficiently specific dance umbrella. Do not assume house, techno or a measured rhythm. | — | No | S01, S19 |
| `facet:bass_music` | facet | Umbrella with variable meanings; preserve and await a more specific style. | — | No | S01, S19 |
| `style:soul` | style | Explicit soul style, preserved as a narrower concept rather than a spelling alias of R&B. | rnb_soul (core) | No | S09 |
| `style:electronica` | style_umbrella | Variable electronic-music umbrella; preserved separately from Electronic and not assumed to be house, techno or downtempo. | — | No | S01, S02 |
| `style:rap` | style_umbrella | Broad rap music term, mapped into the hip-hop family without claiming a specific production neighborhood or changing the vocal-role field. | — | No | S04 |


## Appendix B — Sources and attribution boundaries

Online research used the following primary documentation, catalog-author definitions, producer/software-maker explanations and research publications. They do not agree on one exhaustive genre tree; that disagreement is why the mapping retains types and overlaps. The reference registry is an original operational design, not a transcription of any site's full taxonomy.

**S01. AllMusic: Genres, styles, moods and themes**  
https://www.allmusic.com/faq/topic/genres  
Used for: Different metadata dimensions, not a universal distance scale.

**S02. Discogs: Database Guidelines 9 — Genres / Styles**  
https://support.discogs.com/hc/en-us/articles/360005055213-Database-Guidelines-9-Genres-Styles  
Used for: Broad genres, narrower styles, and combined genres.

**S03. MusicBrainz: Genre**  
https://musicbrainz.org/doc/Genre  
Used for: Subjective, community-maintained genre tags; vocabulary can expand.

**S04. MusicBrainz: Genre list**  
https://musicbrainz.org/genres  
Used for: Terminology reference, including contemporary styles. Does not supply calibrated distances or track truth.

**S05. Bogdanov et al.: The AcousticBrainz Genre Dataset (ISMIR 2019)**  
https://zenodo.org/records/3527818  
Used for: Multi-source, multi-level, multi-label annotations and taxonomy disagreement.

**S06. Native Instruments: What is boom bap?**  
https://blog.native-instruments.com/what-is-boom-bap/  
Used for: Hip-hop production vocabulary; sampled/swinging kick-snare foundations.

**S07. Ableton / Comakid: LoFi HipHop**  
https://www.ableton.com/en/packs/lofi-hiphop/  
Used for: Production texture and groove; lo-fi is not simply absence of vocals.

**S08. Roland: Trap and Lo-Fi Beats**  
https://articles.roland.com/trap-and-lo-fi-beats-with-zenbeats-and-roland-cloud/  
Used for: Related hip-hop styles with differing production tendencies.

**S09. AllMusic: R&B styles**  
https://www.allmusic.com/genre/r-b-ma0000002809/albums  
Used for: R&B, contemporary R&B, alternative R&B, soul and neo-soul relationships.

**S10. AllMusic: Neo-Soul**  
https://www.allmusic.com/genre/neo-soul-ma0000004426  
Used for: Classic-soul-oriented branch related to contemporary R&B.

**S11. AllMusic: Trip-Hop**  
https://www.allmusic.com/style/trip-hop-ma0000002906  
Used for: Downtempo electronic and hip-hop relationships; related is not synonymous.

**S12. AllMusic: Downbeat**  
https://www.allmusic.com/style/downbeat-ma0000012007  
Used for: Electronic listening music need not be dance-floor music.

**S13. AllMusic: Ambient**  
https://www.allmusic.com/style/ambient-ma0000002424  
Used for: Texture-focused atmospheric music, not a synonym for all experimental music.

**S14. Splice: Hyperpop**  
https://splice.com/sounds/genres/hyperpop/samples  
Used for: Pop experimentation, synthetic production and dense processing; catalog ranges are not genre eligibility rules.

**S15. Native Instruments: How to make future bass**  
https://blog.native-instruments.com/how-to-make-future-bass/  
Used for: Synth-heavy bass music and trap/dubstep influences; not equivalent to hard techno.

**S16. Recording Academy: 2023 in review — K-pop**  
https://www.grammy.com/news/2023-in-review-5-trends-in-k-pop/  
Used for: K-pop spans multiple sonic styles; retain scene/context separately.

**S17. Native Instruments: Phonk music**  
https://blog.native-instruments.com/phonk-music/  
Used for: Hip-hop lineage and differences between phonk variants.

**S18. City Girl: Goddess of the Hollow (artist release page)**  
https://city-girl.bandcamp.com/album/goddess-of-the-hollow  
Used for: Artist-supplied album tags and recording credits. Album tags do not prove each track genre.

**S19. MusicBrainz: Folksonomy Tagging**  
https://musicbrainz.org/doc/Folksonomy_Tagging  
Used for: Tags can encode genre, nationality and other non-genre information.

**S20. Oramas et al.: Multimodal Deep Learning for Music Genre Classification**  
https://transactions.ismir.net/articles/10.5334/tismir.10  
Used for: Multi-label genre modeling; musical evidence can span multiple sources.

**S21. Soundation: How to make lo-fi hip hop**  
https://soundation.com/music-genres/how-to-make-lo-fi-hip-hop  
Used for: Jazz/boom-bap overlap and the distinction between production and listening use.

**R01. Frozen100 generation scope and limitations.**  
https://github.com/lennytheworm12/spotify-sorter/blob/190a12596968ed84245aa1a880cdfae97214fe94/ml/audio_similarity/reports/gemini_style_pilot/frozen100_free_genre_v1/README.md

**R02. Earlier Discogs-prior interpretation.**  
https://github.com/lennytheworm12/spotify-sorter/blob/190a12596968ed84245aa1a880cdfae97214fe94/ml/audio_similarity/reports/style_band_prior/v1/interpretation.md

**R03. Frozen100 original classifications (pinned input).**  
https://github.com/lennytheworm12/spotify-sorter/blob/190a12596968ed84245aa1a880cdfae97214fe94/ml/audio_similarity/reports/gemini_style_pilot/frozen100_free_genre_v1/classifications.csv
