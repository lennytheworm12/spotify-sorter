"""Frozen GLAP audio adapter for the historical Stage 2B challenger.

Heavy imports and model loading remain inside ``GlapAudioEncoder`` so normal
unit tests stay model-download-free.  The adapter accepts the exact historical
24 kHz mono excerpt and performs only the contract-frozen 24 kHz -> 16 kHz
conversion required by GLAP.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from .encoder import HolisticEmbedding
from .holistic_encoders import EncoderContractError


GLAP_ENCODER_ID = "glap_stage2b_challenger_v1"
GLAP_DIMENSION = 1024
GLAP_SAMPLE_RATE = 16000
HISTORICAL_SAMPLE_RATE = 24000
GLAP_CONFIGURATION_CODE_SHA256 = "9fb623f5be62e70967ecb8f8c8a49981313b28156b0a0fb4cdf51f4f07d88cb9"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class GlapAudioEncoder:
    """Official ``mispeech/GLAP`` audio tower behind the holistic interface."""

    encoder_id = GLAP_ENCODER_ID
    embedding_dim = GLAP_DIMENSION

    def __init__(
        self,
        model_dir: str | Path,
        *,
        model_revision: str,
        model_sha256: str,
        model_code_sha256: str,
        model_config_sha256: str,
        tokenizer_sha256: str,
        device: str,
        configuration_code_sha256: str = GLAP_CONFIGURATION_CODE_SHA256,
        verify_model_hash: bool = True,
        model_loader: Callable[..., object] | None = None,
    ) -> None:
        workspace = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
        if workspace not in (None, ":4096:8"):
            raise EncoderContractError(
                "GLAP deterministic CUDA requires CUBLAS_WORKSPACE_CONFIG=:4096:8"
            )
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        import torch

        self.model_dir = Path(model_dir).resolve()
        self.model_revision = str(model_revision)
        self.model_sha256 = str(model_sha256)
        self.model_code_sha256 = str(model_code_sha256)
        self.model_config_sha256 = str(model_config_sha256)
        self.configuration_code_sha256 = str(configuration_code_sha256)
        self.tokenizer_sha256 = str(tokenizer_sha256)
        self.device = str(device)
        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise EncoderContractError(f"GLAP device {self.device!r} requested but CUDA is unavailable")
        frozen_files = {
            "model.safetensors": str(model_sha256),
            "modeling_glap.py": str(model_code_sha256),
            "config.json": str(model_config_sha256),
            "configuration_glap.py": str(configuration_code_sha256),
            "sentencepiece.source.256000.model": str(tokenizer_sha256),
        }
        missing = [name for name in frozen_files if not (self.model_dir / name).is_file()]
        if missing:
            raise EncoderContractError(f"missing frozen GLAP files: {missing}")
        if verify_model_hash:
            for filename, expected in frozen_files.items():
                actual = sha256_file(self.model_dir / filename)
                if actual != expected:
                    raise EncoderContractError(f"GLAP {filename} SHA-256 mismatch: {actual}")

        torch.manual_seed(0)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(0)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.use_deterministic_algorithms(True)

        started = time.perf_counter()
        if model_loader is None:
            from transformers import AutoModel

            model_loader = AutoModel.from_pretrained
        self.model = model_loader(
            str(self.model_dir),
            trust_remote_code=True,
            local_files_only=True,
        ).to(self.device).eval()
        self.load_seconds = time.perf_counter() - started
        self._torch = torch

    def encode_segment(self, waveform: np.ndarray, sample_rate: int) -> HolisticEmbedding:
        return self.encode_batch([waveform], sample_rate)[0]

    def encode_batch(
        self,
        waveforms: Sequence[np.ndarray],
        sample_rate: int,
    ) -> list[HolisticEmbedding]:
        """Encode a same-length batch without gradients or autocast."""

        torch = self._torch
        if sample_rate != HISTORICAL_SAMPLE_RATE:
            raise EncoderContractError(
                f"GLAP Stage 2B adapter expects 24 kHz historical excerpts; got {sample_rate}"
            )
        if not waveforms:
            return []
        arrays = []
        for waveform in waveforms:
            array = np.asarray(waveform, dtype=np.float32)
            if array.ndim != 1 or array.size == 0 or not np.isfinite(array).all():
                raise EncoderContractError("GLAP input must be finite, non-empty mono audio")
            arrays.append(array)
        lengths = {array.shape[0] for array in arrays}
        if len(lengths) != 1:
            raise EncoderContractError("GLAP batch inputs must have equal lengths")

        import torchaudio

        audio = torch.from_numpy(np.stack(arrays)).to(self.device, dtype=torch.float32)
        audio = torchaudio.functional.resample(audio, sample_rate, GLAP_SAMPLE_RATE)
        # Use the released audio tower directly.  Float32/no-autocast is frozen
        # in the experiment contract.
        with torch.inference_mode():
            output = self.model.encode_audio(audio)
        matrix = output.detach().float().cpu().numpy()
        if matrix.shape != (len(arrays), self.embedding_dim):
            raise EncoderContractError(
                f"GLAP returned {matrix.shape}; expected {(len(arrays), self.embedding_dim)}"
            )

        results = []
        for vector in matrix:
            norm = float(np.linalg.norm(vector.astype(np.float64)))
            if not np.isfinite(vector).all() or not np.isfinite(norm) or norm <= 0:
                raise EncoderContractError("GLAP produced a zero or non-finite embedding")
            normalized = (vector.astype(np.float64) / norm).astype(np.float32)
            results.append(
                HolisticEmbedding(
                    embedding=normalized,
                    encoder_id=self.encoder_id,
                    embedding_dim=self.embedding_dim,
                    provenance={
                        "model_identifier": "mispeech/GLAP",
                        "model_revision": self.model_revision,
                        "model_sha256": self.model_sha256,
                        "model_code_sha256": self.model_code_sha256,
                        "model_config_sha256": self.model_config_sha256,
                        "configuration_code_sha256": self.configuration_code_sha256,
                        "tokenizer_sha256": self.tokenizer_sha256,
                        "device": self.device,
                        "input_sample_rate": sample_rate,
                        "model_sample_rate": GLAP_SAMPLE_RATE,
                        "resampling": "torchaudio_functional_resample_2.6.0_v1",
                        "compute_dtype": "float32",
                        "autocast": False,
                    },
                )
            )
        return results

    def peak_vram_bytes(self) -> int | None:
        if not self.device.startswith("cuda"):
            return None
        return int(self._torch.cuda.max_memory_allocated(self.device))
