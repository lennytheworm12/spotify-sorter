"""Isolated exact-PCM evaluator server for the Stage 2B collection protocol."""

from __future__ import annotations

import argparse
import json
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from audio_similarity.stage2b_store import RatingPolicyError, Stage2BStore

_STATIC = Path(__file__).resolve().parents[3] / "evaluation" / "static" / "stage2b.html"


def make_stage2b_handler(store: Stage2BStore) -> type:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:
            pass

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")

        def _json(self, payload, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _bytes(self, body: bytes, content_type: str, content_hash: str | None = None, download: str | None = None) -> None:
            size = len(body)
            start, end, status = 0, size - 1, 200
            range_header = self.headers.get("Range")
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                if not match or (not match.group(1) and not match.group(2)):
                    return self._range_error(size)
                if match.group(1):
                    start = int(match.group(1))
                    end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
                else:
                    suffix = int(match.group(2))
                    start = max(0, size - suffix)
                if start > end or start >= size:
                    return self._range_error(size)
                status = 206
            chunk = body[start:end + 1]
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Accept-Ranges", "bytes")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            if content_hash:
                self.send_header("X-Audio-Sample-Rate", "24000")
                self.send_header("X-Audio-Sample-Format", "float32le")
                self.send_header("X-Audio-Sample-Count", "120000")
                self.send_header("X-Content-SHA256", content_hash)
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self._cors()
            self.end_headers()
            self.wfile.write(chunk)

        def _range_error(self, size: int) -> None:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self._cors()
            self.end_headers()

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                return self._bytes(_STATIC.read_bytes(), "text/html; charset=utf-8")
            if parsed.path == "/api/ping":
                return self._json({"ok": True, "mode": "stage2b"})
            if parsed.path == "/api/session":
                try:
                    rater = parse_qs(parsed.query).get("rater_id", [""])[0]
                    return self._json(store.build_session(rater))
                except RatingPolicyError as exc:
                    return self._json({"error": str(exc)}, 400)
            match = re.fullmatch(r"/trial/([a-zA-Z0-9_-]+)/(?P<role>query|a|b)", parsed.path)
            if match:
                try:
                    body, content_hash = store.audio_bytes(match.group(1), match.group("role"))
                    return self._bytes(body, "application/x-float32", content_hash)
                except KeyError:
                    return self._json({"error": "not found"}, 404)
                except RatingPolicyError as exc:
                    return self._json({"error": str(exc)}, 409)
            match = re.fullmatch(r"/api/export/(all|train-validation|test)", parsed.path)
            if match:
                kind = match.group(1)
                body = store.export_bytes(kind)
                return self._bytes(body, "text/csv; charset=utf-8", download=f"stage2b-{kind}-ratings.csv")
            return self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json({"error": "bad JSON"}, 400)
            try:
                if self.path == "/api/rate":
                    return self._json(store.submit(
                        str(payload.get("trial_id", "")), payload.get("rater_id", ""),
                        payload.get("choice", ""), payload.get("note", ""),
                    ))
                if self.path == "/api/import":
                    return self._json({"ok": True, **store.import_rows(list(payload.get("ratings", [])))})
            except (RatingPolicyError, KeyError, ValueError) as exc:
                return self._json({"error": str(exc)}, 400)
            return self._json({"error": "not found"}, 404)

    return Handler


def serve(store: Stage2BStore, host: str, port: int, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), make_stage2b_handler(store))
    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    print(f"Stage 2B evaluator running at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", default="reports/holistic_stage2b")
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--audio-root", default="data/fma/fma_small")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8620)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    serve(Stage2BStore(args.reports, args.manifest, args.audio_root), args.host, args.port, not args.no_browser)


if __name__ == "__main__":
    main()
