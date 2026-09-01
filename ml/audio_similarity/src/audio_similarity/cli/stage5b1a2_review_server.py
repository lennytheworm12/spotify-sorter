"""Serve the local Stage 5B.1A2 yt-dlp human-review site."""

from __future__ import annotations

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from audio_similarity.stage5b1a2_config import load_ytdlp_config
from audio_similarity.stage5b1a2_experiment import load_ytdlp_results
from audio_similarity.stage5b1a2_review_store import Stage5B1A2ReviewStore
from audio_similarity.stage5b1a_models import Stage5B1AValidationError, load_frozen_manifest


STATIC = Path(__file__).resolve().parents[3] / "evaluation" / "static" / "stage5b1a2_review.html"
MAX_REQUEST_BYTES = 16_384


def make_review_handler(store: Stage5B1A2ReviewStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            pass

        def _headers(self, content_type: str, size: int, *, download: str | None = None) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data: https://i.ytimg.com; connect-src 'self'")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')

        def _bytes(
            self,
            body: bytes,
            content_type: str,
            status: int = 200,
            *,
            download: str | None = None,
        ) -> None:
            self.send_response(status)
            self._headers(content_type, len(body), download=download)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: Any, status: int = 200) -> None:
            self._bytes(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                return self._bytes(STATIC.read_bytes(), "text/html; charset=utf-8")
            if path == "/api/ping":
                return self._json({"ok": True, "mode": "stage5b1a2_ytdlp_human_review"})
            if path == "/api/session":
                try:
                    return self._json(store.session())
                except Stage5B1AValidationError as exc:
                    return self._json({"error": str(exc)}, 409)
            if path == "/api/export":
                return self._bytes(
                    store.review_path.read_bytes(),
                    "text/csv; charset=utf-8",
                    download="stage5b1a2-ytdlp-review.csv",
                )
            return self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/review":
                return self._json({"error": "not found"}, 404)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 1 or size > MAX_REQUEST_BYTES:
                    raise Stage5B1AValidationError("invalid request size")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise Stage5B1AValidationError("request body must be an object")
                return self._json(
                    store.submit(
                        payload.get("stable_track_id", ""),
                        payload.get("label", ""),
                        payload.get("note", ""),
                    )
                )
            except (Stage5B1AValidationError, ValueError, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, 400)

    return Handler


def serve(store: Stage5B1A2ReviewStore, host: str, port: int, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), make_review_handler(store))
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"
    print(f"Stage 5B.1A2 reviewer running at {url}", flush=True)
    print(f"Saving labels to {store.review_path}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(root / "configs" / "stage5b1a2_ytdlp.json"))
    parser.add_argument("--review", help="optional review CSV override (useful for a separate reviewer copy)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    try:
        config = load_ytdlp_config(args.config)
        manifest = load_frozen_manifest(
            config.manifest_path,
            expected_sha256=config.manifest_sha256,
        )
        results = load_ytdlp_results(config.artifacts["discovery_results"], manifest, config)
        store = Stage5B1A2ReviewStore(
            manifest,
            results,
            Path(args.review).resolve() if args.review else config.artifacts["review"],
        )
    except (FileNotFoundError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    serve(store, args.host, args.port, not args.no_browser)


if __name__ == "__main__":
    main()
