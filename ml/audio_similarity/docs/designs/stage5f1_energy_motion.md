---
title: Stage 5F.1 — Full-Track Energy and Motion Attribute Layer
aliases:
  - Stage 5F.1 — Tempo and Pulse Attribute Layer
  - Stage 5F.1 — Energy and Motion
status: implementation-design-revised-unvalidated
revision: 2
revised: 2026-09-05
project: Spotify Sorter
tags:
  - spotify-project
  - audio-similarity
  - mechanical-audio-features
  - energy-motion
  - implementation-design
---

# Stage 5F.1 — Full-Track Energy and Motion Attribute Layer

**Decision:** implement an interpretable, full-track energy/motion sensor beside the frozen CLAP + MuQ backbone. Validate extraction and retrospective usefulness before designing a ranking change.

**Design status:** revised implementation contract. The formulas and thresholds below are proposed engineering defaults, not validated findings. An implementation may calibrate them on the defined synthetic/golden development fixtures, record the amendment, and freeze a new configuration before the rated-pair analysis. Passing tests must not be achieved by weakening gates after examining final similarity labels.

**Primary corpus:** the original amended frozen 100 Spotify tracks, restricted on both query and candidate axes. **Optional reference corpus:** the frozen 741-track Stage 5E.1 corpus. **Audio:** existing retained local source files only. **Production activation:** none in this stage.

This revision supersedes the earlier tempo-first design in this same file. The filename is retained to preserve Obsidian links. The emphasis is now **energy and motion first**, with enough rhythm analysis to explain beat strength and subdivision activity. Future tonal and structure sensors remain part of the intended system.

## 1. Product intent and scope

The current system can recognize shared timbre, instruments, vocals, and production while missing how differently two songs move. A mellow lo-fi/R&B song and a harder rap song may share sparse harmony, 808s, and processed vocals while differing in attack density, rhythmic emphasis, loudness, and changing intensity.

The intended architecture is:

```text
retained full source audio
    ├── frozen CLAP + MuQ                 broad acoustic/semantic similarity
    ├── ENERGY / MOTION                   implement first in Stage 5F.1
    ├── RHYTHM                            supporting subset now; extend later
    ├── TONAL                             later, separately validated
    └── STRUCTURE                         later, separately validated
                    ↓
        raw measurements + validity + provenance
                    ↓
        separate, explainable pair components
                    ↓
        retrospective evaluation; later reviewed fusion experiment
```

The system should eventually recognize the following mechanical attributes. Do not implement the entire roadmap in this stage.

| Family | Intended recognition | Stage 5F.1 commitment |
|---|---|---|
| Energy / motion | Perceived arousal, onset density, beat strength, percussion density, spectral flux, loudness, dynamic complexity | Implement the measurements and explicit proxies specified below. Perceived arousal is a transparent, uncalibrated proxy, not a measured human judgment. |
| Rhythm | BPM, tempo confidence, rhythmic regularity, subdivision/activity, danceability-like score | Implement BPM candidates, separate pulse reliability and metrical certainty, regularity, subdivision profile, and a conservative diagnostic danceability proxy. |
| Tonal | Key, mode, chroma, harmonic-change rate | Future sensor. Key/mode will need ambiguity and modulation handling; do not add placeholder numeric values now. |
| Structure | Section boundaries, repetition, intro/verse/chorus/bridge proportions | Future sensor. Repetition/boundaries and semantic section labels are separate problems. Do not infer “chorus” merely from loudness or repetition. |

Energy and rhythm overlap but must not be interchangeable. A slow track may be forceful; fast music may be soft; a loud drone may have little rhythmic motion; a compressed track may be intense but dynamically flat. High dynamic complexity is not automatically high arousal. Dense attacks need not be drums.

### 1.1 Deliverables

1. Deterministic source-to-feature extraction, with per-family validity.
2. Full-track loudness, dynamics, onset, flux, percussive-activity, and supporting pulse measurements.
3. Compact 10-second temporal profiles so one global average does not erase changes within a track.
4. Versioned track, window, scaler, pair, validation, and retrospective-analysis artifacts.
5. A provenance-preserving snapshot of all compatible historical frozen-100 ratings.
6. An explicit decision: `SUPPORTED_FOR_5F2`, `DIAGNOSTIC_ONLY`, `REVISE`, or `REJECT`.

### 1.2 Boundaries

No source acquisition, API calls, model downloads, new encoder inference, new review queue, ranking mutation, learned arousal model, drum transcription, Demucs, key estimation, or semantic song segmentation. A small existing-audio golden audit is engineering validation; it does not create a similarity-rating task.

A future reranker may consume these components. This stage must not implement or run `simulate-rerank`. Ranking improvement belongs to Stage 5F.2 and is not a prerequisite for finishing Stage 5F.1.

## 2. Repository integration and frozen inputs

Paths below are relative to `ml/audio_similarity/` unless stated otherwise.

| Existing contract | Required use |
|---|---|
| `src/audio_similarity/audio.py::load_audio()` | Decode validated `(channels, samples)` float waveform. Reuse it; add full-duration preprocessing in a new module. |
| `audio.py::preprocess_file()` / `preprocess_waveform()` | These enforce the historical 24 kHz / 30-second MERIT path. Do not use them for this sensor and do not change their contract. |
| `src/audio_similarity/conventional_features.py` | Historical FMA table baseline; leave it unchanged. |
| `pyproject.toml`, `uv.lock` | Repository lock resolves librosa 0.11.0 at revision time. Use the locked environment and record resolved versions. |
| `reports/stage5e1_four_arm_retrieval/experiment_config.json` | Frozen A representation, fixed MuQ, weights, and duplicate rules. |
| `reports/stage5e1_four_arm_retrieval/corpus_manifest.json` | Frozen retained source identity and 741 membership. |
| `reports/stage5e1_four_arm_retrieval/similarity_matrices.npz` | Existing scores. Load with `allow_pickle=False`; align by stored Spotify IDs. |
| `reports/stage5c2_representative_100_amended_v2/selected_sources.json` | Authoritative amended original-100 membership and selected video identities. |
| `src/audio_similarity/stage5e2_subset.py` | Existing source-validation and restriction-on-both-axes pattern. Reuse pure helpers where suitable. |
| `src/audio_similarity/stage5e2.py` | Label compatibility and conflict-resolution precedent; do not call its mutating evaluation/queue pipeline. |
| `reports/stage5e2_arm_d_original100_v2/` | Existing original-100 evaluation evidence, including subset reference and review-queue identities. |

The frozen base score is:

```text
base = 0.7172981519 * A_CLAP_cosine + 0.2827018481 * fixed_MuQ_cosine
```

Read and verify these values from the frozen configuration. A mismatch is a contract error, not permission to update the old configuration. Check actual NPZ keys before mapping matrices; do not guess array order. Prefer existing fixed MuQ evidence; if only A and combined matrices are available, derive MuQ algebraically with these weights, mark `score_origin=DERIVED_FROM_FROZEN_COMBINATION`, and verify bounds within floating tolerance. Do not run encoders.

The checked Stage 5E.2 report states `ARM_D_HUMAN_EVIDENCE_INSUFFICIENT`. Describe A as the retained baseline and D as an unpromoted challenger. Do not claim a conclusive A victory or an isolated sampling-method comparison: A/D differ in checkpoint and architecture.

### 2.1 Source manifest contract

Exactly one membership row per Spotify ID:

```text
spotify_track_id, source_sha256, retained_source_path,
youtube_video_id, corpus_memberships, expected_source_duration_seconds,
expected_duration_basis, original100_selected_video_id,
primary_artist_id, artist_credit, source_format, source_bitrate_when_available
```

Use the frozen full-source SHA from Stage 5E for extraction. Compare selected video IDs to establish original-100 membership. A retained recording may differ in duration from Spotify metadata; metadata duration is a warning unless it is explicitly an authoritative retained-source duration.

Require all 100 expected IDs exactly once and the expected video identities. A missing local file creates a failed track row; it must not silently shrink the corpus. Hash mismatches against the frozen manifest stop corpus analysis. Source replacements require a new manifest/run. A cache unit test may use a changed source with a new approved fixture manifest; this is not permission to accept changed production-corpus bytes.

Exclude self-pairs and pairs sharing source SHA or YouTube video ID from retrieval/label analysis. A separate pure-function identity test may compare a valid track with itself.

### 2.2 Snapshot discipline

`prepare` records hashes of the governing design, configuration, original-100 selector, corpus manifest, matrices, historical rating files, and review queues used for identity verification. Capture mutable ratings once into the new run directory. All analysis reads that snapshot; new ratings require a new run. Record pre/post hashes of every Stage 5E input touched by the stage.

## 3. Feature semantics and validity

Every measurement is classified as one of:

- **Measurement:** reproducible quantity with units, such as integrated LUFS or detected onsets per active second.
- **Proxy:** explicitly defined heuristic, such as HPSS percussive onset density or arousal proxy.
- **Reliability:** evidence that a measurement family is usable. It is not a calibrated probability.

Never name the HPSS estimate `drum_count`, the summary score `true_arousal`, or the danceability proxy a Spotify audio feature. No claim of compatibility with Spotify's proprietary feature scale is permitted.

Per-family status enum:

```text
VALID | LOW_CONFIDENCE | UNAVAILABLE
```

Top-level extraction status:

```text
SUCCESS   all required measurement families completed; pulse may be LOW_CONFIDENCE
PARTIAL   at least one valid measurement family, but another computation failed/unavailable
FAILED    source/decode failure or no usable measurement families
```

An ambient track can be `SUCCESS` with valid energy measurements and `pulse=LOW_CONFIDENCE`. Do not require a stable beat to measure loudness or spectral movement. Silence has explicit degenerate reasons and no confident pulse/arousal assertion. Zero onset count is a valid measured zero on audible sustained audio; null means unmeasurable or unsupported.

## 4. Configuration and reproducibility contract

Use separate immutable configurations:

- `extraction_config`: all waveform/DSP rules and validity thresholds.
- `comparison_config`: scaler choice, feature groups, kernels, proxy formulas.
- `evaluation_config`: label snapshot, hypotheses, thresholds, uncertainty method.
- `execution_config`: worker count, deadlines, memory ceiling, output locations.

Cache raw extraction by source + extractor code + environment + extraction configuration. Changing an evaluation threshold or output directory must not trigger audio recomputation.

