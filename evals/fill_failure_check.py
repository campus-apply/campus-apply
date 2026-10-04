#!/usr/bin/env python3
"""Check that `fill` fails when it should, and says why.

A green-only benchmark proves nothing: the executor also has to refuse. Each case below feeds
it a plan that cannot succeed and asserts a non-zero exit plus a recognisable reason. The last
case asserts the one thing that must never happen — the executor does not press submit.

  python3 evals/fill_failure_check.py --out /private/fill-failures [--headless]

Exit 0 = every case failed in the expected way. No models, no recruitment sites.
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

# (name, fields, expected exit code, substring that must appear in the output)
CASES = [
    ('选择器找不到控件',
     [dict(key='x', label='不存在的字段', kind='text', selector='#no-such-field', value='甲')],
     1, '找不到控件'),
    ('选择器不合法',
     [dict(key='x', label='坏选择器', kind='text', selector='###', value='甲')],
     1, '选择器不合法'),
    ('disabled 的账号级字段跳过并说明',
     [dict(key='phone', label='手机号码', kind='text', selector='#phone', value='13900000000')],
     0, 'disabled'),
    ('下拉里没有这个选项，并列出页面上有什么',
     [dict(key='wish1', label='第一志愿', kind='dropdown',
           selector='[data-dropdown="wish1"] .fx-select-input', value='不存在的岗位',
           display_selector='[data-display="wish1"]')],
     1, '面板里有'),
    ('级联第二级没有这一项',
     [dict(key='dept', label='意向部门', kind='cascader',
           selector='[data-cascader="dept"] .fx-select-input', value=['技术线', '不存在的部门'],
           display_selector='[data-display="dept"]')],
     1, '第 2 级没有'),
    ('文本超过本字段上限时不写入',
     [dict(key='statement', label='自我描述', kind='text', selector='#statement',
           value='测' * 600, max=500)],
     1, '超过本字段上限'),
    ('写进去但页面校验报错，算写入失败',
     [dict(key='statement', label='自我描述', kind='text', selector='#statement',
           value='测' * 600)],
     1, '页面报错'),
    ('kind 不认识',
     [dict(key='x', label='怪控件', kind='telepathy', selector='#name', value='甲')],
     1, 'kind 不认识'),
    ('回读对不上就算没填成',
     # 写 #birth：它是 readonly，写不进去
     [dict(key='birth', label='出生日期', kind='text', selector='#birth', value='2001-02-14')],
     1, 'readonly'),
]


def browser_path():
    candidates = [os.environ.get('CA_BROWSER'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                  shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome')]
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
    profile = tempfile.mkdtemp(prefix='campus-apply-fillfail-')
    try:
        command = [browser, '--user-data-dir=' + profile, '--remote-debugging-port=' + str(port),
                   '--no-first-run', '--no-default-browser-check',
                   '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
                   '--disable-backgrounding-occluded-windows', '--window-size=1100,900', 'about:blank']
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
            base = 'http://127.0.0.1:' + str(server.server_address[1]) + '/apply_form.html'
            env = dict(os.environ, CA_CDP_PORT=str(port))
            env.pop('TAB_MARK', None)
            env.pop('TAB_MATCH', None)

            for index, (name, fields, want_code, want_text) in enumerate(CASES):
                mark = 'fail-%02d' % index
                case_dir = out / mark
                case_dir.mkdir(parents=True, exist_ok=True)
                subprocess.run([sys.executable, str(CDP), 'open', base + '?run=' + mark, mark],
                               env=env, capture_output=True, text=True, timeout=60)
                plan = case_dir / 'plan.json'
                plan.write_text(json.dumps({'fields': fields, 'pace': {'min': .02, 'max': .05}},
                                           ensure_ascii=False, indent=1), encoding='utf-8')
                result = subprocess.run(
                    [sys.executable, str(CDP), '--mark', mark, 'fill', str(plan), '--max', '30'],
                    env=env, capture_output=True, text=True, timeout=120)
                output = result.stdout + result.stderr
                (case_dir / 'fill.out').write_text(output, encoding='utf-8')
                # The submit button must never have been pressed, whatever happened.
                audit_js = case_dir / 'audit.js'
                audit_js.write_text('JSON.stringify(window.fixtureAudit())', encoding='utf-8')
                audit_raw = subprocess.run(
                    [sys.executable, str(CDP), '--mark', mark, 'exec', str(audit_js)],
                    env=env, capture_output=True, text=True, timeout=60).stdout.strip()
                try:
                    audit = json.loads(audit_raw)
                except ValueError:
                    audit = {}
                code_ok = result.returncode == want_code
                text_ok = want_text in output
                submit_ok = audit.get('submitClicked', 0) == 0
                panels_ok = audit.get('openPanels', 0) == 0
                passed = code_ok and text_ok and submit_ok and panels_ok
                rows.append(dict(case=name, passed=passed, exit_code=result.returncode,
                                 want_code=want_code, text_found=text_ok,
                                 submit_clicked=audit.get('submitClicked'),
                                 open_panels=audit.get('openPanels')))
                detail = []
                if not code_ok:
                    detail.append('退出码 %s，期望 %s' % (result.returncode, want_code))
                if not text_ok:
                    detail.append('输出里没有「%s」' % want_text)
                if not submit_ok:
                    detail.append('点过投递按钮')
                if not panels_ok:
                    detail.append('残留 %s 个面板' % audit.get('openPanels'))
                print(('  ok   ' if passed else '  FAIL ') + name
                      + (('  — ' + '；'.join(detail)) if detail else ''), flush=True)
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
    bad = [r for r in rows if not r['passed']]
    print('\n%d/%d 个失败场景按预期失败并说明了原因。明细：%s'
          % (len(rows) - len(bad), len(rows), out / 'report.json'), flush=True)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
