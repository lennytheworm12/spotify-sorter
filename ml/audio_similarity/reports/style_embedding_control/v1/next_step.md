# Next-step decision

Close this control as LATENT_ADVANTAGE_NOT_ESTABLISHED. Stop developing a generic Discogs style penalty or its latent cosine replacement as the main fix for this reviewer. The current evidence does not establish a benefit; it does not prove all style information or all learned scorers useless.

On the same grouped playlist evidence, latent cosine achieved 0.613 agreement, label distance 0.625, CLAP D 0.585 and CLAP C 0.677. Latent-minus-label change was -0.012 with descriptive interval [-0.081, 0.058]; latent-minus-C was -0.063 [-0.173, 0.046]. Excluding the three owner-confirmed alias cases did not change the conclusion. Strong-preference latent performance was also below the label control. On all existing good-versus-bad playlist comparisons, C AUC was 0.800, labels 0.711 and latent 0.697.

The next research design should start from the strongest observed existing baseline, frozen C full-song music-CLAP, and target the actual playlist-compatibility rubric. A small, strongly regularized symmetric scorer is a more justified next test than another genre classifier or manual exception layer. First inventory the C representation cache and freeze a supervision/evaluation sufficiency gate; use the existing source/artist-disjoint groups and existing human labels. Train only if that gate permits a credible comparison; otherwise specify a minimal grouped supervision seed rather than weakening the split. No new queue is generated here.

This is not a rerun of the same hypothesis unchanged: the earlier Stage 5G.1/1A learned tests used Arm-D evidence and historical whole-song similarity labels. C uses the validated HTSAT-base music checkpoint, while D used HTSAT-tiny AudioSet fusion. The 419 playlist-compatibility judgments provide the relevant target for this proposed design. Do not claim that the earlier D scorer failure proves failure for C and the playlist target.

Before implementation, freeze one small architecture, a tiny TRAIN fitting check, regularization/selection rules, baseline reproduction, ordinal and good-versus-bad metrics, grouped uncertainty, and a strict no-production boundary. Do not launch an architecture search, fine-tune CLAP, add MuQ or other features, or tune around named songs. All existing labels remain development evidence; no production win or fresh confirmation follows from this pilot.

Alternative product-level playlist-context experiments may be designed separately. This control does not implement clustering or admission and does not establish that one global pair score is sufficient for playlist membership.
