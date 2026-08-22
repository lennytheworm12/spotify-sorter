"""MERIT encoder: frozen MERT-v1-330M backbone + melody/rhythm/timbre projection heads.

Implements the published MERIT inference path (AMAAI-Lab/MERIT README, 2026):

    audio (24 kHz mono, 30 s)
      -> MERT-v1-330M [frozen], output_hidden_states=True
      -> hidden layers (3, 4, 5, 6, 23), mean-pool over time each
      -> concatenate -> 5120-D backbone vector   (ONE shared forward pass)
      -> head_mel / head_rhy / head_tim
           Linear(5120->512) -> ReLU -> Linear(512->128, bias=False) -> L2 normalize
      -> three 128-D unit vectors

The pooled 5120-D general-MERT representation is preserved as Baseline A.

Design reference: Phase 1 doc, sections 7-9.
"""

from __future__ import annotations

import hashlib
import platform
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from huggingface_hub import hf_hub_download, model_info

from .audio import PREPROCESSING_VERSION

MERT_MODEL_ID = "m-a-p/MERT-v1-330M"
MERIT_REPO_ID = "amaai-lab/merit"
EXTRACT_LAYERS = (3, 4, 5, 6, 23)

HEAD_FILES = {
    "melody": "head_mel/best_head.pt",
    "rhythm": "head_rhy/best_head.pt",
    "timbre": "head_tim/best_head.pt",
}
FACTORS = ("melody", "rhythm", "timbre")

EMBEDDING_DIM = 128
BACKBONE_DIM = 1024 * len(EXTRACT_LAYERS)  # 5120
NORM_TOLERANCE = 1e-3


class ModelOutputInvalidError(RuntimeError):
    """Raised when encoder output violates the embedding contract."""


class ProjectionHead(torch.nn.Module):
    def __init__(self, in_dim: int = BACKBONE_DIM, hidden_dim: int = 512, out_dim: int = EMBEDDING_DIM):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(in_dim, hidden_dim),
            torch.nn.ReLU(inplace=True),
            torch.nn.Linear(hidden_dim, out_dim, bias=False),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.nn.functional.normalize(self.net(x), dim=-1)


def load_head_state(path: str | Path) -> dict:
    ckpt = torch.load(str(path), map_location="cpu", weights_only=True)
    for key in ("in_dim", "hidden_dim", "out_dim", "state_dict"):
        if key not in ckpt:
            raise ValueError(f"head checkpoint {path} missing key '{key}'")
    return ckpt


def load_head_from_checkpoint(ckpt: dict) -> ProjectionHead:
    head = ProjectionHead(int(ckpt["in_dim"]), int(ckpt["hidden_dim"]), int(ckpt["out_dim"]))
    head.load_state_dict(ckpt["state_dict"])
    return head.eval()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _library_versions() -> dict[str, str]:
    import transformers
    import torchaudio

    return {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torchaudio": torchaudio.__version__,
        "transformers": transformers.__version__,
        "cuda": torch.version.cuda or "none",
        "cudnn": str(torch.backends.cudnn.version()),
    }


@dataclass(frozen=True)
class ModelProvenance:
    backbone_id: str
    backbone_revision: str
    merit_repo_id: str
    merit_revision: str
    preprocessing_version: str
    extract_layers: tuple[int, ...]
    head_sha256: dict[str, str]
    library_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "backbone_id": self.backbone_id,
            "backbone_revision": self.backbone_revision,
            "merit_repo_id": self.merit_repo_id,
            "merit_revision": self.merit_revision,
            "preprocessing_version": self.preprocessing_version,
            "extract_layers": list(self.extract_layers),
            "head_sha256": dict(self.head_sha256),
            "library_versions": dict(self.library_versions),
        }


@dataclass(frozen=True)
class EmbeddingResult:
    melody: np.ndarray
    rhythm: np.ndarray
    timbre: np.ndarray
    mert_general: np.ndarray
    diagnostics: dict

    @property
    def factors(self) -> dict[str, np.ndarray]:
        return {"melody": self.melody, "rhythm": self.rhythm, "timbre": self.timbre}


def validate_factor_vector(name: str, vector: np.ndarray) -> None:
    if vector.shape != (EMBEDDING_DIM,):
        raise ModelOutputInvalidError(f"{name}: expected shape ({EMBEDDING_DIM},), got {vector.shape}")
    if not np.isfinite(vector).all():
        raise ModelOutputInvalidError(f"{name}: non-finite values present")
    norm = float(np.linalg.norm(vector))
    if abs(norm - 1.0) > NORM_TOLERANCE:
        raise ModelOutputInvalidError(f"{name}: L2 norm {norm} outside 1.0 +/- {NORM_TOLERANCE}")


