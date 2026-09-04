from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from audio_similarity.stage5b1a2_ytdlp import (
    YtDlpBackendResponse,
    YtDlpSearchError,
)
from audio_similarity.stage5b1a_models import SpotifyTrack, file_sha256
from audio_similarity.stage5b3_minimal_selector import AUTO_SELECT, select_native_rank
from audio_similarity.stage5b4a_query_contract_repair import (
    natural_title_first3_artists_query,
)
from audio_similarity.stage5b4b_browser import (
    BrowserSearchConfig,
    BrowserSearchOutcome,
    BrowserVideoResult,
    PLAYWRIGHT_CHALLENGE_BLOCKED,
    PLAYWRIGHT_CONSENT_BLOCKED,
    PLAYWRIGHT_NAVIGATION_TIMEOUT,
    PlaywrightYouTubeSearchAdapter,
    collect_watch_results,
)
from audio_similarity.stage5b4b_experiment import (
    fallback_config_document,
    verify_history_guards,
)
from audio_similarity.stage5b4b_playwright_fallback import (
    PLAYWRIGHT_FALLBACK,
    YTDLP_SEARCH,
    ExactUrlHydrationOutcome,
    YtDlpExactUrlHydrator,
    discover_with_zero_result_fallback,
    exact_url_provider_config,
)


QUERY = "Girl, Interrupted 2xxx Miso"
VIDEO_IDS = ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc", "ddddddddddd")


def _track() -> SpotifyTrack:
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": "stage5b4_representative_v3_010",
            "spotify_track_id": "1cBNzkPsAdI7XJaKIsjKUk",
            "title": "Girl, Interrupted",
            "artists": ["2xxx", "Miso"],
            "duration_ms": 180_972,
        }
    )


def _browser_result(rank: int, video_id: str) -> BrowserVideoResult:
    return BrowserVideoResult(
        rank=rank,
        video_id=video_id,
        watch_url=f"https://www.youtube.com/watch?v={video_id}",
        displayed_anchor_index=rank,
    )


def _browser_outcome(results: tuple[BrowserVideoResult, ...]) -> BrowserSearchOutcome:
    return BrowserSearchOutcome(
        query=QUERY,
        search_url="https://www.youtube.com/results?search_query=Girl%2C+Interrupted+2xxx+Miso",
        navigation_succeeded=True,
        consent_interactions=0,
        inspected_anchor_count=len(results),
        results=results,
        warnings=(),
        error=None,
        elapsed_seconds=0.5,
        browser={"persistent_context": False, "cookies_loaded": False},
    )


class _Primary:
    def __init__(self, candidates: list[dict]) -> None:
        self.candidates = candidates
        self.calls: list[tuple[str, int]] = []

    def discover_query(self, track, query, *, limit):
        self.calls.append((query, limit))
        return SimpleNamespace(
            to_dict=lambda: {
                "track": track.to_dict(),
                "query": query,
                "request": {
                    "search_expression": f"ytsearch3:{query}",
                    "download": False,
                },
                "provider": {"name": "yt_dlp", "version": "test"},
                "candidates": self.candidates,
                "candidate_video_ids": [
                    candidate["youtube_video_id"] for candidate in self.candidates
                ],
                "warnings": [],
                "error": None,
            }
        )


class _Browser:
    def __init__(self, outcome: BrowserSearchOutcome) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, int]] = []

    def search(self, query, *, limit=3):
        self.calls.append((query, limit))
        return self.outcome


class _Hydrator:
    def __init__(self, candidates: tuple[dict, ...]) -> None:
        self.candidates = candidates
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def hydrate(self, track, query, results):
        self.calls.append((query, tuple(result.video_id for result in results)))
        return ExactUrlHydrationOutcome(
            query=query,
            requested_urls=tuple(result.watch_url for result in results),
            results=tuple(
                {
                    "status": "HYDRATED",
                    "video_id": result.video_id,
                    "browser_rank": result.rank,
                }
                for result in results
            ),
            candidates=self.candidates,
            elapsed_seconds=0.25,
        )


def test_playwright_is_not_called_when_primary_returns_candidates() -> None:
    candidate = {"rank": 1, "youtube_video_id": VIDEO_IDS[0]}
    primary = _Primary([candidate])
    browser = _Browser(_browser_outcome((_browser_result(1, VIDEO_IDS[1]),)))
    hydrator = _Hydrator(())
    result = discover_with_zero_result_fallback(
        _track(), QUERY, primary, browser, hydrator
    )
    assert result["provider_path"] == YTDLP_SEARCH
    assert result["candidates"] == [candidate]
    assert browser.calls == []
    assert hydrator.calls == []


