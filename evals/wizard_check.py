#!/usr/bin/env python3
"""Check `fill` behaves honestly on a multi-step (分步) form.

Real application forms often put 教育经历 on step 1 and 实践经历 behind a 下一步 button. Two
rendering strategies exist and `fill` must handle both without lying:

  keep=1  step 2 is in the DOM from the start, merely display:none (antd Tabs keeps mounted
          panes, Element UI lazy=false, hand-rolled wizards). A hidden input CAN be written by
          script and a three-layer readback WILL pass — so without a visibility gate the report
          says OK while the user sees nothing. This was a real defect, found 2026-10-04.
  keep=0  step 2 is not mounted until 下一步 is pressed. Selectors simply do not resolve.

The rule this enforces: **one plan per activated step.** `fill` never presses 下一步 — page
turning stays an explicit action — and it must refuse any field it cannot see.

  python3 evals/wizard_check.py --out /private/wizard-check [--headless]
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
CDP = HERE.parent / 'skills/campus-apply/scripts/browser/chrome_cdp.py'

STEP1 = [dict(key='school', label='学校名称', kind='text', selector='#school', value='虚构大学'),
         dict(key='major', label='专业名称', kind='text', selector='#major', value='虚构专业')]
STEP2 = [dict(key='org', label='单位名称', kind='text', selector='#org', value='虚构单位'),
         dict(key='role', label='担任职位', kind='text', selector='#role', value='虚构职位'),
         dict(key='agree', label='同意公开这段经历', kind='checkbox', selector='#agree', value=True)]


def browser_path():
    candidates = [os.environ.get('CA_BROWSER'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                  shutil.which('google-chrome'), shutil.which('chromium')]
    return next((p for p in candidates if p and Path(p).is_file()), None)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class Report:
    def __init__(self):
        self.rows = []

    def check(self, name, ok, detail=''):
        self.rows.append(dict(case=name, passed=bool(ok), detail=str(detail)[:300]))
        print(('  ok   ' if ok else '  FAIL ') + name + (('  — ' + str(detail)[:150]) if detail else ''),
              flush=True)

    @property
    def failed(self):
        return [r for r in self.rows if not r['passed']]


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

    report = Report()
    proc = None
    profile = tempfile.mkdtemp(prefix='campus-apply-wizard-')
    try:
        command = [browser, '--user-data-dir=' + profile, '--remote-debugging-port=' + str(port),
                   '--no-first-run', '--no-default-browser-check',
                   '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
                   '--disable-backgrounding-occluded-windows', '--window-size=1000,800', 'about:blank']
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
            base = 'http://127.0.0.1:' + str(server.server_address[1]) + '/wizard_form.html'
            env = dict(os.environ, CA_CDP_PORT=str(port))
            env.pop('TAB_MARK', None)
            env.pop('TAB_MATCH', None)

            def run(mark, *args_, timeout=90):
                r = subprocess.run([sys.executable, str(CDP), '--mark', mark, *args_],
                                   env=env, capture_output=True, text=True, timeout=timeout)
                return r.returncode, r.stdout + r.stderr

            def state(mark, name):
                js = out / (name + '.js')
                js.write_text('JSON.stringify({truth: window.wizardTruth(), '
                              'audit: window.wizardAudit()})', encoding='utf-8')
                _, text = run(mark, 'exec', str(js))
                return json.loads(text.strip())

            def plan(name, fields):
                path = out / (name + '.json')
                path.write_text(json.dumps({'pace': {'min': .02, 'max': .05}, 'fields': fields},
                                           ensure_ascii=False), encoding='utf-8')
                return str(path)

            for keep, label in (('1', '步骤二已挂载但 display:none'), ('0', '步骤二条件渲染，未挂载')):
                mark = 'wizard-' + keep
                subprocess.run([sys.executable, str(CDP), 'open',
                                base + '?keep=' + keep + '&run=' + mark, mark],
                               env=env, capture_output=True, text=True, timeout=60)

                # 把两步的字段混在一份计划里：这是 agent 最可能犯的错，必须被挡住
                code, output = run(mark, 'fill', plan('both-' + keep, STEP1 + STEP2), '--max', '30')
                truth = state(mark, 'after-both-' + keep)['truth']
                wrote_step2 = bool(truth['org'] or truth['role'] or truth['agree'])
                report.check(f'[{label}] 两步混在一份计划里 → 退出非零',
                             code != 0, 'exit=' + str(code))
                report.check(f'[{label}] 第二步的字段一个都没被写进去',
                             not wrote_step2, json.dumps(truth, ensure_ascii=False))
                report.check(f'[{label}] 第一步的字段照常填好',
                             truth['school'] == '虚构大学' and truth['major'] == '虚构专业',
                             json.dumps(truth, ensure_ascii=False))
                expected = '不可见' if keep == '1' else '找不到控件'
                report.check(f'[{label}] 原因说得准（{expected}）', expected in output,
                             [l for l in output.splitlines() if l.startswith('FAIL')][:1])
                audit = state(mark, 'audit-' + keep)['audit']
                report.check(f'[{label}] fill 没有去点「下一步」',
                             audit['nextClicked'] == 0, 'nextClicked=' + str(audit['nextClicked']))

                # 正确的走法：一份计划一个激活步骤，翻页是显式动作
                mark2 = mark + '-ok'
                subprocess.run([sys.executable, str(CDP), 'open',
                                base + '?keep=' + keep + '&run=' + mark2, mark2],
                               env=env, capture_output=True, text=True, timeout=60)
                code1, _ = run(mark2, 'fill', plan('s1-' + keep, STEP1), '--max', '30')
                run(mark2, 'click', '#next')
                code2, out2 = run(mark2, 'fill', plan('s2-' + keep, STEP2), '--max', '30')
                final = state(mark2, 'final-' + keep)
                report.check(f'[{label}] 一步一份计划：两次都 DONE',
                             code1 == 0 and code2 == 0,
                             'step1=' + str(code1) + ' step2=' + str(code2))
                report.check(f'[{label}] 一步一份计划：五个字段全部填对',
                             final['truth'] == {'school': '虚构大学', 'major': '虚构专业',
                                                'org': '虚构单位', 'role': '虚构职位', 'agree': True},
                             json.dumps(final['truth'], ensure_ascii=False))
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

    (out / 'report.json').write_text(json.dumps(dict(cases=report.rows), ensure_ascii=False, indent=1),
                                     encoding='utf-8')
    passed = len(report.rows) - len(report.failed)
    print('\n%d/%d 项通过。明细：%s' % (passed, len(report.rows), out / 'report.json'), flush=True)
    return 1 if report.failed else 0


if __name__ == '__main__':
    sys.exit(main())
