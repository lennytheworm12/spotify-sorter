"""Serve the local Stage 5B.1B per-candidate human-review workbench."""
from __future__ import annotations

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b1b_config import load_stage5b1b_config
from audio_similarity.stage5b1b_manifest import load_heldout_manifest
from audio_similarity.stage5b1b_review_store import Stage5B1BReviewStore
from audio_similarity.stage5b1b_sol_comparison import load_audit_queue


STATIC = Path(__file__).resolve().parents[3] / "evaluation" / "static" / "stage5b1b_review.html"
MAX_REQUEST_BYTES = 16_384


class ReviewStore(Protocol):
    """Minimal persistence boundary shared by the two local review modes."""

    review_path: Path

    def session(self) -> dict[str, Any]: ...

    def submit(
        self,
        stable_track_id: str,
        video_id: str,
        label: str,
        candidate_note: str = "",
        track_note: str = "",
    ) -> dict[str, Any]: ...


def make_review_handler(
    store: ReviewStore,
    *,
    static: Path = STATIC,
    mode: str = "stage5b1b_heldout_candidate_review",
    export_filename: str = "stage5b1b-heldout-review.csv",
    frame_sources: tuple[str, ...] = (),
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            return None

        def _headers(
            self, content_type: str, size: int, *, download: str | None = None
        ) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            frame_policy = (
                f" frame-src {' '.join(frame_sources)};" if frame_sources else ""
            )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
                f"img-src 'self' data:;{frame_policy}",
            )
            if download:
                self.send_header(
                    "Content-Disposition", f'attachment; filename="{download}"'
                )

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

        def _json(self, value: Any, status: int = 200) -> None:
            self._bytes(
                json.dumps(value, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                return self._bytes(static.read_bytes(), "text/html; charset=utf-8")
            if path == "/api/ping":
                return self._json({"ok": True, "mode": mode})
            if path == "/api/session":
                try:
                    return self._json(store.session())
                except Stage5B1AValidationError as exc:
                    return self._json({"error": str(exc)}, 409)
            if path == "/api/export":
                return self._bytes(
                    store.review_path.read_bytes(),
                    "text/csv; charset=utf-8",
                    download=export_filename,
                )
            return self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/review":
                return self._json({"error": "not found"}, 404)
            try:
                content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
                if content_type != "application/json":
                    raise Stage5B1AValidationError("review request must use application/json")
                origin = self.headers.get("Origin")
                host = self.headers.get("Host")
                if origin and origin not in {f"http://{host}", f"https://{host}"}:
                    raise Stage5B1AValidationError("cross-origin review request rejected")
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= MAX_REQUEST_BYTES:
                    raise Stage5B1AValidationError("invalid request size")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise Stage5B1AValidationError("request body must be an object")
                return self._json(
                    store.submit(
                        payload.get("stable_track_id", ""),
                        payload.get("video_id", ""),
                        payload.get("label", ""),
                        payload.get("candidate_note", ""),
                        payload.get("track_note", ""),
                    )
                )
            except (Stage5B1AValidationError, ValueError, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, 400)

    return Handler


def serve(
    store: ReviewStore,
    host: str,
    port: int,
    *,
    open_browser: bool = True,
    static: Path = STATIC,
    mode: str = "stage5b1b_heldout_candidate_review",
    export_filename: str = "stage5b1b-heldout-review.csv",
    server_name: str = "Stage 5B.1B reviewer",
    frame_sources: tuple[str, ...] = (),
) -> None:
    server = ThreadingHTTPServer(
        (host, port),
        make_review_handler(
            store,
            static=static,
            mode=mode,
            export_filename=export_filename,
            frame_sources=frame_sources,
        ),
    )
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"
    print(f"{server_name} running at {url}", flush=True)
    print(f"Autosaving labels to {store.review_path}", flush=True)
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
    parser.add_argument("--config", default=str(root / "configs" / "stage5b1b.json"))
    parser.add_argument(
        "--review", help="optional review CSV override for a disposable or exported copy"
    )
    parser.add_argument(
        "--queue",
        help="optional targeted-audit queue; only listed tracks are shown while labels autosave to the review CSV",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        config = load_stage5b1b_config(args.config)
        manifest = load_heldout_manifest(
            config.heldout_manifest_path,
            expected_sha256=config.heldout_manifest_sha256,
        )
        audit_cases = (
            load_audit_queue(Path(args.queue).resolve(), manifest.sha256)
            if args.queue else None
        )
        store = Stage5B1BReviewStore(
            manifest,
            Path(args.review).resolve()
            if args.review else config.artifacts["heldout_review"],
            case_filter=tuple(audit_cases) if audit_cases is not None else None,
            candidate_filter=audit_cases,
        )
    except (FileNotFoundError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    serve(store, args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
