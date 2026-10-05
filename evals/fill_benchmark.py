#!/usr/bin/env python3
"""Fill the whole fixture page two ways and compare: one `fill` call vs per-field stage scripts.

This is the measurement that justifies the `fill` executor. The "stage" arm imitates what the
agent actually did during the 2026-10-04 Meituan POC: write a one-off JS file per field, run it,
read back. The "fill" arm hands over one plan JSON. Same page, same target values, same browser.

  python3 evals/fill_benchmark.py --out /private/fill-bench [--headless] [--repeats 3]

Both arms must reach the same verified end state, or the comparison is void. No models, no
recruitment sites; isolated profile and port. Artifacts land under --out, outside the repo.
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

# One target state, used by both arms and by the oracle. The two sensitive fields carry
# sensitive_ok because a speed comparison is only valid if both arms write the same set —
# and because the allow-path needs covering too; real plans leave them to the user.
TARGET = dict(wish1='AI产品岗', dept=['技术线', '平台研发'], city='北京市', gender='男',
              name='瞿某某', email='wenkai@example.com', idcard='110101200001011234',
              birth='2001-02-14', statement='测' * 300, transfer=False)
EXPECTED_TRUTH = dict(TARGET, dept='技术线 / 平台研发')

PLAN = {
    'addressing': 'selector',          # fixture plans use selector + index by design
    # options_unverified: this measures how fast the two arms write the same values, not where
    # the values came from. The source gate (panel fields must carry a probed options table)
    # is what option_shapes_check covers; mixing the two would make this timing depend on it.
    'options_unverified': True,
    'pace': {'min': 0.05, 'max': 0.12},
    'panel_wait': 2.0,
    'option_wait': 2.0,
    'fields': [
        dict(key='wish1', label='第一志愿', kind='dropdown',
             selector='[data-dropdown="wish1"] .fx-select-input', value=TARGET['wish1'],
             display_selector='[data-display="wish1"]'),
        dict(key='dept', label='意向部门', kind='cascader',
             selector='[data-cascader="dept"] .fx-select-input', value=TARGET['dept'],
             display_selector='[data-display="dept"]'),
        dict(key='city', label='意向城市', kind='search', selector='#city-search',
             term='北京', value=TARGET['city'], display_selector='[data-display="city"]'),
        dict(key='transfer', label='接受其他职位调剂', kind='checkbox',
             selector='#transfer', value=TARGET['transfer']),
        dict(key='name', label='姓名', kind='text', selector='#name', value=TARGET['name']),
        dict(key='gender', label='性别', kind='dropdown',
             selector='[data-dropdown="gender"] .fx-select-input', value=TARGET['gender'],
             display_selector='[data-display="gender"]'),
        dict(key='email', label='邮箱', kind='text', selector='#email', value=TARGET['email']),
        dict(key='idcard', label='证件号码', kind='text', selector='#idcard',
             value=TARGET['idcard'], sensitive_ok=True),
        dict(key='birth', label='出生日期', kind='date', selector='#birth', value=TARGET['birth'],
             display_selector='[data-display="birth"]', sensitive_ok=True),
        dict(key='statement', label='自我描述', kind='text', selector='#statement',
             value=TARGET['statement'], max=500),
    ],
}


def browser_path():
    candidates = [os.environ.get('CA_BROWSER'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                  shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome')]
    return next((p for p in candidates if p and Path(p).is_file()), None)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class Arm:
    """Runs one arm and counts every driver invocation."""

    def __init__(self, port, out, mark):
        self.env = dict(os.environ, CA_CDP_PORT=str(port))
        self.env.pop('TAB_MARK', None)
        self.env.pop('TAB_MATCH', None)
        self.out = out
        self.mark = mark
        self.calls = []
        out.mkdir(parents=True, exist_ok=True)

    def run(self, phase, *args, check=True):
        before = time.monotonic()
        result = subprocess.run([sys.executable, str(CDP), *args], env=self.env,
                                capture_output=True, text=True, timeout=180)
        self.calls.append(dict(phase=phase, seconds=round(time.monotonic() - before, 3),
                               exit_code=result.returncode))
        (self.out / (phase + '.out')).write_text(
            result.stdout + ('\n--- stderr ---\n' + result.stderr if result.stderr else ''),
            encoding='utf-8')
        if check and result.returncode:
            raise RuntimeError(phase + ' exited ' + str(result.returncode) + ': '
                               + (result.stdout + result.stderr).strip()[:600])
        return result

    def marked(self, phase, *args, **kw):
        return self.run(phase, '--mark', self.mark, *args, **kw)

    def read_json(self, phase, expression):
        path = self.out / (phase + '.js')
        path.write_text('JSON.stringify(' + expression + ')', encoding='utf-8')
        return json.loads(self.marked(phase, 'exec', str(path)).stdout.strip())


# --- arm 1: one fill call ------------------------------------------------------------------
def arm_fill(arm, url):
    arm.run('open', 'open', url, arm.mark)
    plan = arm.out / 'plan.json'
    plan.write_text(json.dumps(PLAN, ensure_ascii=False, indent=1), encoding='utf-8')
    arm.marked('fill', 'fill', str(plan), '--max', '90')


# --- arm 2: a one-off stage script per field, as the POC actually did ----------------------
STAGE_TEXT = """(async () => {
 const L = window.__ca.L;
 const el = document.querySelector(%(sel)s);
 if (!el) { L('ERR 找不到控件'); return; }
 const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
 Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, %(val)s);
 el.dispatchEvent(new Event('input', {bubbles:true}));
 el.dispatchEvent(new Event('change', {bubbles:true}));
 el.dispatchEvent(new FocusEvent('blur'));
 el.dispatchEvent(new FocusEvent('focusout', {bubbles:true}));
 await new Promise(r => setTimeout(r, 80));
 L(el.value === %(val)s ? 'DONE' : 'ERR 回读不一致');
})()"""

STAGE_PICK = """(async () => {
 const L = window.__ca.L;
 const input = document.querySelector(%(sel)s);
 if (!input) { L('ERR 找不到控件'); return; }
 input.click();
 await new Promise(r => setTimeout(r, 250));
 const items = [...document.querySelectorAll('.fx-panel .fx-select-item')]
   .filter(e => e.innerText.trim() === %(val)s);
 if (!items.length) { L('ERR 面板里没有这一项'); return; }
 items[0].click();
 await new Promise(r => setTimeout(r, 200));
 const shown = document.querySelector(%(disp)s);
 const text = shown.tagName === 'INPUT' ? shown.value : shown.textContent;
 L(text.trim() === %(val)s ? 'DONE' : 'ERR 显示值不对：' + text);
})()"""


def arm_stage(arm, url):
    arm.run('open', 'open', url, arm.mark)
    step = 0

    def stage(name, body):
        nonlocal step
        step += 1
        path = arm.out / ('stage%02d-%s.js' % (step, name))
        path.write_text(body, encoding='utf-8')
        arm.marked('stage%02d-%s' % (step, name), 'stage', str(path),
                   '--libs', str(BROWSER_DIR / 'lib_antd3.js'), '--max', '15')

    # Plain dropdowns: page-script click works on these, which is why the POC used stage for them.
    stage('wish1', STAGE_PICK % dict(sel=json.dumps('[data-dropdown="wish1"] .fx-select-input'),
                                     val=json.dumps(TARGET['wish1']),
                                     disp=json.dumps('[data-display="wish1"]')))
    # Cascader needs two levels, so it took two scripts plus a panel-closing one.
    stage('dept-level1', """(async () => {
 const L = window.__ca.L;
 document.querySelector('[data-cascader="dept"] .fx-select-input').click();
 await new Promise(r => setTimeout(r, 250));
 const first = [...document.querySelectorAll('.fx-panel .fx-select-item')]
   .find(e => e.innerText.trim() === %(a)s);
 if (!first) { L('ERR 第一级没有这一项'); return; }
 first.click();
 await new Promise(r => setTimeout(r, 200));
 L('DONE');
})()""" % dict(a=json.dumps(TARGET['dept'][0])))
    stage('dept-level2', """(async () => {
 const L = window.__ca.L;
 const cols = [...document.querySelectorAll('.fx-panel .fx-cascader-col')];
 if (cols.length < 2) { L('ERR 第二级没出现'); return; }
 const leaf = [...cols[1].querySelectorAll('.fx-select-item')]
   .find(e => e.innerText.trim() === %(b)s);
 if (!leaf) { L('ERR 第二级没有这一项'); return; }
 leaf.click();
 await new Promise(r => setTimeout(r, 200));
 const shown = document.querySelector('[data-display="dept"]');
 L(shown.value.includes(%(b)s) ? 'DONE' : 'ERR 显示值不对：' + shown.value);
})()""" % dict(b=json.dumps(TARGET['dept'][1])))
    # Searchable dropdown: type, wait for suggestions, click the exact option.
    stage('city', """(async () => {
 const L = window.__ca.L;
 const input = document.querySelector('#city-search');
 Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, '北京');
 input.dispatchEvent(new Event('input', {bubbles:true}));
 await new Promise(r => setTimeout(r, 250));
 const hit = [...document.querySelectorAll('.fx-panel .fx-select-item')]
   .find(e => e.innerText.trim() === %(val)s);
 if (!hit) { L('ERR 建议项里没有目标城市'); return; }
 hit.click();
 await new Promise(r => setTimeout(r, 200));
 L(document.querySelector('[data-display="city"]').textContent.trim() === %(val)s
   ? 'DONE' : 'ERR 显示值不对');
})()""" % dict(val=json.dumps(TARGET['city'])))
    stage('transfer', """(async () => {
 const L = window.__ca.L;
 const box = document.querySelector('#transfer');
 if (box.checked !== %(want)s) box.click();
 await new Promise(r => setTimeout(r, 80));
 L(box.checked === %(want)s ? 'DONE' : 'ERR 勾选状态没改成');
})()""" % dict(want='true' if TARGET['transfer'] else 'false'))
    stage('name', STAGE_TEXT % dict(sel=json.dumps('#name'), val=json.dumps(TARGET['name'])))
    # The sticky panel needs its own closing script, which is exactly the kind of extra
    # round trip the POC kept paying for.
    stage('gender', STAGE_PICK % dict(sel=json.dumps('[data-dropdown="gender"] .fx-select-input'),
                                      val=json.dumps(TARGET['gender']),
                                      disp=json.dumps('[data-display="gender"]')))
    arm.marked('close-gender-panel', 'click',
               'js:document.querySelector(\'.field[data-key="gender"] > label\')')
    stage('email', STAGE_TEXT % dict(sel=json.dumps('#email'), val=json.dumps(TARGET['email'])))
    stage('idcard', STAGE_TEXT % dict(sel=json.dumps('#idcard'), val=json.dumps(TARGET['idcard'])))
    # The date panel only listens on mousedown, so stage cannot open it: real mouse event needed.
    arm.marked('birth-open', 'click', '#birth')
    stage('birth-pick', """(async () => {
 const L = window.__ca.L;
 const hit = [...document.querySelectorAll('.fx-panel[data-owner="birth"] .fx-select-item')]
   .find(e => e.innerText.trim() === %(val)s);
 if (!hit) { L('ERR 日期面板里没有这一天'); return; }
 hit.click();
 await new Promise(r => setTimeout(r, 200));
 L(document.querySelector('[data-display="birth"]').value === %(val)s ? 'DONE' : 'ERR 显示值不对');
})()""" % dict(val=json.dumps(TARGET['birth'])))
    stage('statement', STAGE_TEXT % dict(sel=json.dumps('#statement'),
                                         val=json.dumps(TARGET['statement'])))


def verify(arm, label):
    """Independent oracle: read the page's own truth and audit, assert the same end state."""
    truth = arm.read_json('verify-truth', 'window.fixtureTruth()')
    audit = arm.read_json('verify-audit', 'window.fixtureAudit()')
    problems = []
    for key, want in EXPECTED_TRUTH.items():
        got = truth.get(key)
        if got != want:
            problems.append(key + ': 期望 ' + repr(want)[:40] + '，实际 ' + repr(got)[:40])
    if audit['openPanels']:
        problems.append('还有 %d 个面板开着' % audit['openPanels'])
    if audit['submitClicked']:
        problems.append('点过投递按钮 %d 次' % audit['submitClicked'])
    return dict(label=label, verified=not problems, problems=problems, truth=truth, audit=audit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='artifact directory, outside this repo')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 10:
        parser.error('--repeats must be 1..10')
    browser = browser_path()
    if not browser:
        parser.error('Chrome/Edge not found; set CA_BROWSER')
    out = Path(args.out).resolve()
    if out.is_relative_to(HERE.parent):
        parser.error('--out must be outside the repository')
    out.mkdir(parents=True, exist_ok=True)

    handler = functools.partial(QuietHandler, directory=str(HERE / 'fixtures'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    proc = None
    profile = tempfile.mkdtemp(prefix='campus-apply-fillbench-')
    results = []
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
                            'http://127.0.0.1:' + str(port) + '/json/version', timeout=1) as response:
                        version = json.load(response)['Browser']
                    break
                except OSError:
                    if time.monotonic() >= deadline or proc.poll() is not None:
                        raise RuntimeError('isolated browser did not start')
                    time.sleep(.2)
            print(version, flush=True)
            base = 'http://127.0.0.1:' + str(server.server_address[1]) + '/apply_form.html'
            for i in range(args.repeats):
                # Alternate order so warm-up does not favour one arm.
                arms = [('fill', arm_fill), ('stage', arm_stage)]
                if i % 2:
                    arms.reverse()
                for name, runner in arms:
                    label = name + '-' + str(i)
                    arm = Arm(port, out / label, label)
                    started = time.monotonic()
                    error = None
                    try:
                        runner(arm, base + '?run=' + label)
                    except Exception as exc:          # a failed arm is a result, not a crash
                        error = str(exc)[:400]
                    elapsed = time.monotonic() - started
                    check = verify(arm, label)
                    record = dict(variant=name, run=i, elapsed_seconds=round(elapsed, 3),
                                  driver_calls=len(arm.calls), error=error, **check)
                    (arm.out / 'result.json').write_text(
                        json.dumps(dict(record, calls=arm.calls), ensure_ascii=False, indent=1),
                        encoding='utf-8')
                    results.append(record)
                    print('%-6s run%d  %5.2fs  %2d 次调用  %s%s'
                          % (name, i, elapsed, len(arm.calls),
                             '一致' if check['verified'] else '不一致: ' + '; '.join(check['problems'])[:120],
                             ('  [错误] ' + error) if error else ''), flush=True)
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

    def median(values):
        values = sorted(values)
        return values[len(values) // 2] if values else None

    summary = {}
    for name in ('fill', 'stage'):
        rows = [r for r in results if r['variant'] == name]
        good = [r for r in rows if r['verified']]
        summary[name] = dict(runs=len(rows), verified=len(good),
                             median_seconds=median([r['elapsed_seconds'] for r in rows]),
                             median_calls=median([r['driver_calls'] for r in rows]))
    report = dict(browser=version, headless=args.headless, repeats=args.repeats,
                  models_used=False, fields=len(PLAN['fields']),
                  scope='local fixture, driver path only; excludes browser startup and any model time',
                  summary=summary, results=results)
    (out / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                         encoding='utf-8')
    print('\n' + json.dumps(summary, ensure_ascii=False, indent=1), flush=True)
    both_ok = all(s['verified'] == s['runs'] and s['runs'] for s in summary.values())
    if not both_ok:
        print('两条路径没有都达到同一个已核验的终态，这次对照不成立。', flush=True)
    print('明细：' + str(out / 'comparison.json'), flush=True)
    return 0 if both_ok else 1


if __name__ == '__main__':
    sys.exit(main())