The following JSON is the required initial configuration. Sections below define all algorithms; their constants are also extraction/comparison identity through the versioned algorithm specification hash. Do not implement undocumented library defaults. Schema validation must reject unsupported enum values, nonfinite numbers, nonpositive lengths/sigmas, reversed tempo/rate limits, thresholds outside their stated bounds, mel_fmax above analysis Nyquist, and disagreement between hop/window parameters and the versioned algorithm specification. Unknown config keys fail validation.

```json
{
  "schema_version": "stage5f1-energy-motion-config-v2",
  "extractor_id": "FULL_TRACK_ENERGY_MOTION_LIBROSA_FFMPEG_V1",
  "extraction": {
    "sample_rate_hz": 22050,
    "hop_length": 256,
    "n_fft": 2048,
    "win_length": 2048,
    "window": "hann",
    "center": true,
    "pad_mode": "constant",
    "maximum_duration_seconds": 1800.0,
    "minimum_active_seconds": 10.0,
    "minimum_pulse_active_seconds": 20.0,
    "minimum_sample_rate_hz": 8000,
    "maximum_sample_rate_hz": 192000,
    "maximum_channels": 2,
    "active_reference_percentile": 95.0,
    "active_db_below_reference": 40.0,
    "absolute_silence_dbfs": -80.0,
    "profile_window_seconds": 10.0,
    "profile_minimum_active_seconds": 2.0,
    "mel_bands": 128,
    "mel_fmin_hz": 30.0,
    "mel_fmax_hz": 10000.0,
    "onset_lag_frames": 1,
    "onset_log_top_db": 80.0,
    "minimum_raw_onset_strength": 0.5,
    "onset_max_size": 1,
    "onset_peak_delta": 0.07,
    "onset_peak_pre_max_frames": 3,
    "onset_peak_post_max_frames": 3,
    "onset_peak_pre_avg_frames": 9,
    "onset_peak_post_avg_frames": 9,
    "onset_peak_wait_frames": 3,
    "hpss_kernel_size": [31, 31],
    "hpss_power": 2.0,
    "hpss_margin": [2.0, 2.0],
    "tempogram_win_length": 768,
    "minimum_tempo_bpm": 30.0,
    "maximum_tempo_bpm": 300.0,
    "candidate_count": 5,
    "candidate_nms_octaves": 0.08,
    "tempo_match_fraction": 0.04,
    "candidate_support_ratio": 0.50,
    "metrical_factors": [0.5, 1.0, 2.0, 4.0],
    "pulse_reliability_threshold": 0.55,
    "exact_tempo_certainty_threshold": 0.60,
    "loudness_backend": "ffmpeg_ebur128_original_channels",
    "loudness_dualmono": false,
    "normalization_mode": "integrated_lufs_linear_gain",
    "normalization_target_lufs": -23.0,
    "maximum_absolute_normalization_gain_db": 20.0,
    "raw_source_loudness_in_similarity": false
  },
  "comparison": {
    "reference_corpus": "original100",
    "minimum_reference_values": 30,
    "scaler_clip_z": 4.0,
    "iqr_minimum": 0.000001,
    "exact_sigma_octaves": 0.15,
    "family_sigma_octaves": 0.10,
    "minimum_common_features": 2,
    "minimum_common_weight_fraction": 0.75,
    "production_activation": false
  },
  "evaluation": {
    "seed": 20260905,
    "bootstrap_replicates": 2000,
    "high_base_quantile": 0.75,
    "low_rating_max": 2,
    "high_rating_min": 4,
    "minimum_slice_pairs_per_group": 20,
    "minimum_slice_unique_tracks": 20,
    "minimum_slice_unique_artists": 10,
    "minimum_primary_mismatch_difference": 0.05,
    "minimum_core_measurement_coverage": 0.95,
    "minimum_pulse_valid_fraction": 0.60
  },
  "execution": {
    "workers": 1,
    "per_track_timeout_seconds": 900,
    "loudness_timeout_seconds": 180,
    "worker_memory_limit_gib": 12,
    "retry_failed": false
  }
}
```

The hop is deliberately 256 rather than the earlier 512: approximately 11.6 ms for onset timing and finer fast-tempo lag resolution. The 768-frame tempogram retains approximately 8.9 seconds of context. This is a design choice requiring runtime measurement, not a speed claim.

Float32 waveform/spectral intermediates and float64 scalar reductions are the defaults. The first implementation need not share arrays across worker processes; share them only within one source worker. Quantiles use NumPy `method="linear"`; medians use the same quantile convention. Every ratio must specify zero-denominator behavior. Helpers for nearest-integer octave rounding must implement the explicit tie rule; do not rely on language-dependent rounding defaults. Use `eps=1e-12` for numerical division where a valid positive quantity exists; use explicit invalid/degenerate handling instead of epsilon to fabricate data. `clip01(x)=min(1,max(0,x))`.

Canonical JSON uses sorted keys, UTF-8, fixed separators, and `allow_nan=False`. Record Python, librosa, NumPy, SciPy, PyTorch, torchaudio, decoder backend, FFmpeg version/build, and algorithm implementation SHA. Backend drift creates a distinct environment hash/cache namespace. Record timestamps and runtimes in execution ledgers, outside canonical feature payloads.

## 5. Full-duration decoding and two analysis branches

### 5.1 Validation order

1. Verify local path and frozen SHA. No URL input.
2. Probe local metadata with existing FFprobe support, using argument lists and timeouts. Reject duration above 1800 seconds, channels outside 1–2, or sample rate outside 8–192 kHz. Missing/untrustworthy metadata must be handled by a resource-limited decoder worker rather than an unbounded parent-process decode.
3. Decode via `load_audio()` inside the worker. Recheck shape, sample rate, finite samples, duration, channels, and authoritative source-duration tolerance `max(2 seconds, 1% of expected)`.
4. Save original-channel scalar diagnostics and run loudness measurement before discarding the original waveform.
5. Apply the common LUFS linear gain defined in Section 6 to the original channels. Create mono from this normalized waveform by arithmetic channel mean; resample the whole waveform with `torchaudio.functional.resample`, `resampling_method="sinc_interp_hann"`, `lowpass_filter_width=6`, `rolloff=0.99`, `beta=None`.
6. Never use peak normalization, dynamic loudness normalization, truncation to 30 seconds, or padding to a fixed song length. The one permitted normalization is the constant gain in Section 6. Short STFT boundary padding is computational padding only.

Track duration remains decoded `N/original_sr`; differences of a resampled endpoint must be below one target sample plus floating tolerance. Reject unexpected channel layouts instead of guessing a multichannel downmix.

### 5.2 Branches

**Level branch:** original sample rate and channel layout. Integrated loudness, sample peak, whole-track RMS, clipping diagnostics, and crest factor belong here. Stereo-to-mono cancellation must not alter source loudness.

**Motion branch:** full-duration 22,050 Hz mono after the common LUFS linear gain in Section 6. One common STFT/mel/frame clock feeds onset, flux, HPSS, and pulse. No inverse HPSS waveform is necessary.

Calculate `mono_energy_ratio = mean(mono_original**2) / mean(original_channels**2)` when the denominator is positive. If ratio < 0.01, report `MONO_CANCELLATION`, leave the original-channel level features valid, and mark all mono-derived families unavailable. Do not silently switch to one channel.

Sample peak is `max(abs(original_waveform))`; `sample_peak_dbfs=20*log10(peak)` for positive peak, otherwise null. `clipped_sample_fraction=mean(abs(waveform)>=0.999)` is a warning metric, not proof of malformed audio. Finite clipped audio is analyzed with `POSSIBLE_CLIPPING` when the fraction exceeds 0.001; do not reject it automatically.

### 5.3 Frame clock and active mask

Create `D=librosa.stft(y, n_fft=2048, hop_length=256, win_length=2048, window="hann", center=True, pad_mode="constant")`. Frame time is `t*hop/sr`. Keep frames whose center is strictly before decoded duration. All derived arrays use this same retained frame index.

Compute frame RMS on mono waveform with the same frame length, hop, centering, and padding, using the rectangular time-domain RMS definition. Let `r_db[t]=20*log10(max(rms[t],1e-12))`. Let `ref=Q95(r_db)`. Active iff:

```text
r_db[t] > -80 AND r_db[t] >= ref - 40
```

Each frame owns time cell `[t*hop/sr, min((t+1)*hop/sr, duration))`; active duration is the sum of active cell lengths. This prevents the final partial cell from inflating duration. Summary percentiles use equal frame weights; energy integrals and durations use cell durations. Record active fraction and leading/trailing inactive seconds. This is an analysis mask, not a section detector.

The original-level eligibility mask used before normalization is separately defined in Section 6.1. At least 10 active seconds on this normalized mask are required for motion summary validity; 20 for pulse reliability. Active-frame thresholds must not eliminate the loudness branch's own EBU gating. An all-zero or effectively silent track is `NO_ACTIVE_AUDIO`; do not turn a relative mask into evidence that a nearly silent noise floor is musically active.

## 6. Loudness normalization and source-distribution safeguards

This section specifies the normalization called by the Section 5 preprocessing pipeline. It implements the user's requirement that differently distributed MP3s must not be judged more energetic simply because one export has a higher playback level.

### 6.1 Preserve source measurements; use a common analysis loudness

After measuring original-channel integrated LUFS in Section 7.1, compute:

```text
target_lufs = -23.0
normalization_gain_db = target_lufs - source_integrated_loudness_lufs
gain = 10**(normalization_gain_db/20)
normalized_original_channels = original_channels * gain
```

Only a global linear gain is applied. No limiter, compressor, AGC, clipping to [-1,1], or peak normalization. Work in floating point; transient samples above 1 are allowed and are not source clipping. Preserve original clipping diagnostics before scaling. Record target, applied gain, resulting floating-point peak, source LUFS, and normalization status.

Calculate canonical mono/STFT/onset/flux/HPSS/pulse features from this normalized waveform, following Section 5's full-duration downmix/resample. Calculate block dynamics from normalized original channels; the profile frame-RMS summary uses the shared normalized mono frame clock defined in Section 7.5. Source LUFS/RMS/peak/crest/LRA remain raw-source provenance measurements. Dynamics based on dB differences should be gain-invariant above the activity floor, but use the common normalized branch to make threshold effects explicit.

