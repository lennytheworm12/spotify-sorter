# Frozen 100: genre-neighborhood manual review

Mapping uses only the four raw Gemini family/style fields. Context and owner comments below are display-only.
Each card separates a literal-label mapping decision from a possible classification disagreement. Blank owner decisions remain unsubmitted.

## F001 — Saturation in Delay, Love in Anger — City Girl, tiffi

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** style_concept_in_family_slot: Resolve by explicit concept, not by the model field name; original slot retained.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F002 — Stay With Me — jrd.

Stable Spotify ID: `02CCi0N3pMK4Rjxq5e6UmE`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "hip-hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[1] | "ambient" | Ambient | [] | ["ambient_related"] | [] | mapped |
| primary_style | "lo-fi beats" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "chillhop" | Chillhop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[1] | "downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |

**Broad families:** electronic, hip_hop

**Overlapping neighborhoods:** ambient_related, downtempo_related, hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["sample_based", "electronic", "hazy"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** style_concept_in_family_slot: Resolve by explicit concept, not by the model field name; original slot retained.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F003 — We (OUI) (Feat. sogumm) — jeebanoff, sogumm

Stable Spotify ID: `043ryKJlgSnAUzpXnfxU6b`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B and Soul" | R&B and Soul | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["clean", "electronic", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F004 — The Way — Ariana Grande, Mac Miller

Stable Spotify ID: `06EL94D0TA27Ik0Ke5usbj`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "r&b" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "hip hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "contemporary r&b" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "dance-pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[1] | "pop rap" | Pop rap | ["hip_hop", "pop"] | ["rap_pop_crossover"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** dance_pop, modern_rnb, pop_electronic, rap_pop_crossover

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "lead_vocal", "texture_tags": ["clean", "layered", "sample_based"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F005 — id T41104 (feat. 267) — W/N, 267

Stable Spotify ID: `07tiPBhMqiKqHowwqDBtfK`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "r&b" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "lo-fi chill beats" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "chillout" | Chillout | [] | [] | ["chillout_umbrella"] | mapping_review_required |
| secondary_styles[1] | "bedroom pop" | null | [] | [] | [] | mapping_review_required |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** none

**Separate scene/context:** chillout_umbrella

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "hazy"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.; context_separate_from_sonic_style: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F006 — falling down — Nohidea

Stable Spotify ID: `0ASYuzPsTBA6ZmIsuvNZby`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "hip-hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "lo-fi hip hop" | Lo-fi hip-hop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[0] | "chillout" | Chillout | [] | [] | ["chillout_umbrella"] | mapping_review_required |

**Broad families:** electronic, hip_hop

**Overlapping neighborhoods:** hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** chillout_umbrella

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "balanced", "texture_tags": ["sample_based", "hazy", "electronic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.; context_separate_from_sonic_style: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F007 — Panorama — IZ*ONE

Stable Spotify ID: `0CnpSTdL9l5vQM4YnzXtyo`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Electropop" | Electropop | ["pop", "electronic"] | ["pop_electronic"] | [] | mapped |
| secondary_styles[1] | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F008 — Sunday (feat. HEIZE, Jay Park) — GroovyRoom, Heize, Jay Park

Stable Spotify ID: `0JJeoiCAa1hwcBsPxBN2w4`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "r&b" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "hip hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "contemporary r&b" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "k-pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[1] | "trap soul" | null | [] | [] | [] | mapping_review_required |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F009 — Jocelyn Flores — Dontcry

Stable Spotify ID: `0WJxkgYXRoOxFb4Vq3Ddmg`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Jazz" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Lo-Fi Beats" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Jazz Rap" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Chillhop" | Chillhop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |

**Broad families:** hip_hop

**Overlapping neighborhoods:** hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["sample_based", "hazy", "electronic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F010 — (empty) — OuiOui

Stable Spotify ID: `0ayK1CJh1cMRjUJRCDWhCd`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B and Soul" | R&B and Soul | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[1] | "Pop Soul" | null | [] | [] | [] | mapping_review_required |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F011 — Heart — chicken97

Stable Spotify ID: `0mjbciwK9zhfQl44jXfQv6`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "K-R&B" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Pop Soul" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F012 — Shiawase no Monosashi — Pokke

Stable Spotify ID: `0xlx3pH8TxNah8hdiINqeA`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "Modern Classical" | null | [] | [] | [] | mapping_review_required |
| secondary_families[1] | "Experimental" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Ambient" | Ambient | [] | ["ambient_related"] | [] | mapped |
| secondary_styles[0] | "Minimalism" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Glitch" | null | [] | [] | [] | mapping_review_required |

**Broad families:** electronic

**Overlapping neighborhoods:** ambient_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "instrumental", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["electronic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F013 — Temporary — Kiri T

Stable Spotify ID: `1AHtqWqufKsgBmdNEi1WVO`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "r&b" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "contemporary r&b" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "neo soul" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "downtempo pop" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F014 — Top Secret — Weeekly

Stable Spotify ID: `1CwmoUvvRyhiwqhMfvbB4K`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[1] | "Bubblegum Pop" | null | [] | [] | [] | mapping_review_required |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F015 — Uncertainty — Chill Select, kretzschクレツ, Milkz

Stable Spotify ID: `1DaXVM8npVKa2AQBrYz4xS`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Chillhop" | Chillhop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[0] | "Lo-Fi Hip-Hop" | Lo-fi hip-hop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[1] | "Downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |

**Broad families:** electronic, hip_hop, rnb_soul

**Overlapping neighborhoods:** downtempo_related, hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["electronic", "sample_based", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F016 — DOWNPOUR (feat. Gliiico) — CHAEYOUNG, Gliiico

Stable Spotify ID: `1IIcy1TpuiAT6S206OjYvC`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |
| secondary_styles[0] | "Trap Soul" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Alternative R&B" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |

**Broad families:** electronic, hip_hop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, modern_rnb, trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F017 — boys dont cry — sysmint

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F018 — Hit the Wall — Gracie Abrams

Stable Spotify ID: `1U90UBmMrQTx9GNweUA4LZ`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Folk & Acoustic Pop" | null | [] | [] | [] | mapping_review_required |
| secondary_families[1] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "Indie Pop" | Indie pop | ["pop"] | ["indie_pop_related"] | [] | mapped |
| secondary_styles[0] | "Bedroom Pop" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Alt-Pop" | Alternative pop | ["pop"] | ["alternative_pop"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** alternative_pop, indie_pop_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "acoustic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F019 — Shoulder — Galdive

Stable Spotify ID: `1VAtYkKvDenA1KypImlZIY`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "experimental" | null | [] | [] | [] | mapping_review_required |
| primary_style | "ambient pop" | Ambient pop | ["pop"] | ["atmospheric_pop"] | [] | mapped |
| secondary_styles[0] | "deconstructed club" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "art pop" | null | [] | [] | [] | mapping_review_required |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** atmospheric_pop

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "hazy", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F020 — 门没锁 — 我是土豆

Stable Spotify ID: `1Y6Ra2erZ6Mru0JOcJBSzK`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Asian Pop" | null | [] | [] | [] | mapping_review_required |
| secondary_families[0] | "Jazz" | null | [] | [] | [] | mapping_review_required |
| secondary_families[1] | "Easy Listening" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Mandopop" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Vocal Jazz" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Bossa Nova" | null | [] | [] | [] | mapping_review_required |

**Broad families:** none

**Overlapping neighborhoods:** none

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F021 — too afraid — hateful

Stable Spotify ID: `1ZhrRS2xY1ZoD2QJ9aZQxX`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Folk" | null | [] | [] | [] | mapping_review_required |
| secondary_families[1] | "Indie" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Bedroom Pop" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Indie Pop" | Indie pop | ["pop"] | ["indie_pop_related"] | [] | mapped |
| secondary_styles[1] | "Indie Folk" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop

**Overlapping neighborhoods:** indie_pop_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "hazy", "electronic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F022 — Magnetic — ILLIT

Stable Spotify ID: `1aKvZDoLGkNMxoRYgkckZG`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Synthpop" | Synth-pop | ["pop", "electronic"] | ["pop_electronic", "synth_pop"] | [] | mapped |
| secondary_styles[1] | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** dance_pop, pop_electronic, synth_pop

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "sample_based", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F023 — vampire — Olivia Rodrigo

Stable Spotify ID: `1kuGVB7EU95pJObxwvfwKS`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Rock" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Pop Rock" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Piano Pop" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop

**Overlapping neighborhoods:** none

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "layered", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F024 — No I Don't Want, Just Anyone — Unclenathannn, Shiloh Dynasty

Stable Spotify ID: `23V5SeHanwL6PlqyJ99dH8`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |
| secondary_styles[0] | "Phonk" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Cloud Rap" | null | [] | [] | [] | mapping_review_required |

**Broad families:** electronic, hip_hop

**Overlapping neighborhoods:** trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["sample_based", "electronic", "hazy"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F025 — Soft Static Sky on Early Mornings — City Girl

Stable Spotify ID: `2Ah7oAy4esXD8pEEhY0hyR`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Lo-Fi Beats" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Chillhop" | Chillhop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[1] | "Neo-Soul" | null | [] | [] | [] | mapping_review_required |

**Broad families:** electronic, hip_hop, rnb_soul

**Overlapping neighborhoods:** downtempo_related, hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "instrumental", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["clean", "hazy", "electronic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** style_concept_in_family_slot: Resolve by explicit concept, not by the model field name; original slot retained.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F026 — You Are Enough — .Uzu, Clavita

Stable Spotify ID: `2BFAfMIblG0RZeAvlmLC81`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "r&b" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "contemporary r&b" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "ambient pop" | Ambient pop | ["pop"] | ["atmospheric_pop"] | [] | mapped |
| secondary_styles[1] | "downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** atmospheric_pop, downtempo_related, modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "hazy"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F027 — Shoota (feat. Lil Uzi Vert) — Playboi Carti, Lil Uzi Vert

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F028 — My Gamecube Broke. — .Uzu

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: Heterogeneous electronic/club/regional umbrella; do not equate with drum-and-bass, dubstep, or a single family.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F029 — Dear My All — Mingginyu

Stable Spotify ID: `2X71ww8wImSYbw4s0Mr2ur`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Folk" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Korean Ballad" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Acoustic Pop" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop

**Overlapping neighborhoods:** none

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F030 — 11:11 — TAEYEON

Stable Spotify ID: `2Y4iTaIAamhYPyZcOdfL3g`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Folk & Acoustic" | null | [] | [] | [] | mapping_review_required |
| primary_style | "K-Pop Ballad" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Acoustic Pop" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop

**Overlapping neighborhoods:** none

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F031 — It'll Be Ok — Yoandri

Stable Spotify ID: `2YO6ZDPdQFkrOa6YYceEN4`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "rnb" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "contemporary_rnb" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "neo_soul" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "pop_soul" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["clean", "electronic", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F032 — Daydreaming — Chevy, City Girl

Stable Spotify ID: `2aiVdNIqY5BDCM10fKlKpS`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Alt-R&B" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "hazy", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F033 — strawberry moon — IU

Stable Spotify ID: `2g0LdZQce9xlcHb1mBJyuz`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B/Soul" | R&B and Soul | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Acoustic Pop" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** none

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F034 — risk — lace

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** style_concept_in_family_slot: Resolve by explicit concept, not by the model field name; original slot retained.; repeated_concept_not_extra_weight: All raw occurrences retained; one set membership, no extra vote or confidence.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F035 — Fall in love with you in every 4AM. — Friday Night Plans

Stable Spotify ID: `2sXQnT404FrXeSEZkJXfKM`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Alt-R&B" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F036 — Pray — City Girl, tiffi

Stable Spotify ID: `2yQY2IzeQtUKanVo78Fg23`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "Dance" | Dance | [] | [] | [] | mapping_review_required |
| primary_style | "Hard Techno" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Schranz" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Industrial Techno" | null | [] | [] | [] | mapping_review_required |

**Broad families:** electronic

**Overlapping neighborhoods:** none

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["electronic", "distorted", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: Bare dance label does not distinguish function, dance-pop, or electronic dance music.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F037 — Fresh Air — Maasho, Weston Estate

Stable Spotify ID: `30NAF18yQGvwKrbn1IEMKn`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Trap R&B" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Melodic Trap" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F038 — You Might (Feat. SHIRT) — g0nny, SHIRT

Stable Spotify ID: `340yvMO5adu3bo1x5Zrw14`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["clean", "electronic", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F039 — Ever2Late! — KiiiKiii

Stable Spotify ID: `37BvHZhn4399Zhh6EDa4km`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "electronic / dance" | null | [] | [] | [] | mapping_review_required |
| primary_style | "k-pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "dance-pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[1] | "afro-house" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "balanced", "texture_tags": ["electronic", "layered", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F040 — You Never Know — BLACKPINK

Stable Spotify ID: `39kzWAiVPpycdMpr745oPj`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[1] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |

**Broad families:** electronic, hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** dance_pop, modern_rnb, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F041 — 2080 — chicken97

Stable Spotify ID: `3F5HhdyBfvCbzuPJbGBHkc`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Synthpop" | Synth-pop | ["pop", "electronic"] | ["pop_electronic", "synth_pop"] | [] | mapped |
| secondary_styles[1] | "Ballad" | null | [] | [] | [] | mapping_review_required |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** pop_electronic, synth_pop

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["clean", "electronic", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F042 — bamsopoong — ILLIT

Stable Spotify ID: `3INETdToKVgt2vfp1wYBFw`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "dance" | Dance | [] | [] | [] | mapping_review_required |
| primary_style | "k-pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "dance-pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[1] | "electropop" | Electropop | ["pop", "electronic"] | ["pop_electronic"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: Bare dance label does not distinguish function, dance-pop, or electronic dance music.; context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F043 — Make the Move (feat. pH-1) — SOOVI, pH-1

Stable Spotify ID: `3JxRNkoNmAcPgnA5HSnKiz`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[1] | "Pop Rap" | Pop rap | ["hip_hop", "pop"] | ["rap_pop_crossover"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb, rap_pop_crossover

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F044 — SATELLITE — City Girl, Kelsey Kuan

Stable Spotify ID: `3X45Wd5yRNoe2twmyc5CvO`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Trap Soul" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Alt-Pop" | Alternative pop | ["pop"] | ["alternative_pop"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** alternative_pop, modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "acoustic", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F045 — 1-4-3 — Nana Ou-Yang

Stable Spotify ID: `3aFh82SrVntBmW9Lx0Gb7W`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Alt-Pop" | Alternative pop | ["pop"] | ["alternative_pop"] | [] | mapped |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** alternative_pop, modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "electronic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F046 — The Color Violet — Tory Lanez

Stable Spotify ID: `3azJifCSqg9fRij2yKIbWz`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Electronic / Dance" | null | [] | [] | [] | mapping_review_required |
| secondary_families[0] | "Hip Hop / Rap" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[0] | "Pop Rap" | Pop rap | ["hip_hop", "pop"] | ["rap_pop_crossover"] | [] | mapped |

**Broad families:** hip_hop, pop

**Overlapping neighborhoods:** dance_pop, pop_electronic, rap_pop_crossover

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F047 — 慢冷 — Ren Ran

Stable Spotify ID: `3fzeNQfannmBQWGecQZ93s`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Ambient" | Ambient | [] | ["ambient_related"] | [] | mapped |
| primary_style | "Mandopop" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Piano Pop" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop

**Overlapping neighborhoods:** ambient_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean", "electronic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** style_concept_in_family_slot: Resolve by explicit concept, not by the model field name; original slot retained.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F048 — MOON — i-dle

Stable Spotify ID: `3uOeutrLztSX6lU0b0et3B`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "k-pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "dance-pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[1] | "electropop" | Electropop | ["pop", "electronic"] | ["pop_electronic"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F049 — DANCING ALONE — KiiiKiii

Stable Spotify ID: `3vC63Nh3rSREo7qDHgnx8I`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic / Dance" | null | [] | [] | [] | mapping_review_required |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |

**Broad families:** pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F050 — Tell Me — hyejin

Stable Spotify ID: `40TJl2hLf6Sr7K1a2SkkVA`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B/Soul" | R&B and Soul | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "Folk/Americana" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "K-Indie" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Acoustic Pop" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F051 — idontwannabeyouanymore — Billie Eilish

Stable Spotify ID: `41zXlQxzTi6cGAjpOXyLYH`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B and Soul" | R&B and Soul | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Bedroom Pop" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Alt-Pop" | Alternative pop | ["pop"] | ["alternative_pop"] | [] | mapped |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** alternative_pop

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["clean", "acoustic", "electronic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F052 — DINOSAUR — AKMU

Stable Spotify ID: `49KDK2ccYnOCYPeXfDO3YT`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[1] | "Electropop" | Electropop | ["pop", "electronic"] | ["pop_electronic"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["clean", "electronic", "acoustic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F053 — Fade (Feat. Rachel Lim) — JIDA, Rachel Lim

Stable Spotify ID: `49iccsmr8Su1SXXwNfFO70`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Dream Pop" | Dream pop | ["pop"] | ["indie_pop_related", "atmospheric_pop"] | [] | mapped |
| secondary_styles[0] | "Electropop" | Electropop | ["pop", "electronic"] | ["pop_electronic"] | [] | mapped |
| secondary_styles[1] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** atmospheric_pop, indie_pop_related, modern_rnb, pop_electronic

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "hazy", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F054 — for what — potsu

Stable Spotify ID: `4B8L0sByBRJRUV1Uot2Ebd`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "African Traditional" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Afro House" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "West African Folk Music" | null | [] | [] | [] | mapping_review_required |

**Broad families:** electronic

**Overlapping neighborhoods:** none

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["electronic", "acoustic", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F055 — GET IT — keshi

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F056 — I'm Not Enough and I'm Sorry — Teqkoi, Snøw

Stable Spotify ID: `4P1L6AniTDJzANaubzWGYs`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Emo Rap" | Emo rap | ["hip_hop"] | ["emo_rap"] | [] | mapped |
| secondary_styles[0] | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |

**Broad families:** hip_hop, rnb_soul

**Overlapping neighborhoods:** emo_rap, trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "hazy", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F057 — The Bottom — Gracie Abrams

Stable Spotify ID: `4Sk74gcXTe9dnE1HU5Pn1y`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Rock" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Indie Pop" | Indie pop | ["pop"] | ["indie_pop_related"] | [] | mapped |
| secondary_styles[0] | "Alt-Pop" | Alternative pop | ["pop"] | ["alternative_pop"] | [] | mapped |

**Broad families:** pop

**Overlapping neighborhoods:** alternative_pop, indie_pop_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["clean", "layered", "acoustic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F058 — To My Youth — BOL4

Stable Spotify ID: `4gMPlHHAjOQnUrhsuqHivn`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Folk & Acoustic" | null | [] | [] | [] | mapping_review_required |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "K-Pop Ballad" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Piano Ballad" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F059 — Smart — LE SSERAFIM

Stable Spotify ID: `4lR8sYGMGZPvthF2yUfo7T`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "African Dancehall and Reggae" | null | [] | [] | [] | mapping_review_required |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Afrobeats" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F060 — summer — raph, EJEAN

Stable Spotify ID: `4osRLDg7abL4hLdfZ1c39g`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Alt-R&B" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F061 — Wet Dreamz — J. Cole

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Thematic/context concept only; no boom-bap or other sonic style inferred.; context_separate_from_sonic_style: The explicit hip-hop name supports its broad family; geography does not imply boom-bap.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F062 — Not Afraid — INTRN

Stable Spotify ID: `4yNhVidUIAtKPT72PrZuLP`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "hip hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[1] | "r&b" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "ambient pop" | Ambient pop | ["pop"] | ["atmospheric_pop"] | [] | mapped |
| secondary_styles[0] | "cloud rap" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "alternative r&b" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |

**Broad families:** electronic, hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, atmospheric_pop, modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["hazy", "electronic", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F063 — Morning Walk — Park Bird

Stable Spotify ID: `53eKx8ec2jDjt1m3VBUCEM`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "Jazz" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Lo-Fi Hip Hop" | Lo-fi hip-hop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[0] | "Chillhop" | Chillhop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[1] | "Downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |

**Broad families:** electronic, hip_hop

**Overlapping neighborhoods:** downtempo_related, hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "instrumental", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["clean", "electronic", "sample_based"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F064 — Do We Start to Like Each Other ? — Jordy Chandra

Stable Spotify ID: `5UUnRflW65AsvluD8d5N2U`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Lo-Fi Hip Hop" | Lo-fi hip-hop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[0] | "Chillout" | Chillout | [] | [] | ["chillout_umbrella"] | mapping_review_required |
| secondary_styles[1] | "Downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |

**Broad families:** electronic, hip_hop, pop

**Overlapping neighborhoods:** downtempo_related, hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** chillout_umbrella

**Gemini context, display only:** {"vocal_role": "spoken_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["sample_based", "clean", "electronic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.; context_separate_from_sonic_style: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F065 — If I Weren't Me — Katherine Li

Stable Spotify ID: `5VGDusp81Ed3T9xACRw5Os`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "Electropop" | Electropop | ["pop", "electronic"] | ["pop_electronic"] | [] | mapped |
| secondary_styles[0] | "Alt-Pop" | Alternative pop | ["pop"] | ["alternative_pop"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** alternative_pop, pop_electronic

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F066 — CLOUT CHASER — Tiffany Day

Stable Spotify ID: `5aawFqyuCB3K2P8KQvhFVs`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "rnb" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "hip_hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "contemporary_rnb" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "trap_soul" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "pop_rnb" | null | [] | [] | [] | mapping_review_required |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F067 — TOUCH — keshi

Stable Spotify ID: `5cgy5vMqVZbd8hYutp2txu`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Alternative R&B" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |
| secondary_styles[1] | "Pop Soul" | null | [] | [] | [] | mapping_review_required |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered", "hazy"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F068 — Fall in love — Han Jihyo, Park Soeun

Stable Spotify ID: `5h6c3ArwadWdEny5yXUPOt`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F069 — Love Always Leaves Me — 오안과 편견, Lee Yerin

Stable Spotify ID: `5l45vVLs4JKkhzN0tvkWJv`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Classical" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Korean Ballad" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Piano Ballad" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop

**Overlapping neighborhoods:** none

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F070 — Don't — Colette Lush

Stable Spotify ID: `5ngJKkOmjkN460b2ApBnLk`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |
| secondary_styles[1] | "Alternative R&B" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, modern_rnb, trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F071 — The Weekend — 88rising, BIBI

Stable Spotify ID: `5q3LwAHTqo9d3rET2EA9Nq`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |
| secondary_styles[0] | "Pop Rap" | Pop rap | ["hip_hop", "pop"] | ["rap_pop_crossover"] | [] | mapped |
| secondary_styles[1] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb, rap_pop_crossover, trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "balanced", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F072 — GANADARA (Feat. IU) — Jay Park, IU

Stable Spotify ID: `5quFr5s5PXYfUX5jV2EBZ1`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[1] | "Pop Rap" | Pop rap | ["hip_hop", "pop"] | ["rap_pop_crossover"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb, rap_pop_crossover

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["clean", "electronic", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F073 — Stay With Me — Teqkoi, Mouse

Stable Spotify ID: `5ri8u5RA8e4vGMyMAGXy0p`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Chopped and Screwed" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Cloud Rap" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |

**Broad families:** electronic, hip_hop, rnb_soul

**Overlapping neighborhoods:** trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "hazy", "sample_based"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F074 — Tea Time — Disvstxr

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F075 — Look At Me Now — Yayyoung

Stable Spotify ID: `5zfpJXfqGGh94YcStRlI2s`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Folk" | null | [] | [] | [] | mapping_review_required |
| secondary_families[1] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Acoustic Pop" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Contemporary Folk" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F076 — OMG — NewJeans

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: Bare dance label does not distinguish function, dance-pop, or electronic dance music.; context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F077 — me2urs2ours — Yayyoung, Sojou Kim

Stable Spotify ID: `6B9HXnRzmokTTxZNdV5T48`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B and Soul" | R&B and Soul | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[1] | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "Alternative R&B" | Alternative R&B | ["rnb_soul"] | ["modern_rnb", "alternative_rnb"] | [] | mapped |
| secondary_styles[1] | "Trap Soul" | null | [] | [] | [] | mapping_review_required |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** alternative_rnb, modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F078 — blue (with MINNIE) — yung kai, MINNIE

Stable Spotify ID: `6HIngEWX8ycnLjuUfSZyah`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "folk" | null | [] | [] | [] | mapping_review_required |
| secondary_families[0] | "pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "indie folk" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "indie pop" | Indie pop | ["pop"] | ["indie_pop_related"] | [] | mapped |

**Broad families:** pop

**Overlapping neighborhoods:** indie_pop_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F079 — Bullet Train Fantasy — Ibrahim, Luvbird

Stable Spotify ID: `6JjD8b5nYnwJ3zxYZ16rKg`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip-Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "Lo-Fi Hip-Hop" | Lo-fi hip-hop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[0] | "Chillout" | Chillout | [] | [] | ["chillout_umbrella"] | mapping_review_required |
| secondary_styles[1] | "Downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |

**Broad families:** electronic, hip_hop

**Overlapping neighborhoods:** downtempo_related, hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** chillout_umbrella

**Gemini context, display only:** {"vocal_role": "instrumental", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["clean", "acoustic", "sample_based"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.; context_separate_from_sonic_style: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F080 — Liability — Lorde

Stable Spotify ID: `6Kkt27YmFyIFrcX3QXFi2o`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Singer-Songwriter" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Piano Pop" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Indie Pop" | Indie pop | ["pop"] | ["indie_pop_related"] | [] | mapped |

**Broad families:** pop

**Overlapping neighborhoods:** indie_pop_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["acoustic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F081 — I'm Drunk And Confused — sagun

Stable Spotify ID: `6ZGqVXaJmhbYAK2DF8mWRR`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "hip-hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[1] | "r&b" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "lo-fi hip-hop" | Lo-fi hip-hop | ["hip_hop"] | ["hip_hop_beat_lineage", "lofi_chill_beats"] | [] | mapped |
| secondary_styles[0] | "chillwave" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[1] | "downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |

**Broad families:** electronic, hip_hop, rnb_soul

**Overlapping neighborhoods:** downtempo_related, hip_hop_beat_lineage, lofi_chill_beats

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["sample_based", "hazy", "electronic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F082 — we used to talk every night — Elijah Who

Stable Spotify ID: `6kAMaQt8UveeTctekIpUjF`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "Lo-Fi Beats" | null | [] | [] | [] | mapping_review_required |
| secondary_styles[0] | "Instrumental Hip Hop" | Instrumental hip-hop | ["hip_hop"] | ["hip_hop_beat_lineage", "instrumental_hip_hop"] | [] | mapped |
| secondary_styles[1] | "Downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |

**Broad families:** electronic, hip_hop

**Overlapping neighborhoods:** downtempo_related, hip_hop_beat_lineage, instrumental_hip_hop

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["sample_based", "hazy"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F083 — Thirsty — aespa

Stable Spotify ID: `6nICBdDevG4NZysIqDFPEa`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[1] | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb, trap_related

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.; broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F084 — Stoked — Weston Estate

Stable Spotify ID: `6nef0wHkelfKqNVHAtzJbR`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| primary_style | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |
| secondary_styles[0] | "Melodic Rap" | Melodic rap | ["hip_hop"] | ["melodic_rap"] | [] | mapped |

**Broad families:** hip_hop, rnb_soul

**Overlapping neighborhoods:** melodic_rap, trap_related

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "mixed_rap_and_singing", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F085 — By My Side — JUNNY

Stable Spotify ID: `6nzCvAtyADh0wwZEVMoujK`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[0] | "K-R&B" | null | [] | [] | [] | mapping_review_required |

**Broad families:** pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["clean", "electronic"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F086 — Sit Around — City Girl, tiffi

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F087 — Phantom Embrace — City Girl

Stable Spotify ID: `6rj9qDXWANe0U69asDzxMp`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "dance_electronic" | null | [] | [] | [] | mapping_review_required |
| primary_style | "ambient" | Ambient | [] | ["ambient_related"] | [] | mapped |
| secondary_styles[0] | "downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |
| secondary_styles[1] | "chillout" | Chillout | [] | [] | ["chillout_umbrella"] | mapping_review_required |

**Broad families:** electronic

**Overlapping neighborhoods:** ambient_related, downtempo_related

**Separate scene/context:** chillout_umbrella

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["electronic", "hazy", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.; context_separate_from_sonic_style: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F088 — The Peace — underscores

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F089 — Favorite Part — JO YURI

Stable Spotify ID: `6zKX91EvxRHr42ZiZ5C9kN`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Hip Hop" | Hip-hop | ["hip_hop"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[1] | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |

**Broad families:** hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb, trap_related

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "layered"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.; broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F090 — Cloudy Thoughts — HYEJIN

Stable Spotify ID: `70YbAV2UKPee15B00RbPcT`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "R&B" | R&B | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Contemporary R&B" | Contemporary R&B | ["rnb_soul"] | ["modern_rnb"] | [] | mapped |
| secondary_styles[1] | "Trap" | Trap | [] | ["trap_related"] | [] | mapped |

**Broad families:** electronic, pop, rnb_soul

**Overlapping neighborhoods:** modern_rnb, trap_related

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.; broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F091 — Perfect Night — LE SSERAFIM

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F092 — Flash Forward — LE SSERAFIM

Stable Spotify ID: `74cpuIw43kA8xPgbQEPdss`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |
| secondary_styles[1] | "Electropop" | Electropop | ["pop", "electronic"] | ["pop_electronic"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F093 — Shouldn't Be — Luke Chiang

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F094 — Season of Memories — GFRIEND

Stable Spotify ID: `7LFwi4RolcCPnVEXXXVfQP`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| secondary_families[0] | "Electronic / Dance" | null | [] | [] | [] | mapping_review_required |
| primary_style | "K-Pop" | K-Pop | [] | [] | ["korean_pop_scene"] | mapped |
| secondary_styles[0] | "Dance-Pop" | Dance-pop | ["pop"] | ["pop_electronic", "dance_pop"] | [] | mapped |

**Broad families:** pop

**Overlapping neighborhoods:** dance_pop, pop_electronic

**Separate scene/context:** korean_pop_scene

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; context_separate_from_sonic_style: Context only. No sonic neighborhood or broad family follows solely from the scene label.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F095 — The Hills — The Weeknd

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** broad_style_subtype_unspecified: Subtype unspecified. Do not derive a hip-hop or electronic family from this label alone.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F096 — Die Right Here — david hugo

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F097 — She loves the color green and I love her — City Girl

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

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.; context_separate_from_sonic_style: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F098 — Lucid (feat. LILAC) — JIDA, Kate Kim

Stable Spotify ID: `7iov2YtUJgLmHXwpYXLcoo`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Synth-pop" | Synth-pop | ["pop", "electronic"] | ["pop_electronic", "synth_pop"] | [] | mapped |
| secondary_styles[0] | "Dream Pop" | Dream pop | ["pop"] | ["indie_pop_related", "atmospheric_pop"] | [] | mapped |

**Broad families:** electronic, pop

**Overlapping neighborhoods:** atmospheric_pop, indie_pop_related, pop_electronic, synth_pop

**Separate scene/context:** none

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "layered", "hazy"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** No mapper warning.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F099 — m o v i e (Feat. Jade) — Stupinuts, Jade

Stable Spotify ID: `7nD9LjsenfCRv4uxy93xhZ`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "R&B / Soul" | R&B and Soul | ["rnb_soul"] | [] | [] | mapped |
| secondary_families[1] | "Pop" | Pop | ["pop"] | [] | [] | mapped |
| primary_style | "Trip-Hop" | Trip-hop | ["electronic", "hip_hop"] | ["hip_hop_beat_lineage", "downtempo_related"] | [] | mapped |
| secondary_styles[0] | "Downtempo" | Downtempo | ["electronic"] | ["downtempo_related"] | [] | mapped |
| secondary_styles[1] | "Chillout" | Chillout | [] | [] | ["chillout_umbrella"] | mapping_review_required |

**Broad families:** electronic, hip_hop, pop, rnb_soul

**Overlapping neighborhoods:** downtempo_related, hip_hop_beat_lineage

**Separate scene/context:** chillout_umbrella

**Gemini context, display only:** {"vocal_role": "sung_led", "arrangement_focus": "lead_vocal", "texture_tags": ["electronic", "clean", "hazy"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.; context_separate_from_sonic_style: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________

## F100 — Celestial Angel — City Girl

Stable Spotify ID: `7rAOIiVhiD3vklTrCUpfYo`

| Raw source field | Raw label (JSON string, exact) | Canonical concept | Broad families | Style neighborhoods | Scene/context | Mapping status |
| --- | --- | --- | --- | --- | --- | --- |
| primary_family | "Electronic" | Electronic | ["electronic"] | [] | [] | mapped |
| secondary_families[0] | "Easy Listening" | null | [] | [] | [] | mapping_review_required |
| primary_style | "Ambient" | Ambient | [] | ["ambient_related"] | [] | mapped |
| secondary_styles[0] | "Chillout" | Chillout | [] | [] | ["chillout_umbrella"] | mapping_review_required |

**Broad families:** electronic

**Overlapping neighborhoods:** ambient_related

**Separate scene/context:** chillout_umbrella

**Gemini context, display only:** {"vocal_role": "vocal_samples_only", "arrangement_focus": "beat_or_instrumental", "texture_tags": ["electronic", "hazy", "clean"]}

**Existing owner first-pass words, verbatim:** ""

**Review note:** Inspect the unchanged mapping and original classification separately. No prior answer is inferred.

**Warnings:** mapping_review_required: No explicit alias. Preserve the label; do not infer a concept.; mapping_review_required: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.; context_separate_from_sonic_style: May denote a listening use or heterogeneous sonic styles. Retain the ambiguous umbrella; do not equate with downtempo or lo-fi.

**Owner mapping decision:** __________  **Owner classification decision:** __________

**Owner notes:** __________
