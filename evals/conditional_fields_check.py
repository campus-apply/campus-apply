# -*- coding: utf-8 -*-
"""探测阶段就该把条件字段触发出来，而不是填完一轮才发现它们。

真实站点上这样栽过：语言水平那一栏，选了语言类型"英语"之后才冒出"语言考试"和"考试分数"
两个必填框。第一轮探测时它们不在页面上，所以计划里没有它们；执行器填完语言类型就转去填
别的板块，那两个框一直空着，整页提交前才发现。

这里验的是：读取选项不选择分支；真实目标执行后重新观察新增字段。

  python3 evals/conditional_fields_check.py --out /tmp/cond-check [--headless]

Exit 0 = 条件字段在探测阶段就被认出来了。No models, no recruitment sites.
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

PAGE = '''<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>条件字段</title>
<style>body{font:14px system-ui;margin:24px;width:860px}
h3{margin:18px 0 8px}.row{margin:8px 0}label{display:inline-block;width:92px}
input{padding:4px 8px;border:1px solid #bbb;border-radius:4px;width:190px}
.sel{position:relative;display:inline-block}
.panel{position:absolute;z-index:40;background:#fff;border:1px solid #bbb;
       min-width:190px;box-shadow:0 2px 8px rgba(0,0,0,.18)}
.panel .mtd-select-item{padding:6px 12px;cursor:pointer}
.panel .mtd-select-item:hover{background:#f0f6ff}
.hidden{display:none}</style></head>
<body>
<h3>基础信息</h3>
<div class="row"><label>姓名</label><input id="name"></div>

<h3>语言水平</h3>
<div class="row">
  <label>语言类型</label>
  <span class="sel" id="lang-box">
    <input id="lang" readonly placeholder="请选择">
  </span>
</div>
<!-- 选了语言类型才出现的两个必填框：真实站点就是这个形状 -->
<div class="row hidden" id="exam-row">
  <label>语言考试</label><input id="exam" placeholder="请输入">
</div>
<div class="row hidden" id="score-row">
  <label>考试分数</label><input id="score" placeholder="请输入">
</div>

<script>
const OPTIONS = ['英语', '德语', '日语'];
const box = document.getElementById('lang-box');
const input = document.getElementById('lang');
input.addEventListener('click', () => {
  if (box.querySelector('.panel')) return;
  const panel = document.createElement('div');
  panel.className = 'panel';
  panel.innerHTML = OPTIONS.map(o =>
    '<div class="mtd-select-item" role="option">' + o + '</div>').join('');
  panel.querySelectorAll('[role=option]').forEach(d => d.addEventListener('click', () => {
    input.value = d.textContent;
    // 选中任意语言，两个考试字段才出现
    document.getElementById('exam-row').classList.remove('hidden');
    document.getElementById('score-row').classList.remove('hidden');
    panel.remove();
  }));
  box.appendChild(panel);
});
// 本页的既有mousedown/click重建机制保留；外部真实点击可关闭。
document.addEventListener("mousedown", e => { if(!box.contains(e.target))box.querySelectorAll(".panel").forEach(p=>p.remove()); });
// 再点一次输入框收面板
input.addEventListener('mousedown', () => {
  const p = box.querySelector('.panel');
  if (p) { p.remove(); }
}, true);
</script>
</body></html>
'''


def browser_path():
    candidates = [os.environ.get('CA_BROWSER'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                  shutil.which('google-chrome'), shutil.which('chromium')]
    return next((p for p in candidates if p and Path(p).is_file()), None)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def run_cdp(port, out, phase, *args, check=True):
    env = dict(os.environ, CA_CDP_PORT=str(port))
    env.pop('TAB_MARK', None)
    env.pop('TAB_MATCH', None)
    r = subprocess.run([sys.executable, str(CDP), *args], env=env,
                       capture_output=True, text=True, timeout=120)
    (out / (phase + '.out')).write_text(
        r.stdout + ('\n--- stderr ---\n' + r.stderr if r.stderr else ''), encoding='utf-8')
    if check and r.returncode:
        raise RuntimeError(phase + ' exited ' + str(r.returncode) + ': '
                           + (r.stdout + r.stderr).strip()[:400])
    return r


def check(port, out, url, rows):
    mark = 'cond-check'
    run_cdp(port, out, 'open', 'open', url + '/cond.html', mark)

    # 探测之前：两个考试字段还没出现，所以骨架里不该有它们
    before = out / 'skeleton-before.json'
    run_cdp(port, out, 'skeleton_before', '--mark', mark, 'plan-skeleton', str(before))
    fields0 = json.loads(before.read_text(encoding='utf-8'))['fields']
    labels0 = {f['label'] for f in fields0}
    rows.append(('探测前骨架里没有条件字段（它们还没出现在页面上）',
                 '语言考试' not in labels0 and '考试分数' not in labels0,
                 '探到的是：' + '、'.join(sorted(labels0))))

    # probe-options：开下拉、读选项、顺手触发一次
    opts = out / 'options.json'
    r = run_cdp(port, out, 'probe_options', '--mark', mark, 'probe-options', str(opts), '--only', '语言类型',
                check=False)
    report = json.loads(opts.read_text(encoding='utf-8'))
    lang = next((f for f in report['fields'] if f['label'] == '语言类型'), None)
    rows.append(('读回了下拉的全部选项',
                 lang is not None and lang.get('count') == 3,
                 str(lang.get('options') if lang else None)))
    rows.append(('读选项不替agent选分支',
                 (lang or {}).get('branch_selected') is False,
                 'branch_selected=' + str((lang or {}).get('branch_selected'))))
    unchanged = out / 'skeleton-readonly.json'
    run_cdp(port, out, 'skeleton_readonly', '--mark', mark, 'plan-skeleton', str(unchanged))
    fields0 = json.loads(unchanged.read_text(encoding='utf-8'))['fields']
    rows.append(('仅读选项后条件字段仍未出现',
                 not any(f['label'] in ('语言考试','考试分数') for f in fields0), 'readonly observed'))
    field = next(f for f in fields0 if f['label']=='语言类型')
    field.update(kind='dropdown', value='英语', options=(lang or {}).get('options') or [])
    plan_path = out / 'confirmed-language.json'
    plan_path.write_text(json.dumps(dict(fields=[field], pace=dict(min=0,max=0)), ensure_ascii=False), encoding='utf-8')
    filled = run_cdp(port, out, 'actual_choice', '--mark', mark, 'fill', str(plan_path), check=False)
    rows.append(('真实选择后交回观察而不是报写入失败',
                 '"status": "filled"' in filled.stdout and '"needs_observation": true' in filled.stdout,
                 filled.stdout[-150:]))
    after = out / 'skeleton-after.json'
    run_cdp(port, out, 'skeleton_after', '--mark', mark, 'plan-skeleton', str(after))
    labels1 = {f['label'] for f in json.loads(after.read_text(encoding='utf-8'))['fields']}
    rows.append(('真实选择后观察到当前新增字段',
                 '语言考试' in labels1 and '考试分数' in labels1,
                 'observed=' + '、'.join(sorted(labels1))))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
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

    pages = Path(tempfile.mkdtemp(prefix='campus-apply-cond-'))
    (pages / 'cond.html').write_text(PAGE, encoding='utf-8')
    server = ThreadingHTTPServer(('127.0.0.1', 0),
                                 functools.partial(QuietHandler, directory=str(pages)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    rows, proc, report = [], None, None
    profile = tempfile.mkdtemp(prefix='campus-apply-cond-profile-')
    try:
        command = [browser, '--user-data-dir=' + profile,
                   '--remote-debugging-port=' + str(port), '--no-first-run',
                   '--no-default-browser-check', '--disable-background-timer-throttling',
                   '--disable-renderer-backgrounding',
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
                            'http://127.0.0.1:' + str(port) + '/json/version', timeout=1) as resp:
                        version = json.load(resp)['Browser']
                    break
                except OSError:
                    if time.monotonic() >= deadline or proc.poll() is not None:
                        raise RuntimeError('isolated browser did not start')
                    time.sleep(.2)
            print(version, flush=True)
            try:
                report = check(port, out, 'http://127.0.0.1:'
                               + str(server.server_address[1]), rows)
            except Exception as error:
                rows.append(('检查跑完（没有中途异常）', False, repr(error)))
            (out / 'report.json').write_text(json.dumps(
                dict(browser=version, probe=report,
                     cases=[dict(name=n, passed=p, detail=d) for n, p, d in rows]),
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

    for name, passed, detail in rows:
        print(('  ok   ' if passed else '  FAIL ') + name + (('  — ' + detail) if detail else ''),
              flush=True)
    failed = [r for r in rows if not r[1]]
    print('\n' + str(len(rows) - len(failed)) + '/' + str(len(rows))
          + ' 项按预期。明细：' + str(out / 'report.json'), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