class MeritEncoder:
    """Frozen MERT + MERIT heads. One shared forward pass per waveform.

    Components are injectable for testing; use :meth:`from_pretrained` for the real models.
    """

    def __init__(
        self,
        model: torch.nn.Module,
        processor,
        heads: dict[str, ProjectionHead],
        provenance: ModelProvenance,
        device: torch.device | None = None,
    ):
        self.device = device or next(model.parameters()).device
        self.model = model.to(self.device).eval()
        self.processor = processor
        self.heads = {name: head.to(self.device).eval() for name, head in heads.items()}
        missing = [name for name in FACTORS if name not in self.heads]
        if missing:
            raise ValueError(f"missing projection heads: {missing}")
        self.provenance = provenance
        self._forward_calls = 0

    @classmethod
    def from_pretrained(
        cls,
        device: str | torch.device | None = None,
        cache_dir: str | Path | None = None,
    ) -> "MeritEncoder":
        from transformers import AutoModel, Wav2Vec2FeatureExtractor

        resolved = torch.device(device) if device else torch.device("cuda" if torch.cuda.is_available() else "cpu")

        processor = Wav2Vec2FeatureExtractor.from_pretrained(MERT_MODEL_ID, trust_remote_code=True)
        try:
            backbone_revision = model_info(MERT_MODEL_ID).sha or "unknown"
        except Exception:
            backbone_revision = "unknown"
        mert = AutoModel.from_pretrained(MERT_MODEL_ID, trust_remote_code=True)

        heads: dict[str, ProjectionHead] = {}
        head_hashes: dict[str, str] = {}
        merit_revision = ""
        for name, filename in HEAD_FILES.items():
            path = Path(hf_hub_download(MERIT_REPO_ID, filename, cache_dir=cache_dir))
            head_hashes[name] = sha256_file(path)
            heads[name] = load_head_from_checkpoint(load_head_state(path))

        if merit_revision == "":
            try:
                merit_revision = model_info(MERIT_REPO_ID).sha or "unknown"
            except Exception:
                merit_revision = "unknown"

        provenance = ModelProvenance(
            backbone_id=MERT_MODEL_ID,
            backbone_revision=backbone_revision,
            merit_repo_id=MERIT_REPO_ID,
            merit_revision=merit_revision,
            preprocessing_version=PREPROCESSING_VERSION,
            extract_layers=EXTRACT_LAYERS,
            head_sha256=head_hashes,
            library_versions=_library_versions(),
        )
        return cls(model=mert, processor=processor, heads=heads, provenance=provenance, device=resolved)

    @property
    def forward_call_count(self) -> int:
        return self._forward_calls

    @torch.no_grad()
    def encode_waveform(self, wav: torch.Tensor) -> EmbeddingResult:
        """Encode a preprocessed (target_samples,) waveform at config sample rate."""
        if wav.ndim != 1:
            raise ValueError(f"expected 1-D preprocessed waveform, got shape {tuple(wav.shape)}")
        inputs = self.processor(wav.numpy(), sampling_rate=int(self.processor.sampling_rate), return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        out = self.model(**inputs, output_hidden_states=True)
        self._forward_calls += 1

        parts = [out.hidden_states[layer].mean(dim=1) for layer in self.provenance.extract_layers]
        backbone = torch.cat(parts, dim=-1)  # (1, 5120)

        factor_vectors: dict[str, np.ndarray] = {}
        norms: dict[str, float] = {}
        for name in FACTORS:
            vec = self.heads[name](backbone)[0].detach().float().cpu().numpy()
            factor_vectors[name] = vec
            norms[f"{name}_norm"] = float(np.linalg.norm(vec))

        general_raw = backbone[0].detach().float().cpu().numpy()
        general_norm = float(np.linalg.norm(general_raw))
        mert_general = general_raw / general_norm if general_norm > 0 else general_raw

        result = EmbeddingResult(
            **factor_vectors,
            mert_general=mert_general,
            diagnostics={
                **norms,
                "mert_general_norm": general_norm,
                "inference_ms": None,  # filled by timed callers
                "device": str(self.device),
                "precision": "fp32",
            },
        )
        for name, vector in result.factors.items():
            validate_factor_vector(name, vector)
        if mert_general.shape != (BACKBONE_DIM,) or not np.isfinite(mert_general).all():
            raise ModelOutputInvalidError(f"mert_general: invalid shape/values {mert_general.shape}")
        return result
