"""Serve the frozen Gemini pilot's two-pass owner review without any inference."""
import argparse
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from audio_similarity.gemini_style_review_store import GeminiStyleReviewStore, STATE
from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.cli.stage5b1b_review_server import ReviewHTTPServer, make_review_handler

STATIC = Path(__file__).resolve().parents[3] / 'evaluation/static/gemini_style_review.html'


def handler(store, *, disposable=False):
    base = make_review_handler(store, static=STATIC,
        mode='gemini_style_disposable' if disposable else 'gemini_style_owner_review',
        export_filename='gemini-style-owner-review.csv')

    class Handler(base):
        def do_GET(self):
            path = urlparse(self.path).path
            if path.startswith('/api/profile/'):
                try:
                    return self._json(store.profile(unquote(path.removeprefix('/api/profile/'))))
                except Stage5B1AValidationError as exc:
                    return self._json({'error': str(exc)}, 409)
            return super().do_GET()

        def do_POST(self):
            path = urlparse(self.path).path
            if path not in ('/api/answer', '/api/advance'):
                return self._json({'error': 'not found'}, 404)
            try:
                host, origin = self.headers.get('Host'), self.headers.get('Origin')
                if origin and origin not in (f'http://{host}', f'https://{host}'):
                    raise Stage5B1AValidationError('Cross-origin request rejected.')
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise Stage5B1AValidationError('JSON required.')
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= store.max_request_bytes:
                    raise Stage5B1AValidationError('Invalid request size.')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise Stage5B1AValidationError('Expected an object.')
                result = store.save(data.get('pilot_id'), data.get('fields'), data.get('revision')) if path == '/api/answer' else store.advance(data.get('revisions'))
                return self._json(result)
            except (ValueError, Stage5B1AValidationError) as exc:
                return self._json({'error': str(exc)}, 400)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8794)
    parser.add_argument('--state-dir', type=Path, help='Disposable testing only; real answers use the default path.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    real = (root / STATE).resolve()
    if args.state_dir and args.state_dir.resolve() == real:
        parser.error('Disposable state must not target the real owner review.')
    store = GeminiStyleReviewStore(root, args.state_dir or real)
    server = ReviewHTTPServer(('127.0.0.1', args.port), handler(store, disposable=bool(args.state_dir)))
    print(f'Gemini audio review: http://127.0.0.1:{server.server_port}', flush=True)
    print(f'Answers save to {store.review_path}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.close()


if __name__ == '__main__':
    main()
