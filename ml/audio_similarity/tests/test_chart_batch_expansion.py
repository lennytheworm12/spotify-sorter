import json

import pytest

from audio_similarity.chart_batch_expansion import expand
from audio_similarity.chart_download_batches import validate_batch, REPORT
from tests.test_chart_download_batches import prepare, snapshot


def test_append_preserves_batches_deduplicates_and_is_idempotent(tmp_path):
    prepare(tmp_path, count=6, size=3)
    directory = tmp_path / REPORT
    before = {p.name:p.read_bytes() for p in directory.glob('*.json')}
    source = tmp_path/'reports/stage5d_chart_catalog_v1/matching_expanded.json'
    source.write_text(json.dumps(snapshot(510)))
    result = expand(tmp_path,source)
    assert result == {'new_tracks':504,'first_batch':3,'last_batch':4,'downloads_started':False}
    assert {p.name:p.read_bytes() for p in directory.glob('*.json')} == before
    a,_ = validate_batch(tmp_path,3)
    b,_ = validate_batch(tmp_path,4)
    assert len(a['tracks']) == 500 and len(b['tracks']) == 4
    assert len({r['spotify_track_id'] for r in a['tracks']+b['tracks']}) == 504
    assert not a['automatic_next_batch']
    assert expand(tmp_path,source)['new_tracks'] == 0
    with pytest.raises(ValueError,match='does not exist'):
        validate_batch(tmp_path,5)


def test_changed_historical_manifest_is_rejected(tmp_path):
    source = prepare(tmp_path)
    path = tmp_path/REPORT/'batch_0001.json'
    path.write_text('{}')
    with pytest.raises(ValueError,match='artifact changed'):
        expand(tmp_path,source)


def test_completion_stops_on_provider_error_without_freezing(tmp_path, monkeypatch):
    from audio_similarity import chart_catalog_complete as module
    charts = tmp_path/'reports/stage5d_chart_catalog_v1/chart_appearances.json'
    charts.parent.mkdir(parents=True)
    charts.write_text(json.dumps({'entries':[]}))
    def failed(*args):
        raise RuntimeError('Spotify request failed: HTTP 429')
    monkeypatch.setattr(module,'execute',failed)
    monkeypatch.setattr(module,'expand',lambda *args:pytest.fail('must not freeze after error'))
    with pytest.raises(RuntimeError,match='429'):
        module.complete(tmp_path)


def test_completion_freezes_only_when_pending_is_zero(tmp_path, monkeypatch):
    from audio_similarity import chart_catalog_complete as module
    charts = tmp_path/'reports/stage5d_chart_catalog_v1/chart_appearances.json'
    charts.parent.mkdir(parents=True)
    charts.write_text(json.dumps({'entries':[{'title':'song','artist':'artist'}]}))
    outcomes = iter([1,0])
    calls = []
    def execute(args, runtime):
        calls.append(args.max_requests)
        path = runtime/'fixture.json'
        path.write_text(json.dumps({'metrics':{'matching_outcomes':{'PENDING':next(outcomes)},
                                              'recordings_matched':1,'coverage_gaps':['gap']}}))
        return path
    monkeypatch.setattr(module,'execute',execute)
    monkeypatch.setattr(module,'expand',lambda *args:{'new_tracks':1,'downloads_started':False})
    result = module.complete(tmp_path)
    assert calls == [500,500]
    assert result['metadata_queue_exhausted'] and not result['downloads_started']
