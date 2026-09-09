"""Validate transport/audio evidence separately from legitimate style uncertainty."""
from .validation import validate_profile


class ResponseStopped(ValueError):
    pass


def validate_response(value: dict, *, schema: dict, allowed: dict, duration: float) -> dict:
    if not value.get('responseId') or not value.get('modelVersion'):
        raise ResponseStopped('provider response ID or model version missing')
    candidates = value.get('candidates', [])
    if len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
        raise ResponseStopped('generation did not finish with exactly one complete candidate')
    if any(candidates[0].get(field) for field in ['groundingMetadata', 'urlContextMetadata']):
        raise ResponseStopped('prohibited external grounding returned')
    audio_tokens = [x.get('tokenCount') for x in value.get('usageMetadata', {}).get('promptTokensDetails', [])
                    if x.get('modality') == 'AUDIO']
    if not audio_tokens or any(type(n) is not int or n <= 0 for n in audio_tokens):
        raise ResponseStopped('provider did not confirm processing audio input tokens')
    parts = candidates[0].get('content', {}).get('parts', [])
    if not parts or any(p.get('thought') or not isinstance(p.get('text'), str) for p in parts):
        raise ResponseStopped('unexpected output part or returned thinking')
    response_text = ''.join(p['text'] for p in parts)
    profile = validate_profile(response_text, schema=schema, allowed_families=allowed, duration_seconds=duration)
    return {'response_id': value['responseId'], 'model_version': value['modelVersion'],
            'finish_reason': candidates[0]['finishReason'], 'usage': value['usageMetadata'],
            'response_text': response_text, 'profile': profile}
