"""Compact presentation of the unchanged frozen Stage 5E.3 review."""
import argparse
from pathlib import Path
from audio_similarity.stage5e3_prepare import REPORT, verify_prepared
from audio_similarity.stage5e3_review import PlaylistReviewStore, ReviewHTTPServer, handler


def main():
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=root / REPORT)
    parser.add_argument('--state', type=Path, default=root / '.research_audio/stage5e3_frozen100_v3_review')
    parser.add_argument('--port', type=int, default=8785)
    args = parser.parse_args()
    verify_prepared(root, args.run)
    store = PlaylistReviewStore(root, args.run, args.state)
    server = ReviewHTTPServer(('127.0.0.1', args.port), handler(
        store, root / 'evaluation/static/stage5e3_compact_review.html'))
    print(f'Compact playlist review: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
