"""Independent classical-MIR feature extraction (Phase 1B design sections 9-11).

Deliberately MERIT-free: everything here derives from librosa DSP on decoded
audio. Features are cached per (audio hash + config hash) so repeated runs
never recompute identical audio.

Extracted per clip:
    melody   chroma_cqt sequence from the harmonic component
    rhythm   percussive onset-strength envelope, tempogram periodicity, BPM
    timbre   MFCC + spectral frame statistics (mean/std)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FEATURE_CONFIG_VERSION = "mir_v1"
SAMPLE_RATE = 24000
N_FFT = 2048
HOP_LENGTH = 512
N_MFCC = 20
TEMPOGRAM_WIN = 384


def feature_config_hash(config: dict | None = None) -> str:
    payload = {
        "version": FEATURE_CONFIG_VERSION,
        "sample_rate": SAMPLE_RATE,
        "n_fft": N_FFT,
        "hop_length": HOP_LENGTH,
        "n_mfcc": N_MFCC,
        "tempogram_win": TEMPOGRAM_WIN,
        **(config or {}),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


class MirFeatureError(RuntimeError):
    """Raised when feature extraction fails or produces invalid output."""


@dataclass(frozen=True)
class TrackFeatures:
    audio_hash: str

    # melody (design section 9)
    chroma_mean: np.ndarray            # (12,) time-averaged pitch-class energy
    chroma_sequence: np.ndarray        # (12, T)

    # rhythm (design section 10)
    onset_envelope: np.ndarray         # (T2,)
    periodicity_profile: np.ndarray    # mean tempogram over time (lags,)
    tempo_bpm: float

    # timbre (design section 11)
    timbre_vector: np.ndarray          # concatenated mean/std frame statistics

    def validate(self) -> None:
        for name in ("chroma_mean", "chroma_sequence", "onset_envelope", "periodicity_profile", "timbre_vector"):
            arr = getattr(self, name)
            if arr.size == 0 or not np.isfinite(arr).all():
                raise MirFeatureError(f"feature '{name}' empty or non-finite")


def _hash_waveform(wav: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(wav, dtype=np.float32).tobytes()).hexdigest()


def extract_features(waveform: np.ndarray, sample_rate: int = SAMPLE_RATE) -> TrackFeatures:
    """Compute all Phase 1B features for one mono waveform."""
    import librosa

    wav = np.asarray(waveform, dtype=np.float32)
    if wav.ndim == 2:
        wav = wav.mean(axis=-1)
    if sample_rate != SAMPLE_RATE:
        wav = librosa.resample(wav, orig_sr=sample_rate, target_sr=SAMPLE_RATE, res_type="soxr_hq")
    if wav.size < N_FFT:
        raise MirFeatureError(f"waveform too short ({wav.size} samples)")
    if not np.isfinite(wav).all():
        raise MirFeatureError("non-finite samples")

    # harmonic/percussive separation feeds both melody and rhythm paths
    harmonic, percussive = librosa.effects.hpss(wav)

    # --- melody: CQT chroma on the harmonic component ---
    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=SAMPLE_RATE, hop_length=HOP_LENGTH)
    chroma = np.nan_to_num(chroma, nan=0.0, posinf=0.0, neginf=0.0)

    # --- rhythm: percussive onsets + tempogram ---
    onset = librosa.onset.onset_strength(y=percussive, sr=SAMPLE_RATE, hop_length=HOP_LENGTH)
    onset = np.nan_to_num(onset, nan=0.0, posinf=0.0, neginf=0.0)
    tempogram = librosa.feature.tempogram(
        onset_envelope=librosa.onset.onset_strength(y=wav, sr=SAMPLE_RATE, hop_length=HOP_LENGTH),
        sr=SAMPLE_RATE,
        hop_length=HOP_LENGTH,
        win_length=TEMPOGRAM_WIN,
    )
    periodicity = np.nan_to_num(tempogram.mean(axis=1))
    tempo = float(librosa.feature.tempo(
        onset_envelope=onset, sr=SAMPLE_RATE, hop_length=HOP_LENGTH, aggregate=np.median
    )[0])

    # --- timbre: frame statistics on the full mix ---
    mfcc = librosa.feature.mfcc(y=wav, sr=SAMPLE_RATE, n_mfcc=N_MFCC, n_fft=N_FFT, hop_length=HOP_LENGTH)
    centroid = librosa.feature.spectral_centroid(y=wav, sr=SAMPLE_RATE, n_fft=N_FFT, hop_length=HOP_LENGTH)
    bandwidth = librosa.feature.spectral_bandwidth(y=wav, sr=SAMPLE_RATE, n_fft=N_FFT, hop_length=HOP_LENGTH)
    contrast = librosa.feature.spectral_contrast(y=wav, sr=SAMPLE_RATE, n_fft=N_FFT, hop_length=HOP_LENGTH)
    rolloff = librosa.feature.spectral_rolloff(y=wav, sr=SAMPLE_RATE, n_fft=N_FFT, hop_length=HOP_LENGTH)
    zcr = librosa.feature.zero_crossing_rate(wav, frame_length=N_FFT, hop_length=HOP_LENGTH)
    flatness = librosa.feature.spectral_flatness(y=wav, hop_length=HOP_LENGTH)

    blocks = [mfcc, centroid / SAMPLE_RATE, bandwidth / SAMPLE_RATE, contrast,
              rolloff / SAMPLE_RATE, zcr, flatness]
    stats = []
    for block in blocks:
        stats.append(block.mean(axis=1))
        stats.append(block.std(axis=1))
    timbre_vector = np.concatenate(stats).astype(np.float64)
    timbre_vector = np.nan_to_num(timbre_vector, nan=0.0, posinf=0.0, neginf=0.0)

    feats = TrackFeatures(
        audio_hash=_hash_waveform(wav),
        chroma_mean=chroma.mean(axis=1),
        chroma_sequence=chroma,
        onset_envelope=onset,
        periodicity_profile=periodicity,
        tempo_bpm=tempo,
        timbre_vector=timbre_vector,
    )
    feats.validate()
    return feats


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------


class FeatureCache:
    """Per-track .npz cache keyed by audio content hash + feature config."""

    def __init__(self, directory: str | Path, config_hash: str | None = None):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.config_hash = config_hash or feature_config_hash()

    def _path(self, audio_hash: str) -> Path:
        return self.dir / f"{audio_hash[:24]}_{self.config_hash}.npz"

    def get(self, audio_hash: str) -> TrackFeatures | None:
        candidates = [self._path(audio_hash)]
        # tolerate files renamed without the config suffix (rekey migration)
        prefix_matches = sorted(self.dir.glob(f"{audio_hash[:24]}_*.npz")) + \
            sorted(self.dir.glob(f"{audio_hash[:24]}.npz"))
        for candidate in prefix_matches:
            if candidate not in candidates:
                candidates.append(candidate)
        for path in candidates:
            if not path.exists():
                continue
            try:
                data = np.load(path, allow_pickle=False)
                return TrackFeatures(
                    audio_hash=str(data["audio_hash"]),
                    chroma_mean=data["chroma_mean"],
                    chroma_sequence=data["chroma_sequence"],
                    onset_envelope=data["onset_envelope"],
                    periodicity_profile=data["periodicity_profile"],
                    tempo_bpm=float(data["tempo_bpm"]),
                    timbre_vector=data["timbre_vector"],
                )
            except Exception:
                continue  # corrupt cache entry -> try next / recompute
        return None

    def put(self, feats: TrackFeatures) -> None:
        np.savez_compressed(
            self._path(feats.audio_hash),
            audio_hash=feats.audio_hash,
            chroma_mean=feats.chroma_mean.astype(np.float32),
            chroma_sequence=feats.chroma_sequence.astype(np.float32),
            onset_envelope=feats.onset_envelope.astype(np.float32),
            periodicity_profile=feats.periodicity_profile.astype(np.float32),
            tempo_bpm=np.float32(feats.tempo_bpm),
            timbre_vector=feats.timbre_vector.astype(np.float32),
        )

    def get_or_extract(
        self,
        waveform: np.ndarray,
        sample_rate: int = SAMPLE_RATE,
        audio_key: str | None = None,
    ) -> TrackFeatures:
        """Extract+cache. When ``audio_key`` (e.g., the source-file SHA-256)
        is supplied, it becomes the cache identity so other pipelines can
        resolve features by file hash without decoding."""
        if audio_key:
            cached = self.get(audio_key)
            if cached is not None:
                return cached
            feats = extract_features(waveform, sample_rate)
            keyed = TrackFeatures(
                audio_hash=audio_key,
                chroma_mean=feats.chroma_mean,
                chroma_sequence=feats.chroma_sequence,
                onset_envelope=feats.onset_envelope,
                periodicity_profile=feats.periodicity_profile,
                tempo_bpm=feats.tempo_bpm,
                timbre_vector=feats.timbre_vector,
            )
            self.put(keyed)
            return keyed and self.get(audio_key)

        probe_hash = _hash_waveform(
            waveform if sample_rate == SAMPLE_RATE else _resample_probe(waveform, sample_rate)
        )
        cached = self.get(probe_hash)
        if cached is not None:
            return cached
        feats = extract_features(waveform, sample_rate)
        self.put(feats)
        return feats


def _resample_probe(waveform: np.ndarray, sample_rate: int) -> np.ndarray:
    ratio = SAMPLE_RATE / sample_rate
    n = max(1, int(len(waveform) * ratio))
    return np.interp(np.linspace(0, len(waveform) - 1, n), np.arange(len(waveform)), waveform)


def cache_stats(directory: str | Path) -> dict:
    dirp = Path(directory)
    files = list(dirp.glob("*.npz")) if dirp.exists() else []
    total = sum(f.stat().st_size for f in files)
    return {"entries": len(files), "bytes": total}
