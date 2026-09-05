"""Frozen Audio Representation v1 contract for Stage 5A consumers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


REPRESENTATION_VERSION = "audio-representation-v1"
SAMPLING_VERSION = "uniform3-dual-mean-5s-centers-5-15-25-v1"
AGGREGATION_VERSION = "per-encoder-segment-l2-mean-l2-v1"
EMBEDDING_DTYPE = "float32"


class RepresentationContractError(ValueError):
    """Raised when the authoritative v1 artifact is incompatible with Stage 5A."""


def _canonical_sha256(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class EncoderIdentity:
    encoder_id: str
    dimension: int
    provenance: dict

    @property
    def provenance_json(self) -> str:
        return json.dumps(self.provenance, sort_keys=True, separators=(",", ":"))

    @property
    def provenance_sha256(self) -> str:
        return hashlib.sha256(self.provenance_json.encode()).hexdigest()


@dataclass(frozen=True)
class RepresentationContract:
    artifact_path: Path
    artifact_sha256: str
    representation_version: str
    preprocessing_version: str
    sampling_version: str
    method: str
    centers_sec: tuple[int, ...]
    segment_duration_sec: int
    sample_rate: int
    channels: str
    embedding_dtype: str
    aggregation_version: str
    encoders: tuple[EncoderIdentity, ...]
    clap_weight: float
    muq_weight: float
    vector_contract_sha256: str

    def encoder(self, encoder_id: str) -> EncoderIdentity:
        for encoder in self.encoders:
            if encoder.encoder_id == encoder_id:
                return encoder
        raise KeyError(encoder_id)

    def encoder_analysis_identity(
        self,
        *,
        corpus: str,
        corpus_version: str,
        stable_track_id: str,
        source_audio_sha256: str,
        canonical_pcm_sha256: str,
        encoder_id: str,
    ) -> str:
        encoder = self.encoder(encoder_id)
        return _canonical_sha256(
            {
                "corpus": corpus,
                "corpus_version": corpus_version,
                "stable_track_id": stable_track_id,
                "source_audio_sha256": source_audio_sha256,
                "canonical_pcm_sha256": canonical_pcm_sha256,
                "vector_contract_sha256": self.vector_contract_sha256,
                "representation_version": self.representation_version,
                "preprocessing_version": self.preprocessing_version,
                "sampling_version": self.sampling_version,
                "centers_sec": self.centers_sec,
                "aggregation_version": self.aggregation_version,
                "embedding_dtype": self.embedding_dtype,
                "encoder_id": encoder.encoder_id,
                "encoder_dimension": encoder.dimension,
                "encoder_provenance_sha256": encoder.provenance_sha256,
            }
        )

    def representation_identity(
        self,
        *,
        corpus: str,
        corpus_version: str,
        stable_track_id: str,
        source_audio_sha256: str,
        canonical_pcm_sha256: str,
    ) -> str:
        return _canonical_sha256(
            {
                "corpus": corpus,
                "corpus_version": corpus_version,
                "stable_track_id": stable_track_id,
                "source_audio_sha256": source_audio_sha256,
                "canonical_pcm_sha256": canonical_pcm_sha256,
                "vector_contract_sha256": self.vector_contract_sha256,
                "encoder_provenance": {
                    encoder.encoder_id: encoder.provenance_sha256
                    for encoder in self.encoders
                },
            }
        )


def load_contract(path: str | Path) -> RepresentationContract:
    artifact_path = Path(path)
    payload = json.loads(artifact_path.read_text())
    audio = payload.get("audio", {})
    sampling = payload.get("temporal_sampling", {})
    fusion = payload.get("fusion", {})
    encoders = payload.get("encoders", {})

    expected = {
        "audio_representation": "Audio Representation v1",
        "sample_rate_hz": 24000,
        "channels": "mono",
        "method": "UNIFORM3_DUAL_MEAN",
        "selected_k": 3,
        "centers": [5, 15, 25],
        "segment_duration_seconds": 5,
        "clap_weight": 0.7172981519,
        "muq_weight": 0.2827018481,
    }
    actual = {
        "audio_representation": payload.get("audio_representation"),
        "sample_rate_hz": audio.get("sample_rate_hz"),
        "channels": audio.get("channels"),
        "method": sampling.get("selected_method"),
        "selected_k": sampling.get("selected_k"),
        "centers": sampling.get("segment_centers_seconds"),
        "segment_duration_seconds": sampling.get("segment_duration_seconds"),
        "clap_weight": fusion.get("clap_weight"),
        "muq_weight": fusion.get("muq_weight"),
    }
    mismatches = [name for name, value in expected.items() if actual[name] != value]
    if mismatches:
        raise RepresentationContractError(
            f"Audio Representation v1 mismatch: {', '.join(mismatches)}"
        )
    if fusion.get("stage4a_refit_weights") is not False:
        raise RepresentationContractError("Stage 4A fusion weights must remain frozen")

    clap = encoders.get("clap", {})
    muq = encoders.get("muq", {})
    required_clap = ("id", "checkpoint", "checkpoint_sha256", "provenance")
    required_muq = ("id", "repository", "revision", "weights_sha256", "config_sha256")
    if any(not clap.get(name) for name in required_clap):
        raise RepresentationContractError("incomplete CLAP provenance")
    if any(not muq.get(name) for name in required_muq):
        raise RepresentationContractError("incomplete MuQ provenance")

    encoder_identities = (
        EncoderIdentity(
            encoder_id=clap["id"],
            dimension=512,
            provenance={name: clap[name] for name in required_clap if name != "id"},
        ),
        EncoderIdentity(
            encoder_id=muq["id"],
            dimension=512,
            provenance={name: muq[name] for name in required_muq if name != "id"},
        ),
    )
    vector_contract = {
        "representation_version": REPRESENTATION_VERSION,
        "preprocessing_version": audio.get("preprocessing_version"),
        "sample_rate": audio["sample_rate_hz"],
        "channels": audio["channels"],
        "sampling_version": SAMPLING_VERSION,
        "method": sampling["selected_method"],
        "centers_sec": sampling["segment_centers_seconds"],
        "segment_duration_sec": sampling["segment_duration_seconds"],
        "aggregation_version": AGGREGATION_VERSION,
        "embedding_dtype": EMBEDDING_DTYPE,
        "encoders": {
            encoder.encoder_id: {
                "dimension": encoder.dimension,
                "provenance_sha256": encoder.provenance_sha256,
            }
            for encoder in encoder_identities
        },
    }
    if not vector_contract["preprocessing_version"]:
        raise RepresentationContractError("missing preprocessing version")
    return RepresentationContract(
        artifact_path=artifact_path,
        artifact_sha256=_file_sha256(artifact_path),
        representation_version=REPRESENTATION_VERSION,
        preprocessing_version=vector_contract["preprocessing_version"],
        sampling_version=SAMPLING_VERSION,
        method=sampling["selected_method"],
        centers_sec=tuple(sampling["segment_centers_seconds"]),
        segment_duration_sec=sampling["segment_duration_seconds"],
        sample_rate=audio["sample_rate_hz"],
        channels=audio["channels"],
        embedding_dtype=EMBEDDING_DTYPE,
        aggregation_version=AGGREGATION_VERSION,
        encoders=encoder_identities,
        clap_weight=fusion["clap_weight"],
        muq_weight=fusion["muq_weight"],
        vector_contract_sha256=_canonical_sha256(vector_contract),
    )