def test_zero_primary_calls_playwright_with_the_exact_original_query() -> None:
    results = (_browser_result(1, VIDEO_IDS[0]),)
    primary = _Primary([])
    browser = _Browser(_browser_outcome(results))
    hydrated = ({"rank": 1, "youtube_video_id": VIDEO_IDS[0]},)
    hydrator = _Hydrator(hydrated)
    result = discover_with_zero_result_fallback(
        _track(), QUERY, primary, browser, hydrator
    )
    assert browser.calls == [(QUERY, 3)]
    assert hydrator.calls == [(QUERY, (VIDEO_IDS[0],))]
    assert result["provider_path"] == PLAYWRIGHT_FALLBACK
    assert result["browser"]["reason"] == "PRIMARY_ZERO_RESULTS"
    assert result["candidates"] == list(hydrated)


def test_structured_browser_failure_is_propagated_without_hydration() -> None:
    browser_outcome = BrowserSearchOutcome(
        query=QUERY,
        search_url="https://www.youtube.com/results",
        navigation_succeeded=True,
        consent_interactions=0,
        inspected_anchor_count=0,
        results=(),
        warnings=(),
        error={
            "category": PLAYWRIGHT_CHALLENGE_BLOCKED,
            "message": "age confirmation blocked results",
            "retryable": False,
        },
        elapsed_seconds=0.5,
        browser={"persistent_context": False},
    )
    browser = _Browser(browser_outcome)
    hydrator = _Hydrator(())
    result = discover_with_zero_result_fallback(
        _track(), QUERY, _Primary([]), browser, hydrator
    )
    assert result["error"]["category"] == PLAYWRIGHT_CHALLENGE_BLOCKED
    assert result["hydration"]["triggered"] is False
    assert hydrator.calls == []


def test_watch_filter_preserves_order_deduplicates_and_ignores_non_video_links() -> None:
    hrefs = [
        "/shorts/aaaaaaaaaaa",
        f"/watch?v={VIDEO_IDS[1]}",
        f"https://www.youtube.com/watch?v={VIDEO_IDS[1]}&pp=abc",
        f"/watch?v={VIDEO_IDS[2]}&list=RD{VIDEO_IDS[2]}",
        "/playlist?list=PL123",
        f"https://www.youtube.com/watch?v={VIDEO_IDS[0]}",
        "https://example.com/watch?v=ddddddddddd",
    ]
    results, inspected = collect_watch_results(hrefs)
    assert [result.video_id for result in results] == [VIDEO_IDS[1], VIDEO_IDS[0]]
    assert [result.rank for result in results] == [1, 2]
    assert inspected == len(hrefs)


def test_watch_filter_stops_after_three_unique_results() -> None:
    hrefs = [f"/watch?v={video_id}" for video_id in VIDEO_IDS]
    results, inspected = collect_watch_results(hrefs)
    assert [result.video_id for result in results] == list(VIDEO_IDS[:3])
    assert inspected == 3


class _Backend:
    version = "test"

    def __init__(self, failed: set[str] | None = None) -> None:
        self.failed = failed or set()
        self.urls: list[str] = []

    def search(self, expression: str) -> YtDlpBackendResponse:
        self.urls.append(expression)
        video_id = expression.rsplit("=", 1)[1]
        if video_id in self.failed:
            raise YtDlpSearchError(
                "YTDLP_EXTRACTION_ERROR",
                "exact URL failed",
                attempts=1,
                retryable=False,
                warnings=("hydration warning",),
            )
        return YtDlpBackendResponse(
            info={
                "id": video_id,
                "webpage_url": expression,
                "extractor_key": "Youtube",
                "title": f"Title {video_id}",
                "uploader": "Uploader",
                "channel": "Channel",
                "duration": 181,
                "view_count": 123,
                "description": "Description",
            },
            warnings=(),
            version="test",
        )


def test_exact_urls_are_hydrated_in_browser_order_without_searches() -> None:
    backend = _Backend()
    hydrator = YtDlpExactUrlHydrator(backend)
    browser_results = tuple(
        _browser_result(rank, video_id)
        for rank, video_id in enumerate(VIDEO_IDS[:3], start=1)
    )
    outcome = hydrator.hydrate(_track(), QUERY, browser_results)
    assert backend.urls == [result.watch_url for result in browser_results]
    assert [candidate["youtube_video_id"] for candidate in outcome.candidates] == list(
        VIDEO_IDS[:3]
    )
    assert all(not url.startswith("ytsearch") for url in backend.urls)
    assert all(
        candidate["discovery_source"] == PLAYWRIGHT_FALLBACK
        for candidate in outcome.candidates
    )


