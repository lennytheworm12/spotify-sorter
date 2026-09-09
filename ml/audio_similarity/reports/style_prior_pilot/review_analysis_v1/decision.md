# Style-prior human audit: next-step decision

The completed 12-pair audit does not justify increasing or activating the style penalty. The frozen classifier showed aggregate separation (playlist anchor-macro AUC 0.711), but its penalty did not improve artist-disjoint development ranking (D delta -0.030, descriptive 95% interval [-0.077, 0.006]). Human explanations identify both missed distinctions and exaggerated distinctions.

## What the reviewer said

Among six previously accepted pairs, four were marked NONE: Fresh Air / Die Right Here; By My Side / Shouldn't Be; me2urs2ours / blue; Shiawase no Monosashi / Do We Start to Like Each Other. Their style distances were respectively 0.602, 0.451, 0.484 and 0.463. These are substantial classifier distances despite reported closeness.

Phantom Embrace / risk was explicitly retained at 4/5 despite different vocal roles: the reviewer described gentle, submerged vocals fitting the shared atmosphere. boys dont cry / Shoota was described as pretty close despite an electronic/hyperpop-versus-rap texture distinction. The latter note supplies no new numeric rating; retain the historical 4/5, rather than inventing a revised score.

Among six previously rejected pairs, four were marked FAMILY: DOWNPOUR / Not Afraid; No I Don't Want, Just Anyone / The Hills; The Color Violet / Hit the Wall; GET IT / I'm Not Enough and I'm Sorry. Their distances were only 0.150, 0.225, 0.160 and 0.197. These notes repeatedly distinguish lo-fi from contemporary/dark R&B or distinguish musical families that the classifier represents similarly. Heart / The Way was marked VOCALS, with dreamy/airy versus sharper presentation; The Peace / Perfect Night was marked TEXTURE, contrasting abrasive editing with smoother production.

These are selected counterexamples, not a random prevalence sample. Category counts cannot estimate the fraction of all failures attributable to a cause. Detailed production/sample claims in prose are reviewer-provided descriptions, not independently verified acoustic facts. Existing compatibility ratings remain immutable.

## Interpretation

The same kind of difference can be acceptable in one pairing and important in another. Neither a genre veto nor a vocal-presence veto follows from these notes. The classifier's distances are not yet a reliable measure of the differences this reviewer considers playlist-relevant. This does not demonstrate that style is irrelevant or that all dedicated representations fail.

## Smallest next experiment

1. Run an audio/provenance and inference audit on the 24 tracks in this packet, prioritizing the strongest contradictions. Confirm the retained source matches the track identity, the same source was served in review and extracted, and pooled classifier scores reconstruct from cached patches. Reproduce a few outlier predictions through the official reference inference path; compare patch-level versus song-mean behavior as diagnostics, without searching for a new scoring rule. A source hash proves consistent bytes, not that a download contains the correct song. Ask the owner to verify identity only where local evidence cannot settle it.
2. If this reveals an engineering or source problem, correct it under a new versioned protocol; preserve the historical run and verdict.
3. If the pipeline is sound, test the same frozen Discogs-EffNet model's existing 1280-D embedding output as one non-learned representation control, against its 400-label distance and frozen CLAP on the same grouped development evidence. Freeze the pooling and cosine rule first. This isolates information lost by the classifier's label output without introducing another model, prompt search, or a trained similarity function. No additional large review queue is needed for that control.

Do not tune lambda around these examples, add exceptions, activate production behavior, or claim untouched confirmation from this audit. Decide whether further learned compatibility work is warranted after this bounded check.

Status: human annotations frozen; next experiment recommended, not executed here.
