"""Local listening-test server (stdlib only; no new dependencies).

    python -m audio_similarity.cli.eval_server \
        --sheets reports/human_eval \
        --manifest data/manifests/fma_small.parquet \
        --audio-root data/fma/fma_small \
        [--port 8616]

Routes:
    GET  /                          evaluator UI
    GET  /api/session               rater-safe session payload
    POST /api/rate                  {cell_id, rating}   0/1/2/3/X
    POST /api/rate_ab               {ab_id, choice}     A/B/Tie/Neither
    GET  /audio/track/<id>          mp3 (HTTP range supported)
    GET  /audio/ab/<ab_id>/<side>   blinded A/B clip
"""

from __future__ import annotations

import argparse
import json
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from audio_similarity.eval_store import SheetStore

_STATIC_DIR = Path(__file__).resolve().parents[3] / "evaluation" / "static"


def make_handler(store: SheetStore) -> type:
    class EvalHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # ------------------------------------------------------------ utils
        def _cors(self) -> None:
            # allows the GitHub Pages UI to talk to a LAN/local server
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _json(self, payload: dict | list, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self._cors()
            self.end_headers()

        def _file(self, path: Path, content_type: str, range_header: str | None = None) -> None:
            if not path.is_file():
                return self._json({"error": "not found"}, 404)
            size = path.stat().st_size
            start, end = 0, size - 1
            status = 200
            if range_header:
                match = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
                if match:
                    if match.group(1):
                        start = int(match.group(1))
                    if match.group(2):
                        end = min(int(match.group(2)), size - 1)
                    elif not match.group(1):
                        end = size - 1
                    else:
                        end = min(start + 512 * 1024 - 1, size - 1)
                    status = 206
            length = end - start + 1
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self._cors()
            self.end_headers()
            with open(path, "rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def log_message(self, fmt: str, *args) -> None:  # quieter logs
            pass

        # ------------------------------------------------------------- gets
        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                return self._file(_STATIC_DIR / "index.html", "text/html; charset=utf-8")
            if self.path.startswith("/examples/"):
                name = Path(self.path).name  # basename only; no traversal
                return self._file(_STATIC_DIR / "examples" / name, "audio/mpeg")
            if self.path == "/api/ping":
                return self._json({"ok": True, "mode": "server"})
            if self.path == "/api/session":
                try:
                    return self._json(store.build_session())
                except FileNotFoundError as exc:
                    return self._json({"error": str(exc)}, 500)
            match = re.match(r"^/audio/track/(\d+)$", self.path)
            if match:
                path = store.audio_path_for_request("track", match.group(1))
                if path is None:
                    return self._json({"error": "not found"}, 404)
                return self._file(path, "audio/mpeg", self.headers.get("Range"))
            match = re.match(r"^/audio/ab/(.+)/([ab])$", self.path)
            if match:
                path = store.audio_path_for_request("ab", match.group(1), match.group(2))
                if path is None:
                    return self._json({"error": "not found"}, 404)
                return self._file(path, "audio/mpeg", self.headers.get("Range"))
            return self._json({"error": "not found"}, 404)

        # ------------------------------------------------------------ posts
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json({"error": "bad json"}, 400)
            if self.path == "/api/rate":
                try:
                    store.rate_factor_cell(
                        str(payload["cell_id"]), str(payload["rating"]), str(payload.get("rated_by", ""))
                    )
                except (ValueError, KeyError) as exc:
                    return self._json({"error": str(exc)}, 400)
                return self._json({"ok": True})
            if self.path == "/api/rate_ab":
                try:
                    store.rate_ab_trial(
                        str(payload["ab_id"]), str(payload["choice"]), str(payload.get("rated_by", ""))
                    )
                except (ValueError, KeyError) as exc:
                    return self._json({"error": str(exc)}, 400)
                return self._json({"ok": True})
            if self.path == "/api/note":
                try:
                    store.set_note(
                        str(payload["kind"]),
                        str(payload["id"]),
                        str(payload.get("note", "")),
                        str(payload.get("rated_by", "")),
                    )
                except (ValueError, KeyError) as exc:
                    return self._json({"error": str(exc)}, 400)
                return self._json({"ok": True})
            if self.path == "/api/import":
                applied = store.import_ratings(
                    list(payload.get("factor_cells", [])),
                    list(payload.get("ab_trials", [])),
                    overwrite_existing=bool(payload.get("overwrite_existing", False)),
                )
                return self._json({"ok": True, "applied": applied})
            return self._json({"error": "not found"}, 404)

    return EvalHandler


def serve(
    sheets_dir: str | Path,
    manifest_path: str | Path,
    audio_root: str | Path,
    port: int = 8616,
    host: str = "127.0.0.1",
    open_browser: bool = True,
) -> None:
    store = SheetStore(sheets_dir, manifest_path, audio_root)
    server = ThreadingHTTPServer((host, port), make_handler(store))
    url = f"http://{'localhost' if host in ('0.0.0.0', '127.0.0.1') else host}:{port}"
    print(f"evaluator running at {url}  (Ctrl-C to stop)")
    if host == "0.0.0.0":
        print("bound to all interfaces — reachable from phones/other devices on your network")
    print(f"sheets: {Path(sheets_dir).resolve()}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheets", default="reports/human_eval")
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--audio-root", default="data/fma/fma_small")
    parser.add_argument("--port", type=int, default=8616)
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to allow phone/LAN access")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    serve(
        args.sheets,
        args.manifest,
        args.audio_root,
        port=args.port,
        host=args.host,
        open_browser=not args.no_browser,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
