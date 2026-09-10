# Original 16: genre-neighborhood manual review

Mapping uses only the four raw Gemini family/style fields. Context and owner comments below are display-only.
Each card separates a literal-label mapping decision from a possible classification disagreement. Blank owner decisions remain unsubmitted.

## A01 — Wet Dreamz — J. Cole

Stable Spotify ID: `4tqcoej1zPvwePZCzuAjJd`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Boom Bap" | Boom bap | ["hip_hop"] | ["hip_hop_beat_lineage", "boom_bap"] | [] | mapped |
| secondary_styles[0] | "Conscious Hip Hop" | Conscious hip-hop | ["hip_hop"] | [] | ["conscious_hip_hop_context"] | mapped |
| secondary_styles[1] | "East Coast Hip Hop" | East Coast hip-hop | ["hip_hop"] | [] | ["east_coast_hip_hop_scene"] | mapped |

**Broad families:** hip_hop, rnb_soul

**Overlapping neighborhoods:** boom_bap, hip_hop_beat_lineage

**Separate scene/context:** conscious_hip_hop_context, east_coast_hip_hop_scene

**Gemini context, display only:** {"vocal_role": "rap_led", "arrangement_focus": "lead_vocal", "texture_tags": ["sample_based", "layered"]}

**Existing owner first-pass words, verbatim:** "the song sounds like boom bap/ golden age rap "

**Review note:** Boom-bap and the lo-fi/chillhop labels share hip-hop beat lineage, while only explicit Boom Bap supplies the narrow boom_bap neighborhood. Conscious and East Coast tags stay context-only; neither is a synonym for boom-bap. The raw secondary R&B family remains present.

**Warnings:** context_separate_from_sonic_style: Thematic/context concept only; no boom-bap or other sonic style inferred.; context_separate_from_sonic_style: The explicit hip-hop name supports its broad family; geography does not imply boom-bap.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## A02 — Shoota (feat. Lil Uzi Vert) — Playboi Carti, Lil Uzi Vert

Stable Spotify ID: `2BJSMvOGABRxokHKB0OI8i`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "hip hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "trap" | Trap | [] | ["trap_related"] | [] | mapped |
| secondary_styles[0] | "plugg" | Plugg | ["hip_hop"] | ["trap_related", "plugg_related"] | [] | mapped |

**Broad families:** hip_hop

**Overlapping neighborhoods:** plugg_related, trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "rap_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean"]}

**Existing owner first-pass words, verbatim:** "trap rap heavy fast/aggressive"

**Review note:** Trap and plugg overlap through a general trap-related neighborhood. Plugg is a model label, not newly owner-confirmed. No fast/aggressive property is inferred from the owner note or the genre labels.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## A03 — My Gamecube Broke. — .Uzu

Stable Spotify ID: `2Vu2hkPW7LxMHPqoMjSIEJ`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "Bass Music" | Bass music | [] | [] | [] | mapping_review_required |
| primary_style | "Drum and Bass" | Drum and bass | ["electronic"] | ["bass_electronic", "drum_and_bass"] | [] | mapped |
| secondary_styles[0] | "Neurofunk" | Neurofunk | ["electronic"] | ["bass_electronic", "drum_and_bass"] | [] | mapped |
| secondary_styles[1] | "Dubstep" | Dubstep | ["electronic"] | ["bass_electronic", "dubstep"] | [] | mapped |

**Broad families:** electronic

**Overlapping neighborhoods:** bass_electronic, drum_and_bass, dubstep

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["electronic", "distorted", "layered"]}

**Existing owner first-pass words, verbatim:** "lofi electronic/gamey style"

**Review note:** Classification-review priority: the free-form Drum and Bass / Neurofunk / Dubstep prediction differs substantially from the owner first-pass lo-fi electronic/gamey description and the older ontology-constrained lo-fi profile. Mapping those literal labels into bass-electronic neighborhoods is not a mapper bug. Do not remap them to lo-fi to repair this song. Bass Music is independently an ambiguous umbrella requiring mapping review.

**Warnings:** mapping_review_required: Heterogeneous electronic/club/regional umbrella; do not equate with drum-and-bass, dubstep, or a single family.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## A04 — She loves the color green and I love her — City Girl

Stable Spotify ID: `7hFW5IN7mQ99PuO86r38Sf`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "Lo-Fi Hip Hop" | Lo-fi hip-hop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[0] | "Downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |
| secondary_styles[1] | "Chillout" | Chillout | [] | [] | ["chillout_umbrella"] | mapping_review_required |

**Broad families:** electronic, hip_hop

**Overlapping neighborhoods:** downtempo_related, hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** chillout_umbrella

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["sample_based", "electronic", "hazy"]}

**Existing owner first-pass words, verbatim:** "soft studying lofi sound"

**Review note:** Lo-Fi Hip Hop normalizes to the same concept as Tea Time's lo_fi_hip_hop. Downtempo contributes its own neighborhood. Chillout remains an ambiguous context/style umbrella. No instrumental role is inferred from the genre map or copied vocal context.

