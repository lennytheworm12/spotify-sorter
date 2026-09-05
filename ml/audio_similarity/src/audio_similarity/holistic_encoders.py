"""Holistic encoder adapters for the Stage 1A benchmark (pivot design section 6).

Three pinned encoders behind one contract (`HolisticAudioEncoder`):

    muq_mulan_large  OpenMuQ/MuQ-MuLan-large   512-D @ 24 kHz
    mert_*           m-a-p/MERT-v1-330M        layer-pooled variants
    laion_clap       LAION 630k-audioset-best  512-D @ 48 kHz / 10 s window

Heavy imports and model loads happen inside the adapters, never at module
import time, so lightweight unit tests stay fast and network-free.

Documented model-contract deviations from the shared 5-s/24 kHz excerpt:
    CLAP resamples to 48 kHz internally quantizing to a fixed 10-s window
    (zero-padding shorter input). Same musical content; different model
    windowing. Recorded per embedding in provenance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class EncoderContractError(RuntimeError):
    """Raised when an encoder violates its declared contract."""


def _l2(vec: np.ndarray) -> np.ndarray:
    vec = np.asarray(vec, dtype=np.float64).reshape(-1)
    norm = float(np.linalg.norm(vec))
    if norm <= 0 or not np.isfinite(norm):
        raise EncoderContractError("encoder produced zero/non-finite vector")
    return vec / norm


@dataclass(frozen=True)
class AdapterSpec:
    encoder_id: str
    hf_repo: str | None = None
    checkpoint: str | None = None
    variant: str | None = None
    declared_dim: int = 512


# ---------------------------------------------------------------------------
# MuQ-MuLan
# ---------------------------------------------------------------------------


class MuQMulanEncoder:
    """OpenMuQ/MuQ-MuLan-large — 512-D audio embeddings at 24 kHz mono."""

    def __init__(
        self,
        spec: AdapterSpec | None = None,
        device: str | None = None,
        revision: str | None = None,
    ):
        self.spec = spec or AdapterSpec(
            encoder_id="muq_mulan_large",
            hf_repo="OpenMuQ/MuQ-MuLan-large",
            declared_dim=512,
        )
        self.encoder_id = self.spec.encoder_id
        self.embedding_dim = self.spec.declared_dim
        self.device = device or ("cuda" if _cuda_available() else "cpu")
        import torch

        from muq import MuQMuLan

        kwargs = {"revision": revision} if revision else {}
        self.model = MuQMuLan.from_pretrained(self.spec.hf_repo, **kwargs).to(self.device).eval()
        self.revision = revision or "auto"

    def encode_segment(self, waveform: np.ndarray, sample_rate: int) -> "HolisticEmbedding":
        import torch

        if sample_rate != 24000:
            raise EncoderContractError(
                f"MuQ-MuLan expects 24 kHz excerpts; got {sample_rate}. "
                "Resample with the shared excerpt contract before encoding."
            )
        wav = torch.tensor(np.asarray(waveform, dtype=np.float32)).unsqueeze(0).to(self.device)
        with torch.no_grad():
            out = self.model(wavs=wav)
        embeds = out.get("output") if isinstance(out, dict) else out
        if embeds is None:
            raise EncoderContractError("MuQ-MuLan returned no 'output' embedding")
        vec = _l2(embeds[0].detach().float().cpu().numpy())
        if len(vec) != self.embedding_dim:
            raise EncoderContractError(f"expected {self.embedding_dim}-D, got {len(vec)}")
        from .encoder import HolisticEmbedding

        return HolisticEmbedding(
            embedding=vec,
            encoder_id=self.encoder_id,
            embedding_dim=self.embedding_dim,
            provenance={
                "hf_repo": self.spec.hf_repo,
                "revision": self.revision,
                "device": self.device,
                "input_sr": sample_rate,
            },
        )


# ---------------------------------------------------------------------------
# MERT variants (reuses Phase 1 backbone loading conventions)
# ---------------------------------------------------------------------------

MERT_BACKBONE_ID = "m-a-p/MERT-v1-330M"
MERT_EXTRACT_LAYERS = (3, 4, 5, 6, 23)


class MertVariantEncoder:
    """Layer-pooled MERT-v1-330M representations.

    variants:
        layers_3_4_5_6_23_concat_meanpool -> 5120-D (historical MERIT-style)
        last_layer_meanpool               -> 1024-D generic challenger
    """

    VARIANTS = {
        "layers_3_4_5_6_23_concat_meanpool": (MERT_EXTRACT_LAYERS, 5120),
        "last_layer_meanpool": ((24,), 1024),
    }

    def __init__(self, variant: str, device: str | None = None, backbone_id: str = MERT_BACKBONE_ID):
        if variant not in self.VARIANTS:
            raise ValueError(f"unknown MERT variant '{variant}'")
        self.variant = variant
        self.layers, self.embedding_dim = self.VARIANTS[variant]
        self.encoder_id = f"mert_{variant}"
        self.backbone_id = backbone_id
        self.device = device or ("cuda" if _cuda_available() else "cpu")

        import torch
        from transformers import AutoModel

        self.model = AutoModel.from_pretrained(
            backbone_id, trust_remote_code=True
        ).to(self.device).eval()

    def encode_segment(self, waveform: np.ndarray, sample_rate: int) -> "HolisticEmbedding":
        import torch

        wav = np.asarray(waveform, dtype=np.float32)
        inputs = {"input_values": torch.tensor(wav).unsqueeze(0).to(self.device)}
        with torch.no_grad():
            out = self.model(**inputs, output_hidden_states=True)
        parts = [out.hidden_states[layer].mean(dim=1) for layer in self.layers]
        vec = torch.cat(parts, dim=-1)[0].detach().float().cpu().numpy()
        vec = _l2(vec)
        if len(vec) != self.embedding_dim:
            raise EncoderContractError(
                f"variant '{self.variant}' produced {len(vec)}-D, expected {self.embedding_dim}"
            )
        from .encoder import HolisticEmbedding

        return HolisticEmbedding(
            embedding=vec,
            encoder_id=self.encoder_id,
            embedding_dim=self.embedding_dim,
            provenance={
                "backbone": self.backbone_id,
                "layers": list(self.layers),
                "device": self.device,
                "input_sr": sample_rate,
            },
        )


def mert_5120_encoder(device: str | None = None) -> MertVariantEncoder:
    return MertVariantEncoder("layers_3_4_5_6_23_concat_meanpool", device=device)


def mert_generic_encoder(device: str | None = None) -> MertVariantEncoder:
    return MertVariantEncoder("last_layer_meanpool", device=device)


# ---------------------------------------------------------------------------
# LAION-CLAP
# ---------------------------------------------------------------------------


class LaionClapEncoder:
    """LAION CLAP (HTSAT-base, 630k-audioset-best) — 512-D @ 48 kHz.

    The model internally quantizes input to a fixed 10-second window;
    shorter excerpts are zero-padded by the library. Recorded as
    preprocessing provenance.
    """

    INPUT_SR = 48000

    def __init__(
        self,
        spec: AdapterSpec | None = None,
        checkpoint_path: str | None = None,
    ):
        self.spec = spec or AdapterSpec(
            encoder_id="laion_clap",
            checkpoint="music_audioset_epoch_15_esc_90.14.pt",
            declared_dim=512,
        )
        self.encoder_id = self.spec.encoder_id
        self.embedding_dim = self.spec.declared_dim
        import laion_clap

        self.model = laion_clap.CLAP_Module(enable_fusion=False, amodel="HTSAT-base")
        ckpt = checkpoint_path or self._default_checkpoint()
        if ckpt and Path(ckpt).exists():
            self.model.load_ckpt(str(ckpt), verbose=False)
        # note: PyPI default weights auto-load when no explicit ckpt given

    @staticmethod
    def _default_checkpoint() -> str | None:
        env = os.environ.get("CLAP_CHECKPOINT_PATH")
        return env or None

    def encode_segment(self, waveform: np.ndarray, sample_rate: int) -> "HolisticEmbedding":
        import librosa

        wav = np.asarray(waveform, dtype=np.float32)
        if wav.ndim == 2:
            wav = wav.mean(axis=-1)
        if sample_rate != self.INPUT_SR:
            wav = librosa.resample(wav, orig_sr=sample_rate, target_sr=self.INPUT_SR)
        # library expects a 2-D float batch; quantizes internally
        embeds = self.model.get_audio_embedding_from_data(
            x=wav.reshape(1, -1).astype(np.float64), use_tensor=False
        )
        vec = _l2(np.asarray(embeds)[0])
        if len(vec) != self.embedding_dim:
            raise EncoderContractError(f"expected {self.embedding_dim}-D, got {len(vec)}")
        from .encoder import HolisticEmbedding

        return HolisticEmbedding(
            embedding=vec,
            encoder_id=self.encoder_id,
            embedding_dim=self.embedding_dim,
            provenance={
                "checkpoint": self.spec.checkpoint,
                "model_input_sr": self.INPUT_SR,
                "excerpt_resampled_from": sample_rate,
                "window_seconds": 10,
                "windowing": "library internal pad/repeat to fixed 10 s",
            },
        )


def _cuda_available() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False
