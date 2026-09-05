# Stage 5E.1 CLAP AFF feasibility

**Status:** `AFF_READY`

The current baseline checkpoint has 505 state keys and no trained AFF or fusion-local projection parameters. Enabling native fusion with that checkpoint would leave new fusion layers untrained.

The installed LAION CLAP implementation defines native `aff_2d` with a resized global log-mel view and three 10-second local log-mel crops. Its official fusion checkpoint is `630k-audioset-fusion-best.pt` (SHA-256 `fb171dd9b608aebdac3d89286cd7615c5100af4cc7dc37797c7fb8d3cc15e3a5`).

A matched design uses the current checkpoint for A/C and the fusion checkpoint for B/D. B versus D then isolates learned AFF from arithmetic view averaging; A versus C isolates centered sampling from full-song chunk averaging. Comparisons across those pairs retain a checkpoint confound.

The final corpus freeze is deferred while a retained-media batch is active. No network requests or encoder inference ran during preparation.
