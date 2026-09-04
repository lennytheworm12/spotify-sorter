"""Minimal Playwright YouTube result-ID extraction for a zero-result fallback."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol
from urllib.parse import parse_qs, quote_plus, urlsplit

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from .stage5b1a_discovery import YOUTUBE_VIDEO_ID
from .stage5b1a_models import Stage5B1AValidationError


PLAYWRIGHT_NO_VIDEO_RESULTS = "PLAYWRIGHT_NO_VIDEO_RESULTS"
PLAYWRIGHT_NAVIGATION_TIMEOUT = "PLAYWRIGHT_NAVIGATION_TIMEOUT"
PLAYWRIGHT_CONSENT_BLOCKED = "PLAYWRIGHT_CONSENT_BLOCKED"
PLAYWRIGHT_CHALLENGE_BLOCKED = "PLAYWRIGHT_CHALLENGE_BLOCKED"
PLAYWRIGHT_LAUNCH_FAILED = "PLAYWRIGHT_LAUNCH_FAILED"
RESULT_SELECTOR = "ytd-video-renderer a#video-title[href*='/watch?v=']"
NO_RESULT_SELECTOR = "ytd-message-renderer"
CHALLENGE_SELECTOR = (
    "form[action*='sorry'], iframe[src*='recaptcha'], #captcha, [id*='captcha']"
)
AGE_CONFIRMATION_SELECTORS = (
    "text=Confirm your age",
    "text=Sign in to confirm your age",
)
CONSENT_BUTTON_SELECTORS = (
    "button[aria-label='Accept all']",
    "button:has-text('Accept all')",
    "button:has-text('I agree')",
)
_ALLOWED_YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
)


@dataclass(frozen=True)
class BrowserSearchConfig:
    headless: bool = True
    locale: str = "en-US"
    viewport_width: int = 1280
    viewport_height: int = 720
    navigation_timeout_ms: int = 20_000
    result_timeout_ms: int = 10_000
    consent_timeout_ms: int = 2_000
    maximum_anchors_inspected: int = 30
    maximum_page_interactions: int = 1

    def __post_init__(self) -> None:
        if not 1_000 <= self.navigation_timeout_ms <= 60_000:
            raise Stage5B1AValidationError("browser navigation timeout is out of bounds")
        if not 500 <= self.result_timeout_ms <= 30_000:
            raise Stage5B1AValidationError("browser result timeout is out of bounds")
        if not 3 <= self.maximum_anchors_inspected <= 100:
            raise Stage5B1AValidationError("browser anchor inspection bound is invalid")
        if self.maximum_page_interactions != 1:
            raise Stage5B1AValidationError("browser fallback permits one consent interaction")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class BrowserVideoResult:
    rank: int
    video_id: str
    watch_url: str
    displayed_anchor_index: int

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class BrowserSearchOutcome:
    query: str
    search_url: str
    navigation_succeeded: bool
    consent_interactions: int
    inspected_anchor_count: int
    results: tuple[BrowserVideoResult, ...]
    warnings: tuple[str, ...]
    error: dict[str, Any] | None
    elapsed_seconds: float
    browser: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "search_url": self.search_url,
            "navigation_succeeded": self.navigation_succeeded,
            "consent_interactions": self.consent_interactions,
            "inspected_anchor_count": self.inspected_anchor_count,
            "results": [result.to_dict() for result in self.results],
            "video_ids_in_displayed_order": [result.video_id for result in self.results],
            "warnings": list(self.warnings),
            "error": self.error,
            "elapsed_seconds": self.elapsed_seconds,
            "browser": dict(self.browser),
        }


class BrowserSearchAdapter(Protocol):
    def search(self, query: str, *, limit: int = 3) -> BrowserSearchOutcome: ...


def _watch_video_id(href: str) -> str | None:
    if not isinstance(href, str) or not href.strip():
        return None
    parsed = urlsplit(href.strip())
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc and parsed.netloc.casefold() not in _ALLOWED_YOUTUBE_HOSTS:
        return None
    if parsed.path != "/watch":
        return None
    parameters = parse_qs(parsed.query, keep_blank_values=False)
    if "list" in parameters:
        return None
    values = parameters.get("v", [])
    if len(values) != 1 or not YOUTUBE_VIDEO_ID.fullmatch(values[0]):
        return None
    return values[0]


def collect_watch_results(
    hrefs: Iterable[Any],
    *,
    limit: int = 3,
    maximum_inspected: int = 30,
) -> tuple[tuple[BrowserVideoResult, ...], int]:
    """Filter native-order anchors to the first unique ordinary watch videos."""

    if not 1 <= limit <= 3:
        raise Stage5B1AValidationError("browser result limit must be between 1 and 3")
    if maximum_inspected < limit:
        raise Stage5B1AValidationError("browser anchor bound must cover the result limit")
    results: list[BrowserVideoResult] = []
    seen: set[str] = set()
    inspected = 0
    for displayed_index, href in enumerate(hrefs, start=1):
        if inspected == maximum_inspected or len(results) == limit:
            break
        inspected += 1
        video_id = _watch_video_id(href) if isinstance(href, str) else None
        if video_id is None or video_id in seen:
            continue
        seen.add(video_id)
        results.append(
            BrowserVideoResult(
                rank=len(results) + 1,
                video_id=video_id,
                watch_url=f"https://www.youtube.com/watch?v={video_id}",
                displayed_anchor_index=displayed_index,
            )
        )
    return tuple(results), inspected


def _failure(category: str, message: str) -> dict[str, Any]:
    return {"category": category, "message": message, "retryable": False}


def _locator_present(page: Any, selector: str) -> bool:
    try:
        return page.locator(selector).count() > 0
    except PlaywrightError:
        return False


def _challenge_category(page: Any) -> str | None:
    url = str(getattr(page, "url", "")).casefold()
    hard_block = (
        "google.com/sorry" in url
        or "captcha" in url
        or "accounts.google.com" in url
        or _locator_present(page, CHALLENGE_SELECTOR)
    )
    age_gate_without_results = not _locator_present(
        page, RESULT_SELECTOR
    ) and any(
        _locator_present(page, selector) for selector in AGE_CONFIRMATION_SELECTORS
    )
    if hard_block or age_gate_without_results:
        return PLAYWRIGHT_CHALLENGE_BLOCKED
    return None


def _is_consent_page(page: Any) -> bool:
    url = str(getattr(page, "url", "")).casefold()
    return "consent.youtube.com" in url or "consent.google.com" in url


class PlaywrightYouTubeSearchAdapter:
    """Launch one clean context, collect result IDs, and close it deterministically."""

    def __init__(
        self,
        config: BrowserSearchConfig | None = None,
        *,
        playwright_factory: Callable[[], Any] = sync_playwright,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.config = config or BrowserSearchConfig()
        self._playwright_factory = playwright_factory
        self._clock = clock

    def _accept_consent(self, page: Any, warnings: list[str]) -> int:
        for selector in CONSENT_BUTTON_SELECTORS:
            button = page.locator(selector).first
            try:
                if button.is_visible(timeout=250):
                    button.click(timeout=self.config.consent_timeout_ms)
                    warnings.append("ephemeral consent prompt accepted")
                    return 1
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        return 0

    def _page_search(
        self,
        page: Any,
        search_url: str,
        *,
        limit: int,
        warnings: list[str],
    ) -> tuple[bool, int, tuple[BrowserVideoResult, ...], int, dict[str, Any] | None]:
        page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=self.config.navigation_timeout_ms,
        )
        navigation_succeeded = True
        interactions = self._accept_consent(page, warnings)
        if _is_consent_page(page):
            return (
                navigation_succeeded,
                interactions,
                (),
                0,
                _failure(
                    PLAYWRIGHT_CONSENT_BLOCKED,
                    "YouTube consent page blocked access to search results",
                ),
            )
        challenge = _challenge_category(page)
        if challenge:
            return (
                navigation_succeeded,
                interactions,
                (),
                0,
                _failure(challenge, "YouTube challenge or sign-in wall blocked results"),
            )
        try:
            page.wait_for_selector(
                RESULT_SELECTOR,
                state="attached",
                timeout=self.config.result_timeout_ms,
            )
        except PlaywrightTimeoutError:
            challenge = _challenge_category(page)
            if challenge:
                category = challenge
                message = "YouTube challenge or sign-in wall blocked results"
            elif _is_consent_page(page):
                category = PLAYWRIGHT_CONSENT_BLOCKED
                message = "YouTube consent page blocked access to search results"
            elif _locator_present(page, NO_RESULT_SELECTOR):
                category = PLAYWRIGHT_NO_VIDEO_RESULTS
                message = "YouTube rendered a no-results state"
            else:
                category = PLAYWRIGHT_NAVIGATION_TIMEOUT
                message = "YouTube video result structure did not appear before timeout"
            return (
                navigation_succeeded,
                interactions,
                (),
                0,
                _failure(category, message),
            )
        hrefs = page.locator(RESULT_SELECTOR).evaluate_all(
            "elements => elements.map(element => element.getAttribute('href'))"
        )
        results, inspected = collect_watch_results(
            hrefs,
            limit=limit,
            maximum_inspected=self.config.maximum_anchors_inspected,
        )
        error = None
        if not results:
            error = _failure(
                PLAYWRIGHT_NO_VIDEO_RESULTS,
                "YouTube result page contained no usable ordinary watch-video links",
            )
        return navigation_succeeded, interactions, results, inspected, error

    def search(self, query: str, *, limit: int = 3) -> BrowserSearchOutcome:
        query = query.strip()
        if not query:
            raise Stage5B1AValidationError("browser query must be non-empty")
        if not 1 <= limit <= 3:
            raise Stage5B1AValidationError("browser result limit must be between 1 and 3")
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        started = self._clock()
        warnings: list[str] = []
        navigation_succeeded = False
        interactions = 0
        inspected = 0
        results: tuple[BrowserVideoResult, ...] = ()
        error: dict[str, Any] | None = None
        browser_details: dict[str, Any] = {
            "engine": "chromium",
            "headless": self.config.headless,
            "locale": self.config.locale,
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            "persistent_context": False,
            "personal_profile_loaded": False,
            "cookies_loaded": False,
        }
        browser = None
        context = None
        try:
            with self._playwright_factory() as playwright:
                browser = playwright.chromium.launch(headless=self.config.headless)
                browser_details["version"] = browser.version
                try:
                    context = browser.new_context(
                        locale=self.config.locale,
                        viewport={
                            "width": self.config.viewport_width,
                            "height": self.config.viewport_height,
                        },
                    )
                    page = context.new_page()
                    (
                        navigation_succeeded,
                        interactions,
                        results,
                        inspected,
                        error,
                    ) = self._page_search(
                        page,
                        search_url,
                        limit=limit,
                        warnings=warnings,
                    )
                finally:
                    if context is not None:
                        try:
                            context.close()
                        except PlaywrightError as exc:
                            warnings.append(f"browser context cleanup warning: {exc}")
                    if browser is not None:
                        try:
                            browser.close()
                        except PlaywrightError as exc:
                            warnings.append(f"browser cleanup warning: {exc}")
        except PlaywrightTimeoutError as exc:
            error = _failure(PLAYWRIGHT_NAVIGATION_TIMEOUT, str(exc))
        except (PlaywrightError, OSError) as exc:
            error = _failure(PLAYWRIGHT_LAUNCH_FAILED, str(exc))
        return BrowserSearchOutcome(
            query=query,
            search_url=search_url,
            navigation_succeeded=navigation_succeeded,
            consent_interactions=interactions,
            inspected_anchor_count=inspected,
            results=results,
            warnings=tuple(warnings),
            error=error,
            elapsed_seconds=self._clock() - started,
            browser=browser_details,
        )
