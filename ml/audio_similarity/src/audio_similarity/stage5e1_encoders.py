"""Encoder adapters for the frozen Stage 5E.1 CLAP arms."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torchaudio

from .stage5a_cache import validate_vector
from .stage5e1_sampling import (
    CHUNK_SAMPLES,
    MEL_HOP_SAMPLES,
    NATIVE_CHUNK_FRAMES,
    normalized_mean,
)


def decode_mono(path: str | Path, sample_rate: int) -> np.ndarray:
    waveform, source_rate = torchaudio.load(str(path))
    if waveform.ndim != 2 or waveform.shape[1] == 0 or not torch.isfinite(waveform).all():
        raise ValueError("invalid retained audio decode")
    waveform = waveform.float().mean(dim=0, keepdim=True)
    if source_rate != sample_rate:
        waveform = torchaudio.functional.resample(waveform, source_rate, sample_rate)
    result = waveform.squeeze(0).contiguous().cpu().numpy().astype(np.float32)
    if not len(result) or not np.isfinite(result).all():
        raise ValueError("invalid resampled retained waveform")
    return result


def encode_segments(encoder: Any, waveform: np.ndarray, sample_rate: int, spans: list[tuple[int, int]]) -> tuple[list[np.ndarray], float]:
    vectors: list[np.ndarray] = []
    elapsed = 0.0
    for start, end in spans:
        began = time.perf_counter()
        encoded = encoder.encode_segment(waveform[start:end], sample_rate)
        elapsed += time.perf_counter() - began
        vectors.append(validate_vector(getattr(encoded, "embedding", encoded), 512))
    return vectors, elapsed


class NativeFusionClapEncoder:
    """Native LAION CLAP AFF plus matched independent-view inference."""

    embedding_dim = 512
    encoder_id = "laion_clap_native_fusion"

    def __init__(self, checkpoint_path: str | Path, *, device: str | None = None):
        import laion_clap

        self.module = laion_clap.CLAP_Module(
            enable_fusion=True,
            amodel="HTSAT-tiny",
            device=device,
        )
        self.module.load_ckpt(str(checkpoint_path), verbose=False)
        self.module.eval()

    @staticmethod
    def _quantize(waveform: np.ndarray) -> torch.Tensor:
        from laion_clap.training.data import float32_to_int16, int16_to_float32

        quantized = int16_to_float32(float32_to_int16(np.asarray(waveform, dtype=np.float32)))
        return torch.from_numpy(quantized).float()

    def native_views(self, waveform: np.ndarray, plan: dict[str, Any]) -> list[torch.Tensor]:
        """Return the exact global/front/middle/back mel tensors consumed by AFF."""
        from laion_clap.training.data import get_mel
        import torchvision

        audio = self._quantize(waveform)
        mel = get_mel(audio, self.module.model_cfg["audio_cfg"])
        if int(mel.shape[0]) != int(plan["total_mel_frames"]):
            raise ValueError("frozen native mel-frame geometry differs from decoded audio")
        starts = [int(value) for value in plan["local_start_frames"]]
        locals_ = [mel[start : start + NATIVE_CHUNK_FRAMES, :] for start in starts]
        if any(tuple(value.shape) != (NATIVE_CHUNK_FRAMES, 64) for value in locals_):
            raise ValueError("native local view has invalid geometry")
        global_ = torchvision.transforms.Resize(
            size=[NATIVE_CHUNK_FRAMES, int(self.module.model_cfg["audio_cfg"]["mel_bins"])]
        )(mel[None])[0]
        return [global_, *locals_]

    def _sample(self, views: list[torch.Tensor], *, longer: bool, waveform: np.ndarray) -> dict[str, torch.Tensor]:
        first = self._quantize(waveform[:CHUNK_SAMPLES])
        if len(first) < CHUNK_SAMPLES:
            repeats = CHUNK_SAMPLES // max(1, len(first))
            first = first.repeat(repeats)
            first = torch.nn.functional.pad(first, (0, CHUNK_SAMPLES - len(first)))
        return {
            "mel_fusion": torch.stack(views),
            "longer": torch.tensor([longer]),
            "waveform": first,
        }

    def encode_aff(self, waveform: np.ndarray, plan: dict[str, Any]) -> tuple[np.ndarray, list[torch.Tensor], float]:
        if not plan.get("longer"):
            raise ValueError("Stage 5E.1 eligible audio must exercise native AFF")
        views = self.native_views(waveform, plan)
        began = time.perf_counter()
        with torch.no_grad():
            vector = self.module.model.get_audio_embedding(
                [self._sample(views, longer=True, waveform=waveform)]
            )[0].detach().float().cpu().numpy()
        return validate_vector(vector, 512), views, time.perf_counter() - began

    def encode_independent_views(
        self,
        waveform: np.ndarray,
        plan: dict[str, Any],
        *,
        views: list[torch.Tensor] | None = None,
    ) -> tuple[list[np.ndarray], np.ndarray, float]:
        views = views or self.native_views(waveform, plan)
        samples = [
            self._sample([view, view, view, view], longer=False, waveform=waveform)
            for view in views
        ]
        began = time.perf_counter()
        with torch.no_grad():
            matrix = self.module.model.get_audio_embedding(samples).detach().float().cpu().numpy()
        elapsed = time.perf_counter() - began
        vectors = [validate_vector(row, 512) for row in matrix]
        return vectors, normalized_mean(vectors), elapsed


def native_view_spans(plan: dict[str, Any]) -> list[tuple[str, int, int]]:
    spans = [("NATIVE_GLOBAL_RESIZED_MEL", 0, int(plan["total_mel_frames"]))]
    spans.extend(
        (kind, int(start), int(start) + NATIVE_CHUNK_FRAMES)
        for kind, start in zip(
            ("NATIVE_FRONT_MEL", "NATIVE_MIDDLE_MEL", "NATIVE_BACK_MEL"),
            plan["local_start_frames"],
            strict=True,
        )
    )
    return spans
