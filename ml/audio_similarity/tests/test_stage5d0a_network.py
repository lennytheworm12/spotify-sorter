import json
import random

import pytest

from audio_similarity.stage5d0a_network import ProviderGovernor, CircuitOpen, WorkerStopped


class Clock:
    def __init__(self):
        self.value = 10000.0
        self.rng = random.Random(41)

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def governor(path, clock):
    return ProviderGovernor(path, now=clock.now, sleep=clock.sleep, rng=clock.rng)


def fail(message):
    def operation():
        raise RuntimeError(message)
    return operation


def test_random_track_pacing_and_restart_deadline(tmp_path):
    clock = Clock()
    g = governor(tmp_path, clock)
    for i in range(6):
        g.start_job(str(i))
        g = governor(tmp_path, clock)
    jobs = g.state["jobs"]
    assert all(30 <= row["next_spacing_seconds"] <= 60 for row in jobs)
    assert len({row["next_spacing_seconds"] for row in jobs}) > 1
    for previous, current in zip(jobs, jobs[1:]):
        assert current["start_unix"] >= previous["start_unix"] + previous["next_spacing_seconds"]


def test_media_retries_are_bounded_and_obey_outer_spacing(tmp_path):
    clock = Clock()
    g = governor(tmp_path, clock)
    g.start_job("track")
    with pytest.raises(RuntimeError, match="503"):
        g.call("track", "MEDIA", "exact", fail("HTTP Error 503"))
    requests = g.state["requests"]
    assert len(requests) == 4
    assert all(b["start_unix"] - a["start_unix"] >= 30 for a, b in zip(requests, requests[1:]))
    assert requests[1]["start_unix"] >= g.state["jobs"][0]["start_unix"] + g.state["jobs"][0]["next_spacing_seconds"]
    assert all(row["backoff_seconds"] <= 31 for row in requests[:-1])


def test_retry_after_and_second_429_open_persistent_circuit(tmp_path):
    clock = Clock()
    g = governor(tmp_path, clock)
    g.start_job("track")
    with pytest.raises(CircuitOpen, match="SECOND_YOUTUBE_HTTP_429"):
        g.call("track", "SEARCH", "same", fail("HTTP Error 429 Retry-After: 1000"))
    requests = g.state["requests"]
    assert len(requests) == 2
    assert requests[1]["start_unix"] - requests[0]["start_unix"] >= 1000
    assert g.state["http_429_count"] == 2
    with pytest.raises(CircuitOpen):
        governor(tmp_path, clock).start_job("later")


def test_first_429_cooldown_survives_graceful_stop_and_restart(tmp_path):
    clock = Clock()
    g = governor(tmp_path, clock)
    def stop_then_fail():
        g.stop_path.write_text("stop")
        raise RuntimeError("HTTP Error 429 Retry-After: 500")
    with pytest.raises(WorkerStopped):
        g.call("one", "MEDIA", "url", stop_then_fail)
    deadline = g.state["cooldown_deadline"]
    g.stop_path.unlink()
    restarted = governor(tmp_path, clock)
    restarted.start_job("two")
    assert clock.now() >= deadline
    assert restarted.state["http_429_count"] == 1


def test_consecutive_unrelated_verification_opens_circuit(tmp_path):
    g = governor(tmp_path, Clock())
    with pytest.raises(RuntimeError, match="not a bot"):
        g.call("first", "SEARCH", "query", fail("Sign in to confirm you're not a bot"))
    assert len(g.state["requests"]) == 1
    with pytest.raises(CircuitOpen, match="VERIFICATION"):
        g.call("second", "SEARCH", "query2", fail("Sign in to confirm you're not a bot"))


def test_unavailable_tracks_do_not_retry_or_open_circuit(tmp_path):
    g = governor(tmp_path, Clock())
    for i in range(5):
        g.start_job(str(i))
        with pytest.raises(RuntimeError):
            g.call(str(i), "MEDIA", "url", fail("Video unavailable"))
        g.finish_job(success=False)
    assert len(g.state["requests"]) == 5
    assert g.state["circuit"] == "CLOSED"


def test_three_exhausted_transient_tracks_open_circuit(tmp_path):
    g = governor(tmp_path, Clock())
    for i in range(3):
        g.start_job(str(i))
        with pytest.raises(RuntimeError):
            g.call(str(i), "SEARCH", "q", fail("socket timeout"))
        if i == 2:
            with pytest.raises(CircuitOpen, match="THREE_CONSECUTIVE"):
                g.finish_job(success=False)
        else:
            g.finish_job(success=False)


def test_success_warnings_recorded_and_stop_does_not_rewrite_state(tmp_path):
    g = governor(tmp_path, Clock())
    g.call("a", "SEARCH", "q", lambda: {"warnings": ["ordinary warning"], "candidates": []})
    prior = g.path.read_bytes()
    g.stop_path.write_text("stop")
    with pytest.raises(WorkerStopped):
        g.start_job("b")
    assert g.path.read_bytes() == prior
    assert json.loads(prior)["requests"][0]["warnings"] == ["ordinary warning"]


def test_restart_does_not_reset_retry_budget(tmp_path):
    clock = Clock()
    g = governor(tmp_path, clock)
    with pytest.raises(RuntimeError):
        g.call("a", "MEDIA", "exact", fail("socket timeout"))
    restarted = governor(tmp_path, clock)
    called = []
    with pytest.raises(RuntimeError, match="persistent retry budget"):
        restarted.call("a", "MEDIA", "exact", lambda: called.append(True))
    assert not called
    assert len(restarted.state["requests"]) == 4


def test_explicit_anti_abuse_stops_without_retry(tmp_path):
    g = governor(tmp_path, Clock())
    with pytest.raises(CircuitOpen, match="EXPLICIT_PROVIDER_ANTI_ABUSE"):
        g.call("a", "SEARCH", "q", fail("Provider anti-abuse response"))
    assert len(g.state["requests"]) == 1