**Warnings:** mapping_review_required: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.; context_separate_from_sonic_style: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## A05 — Tea Time — Disvstxr

Stable Spotify ID: `5sEeuhYWHNczuPKek1zJeG`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "hip_hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "lo_fi_hip_hop" | Lo-fi hip-hop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[0] | "chillhop" | Chillhop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[1] | "downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |

**Broad families:** electronic, hip_hop

**Overlapping neighborhoods:** downtempo_related, hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["sample_based", "hazy", "clean"]}

**Existing owner first-pass words, verbatim:** "lofi hip hop "

**Review note:** Alias normalization agrees with the other explicit lo-fi hip-hop example. The good Tea Time / Sit Around rating does not require equal mapped neighborhoods; do not broaden the mapper just to manufacture that overlap.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## A06 — GET IT — keshi

Stable Spotify ID: `4LaZ8RpIP6DIgN73bXQVlO`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |
| secondary_styles[0] | "Pop Rap" | Pop rap | ["hip_hop", "pop"] | ["rap_pop_crossover"] | [] | mapped |
| secondary_styles[1] | "Melodic Rap" | Melodic rap | ["hip_hop"] | ["melodic_rap"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** melodic_rap, rap_pop_crossover, trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "balanced", "texture_tags": ["electronic", "layered", "clean"]}

**Existing owner first-pass words, verbatim:** "dark alt rnb "

**Review note:** Classification-review question: the owner described dark alternative R&B, whereas Gemini foregrounds Trap / Pop Rap / Melodic Rap. Its explicit secondary R&B and Pop memberships are retained, yielding overlapping hip-hop / pop / R&B families. Do not insert Alternative R&B or a dark-mood attribute that Gemini did not label.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## A07 — The Hills — The Weeknd

Stable Spotify ID: `7fBv7CLKzipRk6EC6TWHOB`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[1] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |
| secondary_styles[1] | "Alternative R&B" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, modern_rnb, trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered"]}

**Existing owner first-pass words, verbatim:** "dark heavy rnb"

**Review note:** The current free-form profile has Contemporary R&B / Trap / Alternative R&B. The earlier owner objection to the original ontology-constrained hyperpop label is historical context, not a rejection of this newer free-form profile. Shared modern-R&B membership with Shouldn't Be preserves the different narrower styles.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## A08 — Shouldn't Be — Luke Chiang

Stable Spotify ID: `7F6PtLP6fJPVtA1FWVkl8K`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Alt-Pop" | Alternative pop | ["pop"] | ["alternative_pop"] | [] | mapped |
| secondary_styles[1] | "Ambient Pop" | Ambient pop | ["pop"] | ["atmospheric_pop"] | [] | mapped |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** alternative_pop, atmospheric_pop, modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** "soul rnb"

**Review note:** Contemporary R&B shares a broad neighborhood with The Hills, while Alt-Pop / Ambient Pop add different style memberships. The owner's soul wording is retained separately; it does not cause the mapper to append a Soul label.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## A09 — Perfect Night — LE SSERAFIM

Stable Spotify ID: `74X2u8JMVooG2QbjRxXwR8`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[0] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[1] | "Nu-Disco" | Nu-disco | ["electronic"] | ["disco_related"] | [] | mapped |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** dance_pop, disco_related, modern_rnb, pop_electronic

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** "kpop contemporary rnb"

**Review note:** Context/classification-review question: the owner included K-Pop, but the current Gemini profile did not. Do not infer scene membership from the artist or owner note. Contemporary R&B is shared wording; Nu-Disco / Dance-Pop remain model claims for inspection.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## A10 — OMG — NewJeans

Stable Spotify ID: `65FftemJ1DbbZ45DUfHJXE`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B and Soul" | R&B and Soul | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Dance" | Dance | [] | [] | [] | mapping_review_required |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[1] | "Synth-Pop" | Synth-pop | ["pop", "electronic"] | ["pop_electronic", "synth_pop"] | [] | mapped |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb, pop_electronic, synth_pop

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** "kpop hip hop contemporary rnb"

**Review note:** K-Pop is stored separately as scene/context. Contemporary R&B and Synth-Pop supply sonic neighborhoods. Bare Dance is ambiguous and contributes no guessed EDM/dance-pop membership. Do not infer hip-hop from mixed rap/singing context or owner wording.

**Warnings:** mapping_review_required: Bare dance label does not distinguish function, dance-pop, or electronic dance music.; context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## C01 — Saturation in Delay, Love in Anger — City Girl, tiffi

Stable Spotify ID: `00njeQb198Lm7Jge2Rsrlg`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "ambient" | Ambient | [] | ["ambient_related"] | [] | mapped |
| primary_style | "minimal techno" | Minimal techno | ["electronic"] | ["techno_related", "minimal_club"] | [] | mapped |
| secondary_styles[0] | "dub techno" | Dub techno | ["electronic"] | ["techno_related", "dub_electronic"] | [] | mapped |
| secondary_styles[1] | "microhouse" | Microhouse | ["electronic"] | ["house_related", "minimal_club"] | [] | mapped |

