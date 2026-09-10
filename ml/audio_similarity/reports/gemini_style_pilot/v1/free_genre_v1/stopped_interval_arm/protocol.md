# Free-genre retry v1: protocol frozen before inference

The owner requested: "try again but let gemini auto derive the genres".
This authorizes a separate additional arm; it does not reset or rewrite the original 20-call ledger.
Use the same full 16 neutral FLAC recordings, hashes, Gemini model and sampler config.
Keep no genre vocabulary, genre definitions, genre examples or family/style mapping in the request.
Broader family and specific style fields are free text. Mechanical facet enums remain for comparability.
The new prompt also removes genre-specific listening hints and the closed-vocabulary unmapped-style field.
Thus this tests removal of the ontology/instruction bundle, not the causal effect of a single definition.
No identities, prior answers, owner expectations, ratings, internet sources or conversation history go to Gemini.
No search, metadata fusion, lyrics analysis, model change or sampler tuning.

Order: original A01 and A03 engineering smokes, then the other 14 primaries in original order;
finally one repeated identical request each for A01 and A03. At most 18 new generations, 38 overall.
Preserve each raw attempt, response ID/version, usage, counted input, reservation, latency and finish reason.
No automatic retries, classification repair, resampling for preferred answers or primary replacement.
Stop on any operational failure. Unknown/uncertain genre is a valid outcome, not a failed smoke.
Budget: prior raw-response costs reconciled first; subtract them from the original $2 combined cap.
Reserve the full documented input limit plus bounded output before every new generation.
Reuse unexpired hash-verified uploaded files; otherwise re-upload the same prepared bytes once.
Freeze the full new primary/repeat inventory before inspecting their genres or comparing owner notes.

Analysis after freeze: side-by-side original/free profiles and existing owner notes for all 16 tracks;
repeat stability, schema/usage/audio validation, cache replay with zero API calls; join all 15 existing
PLAYLIST_COMPATIBILITY_V1 pairs within the pilot by stable IDs, leaving unrated diagnostic pairs null.
Preserve raw free-text labels. No semantic mapping, genre weights or reranking outcomes are fitted.
This is selected development evidence, with expectations already known to the assistant and owner.
A stochastic two-arm comparison cannot isolate prompt causality or establish held-out accuracy.
A changed label is not proof of a correct description or improved playlist compatibility.
No production changes, new pair judgments, CLAP/MuQ inference or modifications to prior artifacts.
