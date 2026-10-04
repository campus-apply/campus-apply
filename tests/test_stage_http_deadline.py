"""Real local HTTP streams: an idle timeout is not an overall deadline."""
import importlib.util
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from test_chrome_cdp import SCRIPT


def driver():
    spec = importlib.util.spec_from_file_location('stage_cdp_http', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def slow_http():
    servers = []
    def start(*, slow_headers=False, slow_body=False):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                body = b'[' + b' ' * 14 + b']'
                header = b'HTTP/1.0 200 OK\r\nContent-Length: 16\r\n\r\n'
                try:
                    if slow_headers:
                        for byte in header:
                            self.wfile.write(bytes([byte])); self.wfile.flush()
                            time.sleep(.05)
                    else:
                        self.wfile.write(header); self.wfile.flush()
                    if slow_body:
                        for byte in body:
                            self.wfile.write(bytes([byte])); self.wfile.flush()
                            time.sleep(.05)
                    else:
                        self.wfile.write(body); self.wfile.flush()
                except OSError:
                    pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        return server.server_address[1]
    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize('part', ['body', 'headers'])
def test_continuous_chunks_cannot_extend_http_deadline(slow_http, part):
    module = driver()
    module.PORT = slow_http(slow_headers=part == 'headers', slow_body=part == 'body')
    started = time.monotonic()
    with pytest.raises((module.StageDeadline, OSError)):
        module.http('/json/list', deadline=started + .15)
    assert time.monotonic() - started < .5


def test_complete_http_response_within_deadline_returns_json(slow_http):
    module = driver()
    module.PORT = slow_http()
    started = time.monotonic()
    assert module.http('/json/list', deadline=started + .5) == []


def test_http_without_deadline_preserves_complete_slow_response(slow_http):
    module = driver()
    module.PORT = slow_http(slow_body=True)
    assert module.http('/json/list') == []
