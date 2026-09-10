# Point-timestamp continuation, frozen before new calls

The original free-genre arm stopped after two engineering requests. A03 returned
an interval starting at 31 seconds and ending at 30 seconds. Both raw responses,
settlements, the STOP marker, and the exact implementation at commit b322790 remain preserved.
No genre output from either request has been inspected for agreement or used to alter the prompt.

The only prompt change replaces the interval request with one at_seconds point timestamp
per observation. The evidence schema changes accordingly, bounded to the same full duration.
All genre/facet instructions, audio, model, sampler, and blinding remain unchanged.
No genre names, definitions, examples, source identities or human judgments are supplied.
No response is repaired or promoted from the failed run to a valid primary.

The two spent requests reduce the new retry allowance from 18 to 16. This continuation
runs all 16 primaries in the original smoke-first order; no repeat requests remain.
The first two replacement smokes must pass operational checks. Another failure stops
this continuation, with no further same-turn revisions or retries. Combined cap is
38 generation attempts and $2 across all original and free-genre runs.
The previous two costs are reconciled from raw responses and subtracted before reservations.

Freeze all 16 profiles before descriptive comparison with prior profiles, owner notes,
and all 15 existing playlist-compatible pair judgments. Preserve uncertainty and unknowns.
No genre weighting, reranking, new judgments, production change or held-out efficacy claim.
This tests an instruction-bundle revision under stochastic generation, not isolated causality.
Same-request stability of this revised arm is explicitly untested because repeats were consumed.