def test_hydration_failure_preserves_survivor_order_and_browser_rank() -> None:
    backend = _Backend({VIDEO_IDS[1]})
    hydrator = YtDlpExactUrlHydrator(backend)
    browser_results = tuple(
        _browser_result(rank, video_id)
        for rank, video_id in enumerate(VIDEO_IDS[:3], start=1)
    )
    outcome = hydrator.hydrate(_track(), QUERY, browser_results)
    assert [candidate["youtube_video_id"] for candidate in outcome.candidates] == [
        VIDEO_IDS[0],
        VIDEO_IDS[2],
    ]
    assert [candidate["rank"] for candidate in outcome.candidates] == [1, 2]
    assert [candidate["browser_rank"] for candidate in outcome.candidates] == [1, 3]
    assert [record["status"] for record in outcome.results] == [
        "HYDRATED",
        "FAILED",
        "HYDRATED",
    ]


def test_hydrated_candidate_shape_is_accepted_without_provider_penalty() -> None:
    outcome = YtDlpExactUrlHydrator(_Backend()).hydrate(
        _track(), QUERY, (_browser_result(1, VIDEO_IDS[0]),)
    )
    decision = select_native_rank(_track().to_dict(), list(outcome.candidates))
    assert decision["decision"] == AUTO_SELECT
    assert decision["selected_rank"] == 1
    assert decision["selected_video_id"] == VIDEO_IDS[0]


def test_exact_url_provider_is_metadata_only_and_single_attempt() -> None:
    provider = exact_url_provider_config()
    options = provider.metadata_only_options()
    assert options["skip_download"] is True
    assert options["simulate"] is True
    assert provider.search_prefix == ""
    assert provider.max_attempts == 1


