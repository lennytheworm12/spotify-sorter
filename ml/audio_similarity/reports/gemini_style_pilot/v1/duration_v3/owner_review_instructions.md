# Owner audio review

The 16-row `owner_review_sheet.csv` is for descriptions of these exact recordings.
It creates no new song-pair ratings. Leave uncertain answers uncertain; ordinary
words are welcome, and there is no note-length limit.

1. Open the neutral full-recording FLAC named in `audio_file` using your player.
2. Before reading the model summary, note whether this is the intended recording,
   your family/style words, the vocal/arrangement character and major section
   changes. You do not need formal genre vocabulary.
3. Then consult `profile_summary.csv` and the individual `profiles/` JSON files.
   Record acceptable alternative labels, any audible description/timestamp
   problems, and whether the model sounds too certain. A disagreement need not
   mean either description is wrong.
4. Save a separate completed CSV and return its path. Keep the identifiers and
   headers. Your answers will be frozen separately from all Gemini outputs.

Start with A03 My Gamecube Broke., A07 The Hills, C01 Saturation in Delay, Love in
Anger and C05 The Peace. They have repeat inconsistencies or descriptions worth
checking carefully. For A03, consult `repeats/A03.json` after your independent
description too. Then complete the remaining tracks briefly.

Do not infer a song's sound from its artist name, previous model score or a desired
playlist separation. The current model profiles have not been accepted as style
truth. In-range timestamps have passed an engineering constraint; you still need
to judge whether the claimed events occur there.

The audio is the entire retained recording, which can be an official video or
another documented retained version rather than an identical Spotify album
master. Source preparation preserved the full decoded waveform, but a mistaken
retained recording can still be flagged here.
