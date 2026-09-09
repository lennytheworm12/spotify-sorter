import hashlib
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from audio_similarity.gemini_style_pilot.prepare import prepare_audio


def test_full_audio_metadata_removal_hash_lock_and_conversion_free_replay(tmp_path):
    source = tmp_path / 'identified.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=31.2',
                    '-metadata', 'artist=DO NOT SEND', '-metadata', 'title=PRIVATE TITLE', str(source)], check=True)
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / 'prepared' / 'N001.flac'
    receipt = prepare_audio(source, sha, destination)
    assert receipt['duration_seconds'] == pytest.approx(31.2)
    assert receipt['full_recording_preserved'] and receipt['identity_metadata_removed']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == sha
    with patch('subprocess.run', side_effect=AssertionError('unexpected conversion')):
        assert prepare_audio(source, sha, destination) == receipt
    with pytest.raises(ValueError, match='source hash'):
        prepare_audio(source, '0' * 64, destination)
    destination.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='integrity mismatch'):
        prepare_audio(source, sha, destination)


from audio_similarity.gemini_style_pilot.budget import AttemptLedger, BudgetStopped


def ledger(tmp_path, **kwargs):
    return AttemptLedger(tmp_path, input_limit=1048576, input_usd_per_million='0.75',
                         output_usd_per_million='3.75', **kwargs)


def reserve(value):
    return value.reserve(counted_input=8000, max_output_tokens=8192, request_sha256='a'*64,
                         manifest_sha256='b'*64, neutral_id='N001')


def test_reservations_include_thinking_stop_unaccounted_attempts_and_preserve_all_attempts(tmp_path):
    value = ledger(tmp_path)
    first = reserve(value)
    assert first['reserved_upper_cost_usd'] == '0.81715200'
    with pytest.raises(BudgetStopped, match='unresolved'):
        reserve(value)
    with pytest.raises(BudgetStopped, match='inconsistent'):
        value.settle(1, {'promptTokenCount': 8000, 'candidatesTokenCount': 900, 'totalTokenCount': 9000})
    settlement = value.settle(1, {'promptTokenCount': 8001, 'candidatesTokenCount': 900,
                                'thoughtsTokenCount': 100, 'totalTokenCount': 9001})
    assert settlement['actual_cost_usd'] == '0.00975075'
    assert reserve(value)['attempt'] == 2
    assert len(list(tmp_path.glob('*.reservation.json'))) == 2


def test_limits_cannot_be_relaxed_or_reinitialized_and_missing_usage_fails(tmp_path):
    value = ledger(tmp_path, max_attempts=1)
    reserve(value)
    with pytest.raises(BudgetStopped):
        value.settle(1, {})
    with pytest.raises(ValueError, match='frozen artifact differs'):
        ledger(tmp_path, max_attempts=20)
    value.settle(1, {'promptTokenCount': 1, 'candidatesTokenCount': 1, 'totalTokenCount': 2})
    with pytest.raises(BudgetStopped, match='exhausted'):
        reserve(value)
    with pytest.raises(BudgetStopped, match='upper cost'):
        reserve(ledger(tmp_path/'small', spend_cap_usd='0.8'))