**Broad families:** electronic

**Overlapping neighborhoods:** ambient_related, dub_electronic, house_related, minimal_club, techno_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["electronic", "sample_based", "clean"]}

**Existing owner first-pass words, verbatim:** "lofi"

**Review note:** Classification-review priority: minimal techno / dub techno / microhouse differs from both the initial owner lo-fi wording and the older hyperpop/digicore profile. The owner later found the older hyperpop interpretation more plausible; that clarification does not endorse this new minimal-techno profile. Preserve all three positions. No automatic model-error or corrected-false-positive claim follows.

**Warnings:** style_concept_in_family_slot: Resolve by explicit concept, not by the model field name; original slot retained.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## C02 — Sit Around — City Girl, tiffi

Stable Spotify ID: `6pWqlKm9ugucgKNldCLigX`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Indie Pop" | Indie pop | ["pop"] | ["indie_pop_related"] | [] | mapped |
| secondary_styles[0] | "Electropop" | Electropop | ["pop", "electronic"] | ["pop_electronic"] | [] | mapped |
| secondary_styles[1] | "Alternative R&B" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, indie_pop_related, modern_rnb, pop_electronic

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** "lofi soft vibes"

**Review note:** Classification-review question: the owner used lo-fi soft wording; the current model uses Indie Pop / Electropop / Alternative R&B. The mapper must not inject lo-fi. Its indie-pop neighborhood overlaps risk's explicit Dream Pop via a general genre relationship, not a pair-specific rule.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## C03 — risk — lace

Stable Spotify ID: `2js0td9w2MzNUVPlMKYOEs`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "Downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |
| primary_style | "Trip Hop" | Trip-hop | ["electronic", "hip_hop"] | ["hip_hop_beat_lineage", "downtempo_related"] | [] | mapped |
| secondary_styles[0] | "Downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |
| secondary_styles[1] | "Dream Pop" | Dream pop | ["pop"] | ["indie_pop_related", "atmospheric_pop"] | [] | mapped |

**Broad families:** electronic, hip_hop, pop

**Overlapping neighborhoods:** atmospheric_pop, downtempo_related, hip_hop_beat_lineage, indie_pop_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "hazy", "layered"]}

**Existing owner first-pass words, verbatim:** "dreamy whisper dream pop bedroom pop"

**Review note:** Downtempo occurs in both a family and style slot: retain both traces, deduplicate membership without extra weight. Trip Hop adds hip-hop lineage, not a rap-vocal claim. Dream Pop supplies indie-pop / atmospheric-pop memberships; no bedroom-pop label is invented.

**Warnings:** style_concept_in_family_slot: Resolve by explicit concept, not by the model field name; original slot retained.; repeated_concept_not_extra_weight: All raw occurrences retained; one set membership, no extra vote or confidence.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## C04 — boys dont cry — sysmint

Stable Spotify ID: `1ON9XudZFxwu43tQXBszIX`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |
| secondary_styles[0] | "Emo Rap" | Emo rap | ["hip_hop"] | ["emo_rap"] | [] | mapped |
| secondary_styles[1] | "Melodic Rap" | Melodic rap | ["hip_hop"] | ["melodic_rap"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** emo_rap, melodic_rap, trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered", "sample_based"]}

**Existing owner first-pass words, verbatim:** "electronic hyperpop"

**Review note:** Classification-review priority: owner electronic hyperpop versus the newer Trap / Emo Rap / Melodic Rap profile. Preserve the discrepancy. A shared trap-related label with The Peace is an exploratory model signal only, not owner-confirmed genre truth.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## C05 — The Peace — underscores

Stable Spotify ID: `6wm3t4VpTxSFfOUgTMlHZM`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B and Soul" | R&B and Soul | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[1] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |
| secondary_styles[1] | "Alternative R&B" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, modern_rnb, trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["sample_based", "electronic", "layered"]}

**Existing owner first-pass words, verbatim:** "alt pop ballad hyperpop"

**Review note:** Classification-review priority: owner alt-pop ballad / hyperpop versus current Contemporary R&B / Trap / Alternative R&B. Do not replace those labels to agree with the owner. The pairing with boys dont cry is owner-specific exploration without a new numeric or confirmatory genre label.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## C06 — Die Right Here — david hugo

Stable Spotify ID: `7fXYFuCTmNrYRGwEUUf5iz`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[0] | "Nu-Disco" | Nu-disco | ["electronic"] | ["disco_related"] | [] | mapped |
| secondary_styles[1] | "Synth-Pop" | Synth-pop | ["pop", "electronic"] | ["pop_electronic", "synth_pop"] | [] | mapped |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** dance_pop, disco_related, pop_electronic, synth_pop

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** "alt upbeat indie"

**Review note:** Classification-review question: owner alt upbeat indie versus current Dance-Pop / Nu-Disco / Synth-Pop. The low-rated OMG pairing still shares pop/electronic-style neighborhoods; that is a compatibility limitation, not a reason to create a song exception.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________
