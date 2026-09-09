
**Ontology version:** `style-pilot-v1-draft`

This is a bounded operational vocabulary for the experiment, **not** a canonical musicology taxonomy. A broad family may be clear while a specific style remains `unknown`. Secondary memberships are allowed and should be sparse.

### 3.1 Allowed broad families

| Value | Operational definition |
| --- | --- |
| hip_hop_rap | Hip-hop/rap is the primary audible idiom: beat construction, rhythmic vocal delivery, sampling/drum language, or closely related production conventions. |
| rnb_soul | R&B/soul is the primary audible idiom: groove- and vocal-centered songwriting/production rooted in contemporary R&B, soul, or closely related forms. |
| pop | Pop-oriented songwriting/production is primary: strong melodic/song-form focus and broadly pop-centered arrangement. This is an acoustic/style family, not a market or nationality label. |
| electronic | Electronic production is a primary musical idiom rather than merely the presence of synthesizers or digital effects. |
| rock | Rock-derived band, guitar, drum, or arrangement language is a primary musical idiom. |
| folk_acoustic | Folk/acoustic singer-songwriter or acoustic-instrument-centered language is primary. |
| jazz | Jazz-derived harmonic, rhythmic, ensemble, or improvisational language is a primary audible idiom. |
| classical | Classical/art-music instrumentation, composition, or ensemble language is primary. |
| other | The recording is clearly music, but none of the offered broad families is defensible. |
| unknown | The available audio does not support a defensible broad-family assignment. |

### 3.2 Allowed styles and legal family memberships

| Style | Allowed family/families | Operational definition |
| --- | --- | --- |
| boom_bap | hip_hop_rap | Hip-hop centered on prominent kick/snare backbeat, sample-oriented or loop-based production, and classic boom-bap rhythmic language. |
| trap | hip_hop_rap | Hip-hop centered on trap drum language such as rapid hi-hats, 808/sub-bass, sparse or synthetic percussion, and related modern rap production. |
| melodic_trap | hip_hop_rap | Trap-rooted production with a strong melodic vocal, hook, or atmospheric emphasis. |
| cloud_rap | hip_hop_rap | Rap/hip-hop with hazy, spacious, atmospheric, dreamlike, or ambient-leaning production. |
| rage | hip_hop_rap, electronic | High-impact, synthetic, distorted or brightly electronic rap production associated with the rage branch of contemporary hip-hop. |
| alternative_rnb | rnb_soul | R&B whose production, structure, timbre, or songwriting departs materially from conventional contemporary R&B norms. |
| contemporary_rnb | rnb_soul | Modern R&B centered on sung vocals, groove, polished production, and contemporary R&B songwriting/arrangement conventions. |
| neo_soul | rnb_soul, jazz | Soul/R&B with strong organic, jazz-, funk-, or classic-soul-derived harmony, groove, instrumentation, or vocal language. |
| pop_rnb | rnb_soul, pop | A substantial blend of pop songwriting/production and R&B groove, vocal, or timbral language. |
| dance_pop | pop, electronic | Pop centered on dance-oriented pulse, rhythmic drive, and polished electronic or club-compatible production. |
| indie_pop | pop, rock | Pop with indie/alternative production, instrumentation, songwriting, or presentation rather than mainstream dance/pop conventions. |
| synthpop | pop, electronic | Pop where synthesizers and electronic timbres form a defining stylistic core, often with clear melodic song structure. |
| electropop | pop, electronic | Pop whose core sound is strongly electronic/digital, broader than classic synthpop and not necessarily club-focused. |
| hyperpop | pop, electronic | Pop/electronic music with exaggerated, highly processed, digitally manipulated, maximalist, abrasive, or intentionally synthetic production traits; it does not require constant speed or loudness. |
| digicore | hip_hop_rap, pop, electronic | Internet-native pop/rap/electronic hybrid language related to hyperpop, often combining digitally processed vocals, trap/rap influence, and highly synthetic production. |
| lofi_hip_hop | hip_hop_rap, electronic | Hip-hop-derived beat music characterized by deliberately softened, degraded, hazy, intimate, or low-fidelity production aesthetics. |
| chillhop | hip_hop_rap, jazz, electronic | Relaxed hip-hop/beat music emphasizing laid-back groove, instrumental texture, and often jazz/soul-derived harmony or sampling. |
| instrumental_hip_hop | hip_hop_rap | Hip-hop production where the instrumental/beat is the main musical foreground rather than a lead rapper or singer. |
| indie_rock | rock | Rock-oriented music with indie/alternative guitar, band, production, or songwriting language. |
| ambient | electronic, folk_acoustic, classical | Music primarily organized around atmosphere, sustained texture, space, gradual development, or non-songlike environmental sound fields. |
| acoustic_ballad | pop, folk_acoustic | A slow-to-moderate song centered on acoustic instrumentation and a ballad-like vocal/songwriting presentation. |
| unknown | hip_hop_rap, rnb_soul, pop, electronic, rock, folk_acoustic, jazz, classical, other, unknown | No offered specific style is defensible even if the broad family may be clear. |