Absolute `source_level` mismatch is **excluded by default** from arousal, activity similarity, primary error contrast, and any proposed automatic penalty. The normalized track's integrated level is also not useful as a discriminating feature because normalization intentionally aligns it. Normalized within-track dynamics, attack rates, percussive texture, and spectral movement remain useful differences.

Before normalization, source eligibility requires at least 10 seconds whose original-channel rectangular frame RMS exceeds -80 dBFS. This absolute-only preliminary mask pools squared samples across channels before taking the square root (no cancellation), uses zero-padded centered rectangular frames and the same frame-duration accounting, at original sample rate with frame length `round(2048*original_sr/22050)` and hop `round(256*original_sr/22050)`, without the relative -40 dB cut. It permits source loudness measurement without a circular dependency on the normalized motion mask. On the normalized branch, compute the final active mask exactly as Section 5.3 specifies.

If source loudness is unavailable, do not substitute RMS normalization while claiming the same extractor. Raw diagnostic extraction may be retained with `normalization.status=UNAVAILABLE`; normalized motion families are unavailable for pair/proxy comparison. Source measurements that remain valid are still exported. This branch failure produces `PARTIAL` or `FAILED` according to Section 3.

If `abs(normalization_gain_db)>20`, emit `EXTREME_NORMALIZATION_GAIN`; raw diagnostics remain but normalized motion comparison and arousal abstain. Do not silently cap the gain and compare at a different target. The final activity mask cannot rescue an almost silent recording by amplifying its noise floor. The fixed gain is constant across the entire song and applied before mono downmix; source channels remain available for original loudness measurement.

These normalization constants are included in the complete Section 4 configuration. The target -23 LUFS is a common analysis reference, not a product playback-volume setting. No runtime toggle may include source LUFS in the primary comparison without a new comparison identity and separately declared experiment.

### 6.2 What normalization can and cannot fix

Multiplying a recording by a constant addresses gain differences. It does not undo lossy encoding, limiting, dynamic-range compression, clipping, EQ, added silence, remastering, or different performances. Retain source hashes, format/bitrate metadata when available, original LUFS, clipping fraction, and gain for audits. MP3 metadata is observational; do not infer quality or genre from bitrate alone.

For the frozen original100, run generated **gain-only variants** at -12, -6, and +6 dB on decoded audio; skip only the +6 variant when it would introduce sample clipping in a real export (`peak*gain>0.999`). Never modify the retained files or the authoritative source cache. Test variants under synthetic fixture identities in an isolated validation cache. Re-measure their LUFS and run the same normalization/extraction path. Exclude variants hitting the source floor/extreme-gain gate and report the exclusions rather than counting them as passes.

Compare each eligible variant to its reference using the frozen scaler:

- integrated LUFS shifts by the imposed gain within 0.2 LU;
- normalized activity similarity >=0.98;
- onset/percussive rates differ by <=max(0.05 Hz, 5% of reference rate);
- spectral-flux Q90 absolute difference <=0.01;
- dynamic-range/complexity/step differences <=0.2 dB;
- arousal proxy difference <=0.03 when available;
- pulse family interpretation remains within 4% modulo octaves or both abstain, with no VALID-to-LOW_CONFIDENCE change except a documented threshold-boundary case.

These are proposed tolerances to validate before label analysis. Source-floor cases are expected exclusions, not proof of gain invariance. Report maximum and percentile deviations, not only pass counts. At least 80 original tracks must have an eligible gain variant for the full-corpus gain gate; otherwise the audit is insufficient.

Optional diagnostic MP3 re-encoding on 10 frozen golden tracks at 128/320 kbps may characterize codec sensitivity if the installed FFmpeg build supports the encoder. This does not replace the mandatory gain audit and does not authorize downloads or replacing sources. Lossy re-encoding is not expected to be numerically invariant; report differences and revise only through a documented versioned decision.

## 7. Energy and motion extraction

### 7.1 Source loudness and level diagnostics

Use the installed FFmpeg `ebur128` measurement filter on the **decoded original channels**, without normalization or mono conversion. Pipe interleaved little-endian float32 PCM from the validated waveform. Pass an argument list equivalent to:

```text
ffmpeg -hide_banner -nostats -loglevel info
  -f f32le -ar ORIGINAL_SR -ac ORIGINAL_CHANNELS -i pipe:0
  -af ebur128=peak=none:dualmono=false:framelog=verbose
  -f null -
```

