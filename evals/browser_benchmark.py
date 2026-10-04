#!/usr/bin/env python3
"""Compare the same complete local CDP fill/save/refresh path on two skill roots.

Uses a separate browser profile and ports, never the user's application pages.
No models or recruitment sites. --headless selects Chrome visibility only.
Artifacts are written under required --out, not inside this repository.
"""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

EXPECTED = [dict(company='模拟甲单位', position='研究助理', city='北京', start='2026-01-01',
                 end='2026-03-01', description='整理公开研究资料，并核对来源与统计口径。'),
            dict(company='模拟乙单位', position='产品实习生', city='上海', start='2025-06-01',
                 end='2025-08-01', description='记录需求访谈，整理问题清单并跟进确认结果。')]


def verify_snapshot(snapshot, require_saved=False):
    for layer in ('dom', 'model', 'display') + (('saved',) if require_saved else ()):
        assert snapshot[layer] == EXPECTED, 'full-value mismatch in ' + layer


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def browser_path():
    candidates = [os.environ.get('CA_BROWSER'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                  shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome')]
    return next((p for p in candidates if p and Path(p).is_file()), None)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def measure(root, url, port, output, label):
    root = Path(root).resolve()
    browser_dir = root / 'skills/campus-apply/scripts/browser'
    script = browser_dir / 'chrome_cdp.py'
    if not script.is_file():
        raise ValueError('skill root does not contain the CDP script')
    target = output / label
    target.mkdir(parents=True, exist_ok=False)
    timings, commands = target / 'timing.jsonl', []
    env = dict(os.environ, CA_CDP_PORT=str(port), CA_TIMING_FILE=str(timings))
    env.pop('TAB_MARK', None)
    env.pop('TAB_MATCH', None)
    started = time.monotonic()

    def run(phase, *args):
        before = time.monotonic()
        result = subprocess.run([sys.executable, str(script), *args], env=env,
                                capture_output=True, text=True, timeout=35)
        commands.append(dict(phase=phase, elapsed_seconds=time.monotonic() - before,
                             exit_code=result.returncode))
        (target / (phase + '.stdout')).write_text(result.stdout, encoding='utf-8')
        (target / (phase + '.stderr')).write_text(result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(phase + ': ' + result.stdout + result.stderr)
        return result.stdout.strip()

    run('open', 'open', url + '/browser_form.html?run=' + label, label)
    env['TAB_MARK'] = label
    run('probe', 'exec', str(browser_dir / 'probe.js'))
    guard = json.loads(run('guard', 'exec', str(browser_dir / 'guard.js')))
    assert not guard['captcha'] and not guard['loginRedirect'] and not guard.get('blocked')
    stage = target / 'fill.js'
    stage.write_text('''(async () => {
const data = ''' + json.dumps(EXPECTED, ensure_ascii=False) + ''';
for (let i=0; i<data.length; i++) {
 for (const [key,value] of Object.entries(data[i])) {
  const el = document.getElementById(key+'-'+i);
  if(el.tagName === 'SELECT'){el.value=value;el.dispatchEvent(new Event('change',{bubbles:true}));}
  else window.__ca.setInput(el,value);
  el.dispatchEvent(new Event('blur',{bubbles:true}));
 }
 await new Promise(r=>setTimeout(r,120));
}
window.__ca.L('DONE');
})()
''', encoding='utf-8')
    run('fill', 'stage', str(stage), '--libs', str(browser_dir / 'lib_antd3.js'), '--max', '10')
    snapshot_file = target / 'snapshot.js'
    snapshot_file.write_text('JSON.stringify(window.fixtureSnapshot())', encoding='utf-8')
    snapshot = json.loads(run('readback', 'exec', str(snapshot_file)))
    verify_snapshot(snapshot)
    run('save', 'click', '#save')
    refresh = target / 'refresh.js'
    refresh.write_text("location.reload(); 'reload'", encoding='utf-8')
    run('refresh', 'exec', str(refresh))
    # Readiness is bounded separately from deliberate site pacing.
    deadline = time.monotonic() + 5
    while True:
        try:
            snapshot = json.loads(run('saved_readback', 'exec', str(snapshot_file)))
            verify_snapshot(snapshot, require_saved=True)
            break
        except (RuntimeError, ValueError, KeyError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(.1)
    result = dict(label=label, elapsed_seconds=time.monotonic() - started,
                  commands=commands, command_count=len(commands), errors=0, rework=0,
                  values_verified=True, saved_after_refresh=True)
    (target / 'snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    (target / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    # Close only this benchmark's tab, keeping target scans equally bounded.
    with urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/json/list', timeout=2) as response:
        targets = json.load(response)
    for item in targets:
        if item.get('url') == url + '/browser_form.html?run=' + label:
            with urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/json/close/' + item['id'], timeout=2):
                pass
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--patched', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args(argv)
    if args.repeats < 1 or args.repeats > 10:
        parser.error('--repeats must be 1..10')
    browser = browser_path()
    if not browser:
        parser.error('Chrome/Edge not found; set CA_BROWSER')
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(QuietHandler, directory=str(Path(__file__).parent / 'fixtures'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = free_port()
    proc = None
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix='campus-apply-bench-') as profile:
            command = [browser, '--user-data-dir=' + profile, '--remote-debugging-port=' + str(port),
                       '--no-first-run', '--no-default-browser-check', '--disable-background-timer-throttling',
                       '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows',
                       '--window-size=1050,800', 'about:blank']
            if args.headless:
                command.insert(1, '--headless=new')
            with (output / 'browser.stderr').open('w') as stderr:
                proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stderr)
                deadline = time.monotonic() + 20
                while True:
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/json/version', timeout=1) as response:
                            version = json.load(response)['Browser']
                        break
                    except OSError:
                        if time.monotonic() >= deadline or proc.poll() is not None:
                            raise RuntimeError('isolated browser did not start')
                        time.sleep(.2)
                url = 'http://127.0.0.1:' + str(server.server_address[1])
                for i in range(args.repeats):
                    # Alternate order to reduce warm-up/order bias; labels get separate URLs/tabs.
                    pairs = [('baseline', args.baseline), ('patched', args.patched)]
                    if i % 2:
                        pairs.reverse()
                    for kind, root in pairs:
                        result = measure(root, url, port, output, kind + '-' + str(i))
                        result['variant'] = kind
                        results.append(result)
                        print(kind, i, round(result['elapsed_seconds'], 3), 'saved values verified', flush=True)
                report = dict(browser=version, repeats=args.repeats, models_used=False,
                              scope='local CDP tools path; excludes browser startup and any model reasoning',
                              results=results)
                (output / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
