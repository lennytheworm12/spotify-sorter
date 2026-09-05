# Stage 5B.2 Blinded Sol Metadata Review

You are independently evaluating raw YouTube search candidates for Spotify songs.

For every supplied Spotify target and each of its three candidates, assign exactly one label:

- `IDEAL`: clearly the intended recording or approved representation-equivalent recording, from a highly suitable source.
- `ACCEPTABLE`: safe for downstream CLAP/MuQ similarity and playlist organization, but the source is not ideal.
- `WRONG`: wrong song, performer, recording, materially distinct version, or otherwise unsuitable.
- `UNCERTAIN`: the supplied metadata is insufficient for a confident judgment.

Product semantics:

- Exact requested recording is preferred.
- An ordinary live target may use a canonical studio recording as an acceptable representation when no exact live recording is established.
- A remaster may use a canonical base/original master as an acceptable representation.
- Remix, acoustic, slowed/sped/reverb, instrumental, karaoke, genre-changing, and other materially different versions remain distinct unless explicitly requested.
- Canonical provenance and popularity can support a judgment but cannot override explicit recording conflicts.

You receive only Spotify target metadata and raw YouTube metadata. Candidate order is deterministically blinded. You must not infer or request human labels, resolver features, original search rank, benchmark outcomes, or prior Stage 5B decisions.

Return the required JSON schema only. Give one concise metadata-grounded reason per candidate. Treat your judgments as secondary evaluation evidence, not human ground truth.
