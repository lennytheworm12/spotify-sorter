# Implementation review

Reviewed the label mapper, registry, separate review-note input, offline review builder and tests against correctness, readability, architecture, security and performance. This is a research-only addition, with no changes to existing production modules or frozen model producers.

- Pure mapping consumes only four genre fields. Metadata, owner judgments and model audio facets cannot influence canonical concepts or memberships. Review notes join afterwards by stable identity and cannot override mapping fields.
- Every membership points to raw field occurrences. Ambiguous/unrecognized labels remain explicit with no guessed sonic memberships. Scene/context rules are checked against sonic leakage. Alias collisions and unknown membership references fail validation.
- Duplicate aliases within one concept are deliberate lexical alternatives. Repeated concepts across source fields preserve traces but add no weight. Compound family labels are not silently split or equated with narrower concepts.
- The CLI enforces the original 16 identities before mapping, accepts no full-corpus override and refuses output paths that overlap frozen inputs. It reuses create-once artifact and hash-verification utilities. The registry, code and review annotations are covered by input hashes.
- No model, audio, network or scorer dependency is needed for mapping. There are no new dependencies or external API calls. An actual replay passed with socket connections forbidden. Current CSV cells passed the formula-prefix scan; raw source strings and copied context matched every frozen input profile.
- Deterministic synthetic tests exercise aliases, Unicode variants, abstention, cross-family overlap, scene separation, metadata/facet independence, identity gates, tamper checks and replay. Full non-heavy suite: 1409 passed, 12 deselected. Actual replay verified 2458 protected files and the original private execution hashes.

The musical relationships remain curator-authored hypotheses for inspection. Literal mapping correctness cannot establish classification accuracy or playlist suitability. In particular, family labels do not infer vocal role, shared neighborhoods are not automatic matches, and no neighborhood overlap is not automatic rejection. The explicit review-required umbrellas and questionable upstream descriptions are retained without song exceptions.
