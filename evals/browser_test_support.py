"""Isolated local Chrome harness for behavioral checks; never attaches to port 9222."""
import base64
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import functools
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
BROWSER = ROOT / 'skills/campus-apply/scripts/browser'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class BrowserSession:
    def __init__(self, out):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.profile = tempfile.mkdtemp(prefix='campus-apply-behavior-')
        self.proc = self.tab = self.server = self.stderr = None

    def __enter__(self):
        spec = importlib.util.spec_from_file_location('ca_browser_behavior', BROWSER / 'chrome_cdp.py')
        self.cdp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cdp)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(
            QuietHandler, directory=str(ROOT / 'evals/fixtures')))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        browser = shutil.which('google-chrome') or shutil.which('chromium')
        if not browser:
            path = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
            if path.exists():
                browser = str(path)
        if not browser:
            self.close()
            raise RuntimeError('Chrome is required for this isolated behavior check')
        self.stderr = (self.out / 'chrome.stderr').open('w')
        self.proc = subprocess.Popen([
            browser, '--headless=new', '--no-first-run', '--no-default-browser-check',
            '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
            '--disable-backgrounding-occluded-windows', '--window-size=1100,900',
            '--user-data-dir=' + self.profile, '--remote-debugging-port=' + str(self.port),
            self.url + 'apply_form.html',
        ], stdout=subprocess.DEVNULL, stderr=self.stderr)
        self.cdp.PORT = self.port
        deadline = time.monotonic() + 15
        try:
            while True:
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json/list', timeout=1) as r:
                        targets = json.load(r)
                    target = next(t for t in targets if t.get('type') == 'page')
                    self.tab = self.cdp.Tab(target)
                    while not self.js("document.readyState === 'complete' && location.href === "
                                       + json.dumps(self.url + 'apply_form.html')):
                        if time.monotonic() > deadline:
                            raise RuntimeError('isolated fixture page did not finish loading')
                        time.sleep(.03)
                    break
                except (OSError, StopIteration):
                    if time.monotonic() > deadline:
                        raise RuntimeError('isolated browser did not start')
                    time.sleep(.05)
            return self
        except BaseException:
            self.close()
            raise

    def js(self, source):
        value, error = self.tab.evaluate(source)
        if error:
            raise RuntimeError(error)
        return value

    def call(self, expression):
        return self.cdp._fill_call(self.tab, expression)

    def document(self, html):
        self.js("document.body.innerHTML = " + json.dumps(html) + "; delete window.__caFill;")
        self.js(self.cdp._fill_lib())

    def screenshot(self, name):
        shot = self.tab.call('Page.captureScreenshot', format='png')
        path = self.out / (name + '.png')
        path.write_bytes(base64.b64decode(shot['data']))
        return path

    def command(self, *args, timeout=30):
        return subprocess.run([
            sys.executable, str(BROWSER / 'chrome_cdp.py'), '--port', str(self.port),
            '--match', self.url, *map(str, args),
        ], capture_output=True, text=True, timeout=timeout)

    def close(self):
        if self.tab:
            self.tab.close()
            self.tab = None
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.stderr:
            self.stderr.close()
        shutil.rmtree(self.profile, ignore_errors=True)

    def __exit__(self, *_):
        self.close()
