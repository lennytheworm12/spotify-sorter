"""Isolated real-browser validation for Stage 5C.2A local review playback."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from .cli.stage5b1b_review_server import ReviewHTTPServer, make_review_handler
from .stage5b1b_artifacts import atomic_json
from .stage5c2_review import Stage5C2ReviewStore
from .stage5c2a_retention import (
    EXPERIMENT_ID,
    MEDIA_ROOT,
    REPORT_DIRECTORY,
    SOURCE_REPORT_DIRECTORY,
    _json,
)


def validate_browser_playback(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    source_report = root / SOURCE_REPORT_DIRECTORY
    report_path = root / REPORT_DIRECTORY / "playback_validation.json"
    playback = _json(report_path)
    static = root / "evaluation/static/stage5c2_similarity_review.html"
    store = Stage5C2ReviewStore(
        source_report / "review_queue.json",
        source_report / "human_similarity_review.csv",
        source_report / "selected_sources.json",
        root / MEDIA_ROOT / "index.json",
    )
    handler = make_review_handler(
        store,
        static=static,
        mode="stage5c2_similarity_review",
    )
    server = ReviewHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    audio_responses: list[dict[str, Any]] = []
    console_errors: list[str] = []
    browser_details: dict[str, Any] = {}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--autoplay-policy=no-user-gesture-required"],
            )
            context = browser.new_context(
                locale="en-US",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.on(
                "response",
                lambda response: audio_responses.append(
                    {"endpoint": urlparse(response.url).path, "status": response.status}
                )
                if "/audio/track/" in response.url
                else None,
            )
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.goto(url, wait_until="networkidle", timeout=30_000)
            page.select_option("#filter", "all")
            page.locator("[data-play-track]").first.click()
            page.locator("#local-player:not([hidden])").wait_for(timeout=10_000)
            audio = page.locator("#local-player")

            def wait_for_audio(
                predicate, argument=None, *, timeout_seconds: float = 15.0
            ) -> None:
                deadline = time.monotonic() + timeout_seconds
                while time.monotonic() < deadline:
                    if audio.evaluate(predicate, argument):
                        return
                    page.wait_for_timeout(100)
                raise RuntimeError("timed out waiting for browser audio state")

            wait_for_audio("element => element.readyState >= 1")
            query_src = audio.evaluate("element => element.currentSrc")
            duration = audio.evaluate("element => element.duration")
            page.locator('[data-segment="1"]').click()
            wait_for_audio("element => element.currentTime >= 12")
            clip_time = audio.evaluate("element => element.currentTime")
            mid_target = max(1.0, float(duration) / 2.0)
            audio.evaluate(
                "(element, target) => { element.currentTime = target; return element.play(); }",
                mid_target,
            )
            page.wait_for_timeout(750)
            mid_time = audio.evaluate("element => element.currentTime")
            audio.evaluate(
                "(element, target) => { element.currentTime = target; return element.play(); }",
                mid_target,
            )
            page.wait_for_timeout(500)
            repeated_mid_time = audio.evaluate("element => element.currentTime")
            near_end_target = max(1.0, float(duration) - 3.0)
            audio.evaluate(
                "(element, target) => { element.currentTime = target; return element.play(); }",
                near_end_target,
            )
            page.wait_for_timeout(500)
            near_end_time = audio.evaluate("element => element.currentTime")
            page.locator(".neighbor [data-play-track]").first.click()
            wait_for_audio(
                "(element, prior) => element.currentSrc !== prior",
                query_src,
                timeout_seconds=15.0,
            )
            neighbor_src = audio.evaluate("element => element.currentSrc")
            browser_details = {
                "engine": "chromium",
                "clean_ephemeral_context": True,
                "personal_profile_loaded": False,
                "query_source_endpoint": urlparse(query_src).path,
                "neighbor_source_endpoint": urlparse(neighbor_src).path,
                "query_neighbor_sources_distinct": query_src != neighbor_src,
                "duration_seconds": duration,
                "frozen_clip_seek_time_seconds": clip_time,
                "mid_song_seek_target_seconds": mid_target,
                "mid_song_observed_seconds": mid_time,
                "repeated_mid_song_observed_seconds": repeated_mid_time,
                "near_end_seek_target_seconds": near_end_target,
                "near_end_observed_seconds": near_end_time,
                "youtube_iframe_hidden": page.locator("#youtube-player").is_hidden(),
                "youtube_link_hidden": page.locator("#youtube-link").is_hidden(),
                "audio_http_responses": audio_responses,
                "console_errors": console_errors,
            }
            browser.close()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    passed = (
        browser_details.get("query_neighbor_sources_distinct") is True
        and browser_details.get("youtube_iframe_hidden") is True
        and browser_details.get("youtube_link_hidden") is True
        and browser_details.get("frozen_clip_seek_time_seconds", 0) >= 12
        and browser_details.get("mid_song_observed_seconds", 0) >= mid_target - 1
        and browser_details.get("repeated_mid_song_observed_seconds", 0)
        >= mid_target - 1
        and browser_details.get("near_end_observed_seconds", 0)
        >= near_end_target - 1
        and len(audio_responses) >= 2
        and all(row["status"] in {200, 206} for row in audio_responses)
    )
    playback["browser_validation"] = "PASS" if passed else "FAIL"
    playback["browser_details"] = browser_details
    atomic_json(report_path, playback)
    if not passed:
        raise RuntimeError("real-browser local playback validation failed")
    return playback
