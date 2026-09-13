"""Start the reviewer demo using only the Python standard library."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import unquote, urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parent

class ReviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parts = unquote(urlsplit(self.path).path).split('/')
        if any(part.startswith('.') and part not in ('', '.') for part in parts):
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        parts = unquote(urlsplit(self.path).path).split('/')
        if any(part.startswith('.') and part not in ('', '.') for part in parts):
            self.send_error(404)
            return
        super().do_HEAD()

    def log_message(self, format, *args):
        pass

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    handler = partial(ReviewHandler, directory=str(ROOT))
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    except OSError:
        if args.port != 8765:
            raise
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    print('TraceMat reviewer demo: ' + url, flush=True)
    print('Keep this terminal open. Press Ctrl+C to stop.', flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Demo stopped.')
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