### 3.3 Vocal roles

| Value | Definition |
| --- | --- |
| rap_led | Foreground lead vocals are predominantly rhythmic speech/rap. |
| sung_led | Foreground lead vocals are predominantly melodic singing. |
| mixed_rap_and_singing | Substantial foreground use of both rapping and melodic singing. |
| instrumental | No meaningful vocal element functions as part of the musical foreground. |
| vocal_samples_only | Voices occur mainly as chopped, sampled, wordless, or textural material rather than a lead performance. |
| spoken_only | Meaningful foreground voice is spoken rather than sung or rapped. |
| unclear | The supplied audio does not support a stable vocal-role assignment. |

### 3.4 Arrangement focus

| Value | Definition |
| --- | --- |
| lead_vocal | A lead vocal performance is the primary foreground focus for most musically active sections. |
| beat_or_instrumental | The beat/instrumental texture is the primary foreground focus for most active sections. |
| balanced | Lead vocal and instrumental/beat contribute comparably to the foreground. |
| varies | The foreground focus changes materially across sections. |
| unclear | No defensible arrangement-focus assignment can be made. |

### 3.5 Texture tags

| Value | Definition |
| --- | --- |
| sample_based | Audibly built around sampled/looped source material or sample-like collage/chop aesthetics. |
| electronic | Synthetic/digital/electronic timbres are a salient part of the recording's sound. |
| acoustic | Acoustic/physical instruments and relatively natural timbres are salient. |
| hazy | Softened, blurred, washed, reverberant, tape-like, or intentionally indistinct texture is salient. |
| distorted | Audible saturation, clipping, overdrive, bitcrushing, harshness, or other distortion is stylistically salient. |
| clean | Relatively polished, separated, low-noise, and controlled production texture is salient. |
| layered | Multiple simultaneous musical/production layers create a noticeably dense or stacked texture. |

### 3.6 Active-section density

| Value | Definition |
| --- | --- |
| sparse | Active sections contain relatively few simultaneous foreground/layered elements. |
| moderate | Active sections contain a typical/intermediate amount of layering and musical activity. |
| dense | Active sections contain many simultaneous, overlapping, or heavily processed layers. |
| varies | Density changes materially between sections. |
| unclear | Density cannot be assessed reliably. |

`active_section_density` describes layering/processing/activity **during musically active sections**. It is not BPM, tempo, or continuous loudness.

### 3.7 Section variation

| Value | Definition |
| --- | --- |
| mostly_consistent | The recording's broad arrangement/texture remains relatively stable across the supplied duration. |
| contrasting_sections | The recording contains clearly different sections in arrangement, density, texture, vocal role, or musical state. |
| cannot_assess | The input coverage is insufficient or ambiguous for a section-variation judgment. |

### 3.8 Certainty

| Value | Definition |
| --- | --- |
| clear | The evidence strongly supports the assignment within this operational vocabulary. |
| tentative | The assignment is plausible but competing labels remain materially defensible. |
| unresolved | The model cannot defensibly choose at this level. |

Self-reported certainty is ordinal diagnostic evidence, **not a calibrated probability or genre-mixture weight**.

### 3.9 Classification status

| Value | Definition |
| --- | --- |
| classified | The recording is music and receives a defensible family/style profile. |
| uncertain | The recording is music, but key classification fields remain unresolved; unknown values are acceptable. |
| not_music | The supplied input is not a music recording or is dominated by non-musical content. |

### 3.10 Boundary/cross-field rules

- Lo-fi hip-hop and boom bap can share hip-hop ancestry. Do not create unrelated parents to force a desired result.
- Instrumental does not imply lo-fi; rap vocals do not exclude lo-fi; sung vocals do not imply R&B.
- Hyperpop-adjacent maximalist production does not require high BPM, continuous loudness, or no quiet sections.
- Language, performer nationality and market labels such as K-pop are not acoustic genre evidence by themselves.
- Primary and secondary assignments form overlapping facets, not a perfect single-parent genre tree.
- No family or style assignment implies pairwise playlist compatibility.

Additional validation rules:
- Up to 2 `secondary_families`.
- Up to 2 `secondary_styles`.
- Up to 3 `texture_tags`.
- Up to 3 `audio_evidence` spans.
- Up to 2 `unmapped_styles`.
- `secondary_families` cannot use `unknown`.
- `secondary_styles` cannot use `unknown`.
- A chosen specific style should be compatible with at least one chosen family according to `style_allowed_families`.
- `unmapped_styles` are proposals for coverage analysis only; they never auto-modify the ontology.
- No family/style assignment implies pairwise playlist compatibility.

---
