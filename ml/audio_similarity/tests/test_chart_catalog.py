import pytest

from audio_similarity.chart_catalog import (
    coverage, deduplicate, match_song, resolve_songs, song_candidates, sources,
    metadata_lock,
)


def entry(title="Song", artist="Artist", territory="US"):
    return dict(title=title, artist=artist, territory=territory, chart_year=2020)


def track(identity="a", title="Song", artist="Artist", duration=200000):
    return dict(id=identity, name=title, artists=[{"name": artist}], duration_ms=duration)


def test_sources_are_deterministic_and_do_not_fabricate_2026_annual():
    plan = sources()
    assert plan == sources()
    assert len(plan) == len({s["url"] for s in plan}) == 60
    assert {s["chart_year"] for s in plan} == set(range(2006, 2026))


def test_metadata_worker_is_serial(tmp_path):
    with metadata_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with metadata_lock(tmp_path):
                pass
    with metadata_lock(tmp_path):
        pass


def test_literal_dedup_preserves_appearances_and_versions():
    songs = song_candidates([entry(), entry(territory="AU"), entry(title="Song - Live")])
    assert len(songs) == 2
    assert sorted(len(s["appearances"]) for s in songs) == [1, 2]


def test_exact_match_does_not_accept_cover_or_remix():
    song = entry()
    assert match_song(song, [track(artist="Cover Band")])["spotify"] is None
    assert match_song(song, [track(title="Song - Remix")])["spotify"] is None
    assert match_song(song, [track()])["status"] == "MATCHED_METADATA"


def test_artist_substring_not_sufficient():
    assert match_song(entry(artist="A"), [track(artist="AB")])["spotify"] is None


def test_duration_ambiguity_is_not_silently_selected():
    result = match_song(entry(), [track(), track("b", duration=210000)])
    assert result["status"] == "AMBIGUOUS_RECORDINGS"


def test_equivalent_editions_deterministic():
    a, b = track(), track("b")
    assert match_song(entry(), [a, b]) == match_song(entry(), [b, a])


def test_resume_and_request_bound(tmp_path):
    songs = song_candidates([entry(), entry(title="Second")])
    calls = []
    def search(query, offset):
        calls.append(query)
        return {"tracks": {"items": []}}
    first = resolve_songs(songs, search, tmp_path, 1)
    assert len(calls) == 1
    assert sum(m["status"] == "PENDING" for m in first) == 1
    resolve_songs(songs, search, tmp_path, 0)
    assert len(calls) == 1
    resolve_songs(songs, search, tmp_path, 1)
    assert len(calls) == 2


def test_provider_error_not_cached_as_empty(tmp_path):
    def failing(query, offset):
        raise RuntimeError("429")
    with pytest.raises(RuntimeError):
        resolve_songs(song_candidates([entry()]), failing, tmp_path, 1)
    assert not list(tmp_path.iterdir())


def test_existing_metadata_hit_prevents_search(tmp_path):
    def forbidden(query, offset):
        raise AssertionError("network not needed")
    matches = resolve_songs(song_candidates([entry()]), forbidden, tmp_path, 1, [track()])
    assert matches[0]["metadata_source"] == "EXISTING_SPOTIFY_METADATA"
    assert matches[0]["spotify"]["id"] == "a"


def test_recording_dedup_retains_cross_chart_evidence():
    songs = song_candidates([entry(), entry(artist="ARTIST", territory="JP")])
    matches = [{"song": song, **match_song(song, [track()])} for song in songs]
    recordings = deduplicate(matches)
    assert len(recordings) == 1
    assert len(recordings[0]["appearances"]) == 2
    assert recordings[0]["acquisition_eligible"] is False
    metrics = coverage({"entries": [entry()], "sources": []}, matches, recordings)
    assert metrics["media_downloads"] == 0
    assert metrics["acquisition_enabled"] is False
