#!/usr/bin/env python3
"""Check that probe never calls a value "empty" when it merely could not read it.

A date picker whose outer node is a <span> keeps its value on an inner input. Reading the
container gives an empty string, so a whole class of filled fields gets reported as empty —
and "empty" is what makes the agent offer to fill them in, over the user's real data. This
is the only defect class in the repository that can destroy something the user typed.

The page below is written here rather than in fixtures/ because every case is a shape of
*reading*, not a trap to drive: four controls, four expected verdicts.

  python3 evals/container_value_check.py --out /tmp/container-check [--headless]

Exit 0 = every case read as documented. No models, no recruitment sites.
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

# 四种取值形状，都来自真实站点：前两种是 antd 3.x 的日期选择器与下拉，第三种是同一个日期
# 控件但确实空着，第四种是连输入控件都没有的容器 —— 只有它才该报 unknown。
PAGE = '''<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>容器取值</title>
<style>body{font:14px system-ui;margin:24px}.ant-form-item{margin:14px 0}
label{display:block;margin-bottom:4px}.ant-calendar-picker,.ant-select{display:inline-block;width:240px}
.ant-select-selection{border:1px solid #bbb;border-radius:4px;padding:5px 9px}
input{width:100%;padding:5px 9px;border:1px solid #bbb;border-radius:4px}</style></head>
<body>
<h3>基本信息</h3>

<!-- 1. 容器型日期，有值：值在内层 input 上，容器自己没有任何文本 -->
<div class="ant-form-item">
  <label>入学时间</label>
  <span class="ant-calendar-picker">
    <div><input readonly class="ant-calendar-picker-input" value="2026-09-01"></div>
  </span>
</div>

<!-- 2. 容器型下拉，有值：值是显示元素的文本，没有任何 input -->
<div class="ant-form-item">
  <label>最高学历</label>
  <div class="ant-select">
    <div class="ant-select-selection" role="combobox">
      <div class="ant-select-selection-selected-value">硕士</div>
    </div>
  </div>
</div>

<!-- 3. 容器型日期，真的空着：下钻到了内层 input，值是空串 —— 这种必须仍然报空 -->
<div class="ant-form-item">
  <label>毕业时间</label>
  <span class="ant-calendar-picker">
    <div><input readonly class="ant-calendar-picker-input" value=""></div>
  </span>
</div>

<!-- 4. 不透明容器：没有输入控件、没有显示元素 —— 读不出，也证明不了是空的 -->
<div class="ant-form-item">
  <label>工作地点</label>
  <div class="ant-cascader-picker" role="combobox"></div>
</div>
</body></html>
'''

# (标签, 期望的 valueUnknown, 期望的 valueLen, 期望的 valueFrom, 这条在防什么)
CASES = [
    ('入学时间', False, len('2026-09-01'), 'inner-input',
     '容器型日期被报成空值，补填会覆盖用户填好的日期'),
    ('最高学历', False, len('硕士'), 'display',
     '纯下拉的选中值在显示元素上，按容器读会读成空'),
    ('毕业时间', False, 0, 'inner-input',
     'unknown 不能滥用：下钻到了、确实是空的，就要说空'),
    ('工作地点', True, None, None,
     '读不出值的容器必须报 unknown，交给上层判断，不许当成空'),
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


def run_cdp(port, out, phase, *args, check=True):
    env = dict(os.environ, CA_CDP_PORT=str(port))
    env.pop('TAB_MARK', None)
    env.pop('TAB_MATCH', None)
    result = subprocess.run([sys.executable, str(CDP), *args], env=env,
                            capture_output=True, text=True, timeout=60)
    (out / (phase + '.out')).write_text(
        result.stdout + ('\n--- stderr ---\n' + result.stderr if result.stderr else ''),
        encoding='utf-8')
    if check and result.returncode:
        raise RuntimeError(phase + ' exited ' + str(result.returncode) + ': '
                           + (result.stdout + result.stderr).strip()[:400])
    return result


def check_values(port, out, url, rows):
    mark = 'container-check'
    run_cdp(port, out, 'open', 'open', url + '/container_value.html', mark)
    probe = json.loads(run_cdp(port, out, 'probe', '--mark', mark,
                               'exec', str(BROWSER_DIR / 'probe.js')).stdout)
    by_label = {}
    for control in probe['controls']:
        by_label.setdefault(control.get('label') or '', control)

    for label, want_unknown, want_len, want_from, guards in CASES:
        got = by_label.get(label)
        if got is None:
            rows.append((label, False, guards, '没探到这个控件：'
                         + str(sorted(by_label))[:160]))
            continue
        ok = (bool(got.get('valueUnknown')) == want_unknown
              and got.get('valueLen') == want_len
              and (want_from is None or got.get('valueFrom') == want_from))
        detail = ('valueUnknown=' + repr(got.get('valueUnknown'))
                  + ' valueLen=' + repr(got.get('valueLen'))
                  + ' valueFrom=' + repr(got.get('valueFrom')))
        rows.append((label, ok, guards, detail))

    # 整页层面的那一条：一旦有字段读不出，报告里必须能一眼看见，否则下游仍然会当成空。
    unknown = [c.get('label') for c in probe['controls'] if c.get('valueUnknown')]
    rows.append(('读不出的字段在报告里可枚举', bool(unknown), '下游要能挑出不许补填的字段',
                 '报 unknown 的：' + ', '.join(filter(None, unknown))))
    return probe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', required=True, help='artifacts directory, outside the repo')
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args(argv)
    browser = browser_path()
    if not browser:
        parser.error('Chrome/Edge not found; set CA_BROWSER')
    out = Path(args.out).resolve()
    if out.is_relative_to(HERE.parent):
        parser.error('--out must be outside the repository')
    out.mkdir(parents=True, exist_ok=True)

    pages = Path(tempfile.mkdtemp(prefix='campus-apply-container-'))
    (pages / 'container_value.html').write_text(PAGE, encoding='utf-8')
    handler = functools.partial(QuietHandler, directory=str(pages))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    rows, proc = [], None
    profile = tempfile.mkdtemp(prefix='campus-apply-container-profile-')
    try:
        command = [browser, '--user-data-dir=' + profile,
                   '--remote-debugging-port=' + str(port),
                   '--no-first-run', '--no-default-browser-check',
                   '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
                   '--disable-backgrounding-occluded-windows',
                   '--window-size=1100,900', 'about:blank']
        if args.headless:
            command.insert(1, '--headless=new')
        with (out / 'browser.stderr').open('w') as stderr:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stderr)
            deadline = time.monotonic() + 20
            while True:
                try:
                    with urllib.request.urlopen(
                            'http://127.0.0.1:' + str(port) + '/json/version', timeout=1) as response:
                        version = json.load(response)['Browser']
                    break
                except OSError:
                    if time.monotonic() >= deadline or proc.poll() is not None:
                        raise RuntimeError('isolated browser did not start')
                    time.sleep(.2)
            print(version, flush=True)
            probe = None
            try:
                probe = check_values(port, out, 'http://127.0.0.1:'
                                     + str(server.server_address[1]), rows)
            except Exception as error:
                rows.append(('检查跑完（没有中途异常）', False, '', repr(error)))
            (out / 'report.json').write_text(json.dumps(
                dict(browser=version, probe=probe,
                     cases=[dict(name=n, passed=p, guards=g, detail=d) for n, p, g, d in rows]),
                ensure_ascii=False, indent=2), encoding='utf-8')
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
        shutil.rmtree(pages, ignore_errors=True)

    for name, passed, guards, detail in rows:
        print(('  ok   ' if passed else '  FAIL ') + name
              + (('  — ' + detail) if detail else ''), flush=True)
    failed = [r for r in rows if not r[1]]
    print('\n' + str(len(rows) - len(failed)) + '/' + str(len(rows))
          + ' 项按预期读出。明细：' + str(out / 'report.json'), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
