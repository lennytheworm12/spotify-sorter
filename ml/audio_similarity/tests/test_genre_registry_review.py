from pathlib import Path
import socket
import pytest
from audio_similarity.genre_registry_review import build, load_comparison, REPORT, SOURCE
from audio_similarity.stage5e3_artifacts import read, verify_hashes
ROOT=Path(__file__).resolve().parents[1]

def test_exact_frozen100_offline_replay(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('No network during mapping')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    rows=build(ROOT,tmp_path/'replay')
    verify_hashes(tmp_path/'replay',read(ROOT/REPORT/'artifact_manifest.json')['files'])
    assert len(rows)==100
    for r in rows:
        assert r['new']['raw_genre_fields']==r['old']['raw_genre_labels']
        assert r['new']['score_adjustment'] is None
    d=load_comparison(ROOT)
    assert d['summary']['new_concepts']==138 and d['summary']['new_neighborhoods']==29

def test_protected_output():
    with pytest.raises(ValueError):build(ROOT,ROOT/SOURCE)
