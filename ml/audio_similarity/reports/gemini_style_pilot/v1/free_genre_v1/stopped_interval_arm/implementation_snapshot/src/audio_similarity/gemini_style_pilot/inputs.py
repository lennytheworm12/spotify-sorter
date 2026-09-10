"""Identity-free generation input and content-addressed profile cache identity."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from audio_similarity.stage5e3_artifacts import digest


@dataclass(frozen=True)
class ModelInput:
    """The only track-specific text permitted across the provider boundary."""

    neutral_id: str
    duration_seconds: float
    prepared_sha256: str

    def __post_init__(self):
        if not re.fullmatch(r'N\d{3}', self.neutral_id):
            raise ValueError('expected neutral audio ID')
        if not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0:
            raise ValueError('invalid complete recording duration')
        if not re.fullmatch(r'[0-9a-f]{64}', self.prepared_sha256):
            raise ValueError('invalid prepared audio SHA-256')


def request_body(track: ModelInput, *, file_uri: str, prompt: str, ontology: str,
                 schema: dict, generation_config: dict) -> dict:
    if not re.fullmatch(r'https://generativelanguage.googleapis.com/v1beta/files/[a-z0-9-]+', file_uri):
        raise ValueError('expected a neutral Gemini Files API resource')
    return {
        'systemInstruction': {'parts': [{'text': prompt}, {'text': ontology}]},
        'contents': [{'role': 'user', 'parts': [
            {'text': f'Clip: {track.neutral_id}\nFull recording duration in seconds: {track.duration_seconds:.9f}'},
            {'fileData': {'mimeType': 'audio/flac', 'fileUri': file_uri}},
        ]}],
        'generationConfig': {**generation_config, 'responseJsonSchema': schema},
    }


def profile_cache_key(track: ModelInput, *, model_id: str, generation_config: dict,
                      prompt_sha256: str, ontology_sha256: str, schema_sha256: str,
                      implementation_sha256: str) -> str:
    # Provider URI is ephemeral, and must not force a second inference. Neutral ID
    # and duration are included because they are actual provider-visible context.
    return digest({
        'cache_version': 'gemini-style-profile-v1', 'prepared_audio_sha256': track.prepared_sha256,
        'neutral_id': track.neutral_id, 'duration_seconds': track.duration_seconds,
        'model_id': model_id, 'generation_config': generation_config,
        'prompt_sha256': prompt_sha256, 'ontology_sha256': ontology_sha256,
        'schema_sha256': schema_sha256, 'implementation_sha256': implementation_sha256,
    })
