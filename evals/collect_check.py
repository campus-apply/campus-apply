#!/usr/bin/env python3
"""Check that `__caNet.collect` recovers from paging duplicates instead of stopping the flow.

Background: on 2026-10-04 a 194-row listing deduped to 192 unique IDs, the hand-written
collection script exited 1, and a human had to re-check four pages by hand. Boundary
duplicates are normal in paginated APIs — the flow should not stop for them.

Three cases, because the right answer differs:
  stable  no duplicates at all — must not retry anything
  (none)  transient duplicates: the first fetch of a page overlaps, a re-fetch is clean.
          This is what unstable server-side ordering looks like. Must self-heal silently.
  sticky  deterministic duplicates: every fetch overlaps. Retrying cannot help, so it must
          stop early and report the shortfall honestly rather than retry forever or lie.

  python3 evals/collect_check.py --out /private/collect-check [--headless]
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

HERE = Path(__file__).resolve().parent
BROWSER_DIR = HERE.parent / 'skills/campus-apply/scripts/browser'
CDP = BROWSER_DIR / 'chrome_cdp.py'

STAGE = '''(async () => {
 const L = window.__ca.L;
 const r = await window.__caNet.collect(
   n => window.fakeFetchPage(n), it => it.id,
   {min: 0.01, max: 0.02, log: m => L(m)});
 window.__collectResult = {unique: r.ids.length, expected: r.expected, pagesRead: r.pagesRead,
   retried: r.retried, duplicates: r.duplicates, duplicatePages: r.duplicatePages,
   missing: r.missingPages, fetches: window.__fetchCount};
 L(r.missingPages ? 'ERR 去重后仍然缺 ' + r.missingPages.short + ' 条' : 'DONE');
})()'''


def browser_path():
    candidates = [os.environ.get('CA_BROWSER'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                  shutil.which('google-chrome'), shutil.which('chromium')]
    return next((p for p in candidates if p and Path(p).is_file()), None)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args(argv)
    browser = browser_path()
    if not browser:
        parser.error('Chrome/Edge not found; set CA_BROWSER')
    out = Path(args.out).resolve()
    if out.is_relative_to(HERE.parent):
        parser.error('--out must be outside the repository')
    out.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer(('127.0.0.1', 0),
                                 functools.partial(QuietHandler, directory=str(HERE / 'fixtures')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    rows = []
    proc = None
    profile = tempfile.mkdtemp(prefix='campus-apply-collect-')
    try:
        command = [browser, '--user-data-dir=' + profile, '--remote-debugging-port=' + str(port),
                   '--no-first-run', '--no-default-browser-check',
                   '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
                   '--disable-backgrounding-occluded-windows', 'about:blank']
        if args.headless:
            command.insert(1, '--headless=new')
        with (out / 'browser.stderr').open('w') as stderr:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stderr)
            deadline = time.monotonic() + 20
            while True:
                try:
                    with urllib.request.urlopen(
                            'http://127.0.0.1:' + str(port) + '/json/version', timeout=1) as resp:
                        version = json.load(resp)['Browser']
                    break
                except OSError:
                    if time.monotonic() >= deadline or proc.poll() is not None:
                        raise RuntimeError('isolated browser did not start')
                    time.sleep(.2)
            print(version, flush=True)
            env = dict(os.environ, CA_CDP_PORT=str(port))
            env.pop('TAB_MARK', None)
            env.pop('TAB_MATCH', None)
            stage = out / 'collect.js'
            stage.write_text(STAGE, encoding='utf-8')
            result_js = out / 'result.js'
            result_js.write_text('JSON.stringify(window.__collectResult)', encoding='utf-8')
            base = 'http://127.0.0.1:' + str(server.server_address[1]) + '/paged_list.html'

            def run(mark, *a):
                r = subprocess.run([sys.executable, str(CDP), '--mark', mark, *a],
                                   env=env, capture_output=True, text=True, timeout=120)
                return r.returncode, r.stdout + r.stderr

            cases = [('stable', '?stable=1', '没有重复'),
                     ('transient', '', '偶发重复（排序不稳，重拉能补回来）'),
                     ('sticky', '?sticky=1', '确定性重复（重拉也补不回来）')]
            for name, query, label in cases:
                subprocess.run([sys.executable, str(CDP), 'open', base + query, name],
                               env=env, capture_output=True, text=True, timeout=60)
                code, output = run(name, 'stage', str(stage), '--libs',
                                   str(BROWSER_DIR / 'lib_antd3.js'),
                                   str(BROWSER_DIR / 'lib_net.js'), '--max', '60')
                (out / (name + '.log')).write_text(output, encoding='utf-8')
                _, raw = run(name, 'exec', str(result_js))
                data = json.loads(raw.strip())
                rows.append(dict(case=name, exit_code=code, **data))
                print('%-10s %s' % (name, label), flush=True)
                print('           ' + json.dumps(data, ensure_ascii=False), flush=True)

            checks = []
            by = {r['case']: r for r in rows}
            checks.append(('没有重复时全部拿到，且一次都不重拉',
                           by['stable']['unique'] == 24 and by['stable']['retried'] == 0
                           and by['stable']['missing'] is None and by['stable']['exit_code'] == 0))
            checks.append(('偶发重复能自愈：补齐 24 条、报 DONE、不用人介入',
                           by['transient']['unique'] == 24 and by['transient']['missing'] is None
                           and by['transient']['exit_code'] == 0
                           and by['transient']['retried'] > 0))
            checks.append(('偶发重复确实发生过（不是测试没触发）',
                           by['transient']['duplicates'] > 0))
            checks.append(('确定性重复：如实报缺，不假装成功',
                           by['sticky']['missing'] is not None and by['sticky']['exit_code'] != 0))
            checks.append(('确定性重复：发现重拉没用就停，不无限重试',
                           by['sticky']['retried'] <= 4,))
            print('', flush=True)
            for text, ok in checks:
                ok = ok if isinstance(ok, bool) else ok[0]
                print(('  ok   ' if ok else '  FAIL ') + text, flush=True)
            failed = [t for t, ok in checks if not (ok if isinstance(ok, bool) else ok[0])]
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
        shutil.rmtree(profile, ignore_errors=True)

    (out / 'report.json').write_text(json.dumps(dict(cases=rows), ensure_ascii=False, indent=1),
                                     encoding='utf-8')
    print('\n%d/%d 项通过。明细：%s' % (len(checks) - len(failed), len(checks), out / 'report.json'),
          flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
