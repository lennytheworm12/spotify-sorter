"""Frozen100 offline mapping contracts; no audio inference or provider transport."""
from pathlib import Path
import socket
import pytest
from audio_similarity.genre_neighborhood_frozen100 import build, REPORT, SOURCE
from audio_similarity.stage5e3_artifacts import read, verify_hashes
from audio_similarity.stage5b1a_models import file_sha256

ROOT = Path(__file__).resolve().parents[1]


def test_frozen100_offline_replay_and_exact_labels(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Network forbidden during mapping')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    packet = build(ROOT, tmp_path / 'replay')
    original = ROOT / REPORT
    expected = read(original / 'artifact_manifest.json')['files']
    verify_hashes(tmp_path / 'replay', expected)
    assert len(packet['tracks']) == 100
    for t in packet['tracks']:
        raw = read(ROOT / SOURCE / 'profiles' / (t['pilot_id'] + '.json'))
        assert raw['spotify_track_id'] == t['spotify_track_id']
        assert all(raw['profile'][k] == v for k,v in t['mapping']['raw_genre_labels'].items())
        assert file_sha256(ROOT / t['audio_path']) == t['audio_sha256']
    assert packet['mapper_sha256'] == file_sha256(ROOT / 'reports/genre_neighborhood_map/v1/pilot16/genre-neighborhood-map-v1.json')


def test_protected_output_rejected():
    with pytest.raises(ValueError, match='protected'):
        build(ROOT, ROOT / SOURCE)