Set subprocess locale to `C`, capture the final summary from stderr, and require return code 0. Stream PCM in bounded blocks while draining stderr, or use a deadlock-safe subprocess helper; do not wait for exit before reading a full stderr pipe. Parse only the final `Summary:` block, with fixtures from the installed build. Do not scrape the intermediate running `I` field. FFmpeg measurement uses its EBU gating and leaves the audio unnormalized. See [FFmpeg ebur128 documentation](https://ffmpeg.org/ffmpeg-filters.html#ebur128).

Required fields:

| Field | Definition |
|---|---|
| `integrated_loudness_lufs` | Final scanner integrated loudness in LUFS. |
| `loudness_range_lu` | Final scanner LRA in LU. Require at least 30 seconds total duration and 10 seconds eligible under the original-level preliminary mask in Section 6.1; otherwise null with `INSUFFICIENT_LRA_DURATION`. |
| `source_rms_dbfs` | `10*log10(mean(original_waveform**2))` across channels and samples, when positive. |
| `sample_peak_dbfs` | Original-channel sample peak; not true peak. |
| `crest_factor_db` | `sample_peak_dbfs-source_rms_dbfs`, whole-track definition including silence. |
| `clipped_sample_fraction` | Diagnostic from Section 5.2. |

For fewer than 10 seconds eligible under the original-level preliminary mask (Section 6.1), nonfinite scanner results, or integrated loudness <= -69 LUFS (scanner-floor guard), loudness comparison is unavailable with reason. The raw scanner summary may be retained in debug evidence. Silence must not become a seemingly valid -70 LUFS musical observation. LRA 0 on sufficiently long constant-level audio is a valid zero.

No new Python loudness package is required. Missing FFmpeg/filter support is a preflight failure, not a fallback from LUFS to RMS under the same name. Small backend rounding differences have a 0.2 LU/LUFS validation tolerance. Mono is measured as mono (`dualmono=false`) and channel count is reported as a potential comparison confound.

### 7.2 Acoustic onset density

Let `M=abs(D)` and `W=M**2`. Build one mel matrix with `librosa.filters.mel(sr=22050,n_fft=2048,n_mels=128,fmin=30,fmax=10000,htk=False,norm="slaney",dtype=float32)` and compute `mel_power=mel_filter @ W`.

Use a fixed-reference log spectrum `L=librosa.power_to_db(mel_power,ref=1.0,amin=1e-10,top_db=80.0)`. Compute onset envelope with `librosa.onset.onset_strength(S=L,sr=22050,hop_length=256,n_fft=2048,lag=1,max_size=1,detrend=False,center=True,aggregate=np.mean)` and retain exactly the common frame count. Here `center=True` is librosa's onset/STFT alignment compensation, not an additional independently cropped time axis. Do not pass log magnitude as log power. The API accepts a precomputed spectrum; see [onset-strength documentation](https://librosa.org/doc/0.11.0/generated/librosa.onset.onset_strength.html).

For peak picking, first set `e_clean[t]=e[t]` when `e[t]>=0.5`, otherwise zero; the 0.5 threshold is in the raw mean log-power-flux units of this exact frontend. Take `den=Q95(e_clean[active AND e_clean>0])` and `e_norm=clip01(e_clean/den)`. If no positive eligible values exist, the envelope is degenerate and count is zero; do not rescale numerical ripple into a full-strength attack. Set inactive frames to zero. The 80 dB log-spectrum floor and raw-onset floor are frozen extractor constants and require gain/quiet-audio validation. Use `librosa.onset.onset_detect(onset_envelope=e_norm,normalize=False,backtrack=False,units="frames",sparse=True,...)` with the explicit pre/post/wait/delta parameters in config and matching sample rate/hop. Count only detected active frames. This normalization is only for event detection; never overwrite the raw envelope. See [onset-detection documentation](https://librosa.org/doc/0.11.0/generated/librosa.onset.onset_detect.html).

Persist `onset_count`, `onset_rate_hz=count/active_duration`, and raw active-envelope mean, Q50, Q90, IQR. All names refer to acoustic events, including instrumental and vocal attacks. Do not count every positive spectral-flux frame as a separate onset.

### 7.3 Spectral flux as a distinct measurement

The onset envelope already uses spectral changes. To avoid exporting two identical features, define a separate, gain-resistant spectral-shape flux:

```text
p[:,t] = M[:,t] / sum(M[:,t])          for nonzero columns
flux[t] = sum(max(p[:,t]-p[:,t-1], 0))
```

Retain only transitions where both adjacent frames are active and nonzero. Other transitions are invalid, not zero observations in the summary. On valid frames flux is in [0,1] within numerical tolerance. Export mean, Q50, Q90, IQR, valid-transition fraction. This measures positive spectral-shape redistribution; it intentionally suppresses pure gain changes, which belong to loudness/dynamics. At least 100 valid transitions are required. Tests must distinguish it from raw onset strength.

### 7.4 Percussive activity and percussion-density proxy

Apply median-filter HPSS to the shared magnitude spectrogram:

```text
H, P = librosa.decompose.hpss(M,
    kernel_size=(31,31), power=2.0, mask=False, margin=(2.0,2.0))
R = max(M-H-P, 0)
```

HPSS separates spectrotemporal patterns rather than recognizing drum instruments. The margin leaves an uncertain residual. It is lightweight DSP and adds no model download. See [librosa HPSS documentation](https://librosa.org/doc/0.11.0/generated/librosa.decompose.hpss.html).

Build `P**2` mel power using the same mel filter, then use the exact onset-envelope and peak-picking path from Section 7.2. The HPSS onset branch must not silently use different timing or log settings.

Required outputs:

- `percussive_onset_count` and `percussive_onset_rate_hz`, divided by original mixture active duration.
- `percussive_energy_ratio=sum(P**2)/sum(M**2)` over active frames, cell-duration weighted.
- `hpss_residual_energy_ratio=sum(R**2)/sum(M**2)` on the same support.
- `percussive_onset_q90` and compact per-window measurements.

H/P/R squared-energy ratios need not sum to one because soft spectrogram components are not orthogonal. Do not renormalize them to imply a physical source-energy partition.

A zero percussive rate is valid if the input is audible and the branch succeeded. High residual ratio (>0.60) marks the percussion proxy `LOW_CONFIDENCE` and excludes it from pair penalties/proxies, while retaining its raw values. This is a conservative development heuristic, not instrument-detection confidence. Percussive vocals, piano attacks, and synthesis transients remain possible confounds. Actual drum-hit transcription is future work only if documented failures justify it.

### 7.5 Dynamic complexity and temporal profiles

Compute energy from the normalized original channels (Section 6) in successive nonoverlapping one-second blocks anchored at time zero. Retain a final partial block only if at least 0.5 seconds. Define block dB as `10*log10(max(mean(samples**2),1e-12))`. Mark a block eligible when its dB is > -80 and at least `Q95(block_db)-40`. Require 10 eligible blocks for the following summaries:

```text
dynamic_range_db = Q90(eligible block_db) - Q10(eligible block_db)
dynamic_complexity_db = mean(abs(eligible block_db - median(eligible block_db)))
dynamic_step_db = median(abs(block_db[t]-block_db[t-1]))
```

`dynamic_step_db` uses only adjacent eligible blocks; require 5 such transitions. These are explicit engineering proxies, not EBU LRA or a general measure of musical complexity. Preserve LRA separately. Global gain should translate block levels but leave these differences approximately unchanged above the silence floor.

Create fixed, nonoverlapping profile windows `[0,10),[10,20),...` clipped to track duration. Every window records boundaries, active duration/fraction, median frame RMS dBFS, onset rate, percussive onset rate, flux Q90, and percussive energy ratio. For window duration, intersect frame-owned time cells with the window bounds; assign point events by timestamp in the half-open window. Use the already computed full-track arrays and event timestamps; **do not restart STFT, onset detection, or HPSS at each window boundary**. Minimum active duration for motion window summaries is 2 seconds; otherwise values are null with a reason. RMS remains a diagnostic when calculable. Window validity never crops away the source.

Track-level dynamic and motion summaries remain authoritative; profiles explain mixtures of calm and active sections. These windows are not intro/verse/chorus labels and do not yield section proportions.

## 8. Supporting rhythm: candidates, pulse, and regularity

This module supports energy/motion interpretation. An uncertain BPM must not disable otherwise valid energy measurements.

### 8.1 One tempo path

Use the normalized mixture onset envelope from Section 7.2. Subtract `scipy.signal.convolve(e_norm,w,mode="same",method="direct")`, where `w=scipy.signal.windows.hann(768,sym=False)` normalized to sum one. This fixes even-window alignment and uses zero extension at the signal edges. The result is a signed detrended envelope `e_d`. Compute one `librosa.feature.tempogram(onset_envelope=e_d,sr=22050,hop_length=256,win_length=768,center=True,window="hann",norm=None)`.

Normalize each autocorrelation column by its zero-lag value when that value > 1e-12. Otherwise the column is invalid. Retain signed normalized autocorrelation for diagnostics; candidate strengths use `rho=max(normalized_autocorrelation,0)`. This suppresses the constant positive background of a nonnegative onset envelope; do not compute entropy of uncorrected positive lag bins as “tempo confidence.” The tempogram is local onset autocorrelation, not a probability distribution. See [tempogram documentation](https://librosa.org/doc/0.11.0/generated/librosa.feature.tempogram.html).

A local column is eligible only when its full 768-frame context lies inside the track and at least 50% of its context's frame cells are active. This handles silent intros/outros and edge padding. Require at least 10 seconds of eligible column-cell duration for pulse summaries.

Lag BPM is `60*sr/(hop*lag)` for integer lag > 0. Restrict **candidate search** to [30,300] BPM; do not discard other lags from the stored in-memory autocorrelation because subdivision measurements may exceed 300 BPM.

For each eligible column, find its highest positive allowed-lag strength. Ties go to higher BPM. Keep its tempo only when peak >= 0.15. Across eligible columns, aggregate each lag with Q75, giving global strengths `g[lag]`. Q75 is a frozen engineering choice to retain periodic sections; the per-frame valid fraction prevents a short periodic fragment from implying full-track reliability.

Find local maxima in `g` including range endpoints, rank by descending strength then descending BPM, and retain up to 5 using log2-BPM nonmaximum suppression radius 0.08 octaves. Primary is the highest-ranked candidate. Fewer than 5 peaks is valid; do not invent candidates. Explicitly sample strengths near primary/2 and primary*2 when in search range and add those as octave alternatives if not already within the suppression radius. Thus `tempo_candidates` may have up to 7 entries; `candidate_count=5` means initial peak budget, not final array length.

Interpolate strengths linearly in lag coordinates at fractional lag. Out-of-range positions return null, not zero. Each candidate stores BPM, raw autocorrelation strength, strength normalized over retained candidates, relation to primary, and support ratio to the strongest candidate. Candidate weights are descriptive; they are not posterior probabilities.

**Do not call `librosa.feature.tempo()` independently in v1.** Its default prior can disagree with the above candidate rule. Define `global_tempo_bpm=primary_bpm`; the local curve comes from the same lag search. This eliminates two competing undocumented tempo authorities.

### 8.2 Local variability and metrical uncertainty

Let `strongest_strength=max(retained candidate strengths)`, independent of the primary label. A supported candidate has strength >= 0.50 * strongest_strength and raw strength >= 0.15. At least one is required. Define:

```text
octave_ambiguity = clip01(max(valid half/double strength) / primary_strength)
metrical_certainty = clip01(1 - strongest_other_retained_peak / primary_strength)
```

If no distinct alternative exists, `metrical_certainty=1`; if half/double lies outside the allowed range, record `OCTAVE_PARTNER_OUT_OF_RANGE` and do not interpret its absence as disproving ambiguity. Primary strength <= 0 yields no reliable tempo. Exact-tempo eligibility additionally requires no out-of-range octave-partner warning, unless the missing partner is below 30 BPM and the in-range candidate is explicitly validated in the golden set; v1 defaults conservatively abstain from exact-tempo use when this warning occurs.

For accepted local BPMs, persist raw Q10/Q25/Q50/Q75/Q90 BPM and IQR/MAD of log2 BPM. Also align each local log BPM to the primary by subtracting the nearest integer octave offset (ties choose the smaller integer) and compute `local_family_mad_octaves` and `local_family_iqr_octaves` on these aligned values. Raw variation reports beat-level switching; family-aligned variation reports non-octave tempo change. Neither should be silently substituted for the other.

`tempo_change_warning=true` when family-aligned IQR > 0.10 octaves. Report raw octave-switch fraction: accepted local estimates whose nearest primary octave offset is nonzero, divided by accepted local estimates. These summaries are diagnostics, not meter recognition.

### 8.3 Pulse reliability independent of beat-tracker regularization

Define components on eligible columns:

```text
periodic_strength = median(per-column allowed-lag maximum rho)
periodic_frame_fraction = count(columns with peak >= 0.15) / eligible_columns
strength_score = clip01((periodic_strength - 0.10) / 0.50)
coverage_score = periodic_frame_fraction
stability_score = exp(-local_family_mad_octaves / 0.10)
duration_score = clip01(active_duration_seconds / 30)
pulse_reliability = (strength_score * coverage_score * stability_score * duration_score)**0.25
```

If active duration < 20 seconds, eligible duration < 10 seconds, fewer than 8 detected mixture onsets, no accepted local tempos, or degenerate onset envelope, set pulse reliability to 0 and provide explicit reasons. Onset count is only a minimum-evidence gate. Low pulse reliability is not a failed energy extractor.

`pulse=VALID` requires reliability >= 0.55. Exact BPM eligibility additionally requires `metrical_certainty>=0.60` and the octave-range rule. High pulse reliability with ambiguous half/double tempo is a normal result.

The geometric mean is an uncalibrated engineering rule. These component mappings must pass the synthetic and golden checks before the experiment configuration is frozen. Do not claim that unrelated components prove BPM correctness. In particular, do not use beat-tracker interval regularity as the main confidence input: the tracker explicitly favors intervals consistent with its tempo parameter. See [beat-tracker documentation](https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html).

### 8.4 Beat strength and regularity diagnostics

If pulse analysis has a positive primary tempo, call `librosa.beat.beat_track(onset_envelope=e_norm,sr=22050,hop_length=256,bpm=primary_bpm,tightness=100,trim=True,units="frames",sparse=True)`. This is the selected-primary interpretation, not an independent tempo estimator.

Retain beat frames landing in active cells. Inter-beat intervals contribute only when at least 80% of intervening cell duration is active; do not bridge long silences. Require at least 8 retained beats and 5 valid intervals for beat-family validity.

Required diagnostics:

```text
beat_interval_robust_cv = 1.4826 * median(abs(IBI-median(IBI))) / median(IBI)
beat_regularity_proxy = exp(-beat_interval_robust_cv / 0.10)
```

For each retained beat, measure maximum `e_norm` within ±2 frames, clipped to the track. Let `onbeat=median(these maxima)` and `background=median(e_norm[active])`:

```text
beat_onset_support = clip01((onbeat-background) / max(1-background,1e-12))
beat_strength_proxy = pulse_reliability * beat_onset_support
```

Report first/last beat, count, median IBI, and active-time coverage between first/last beat divided by total active duration. Regularity/support are interpretation-dependent diagnostics. When pulse is low-confidence or the beat evidence minimum fails, retain raw diagnostics but mark beat strength unavailable for comparison/arousal.

### 8.5 Subdivision/activity profiles and octave safety

For every supported candidate BPM `b`, sample `rho` at lag `60*sr/(hop*b*f)` for factors `f=[0.5,1,2,4]`, interpolating in lag space. Use eligible columns with candidate fundamental strength >= 0.15. Require at least 5 seconds of such columns. Define factor value as the median of `clip(rho_factor/rho_fundamental,0,4)` across these columns. No range extrapolation. Fundamental is 1 by definition when valid. Retain support duration and nulls.

This is relative periodic support, not a count of eighth/sixteenth notes. Only call factors “eighth-like” and “sixteenth-like” under the selected quarter-note interpretation. A profile at 75 BPM and one at 150 BPM use different coordinate systems. Librosa's corresponding API samples metrical factors and can accept per-frame BPM; the explicit formula here avoids accidental independent tempo estimation. See [tempogram-ratio documentation](https://librosa.org/doc/0.11.0/generated/librosa.feature.tempogram_ratio.html).

Actual acoustic and percussive event rates are independent of the selected BPM and remain the primary motion measurements. Do not put raw `log2(primary_bpm)` into the primary energy/motion similarity or arousal proxy.

## 9. Reference scaling and transparent summary proxies

### 9.1 Reference population

Default reference is the frozen original100 feature set after validation. This makes 741 extraction genuinely optional. A separate `reference741` run may fit a new scaler and re-export comparisons without recomputing unchanged source features. Never silently replace a 100-track scaler with a 741-track scaler.

Fit on valid values only, using one row per distinct source SHA. Record corpus, source IDs, feature order, valid counts, transforms, medians, IQRs, and excluded constant features. Require at least 30 valid reference values per feature. A feature with IQR < 1e-6 is disabled, not divided by epsilon. Fit no statistic using human ratings. Including the evaluated corpus in this unlabeled scaler is a declared fixed-corpus/transductive diagnostic; future out-of-corpus learned evaluation must fit preprocessing on its training reference only.

Transforms:

- Onset rates and percussive onset rates: `log1p(x)`.
- Nonnegative dynamic-complexity and dynamic-step values: `log1p(x)`.
- Flux, ratios, beat strength, LUFS, LRA, and dB ranges: identity.
- BPM: log2 only in the separate exact-tempo diagnostic.

For enabled features, `z=clip((transform(x)-median)/IQR,-4,4)`. Preserve raw values separately. Disabled or invalid features remain null/masked; do not median-fill them in authoritative artifacts.

### 9.2 Arousal proxy and limitations

Export `arousal_proxy_0_1` only as a transparent relative descriptor. V1 estimates **motion-associated arousal**, not complete perceived arousal. It cannot capture every aspect of loud, distorted, emotionally intense, or harmonically tense music. No preference labels or genre strings enter its formula.

Using the reference feature distribution, define percentile `u(x)=(count(reference<x)+0.5*count(reference==x))/N`, on the same transformed valid values. Persist the sorted reference values needed to reproduce percentiles. Constant/insufficient features are unavailable.

Required baseline inputs:

```text
A = mean(u(onset_rate_hz), u(percussive_onset_rate_hz), u(spectral_flux_q90))
arousal_proxy_0_1 = A
```

All three inputs must be valid and scalable; otherwise the arousal proxy is null with reasons. Beat strength, BPM, dynamics, and raw source loudness are displayed beside it rather than silently changing the formula for different tracks. Also report a separate `beat_drive_proxy=beat_strength_proxy` when valid. This keeps the arousal proxy well-defined for weak-pulse tracks while showing rhythmic emphasis where available.

The three proxy inputs are correlated. The score is a descriptive convenience; evaluate component redundancy and the raw/grouped feature representation. Do not add the proxy back into similarity along with its own inputs, which would double count them. Do not call a similarity-rating correlation an arousal-validation result.

### 9.3 Danceability-like diagnostic

For valid pulse and beat families only:

```text
danceability_proxy_0_1 = sqrt(pulse_reliability * beat_onset_support)
```

This estimates beat followability. It omits groove, syncopation, cultural context, and personal dance preference, so it is explicitly narrower than danceability. No preferred BPM bell curve is introduced. Half/double ambiguity alone does not invalidate it. Keep it out of the primary similarity and advancement statistic in this stage. If beat interpretation changes its support substantially, expose that in the golden audit rather than claiming calibrated danceability.

## 10. Pair representation and abstention

Compute components symmetrically on source-verified tracks. Canonical unordered pair identity is separate from directed query/candidate appearances in historical retrieval lists. Never overwrite provenance to make a pair look independent.

### 10.1 Primary energy/motion similarity

Group the raw features to limit double counting:

| Component | Features | Role |
|---|---|---|
| `activity` | onset_rate_hz, percussive_onset_rate_hz, spectral_flux_q90 | Primary energy/motion screening signal. |
| `attack_texture` | percussive_energy_ratio, beat_strength_proxy | Optional rhythmic/attack explanation; may abstain. |
| `dynamics` | dynamic_range_db, dynamic_complexity_db, dynamic_step_db, loudness_range_lu | Separate changing-intensity comparison. High values do not imply higher arousal. |
| `source_level` | integrated_loudness_lufs | Source-distribution audit only; excluded from default similarity, arousal, and advancement. |

For each component, require at least 2 common enabled valid features and >=75% of its configured equal weight. The single-feature source-level audit is explicitly exempt and requires valid LUFS on both sides. With three activity features, 75% means all three are required; with four dynamics features, at least three are required. This deliberate rule prevents different pairs from being compared using unrelated scraps of evidence.

For a usable group:

```text
d_group = weighted_mean(abs(z_i-z_j)) over common valid features
s_group = exp(-d_group)
mismatch_group = 1-s_group
```

Weights are equal within a group and renormalized over valid common features after the coverage gate. Persist common-feature masks and each absolute difference. A disabled reference feature still counts against the original configured weight coverage; otherwise a collapsed feature set could silently become a different experiment.

`energy_motion_similarity_v1 = s_activity`. Dynamics and attack texture remain separate pair outputs, not arbitrary extra weights in the primary score. This intentionally simple first comparison should show whether acoustic movement adds useful information. A later design may combine the groups after validation.

### 10.2 Exact and family tempo diagnostics

For positive primary BPMs:

```text
d_exact = abs(log2(bpm_i/bpm_j))
s_exact = exp(-0.5*(d_exact/0.15)**2)
d_family_primary = abs(log2(bpm_i/bpm_j)-nearest_integer(log2(bpm_i/bpm_j)))
s_family_primary = exp(-0.5*(d_family_primary/0.10)**2)
```

Using the nearest integer handles the entire allowed BPM range, including octave offsets beyond ±2. Exact scores may be exported diagnostically but are comparison-eligible only when both exact-tempo gates pass. Do not penalize ambiguous half/double selection.

For octave-aware subdivision comparison, enumerate supported candidate pairs whose family distance <= `log2(1.04)`. Align their metrical levels by multiplying the slower BPM by `2**round(log2(faster/slower))`, with half-integer ties choosing the smaller exponent. The two resulting BPMs remain track-specific (for example, 75/152 becomes 150/152), must both lie in [30,300], and must differ by at most the 4% log tolerance. **Resample each track's autocorrelation profile at its own aligned BPM**; do not compare unaligned factor arrays. Export profiles for these needed supported octave lifts within [30,300] BPM in the track payload, so pair scoring requires no audio/cache mutation. A lift is eligible only if its fundamental has >=50% of the track's strongest retained global candidate strength and raw strength >=0.15.

For each eligible alignment, compare the 0.5/2/4 factor entries with equal mean absolute difference after `log1p`; all three must exist. Use the smallest distance across supported alignments and store the winning BPMs and alternatives considered. Similarity is `exp(-distance)`. If no supported alignment exists, subdivision comparison abstains. This minimum is an optimistic diagnostic under ambiguity, not independent evidence of shared groove. Relabeling the same supported candidate set's primary must not change its result.

### 10.3 Hard gates before soft weights

Eligibility is per component. Energy/motion requires valid normalized motion/percussion/flux values on **both** tracks. Beat and subdivision components additionally require both individual pulse gates. Exact BPM additionally requires both metrical certainty gates.

```text
if not eligible_i or not eligible_j or insufficient_common_features:
    similarity = null OR diagnostic_only_value
    abstain = true
    effective_mismatch = 0.0
else:
    abstain = false
    pair_reliability = min(reliability_i, reliability_j)
    effective_mismatch = pair_reliability * (1-similarity)
```

For valid non-pulse measurement groups, reliability is a binary measurement-validity weight of 1, not a invented perceptual-confidence score. Pulse components use the measured pulse heuristic after their hard gates. Raw diagnostics may remain available when ineligible, but must be labeled `diagnostic_only=true`.

Never use `sqrt(r_i*r_j)` to allow a confident track to rescue one below its individual threshold. A future consumer must read the abstention flag; absence of a usable component means zero contribution, not dissimilarity. Stage 5F.1 does not apply this hypothetical contribution to production rankings.

## 11. Schema and artifacts

### 11.1 Track record

Use typed dataclasses or equivalent strict models. Required top-level fields:

```text
schema_version, extractor_id, algorithm_spec_sha256,
implementation_sha256, extraction_config_sha256, environment_sha256,
source_sha256, duration_seconds, source_sample_rate_hz, source_channels,
analysis_sample_rate_hz, normalization,
status, family_statuses, warnings, failure,
source_level, dynamics, activity, percussion, pulse, beat, metrical_profiles,
profile_window_count
```

The content-addressed feature payload is source-specific, not Spotify-specific. A separate membership table maps Spotify IDs and corpus membership to feature keys, allowing distinct IDs with identical source bytes to share extraction safely. Exports join that mapping to add Spotify IDs. Local paths, wall-clock timestamps, and run IDs belong to provenance/ledgers, not the mathematical feature payload.

Every family has `status`, `reasons`, `valid_feature_names`, and its scalar fields. Warning/reason codes are stable uppercase enums, sorted lexicographically. `failure` is null unless a computation/source failure occurred; it contains stage, code, and sanitized message. All persisted scalars are finite or null. Missing arrays are empty only when semantically “no observations,” never a substitute for unexplained failure.

The complete scalar field registry is built directly from Sections 5–8 and must list name, unit, valid range, required support, and null reason. Required standard names include:

```text
source_level.integrated_loudness_lufs
source_level.loudness_range_lu
source_level.source_rms_dbfs
source_level.sample_peak_dbfs
source_level.crest_factor_db
source_level.clipped_sample_fraction
dynamics.dynamic_range_db
dynamics.dynamic_complexity_db
dynamics.dynamic_step_db
activity.onset_count
activity.onset_rate_hz
activity.spectral_flux_q90
percussion.percussive_onset_count
percussion.percussive_onset_rate_hz
percussion.percussive_energy_ratio
percussion.hpss_residual_energy_ratio
pulse.primary_bpm
pulse.tempo_candidates
pulse.pulse_reliability
pulse.metrical_certainty
pulse.octave_ambiguity
pulse.local_family_mad_octaves
pulse.tempo_change_warning
beat.beat_strength_proxy
beat.beat_onset_support
beat.beat_interval_robust_cv
beat.beat_regularity_proxy
```

`activity` also contains the specified onset/flux summary statistics and support counts. `pulse` contains raw/family local summaries and reliability components. `beat` contains count, interval/support/coverage diagnostics. This list is a naming anchor, not permission to drop required diagnostics from the preceding sections.

Derived z values, arousal/danceability proxies, and scaler IDs belong in a separate derived-feature export so recalibration does not overwrite raw extraction.

### 11.2 Pair record

```text
pair_id, left_spotify_id, right_spotify_id,
left_source_sha256, right_source_sha256,
comparison_config_sha256, scaler_sha256,
base_a_clap, base_muq, base_combined, base_score_origin,
activity_similarity, dynamics_similarity, attack_texture_similarity,
source_loudness_difference_lu,
exact_tempo_similarity, family_tempo_similarity, subdivision_similarity,
component_validity, component_abstentions, component_reliabilities,
feature_differences, common_feature_masks, metrical_alignment,
rating_snapshot_pair_id
```

Store rating evidence in a separate snapshot table keyed by pair ID; the analyzed pair export may join resolved numeric rating and provenance. Directed query appearances remain a separate table for later query-level statistics.

### 11.3 Files

```text
reports/stage5f1_energy_motion/<run_id>/
  design.md
  algorithm_spec.json
  experiment_config.json
  input_reference.json
  source_manifest.json
  environment.json
  schema_registry.json
  validation_config.json
  golden_manifest.json
  synthetic_validation.json
  golden_validation.json
  extraction_diagnostics.json
  tempo_motion_features.parquet
  temporal_profiles.parquet
  derived_features.parquet
  scaler.json
  label_search_audit.json
  label_evidence.json
  resolved_labels.json
  rated_pair_features.parquet
  directed_pair_appearances.parquet
  rated_pair_analysis.json
  error_slice_analysis.json
  distribution_gain_audit.json
  experiment_report.md
  artifact_manifest.json
  ledgers/first_run.json
  ledgers/cache_rerun_<id>.json

.research_audio/stage5f1_energy_motion/
  feature_cache.sqlite
  debug/<feature_key>/...                 optional frame-level evidence
```

Do not commit source audio or generated waveforms. SQLite/debug artifacts follow the repository's ignored research-storage practice; the report records logical cache/export checksums rather than relying on a live SQLite file's byte hash.

## 12. Cache, materialization, and resource behavior

Feature key:

```text
SHA256(canonical_json([
  source_sha256, extractor_id, algorithm_spec_sha256,
  implementation_sha256, extraction_config_sha256, environment_sha256
]))
```

SQLite stores feature key, canonical payload, payload SHA, status, and execution metadata. Use one unique key and transactional insert/update; a completed cache entry is reusable only if its payload checksum and schema validate. An interrupted `RUNNING` row is retryable; failed rows remain evidence and require `--retry-failed` to recompute. Invalid cache payloads are quarantined with an audit reason and recomputed from the same verified source, never silently trusted.

Materialize distinct source hashes in deterministic order with one worker by default. Join all original100 membership rows back into exports, including failures. Reverify source SHA before accepting a cache hit and after extraction; a mid-run file change aborts that source and blocks final corpus analysis.

Use a bounded worker process so a bad source cannot kill the ledger owner. Enforce the configured wall time and memory budget; record `RESOURCE_LIMIT` or `TIMEOUT` without truncating the song. Whole-track STFT/HPSS/tempogram arrays can be large. Release complex STFT after needed magnitude/power values are obtained, release HPSS matrices after compact reductions, and avoid keeping duplicated tempograms or all tracks' arrays simultaneously. Log actual peak RSS. Do not claim 30-minute support until the resource fixture passes on the declared execution hardware; a failed resource gate requires a recorded implementation/config revision, not silent cropping.

Export fixed Arrow schemas, Spotify-ID ordering, canonical pair ordering, window start ordering, stable warning lists, and pinned Parquet writer options. Canonical logical content hashes are the cross-platform comparison contract. Exact export byte preservation is required for a same-environment cache rerun that reuses already finalized exports; do not rewrite them merely to update a timestamp.

`artifact_manifest.json` hashes every immutable output except itself and records a sorted list of input hashes. Do not recursively hash the manifest into itself. Execution ledgers are separately versioned and hashed; a rerun never replaces the first-run ledger. A zero-recomputation cache rerun is an engineering gate.

## 13. Historical-rating compatibility and analysis snapshot

### 13.1 Reuse existing compatible evidence

Snapshot all compatible original100 ratings, not only Arm D pairs or currently displayed top-five pairs. Use the existing Stage 5E.2 compatibility logic as a reviewed reference, adding explicit support for its **current** original100 mutable review state and matching frozen queue. Do not blindly call `audit_labels()` and assume it includes the current state: at revision time that helper deliberately excludes its own output-state directory during its historical search.

Required input sources to audit when present:

- Historical Stage 5C.2 amended-source similarity exports with `stage5c2-human-similarity-review-v2`.
- `.research_audio/stage5e1_review/human_similarity_review.csv` and its frozen Stage 5E.1 queue.
- `.research_audio/stage5e2_review/human_similarity_review.csv` and the retired Stage 5E.2 queue, restricted to original100 membership.
- `.research_audio/stage5e2_original100_v2_review/human_similarity_review.csv` and `reports/stage5e2_arm_d_original100_v2/review_queue.json`.
- Explicitly supplied existing exports with independently verified schema and source identity.

Rules:

1. Both Spotify IDs must be in the original100, nonidentical, and not duplicate-source pairs.
2. Canonical pair ID must agree with the IDs. Preserve original query origin when available.
3. Accept only compatible human-similarity scales; exclude scale-v1/FMA/identity `SAFE` labels.
4. For Stage 5E queues, require both full-source SHA and video ID to match the snapshot.
5. For historical Stage 5C.2 excerpts, accept the established same-selected-video identity mapping even when excerpt bytes differ from retained full-track bytes. Persist `source_identity_basis=SAME_SELECTED_VIDEO_HISTORICAL_EXCERPT`. Never confuse the CSV file checksum with an audio source checksum.
6. Preserve rating-file SHA, original row identity, timestamp, notes, review schema, playback scope, and identity-verification basis.
7. Numeric labels are integers 1–5. `UNSURE` is nonnumeric. Repeated copies of one rating add provenance, not sample size. Multiple different numeric labels for the same unordered pair create `CONFLICT`; exclude the pair from numeric analysis, retain evidence, and do not open a new review task.
8. Pair-level resolved labels are immutable within the run. Emit counts for every inclusion/exclusion reason and preserve unique-track/query counts.

Historical excerpt ratings and full-track features are not perfectly aligned in listening scope. Report a sensitivity slice by playback scope/source-identity basis. Do not claim a full-track perceptual judgment where only a historical excerpt was reviewed.

### 13.2 No fabricated ranking evidence

Stage 5F.1 is a retrospective association screen, not a held-out retrieval-win test. Historical ratings were selected by earlier models and known errors helped motivate this design. Freezing a new config does not make those judgments an untouched prospective holdout.

The checked Stage 5E.2 original100 report has incomplete ranking coverage. Recompute coverage from the new snapshot; do not copy old counts as current results. Missing ratings are never zero or median-filled.

Stage 5F.2, if later designed, must distinguish:

- **Fully judged top-five comparison:** same query, complete judgments for baseline and challenger top-five lists; paired result only on their shared eligible queries.
- **Reranking among already-judged candidates:** a narrower diagnostic on a fixed judged candidate pool; cannot establish full-universe retrieval quality.
- **nDCG:** the ideal ranking pool and gain mapping must be specified, with missing judgments handled explicitly. Do not compute an apparent global nDCG from a selectively observed subset.

For future learned fusion, group by tracks/source duplicates or artists with crossing-edge policy specified. Query grouping alone does not prevent a candidate track appearing in both training and test. Reciprocal unordered pairs must never cross folds. No learned fusion, weight search, or cross-validation pipeline is required in 5F.1.

## 14. Retrospective hypotheses, statistics, and decisions

### 14.1 Freeze before label analysis

The implementation first calibrates extraction using generated and golden audio, then freezes all configs, source identity, labels, scaler reference, and analysis code. Do not inspect the final error-slice report while adjusting thresholds. Known motivating examples are development anecdotes and remain explicitly marked as such.

Predeclared hypotheses:

- **H1 engineering validity:** measurements behave correctly under silence, gain changes, controlled attacks, dynamics, pulse ambiguity, and changing tempo.
- **H2 complementarity:** activity mismatch contains variation beyond the frozen CLAP/MuQ scores.
- **H3 target error slice:** among high-base-similarity pairs, low-rated pairs show greater valid activity mismatch than high-rated pairs.
- **H4 safe partial availability:** low pulse confidence does not erase valid energy features; invalid components contribute no mismatch.
- **H5 distribution robustness:** harmless source gain changes do not materially change normalized activity comparison or the arousal proxy.

No claim of measured arousal accuracy or ranking improvement follows from H2/H3.

### 14.2 Primary error-slice definition

Compute the 75th percentile of `base_combined` over **all eligible unordered original100 pairs**, after duplicate-source exclusion, without rating selection. Freeze that numeric cutoff. Restrict rated pairs to base score >= cutoff:

```text
low group:  numeric rating <= 2
high group: numeric rating >= 4
rating 3:  excluded from primary contrast, retained in all-rating diagnostics
outcome:   activity mismatch = 1 - activity similarity
primary_effect = median(low-group mismatch) - median(high-group mismatch)
```

Include only valid activity comparisons in the contrast, and separately report missingness/abstention in both groups. Require >=20 unique pairs in each group, >=20 distinct tracks and >=10 distinct frozen primary-artist identities across the comparison. If artist IDs are unavailable, use the entire normalized artist-credit string as an explicitly weaker grouping proxy; do not split collaborator names on punctuation. Missing both identities makes the artist-support check unavailable, not automatically passed.

### 14.3 Dependence-aware uncertainty

Canonical unordered pairs are graph edges sharing tracks. Primary uncertainty uses a **track-node bootstrap**, not independent pair resampling:

1. Sort all original100 track IDs. Use `numpy.random.default_rng(seed)`.
2. For each of 2,000 replicates, draw 100 track IDs with replacement. Let `m_i` be each ID's multiplicity.
3. Each existing pair `(i,j)` receives weight `m_i*m_j`. Do not generate new pair labels or count self-pairs.
4. Recompute the weighted median difference using fixed group membership and frozen base cutoff. Weighted median is the smallest sorted outcome whose cumulative weight reaches at least half total weight. In the unweighted point estimate use this same rule, including even-sized groups, for consistency.
5. A replicate with zero weight in either group is invalid. Require >=1,900 valid replicates or label the interval unavailable.
6. Report empirical 2.5th/97.5th percentiles with the frozen linear quantile method.

Also run the same procedure resampling frozen primary-artist groups, multiplying endpoint-group multiplicities for edges between different groups and using one group multiplicity for within-group edges. Use exactly the number of unique original100 artist groups as each replicate's draw count; hold group assignments fixed. Report this as a conservative grouping sensitivity, not a guarantee that all dependence is solved. No claim of population representativeness follows from either bootstrap.

For query-attributed plots, preserve real query origins; do not assign the lexicographically first track as an invented original query. Reciprocal appearances can be shown directionally but contribute only one label to the primary unordered-pair analysis.

### 14.4 Required reports

- Coverage by track, family, artist grouping, source format, sample rate, and source-channel count.
- Raw and normalized source-level distributions; gain diagnostics from Section 6.
- All feature distributions, invalid reasons, tempo candidates, ambiguity, dynamic profiles.
- Spearman correlations of activity similarity and each component with CLAP, MuQ, combined score, and numeric ratings. Use average ranks for ties; constant-input correlations are null, not zero. Track-node resampling supplies descriptive intervals.
- The primary contrast and uncertainty, effect sizes, counts, and eligible/abstaining group breakdown.
- Separate dynamics, beat/attack, and exact/family/subdivision diagnostics, explicitly secondary.
- Known mellow R&B/lo-fi versus hard/dense rap cases; matched counterexamples; playback-scope slices.
- Normalization-confound audit: whether the apparent effect is driven by source LUFS, clipping warnings, or channel layout.
- Reliability sensitivity at pulse thresholds 0.45/0.55/0.65; these affect pulse-dependent outputs, not primary activity comparisons. Do not choose the best threshold after seeing labels.
- No subtraction of human ratings from cosine scores: the scales differ. “Overestimation” means the predefined high-base/low-rated group, not `cosine-rating` residual arithmetic.

### 14.5 Gates and decision precedence

**Engineering gates:** all schema/hash/abstention/immutability tests pass; 100/100 tracks have explicit rows; no unexplained extraction failures; cache rerun performs zero feature recomputation and preserves canonical outputs; no new network or encoder path; required gain-invariance and synthetic tests pass.

**Golden gate:** every predeclared hard expectation passes, or the run stops as `REVISE`. Some clips may legitimately be pulse-ambiguous; expectations must distinguish family correctness from exact tactus. A missing required golden category or unreviewed manifest is incomplete validation, not permission to manufacture pass labels.

**Coverage gate:** >=95 of the original100 have valid normalized activity, percussion, flux, and loudness branches sufficient for the primary comparison. Pulse >=60% valid is a separate rhythm-submodule gate; missing it can mark rhythm `REVISE` without rejecting validated energy/motion. Dynamic-family validity >=90 tracks is required to call the dynamic-complexity deliverable validated; otherwise report that submodule as incomplete/revise and explain.

**Advancement screen:** after engineering/golden/energy coverage gates, require all of:

1. Primary slice meets the support counts.
2. Primary median mismatch difference >=0.05, with track-bootstrap lower 95% bound >0.
3. The artist-group bootstrap lower 95% bound is > -0.02 (no materially reversed contrast within that sensitivity interval); if group evidence/interval is unavailable, result is `DIAGNOSTIC_ONLY` pending more evidence.
4. Absolute Spearman correlation between activity similarity and each of CLAP, MuQ, combined is <0.95 on valid rated pairs. This is a coarse nonredundancy check, not proof of independent causal information.
5. On a sensitivity excluding `POSSIBLE_CLIPPING`, `EXTREME_NORMALIZATION_GAIN`, and nonexact historical source-identity mappings, the primary effect remains positive with >=10 pairs/group. If insufficient, no robust advancement claim yet.
6. At least 95% of the gain-audit eligible tracks pass the specified gain-stability checks, with every failure explained and no systematic gain-direction bias.

Decision precedence:

- `REVISE`: engineering/golden/required energy-family validity fails, or normalization-dependent behavior invalidates the comparison.
- `SUPPORTED_FOR_5F2`: core gates and all advancement checks pass. This supports designing a separate conservative reranking experiment, not activating one. Report any rhythm/dynamics submodule limitations explicitly.
- `DIAGNOSTIC_ONLY`: valid feature layer but insufficient labels, coverage for the contrast, effect, robustness, or evidence of incremental usefulness.
- `REJECT`: use only with affirmative documented evidence that the proposed layer is unusable or consistently redundant/harmful after a recorded revision; missing statistical power alone is not rejection.

The thresholds are practical screening defaults, not established scientific constants. A reported `SUPPORTED_FOR_5F2` means plausible additional signal on this frozen, selected historical set. Broad ranking regression and held-out ranking gain are Stage 5F.2 questions.

## 15. Validation fixtures and acceptance tests

### 15.1 Deterministic generated audio

Use NumPy RNG seed 20260905. Default sample rate 22,050 Hz, length 40 seconds unless stated. A click is a 20 ms exponentially decaying 1 kHz sinusoid (`sin(2*pi*1000*t)*exp(-t/0.003)`), placed starting at 1 second and ending before 39 seconds. Maximum click amplitude 0.4. For click/pulse fixtures add a continuous 220 Hz sine bed of amplitude 0.003, so the intended 40-second rhythmic signal meets the active-duration requirements; silence/degenerate fixtures never receive this bed. Noise bursts use the same envelope and a seeded Gaussian carrier, scaled to peak 0.4. Fixtures are generated at test runtime and never stored as copyrighted audio.

Freeze the generated fixture manifest and expected comparisons before human-label analysis. These fixtures validate mechanics, not universal musical correctness.

| Fixture | Required behavior |
|---|---|
| Stable clicks at 60/75/90/120/150/180 BPM | Primary or supported tempo matches known BPM modulo powers of two within 4%; pulse valid on >=5/6, no incorrect nonfamily confident claim. Exact BPM is required only when the fixture's accent pattern makes it a declared exact-tempo golden target. |
| 75 BPM strong pulses plus 150 BPM half-amplitude subdivisions | Supported half/double evidence retained; octave ambiguity >=0.50 or marked for estimator revision. Never invent a strong exact-tempo distinction based only on selecting 75 vs 150. |
| 100 BPM quarter pulses vs same quarter pulses plus quarter-amplitude sixteenths | Dense version has >=1.5 times acoustic onset rate, or fixture/peak detector is revised before freeze; do not use this one fixture to claim true drum transcription. |
| Mixture of sustained 220/440 Hz tones and increasing noise-burst density | Percussive onset rate increases; source-loudness normalization does not reverse the order. |
| Sustained tone and seeded stationary noise | Do not produce a confident stable beat solely because beat_track can return regular intervals. |
| Irregular clicks with seeded interval jitter uniform in [-35%,35%] | Lower pulse reliability than matched stable control; no strong exact-tempo claim. |
| First half 90 BPM, second half 120 BPM, 80 seconds total | Family-aligned variability exceeds stable control and tempo-change warning is true. |
| Sustained sound with constant amplitude vs alternating 5-second levels 12 dB apart | Alternating fixture has greater dynamic range and complexity. This is not a requirement that it have higher onset-independent arousal. |
| Same waveform multiplied by known gains | Section 6 gain-invariance checks pass when above silence floor and not newly clipped. |
| Same magnitude spectral shape with amplitude-only change | Shape flux remains near zero away from boundary artifacts; block dynamics changes. |
| Loud sustained drone vs softer dense pulse pattern | Raw LUFS cannot dominate primary energy/motion ordering; report separate level/activity measurements. |
| Silence, 1e-6-scale noise, empty, NaN/Inf | Explicit degenerate/failure status; no fabricated BPM, arousal, or pair demotion. |
| Finite hard-clipped waveform | Analyze with clipping warning; do not confuse clipping with nonfinite decode failure. |
| Stereo x/x, x/-x | In-phase collapse works; anti-phase flags mono cancellation while original-channel loudness remains usable. |
| 5-second clip and 40-second track with silent intro/outro | Insufficient-duration status is explicit; valid full-track source remains untruncated; active denominators and window boundaries are correct. |
| 65-second signal with events only after 35 seconds | Features and profiles include those events; catches accidental fixed-30-second preprocessing. |
| Maximum-duration generated input, marked heavy | Meets declared resource budget or produces an explicit implementation revision before claiming support. |

Add direct feature-array unit tests for empty support, zero IQR, no common features, source duplicate mappings, octave candidate relabeling, and reliability gates. In the octave relabeling test, preserve the same candidate strengths and supported profiles while changing only which candidate is labeled primary; activity and aligned subdivision similarity must remain unchanged.

### 15.2 Engineering golden set

Freeze 12 retained local tracks by source hash and timestamped human engineering annotations, selected without selecting for favorable final similarity effects. Include at least one each: steady electronic beat, half-time trap, dense rap, mellow lo-fi/R&B, live/rubato, ambient/weak pulse, quiet recording, strongly limited/loud recording, quiet intro/outro, and a tempo-changing or strongly varying-intensity track. A track can satisfy multiple categories. Add examples until the categories are covered.

For each, record the observed pulse family/range, expected ambiguity or abstention, audible sparse/dense behavior, expected dynamic-profile behavior, and timestamps supporting the annotation. No universal exact BPM or arousal number is required. Identify which expectations are hard gates and which are descriptive.

Do not invent manual listening results from filenames or model output. If existing engineering annotations are unavailable, implementation can finish extraction/tests and prepare golden diagnostics, but validation remains `PENDING_GOLDEN_AUDIT` until the small audit is actually performed. This is an engineering dependency, not a new similarity-review queue.

### 15.3 Tests by layer

- **Pure math:** normalization gain, frame-duration accounting, flux bounds, dynamics formulas, candidate selection/ties, log distances, aligned profiles, group masks, hard abstention, proxy percentiles, weighted bootstrap medians.
- **DSP contracts:** common frame alignment, normalized full duration, no duplicated window-boundary onsets, HPSS identity/config, beat evidence limits, normalization and weak-pulse behavior.
- **Loudness adapter:** actual installed FFmpeg fixture plus parser fixtures for final summary, silence floor, missing filter, nonzero exit, timeout, unexpected output, mono/stereo.
- **Pipeline:** tiny manifest, source-before/after checks, duplicate-source cache sharing, corrupt-payload recovery, interrupted resume, changed extraction vs comparison config, first-run ledger preservation, deterministic logical exports.
- **Evaluation:** include current Stage 5E.2 review state, historical excerpt identity, conflicts, UNSURE, duplicate/reciprocal evidence, current snapshot immutability, no missing-label imputation, node-bootstrap multiplicities.
- **Integration/heavy:** original100 mapping, golden audio, gain audit, resource check, same-environment cache rerun, frozen Stage 5E byte preservation.

Default `pytest` remains fast. Mark corpus-wide and expensive FFmpeg/DSP workloads `heavy` using the repository's existing marker and update its description if needed. A few short local generated-signal tests can remain fast after measuring runtime. Do not add a separate browser UI or browser test requirement for a CLI-only feature layer.

## 16. Implementation modules and callable contracts

Prefer bounded modules with pure transformations and a thin orchestrator:

```text
src/audio_similarity/
  energy_motion_config.py       strict configs, constants, canonical hashes
  energy_motion_schema.py       typed track/window/pair records and validation
  energy_motion_audio.py        full decode wrapper, gain, frame clock/mask
  energy_motion_loudness.py     original-channel FFmpeg measurement adapter
  energy_motion_features.py     onset, flux, HPSS, dynamics, profiles
  energy_motion_rhythm.py       one tempogram, candidates, reliability, beat profiles
  energy_motion_similarity.py  reference scaler, proxies, symmetric components
  stage5f1_inputs.py            frozen sources/matrices/rating snapshot adapters
  stage5f1_cache.py             SQLite ledger, payload integrity, membership joins
  stage5f1_pipeline.py          materialize/export orchestration and run ledgers
  stage5f1_analysis.py          fixed retrospective hypotheses and uncertainty
  cli/stage5f1.py               command dispatch only
```

Do not create a generic plugin framework or a single giant module with every stage embedded. The schema's family structure is sufficient for later tonal/structure modules to join by source identity.

Required functional boundaries:

```python
measure_source_level(waveform, sample_rate, config) -> SourceLevelResult
normalize_for_motion(waveform, source_level, config) -> NormalizedAudioResult
extract_motion(normalized_audio, config) -> MotionResult
extract_rhythm(shared_frame_evidence, config) -> RhythmResult
extract_track(source_input, config, environment) -> TrackFeatures
fit_reference_scaler(valid_track_features, comparison_config) -> Scaler
compare_tracks(left, right, scaler, comparison_config) -> PairFeatures
snapshot_compatible_labels(inputs, frozen_tracks) -> LabelSnapshot
analyze_rated_pairs(pair_features, label_snapshot, evaluation_config) -> Analysis
```

`extract_motion` returns compact persisted measurements plus ephemeral shared frame evidence for `extract_rhythm`; the pipeline discards ephemeral arrays after the source. `compare_tracks` never decodes audio, fits a scaler, writes cache rows, or reads mutable labels. `extract_track` never calls CLAP/MuQ or acquisition. Keep pure DSP helpers independent of Spotify/corpus infrastructure.

CLI, run from `ml/audio_similarity/`:

```bash
uv run python -m audio_similarity.cli.stage5f1 prepare --run-id energy_motion_v1
uv run python -m audio_similarity.cli.stage5f1 validate-synthetic --run-id energy_motion_v1
uv run python -m audio_similarity.cli.stage5f1 materialize --run-id energy_motion_v1
uv run python -m audio_similarity.cli.stage5f1 validate-golden --run-id energy_motion_v1
uv run python -m audio_similarity.cli.stage5f1 fit-scaler --run-id energy_motion_v1
uv run python -m audio_similarity.cli.stage5f1 audit-gain --run-id energy_motion_v1
uv run python -m audio_similarity.cli.stage5f1 analyze-rated-pairs --run-id energy_motion_v1
uv run python -m audio_similarity.cli.stage5f1 cache-rerun --run-id energy_motion_v1
uv run python -m audio_similarity.cli.stage5f1 finalize --run-id energy_motion_v1
```

`prepare` creates a draft run and validates dependencies/input manifests. It may snapshot labels without computing outcome statistics. A development config may be revised before analysis, with new hashes and invalidation of dependent outputs. `analyze-rated-pairs` refuses to run until synthetic/golden/config-freeze checks pass, then makes the run immutable. Subsequent changes require a new run ID. `finalize` can record an honest incomplete/revise state; it must not label missing validation complete.

Every command reports input/config IDs, per-family/status counts where applicable, cache counts, runtime, RSS where relevant, artifact hashes, and explicit missing prerequisites. Use null/`not_applicable` for metrics a command cannot meaningfully produce. Exit 0 for completed valid execution (including a valid diagnostic-only scientific outcome), 2 for configuration/identity contract failure, 3 for incomplete required validation, and 4 for execution failure. Do not implement the earlier `simulate-rerank` command.

## 17. Milestones and definition of done

1. **Freeze implementation contracts:** copy this design into the new report; implement strict config/schema; verify frozen source/matrix/label mappings; record dependency/build identity. No corpus outcome analysis.
2. **Build level and normalization branch:** prove source LUFS, global gain, source-floor guards, clipping diagnostics, and original-channel handling on generated audio.
3. **Build core motion extractor:** onset/flux/HPSS/dynamics/profiles on one shared frame clock. Prove full duration and gain stability. This is the central product deliverable.
4. **Add supporting rhythm:** one candidate path, separate pulse/metrical certainty, beat strength/regularity, candidate-aligned subdivisions. Keep energy validity independent of pulse confidence.
5. **Materializer and cache:** exact source identity, restart behavior, canonical exports, error rows, first-run/rerun evidence. Run a tiny manifest before all 100.
6. **Validate original100:** materialize all sources; complete golden audit; fit frozen original100 scaler; run gain audit. Stop and revise invalid feature families before final label analysis.
7. **Retrospective screen:** snapshot-compatible labels, fixed error contrast, dependence-aware uncertainty, confounds/counterexamples, honest coverage. No new judgments or reranking.
8. **Closeout:** prove cache rerun and unchanged Stage 5E inputs; publish report with the stage decision and separately graded energy, dynamics, and rhythm submodules.

Optional 741 extraction is a separate reference-scaler run after the original100 path works. It is not required to implement or finish v1. Later tonal and structure stages reuse source identity/provenance patterns, not an assumption that all music can be reduced to one scalar.

Implementation is complete when the extractor, cache, exports, comparison layer, tests, and honest report exist and the required validation is performed. Scientific advancement is a separate outcome: a complete implementation may correctly conclude `DIAGNOSTIC_ONLY`.

## 18. Reviewed failure modes and required safeguards

| Risk | Required safeguard |
|---|---|
| Louder MP3 mistaken for higher musical energy | Common LUFS linear-gain analysis branch; raw source LUFS excluded from default similarity/arousal; mandatory gain audit. |
| Normalization alters dynamics or clips transients | Global gain only, floating-point processing, no compressor/limiter/clipping. |
| Compression/remaster differences mistaken for simple gain | Preserve provenance/clipping/source-level diagnostics; report limitations and sensitivity. |
| 75/150 selection creates false motion mismatch | No primary BPM in activity/arousal; candidate-supported aligned subdivision comparison; exact-tempo certainty gate. |
| Strong half/double evidence mistaken for absent pulse | Separate pulse reliability from metrical certainty; no entropy gate penalizing normal metrical alternatives. |
| Regular beat tracker output mistaken for correctness | Reliability based on pretracking periodic evidence; interval regularity remains a diagnostic. |
| Weak-pulse music loses all features | Per-family validity; energy measurements survive rhythm abstention. |
| One reliable track rescues an invalid partner | Both individual gates required; abstention gives zero effective mismatch. |
| HPSS called drum transcription | Explicit percussive-pattern proxy; residual/confound diagnostics. |
| Dynamic complexity called high arousal | Separate dynamics component and proxy semantics. |
| Full-track summaries hide contrast within the song | Fixed 10-second profiles and block dynamics, with no semantic section claims. |
| Different feature subsets silently change pair meaning | Common-weight gates, masks, and disabled-feature accounting. |
| Historical ratings appear independent/held-out | Immutable evidence snapshot, canonical pairs, node/group bootstrap, retrospective wording. |
| Historical excerpt bytes fail full-source SHA join | Explicit same-selected-video compatibility tier with listening-scope sensitivity. |
| Reranking required to authorize reranking | No ranking gate in 5F.1; separate 5F.2 design. |
| Environment drift reuses incompatible cache | Code/config/environment identity in raw feature key; hash-verified payloads. |
| All future feature families creep into v1 | Energy/motion implementation first; bounded rhythm support; tonal/structure roadmap only. |

## 19. Revision record and implementation references

**Revision 2, 2026-09-05:** expands the original tempo/pulse-only emphasis into energy/motion-first mechanical feature recognition; introduces source loudness measurement and common-level analysis; includes HPSS percussion proxy, spectral-shape flux, dynamic complexity, and temporal profiles; separates raw measurements from arousal/danceability heuristics; fixes octave ambiguity and abstention; removes circular reranking gates; specifies rating reuse, sparse-label limitations, source/corpus identities, cache provenance, and validation contracts.

Related project context: [[Spotify Future Multi-View Adaptive Similarity and Full-Track Research Design]], [[Spotify Multimodal Song Representation System Design]], and [[Spotify Audio Similarity Research Roadmap]]. This stage preserves the full-track specialized-sensor direction and frozen holistic backbone.

API choices were checked against the repository's locked librosa 0.11.0 and installed FFmpeg filter interface. The cited DSP APIs describe extraction primitives; the arousal, reliability, comparison, and advancement formulas in this document are project engineering proposals requiring the stated validation. They are not published calibrated measures.

The intended explanation after this stage is concrete:

> These songs share production and timbre, but at a common playback loudness one has denser acoustic attacks, stronger percussive activity, and different rhythmic motion. Here are the measurements and the components that were reliable enough to compare.