class _Locator:
    def __init__(self, page, selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def count(self):
        if "captcha" in self.selector:
            return int(self.page.challenge)
        if "Confirm your age" in self.selector:
            return int(self.page.state == "age_gate")
        if self.selector == "ytd-message-renderer":
            return int(self.page.no_results)
        return len(self.page.hrefs) if "video-title" in self.selector else 0

    def is_visible(self, timeout=None):
        return False

    def click(self, timeout=None):
        raise AssertionError("no consent button should be clicked in this fake")

    def evaluate_all(self, _expression):
        return list(self.page.hrefs)


class _Page:
    def __init__(
        self,
        hrefs: tuple[str, ...] = (),
        *,
        timeout: bool = False,
        state: str = "normal",
    ) -> None:
        self.hrefs = hrefs
        self.timeout = timeout
        self.challenge = state == "challenge"
        self.no_results = state == "no_results"
        self.state = state
        self.url = "about:blank"
        self.goto_call = None

    def goto(self, url, **kwargs):
        self.goto_call = (url, kwargs)
        if self.state == "consent":
            self.url = "https://consent.youtube.com/"
        elif self.state == "challenge":
            self.url = "https://www.google.com/sorry/index"
        else:
            self.url = url

    def wait_for_selector(self, *_args, **_kwargs):
        if self.timeout:
            raise PlaywrightTimeoutError("result wait timed out")

    def locator(self, selector):
        return _Locator(self, selector)


class _Context:
    def __init__(self, page: _Page) -> None:
        self.page = page
        self.closed = False

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class _BrowserRuntime:
    version = "test-chromium"

    def __init__(self, page: _Page) -> None:
        self.context = _Context(page)
        self.context_options = None
        self.closed = False

    def new_context(self, **kwargs):
        self.context_options = kwargs
        return self.context

    def close(self):
        self.closed = True


class _PlaywrightManager:
    def __init__(self, page: _Page) -> None:
        self.browser = _BrowserRuntime(page)
        self.launch_options = None

    def __enter__(self):
        manager = self

        class Chromium:
            def launch(self, **kwargs):
                manager.launch_options = kwargs
                return manager.browser

        return SimpleNamespace(chromium=Chromium())

    def __exit__(self, *_args):
        return False


def test_browser_uses_clean_ephemeral_context_and_closes_everything() -> None:
    page = _Page((f"/watch?v={VIDEO_IDS[0]}",))
    manager = _PlaywrightManager(page)
    adapter = PlaywrightYouTubeSearchAdapter(
        playwright_factory=lambda: manager,
    )
    outcome = adapter.search(QUERY)
    assert [result.video_id for result in outcome.results] == [VIDEO_IDS[0]]
    assert manager.launch_options == {"headless": True}
    assert manager.browser.context_options == {
        "locale": "en-US",
        "viewport": {"width": 1280, "height": 720},
    }
    assert manager.browser.context.closed is True
    assert manager.browser.closed is True
    assert outcome.browser["persistent_context"] is False
    assert outcome.browser["personal_profile_loaded"] is False
    assert outcome.browser["cookies_loaded"] is False


def test_browser_timeout_is_structured_and_cleanup_still_occurs() -> None:
    manager = _PlaywrightManager(_Page(timeout=True))
    adapter = PlaywrightYouTubeSearchAdapter(playwright_factory=lambda: manager)
    outcome = adapter.search(QUERY)
    assert outcome.error["category"] == PLAYWRIGHT_NAVIGATION_TIMEOUT
    assert outcome.results == ()
    assert manager.browser.context.closed is True
    assert manager.browser.closed is True


@pytest.mark.parametrize(
    ("state", "category"),
    [
        ("consent", PLAYWRIGHT_CONSENT_BLOCKED),
        ("challenge", PLAYWRIGHT_CHALLENGE_BLOCKED),
        ("age_gate", PLAYWRIGHT_CHALLENGE_BLOCKED),
    ],
)
def test_consent_and_challenge_states_return_structured_failure(
    state: str, category: str
) -> None:
    manager = _PlaywrightManager(_Page(state=state))
    adapter = PlaywrightYouTubeSearchAdapter(playwright_factory=lambda: manager)
    outcome = adapter.search(QUERY)
    assert outcome.error["category"] == category
    assert outcome.results == ()


def test_frozen_query_contract_is_reused_without_new_terms() -> None:
    assert natural_title_first3_artists_query(_track()) == QUERY
    assert "official" not in QUERY.casefold()
    assert '"' not in QUERY


def test_history_guards_pin_stage5b4a_v3_and_unchanged_selector() -> None:
    project_root = Path(__file__).resolve().parents[1]
    history = verify_history_guards(project_root)
    config = fallback_config_document(project_root)
    assert history["production_activation"] is False
    assert config["architecture"]["fallback_trigger"] == (
        "ZERO_USABLE_PRIMARY_CANDIDATES_ONLY"
    )
    assert config["scope_guards"]["selector_tuning"] is False
    selector = config["frozen_inputs"]["stage5b3_selector"]
    assert selector["sha256"] == file_sha256(project_root / selector["path"])
    stage5b4a = json.loads(
        (
            project_root
            / "reports/stage5b4a_query_contract_repair/repaired_discovery.json"
        ).read_text()
    )
    assert stage5b4a["tracks"][0]["exact_generated_query"] == QUERY


def test_committed_failed_live_supplement_is_complete_and_hash_locked() -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "reports/stage5b4b_playwright_fallback"
    required = {
        "fallback_config.json",
        "primary_discovery.json",
        "playwright_discovery.json",
        "hydrated_candidates.json",
        "human_review.csv",
        "fallback_metrics.json",
        "fallback_report.md",
        "artifact_manifest.json",
    }
    assert required == {path.name for path in output_dir.iterdir() if path.is_file()}
    artifact_manifest = json.loads((output_dir / "artifact_manifest.json").read_text())
    primary = json.loads((output_dir / "primary_discovery.json").read_text())
    browser = json.loads((output_dir / "playwright_discovery.json").read_text())
    hydration = json.loads((output_dir / "hydrated_candidates.json").read_text())
    metrics = json.loads((output_dir / "fallback_metrics.json").read_text())
    assert artifact_manifest["verdict"] == "PLAYWRIGHT_FALLBACK_FAILED"
    assert primary["query"] == QUERY
    assert primary["result_count"] == 0
    assert primary["error"] is None and primary["warnings"] == []
    assert browser["triggered"] is True
    assert browser["outcome"]["query"] == QUERY
    assert browser["outcome"]["error"]["category"] == PLAYWRIGHT_CHALLENGE_BLOCKED
    assert browser["outcome"]["results"] == []
    assert browser["live_browser_navigation_count"] == 3
    assert hydration["triggered"] is False
    assert hydration["candidates"] == []
    assert hydration["error"]["category"] == PLAYWRIGHT_CHALLENGE_BLOCKED
    assert metrics["human_review"]["candidate_unavailable"] is True
    assert metrics["selector_evaluation_after_human_review"] is None
    assert metrics["scope_guards"]["audio_downloads"] == 0
    for name, identity in artifact_manifest["artifacts"].items():
        assert identity["sha256"] == file_sha256(output_dir / name)
    for group in ("stage5b4a", "representative_v3"):
        for identity in artifact_manifest["frozen_inputs"][group].values():
            assert identity["sha256"] == file_sha256(project_root / identity["path"])
    selector = artifact_manifest["frozen_inputs"]["stage5b3_selector"]
    assert selector["sha256"] == file_sha256(project_root / selector["path"])
