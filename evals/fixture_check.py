#!/usr/bin/env python3
"""Check that every trap in apply_form.html actually fires in a real browser.

The fixture only earns its keep if its traps reproduce the real failures. This script
drives it through the same chrome_cdp.py the skill uses, on an isolated profile and
port, and asserts each trap behaves as documented. No recruitment sites, no models.

  python3 evals/fixture_check.py --out /tmp/fixture-check [--headless]

Exit 0 = every trap reproduced. Exit 1 = a trap did not fire (the fixture is lying,
or the driver changed). Artifacts land under --out, never inside the repo.
"""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
BROWSER_DIR = HERE.parent / 'skills/campus-apply/scripts/browser'
CDP = BROWSER_DIR / 'chrome_cdp.py'


def browser_path():
    import shutil
    candidates = [os.environ.get('CA_BROWSER'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                  shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome')]
    return next((p for p in candidates if p and Path(p).is_file()), None)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class Driver:
    """Runs chrome_cdp.py subcommands and keeps every stdout/stderr/exit code."""

    def __init__(self, port, out, mark):
        self.env = dict(os.environ, CA_CDP_PORT=str(port))
        self.env.pop('TAB_MARK', None)
        self.env.pop('TAB_MATCH', None)
        self.out = out
        self.mark = mark
        self.calls = []

    def run(self, phase, *args, check=True):
        before = time.monotonic()
        result = subprocess.run([sys.executable, str(CDP), *args], env=self.env,
                                capture_output=True, text=True, timeout=40)
        self.calls.append(dict(phase=phase, seconds=round(time.monotonic() - before, 3),
                               exit_code=result.returncode))
        (self.out / (phase + '.out')).write_text(
            result.stdout + ('\n--- stderr ---\n' + result.stderr if result.stderr else ''),
            encoding='utf-8')
        if check and result.returncode:
            raise RuntimeError(phase + ' exited ' + str(result.returncode) + ': '
                               + (result.stdout + result.stderr).strip()[:400])
        return result

    def marked(self, phase, *args, check=True):
        return self.run(phase, '--mark', self.mark, *args, check=check)

    def js(self, phase, expression):
        """Evaluate an expression via exec, which takes a file."""
        path = self.out / (phase + '.js')
        path.write_text(expression, encoding='utf-8')
        return self.marked(phase, 'exec', str(path)).stdout.strip()

    def read_json(self, phase, expression):
        return json.loads(self.js(phase, 'JSON.stringify(' + expression + ')'))


class Report:
    def __init__(self):
        self.rows = []

    def check(self, trap, condition, detail=''):
        self.rows.append(dict(trap=trap, passed=bool(condition), detail=str(detail)[:300]))
        print(('  ok   ' if condition else '  FAIL ') + trap + (('  — ' + str(detail)[:160]) if detail else ''),
              flush=True)

    @property
    def failed(self):
        return [r for r in self.rows if not r['passed']]


def check_traps(driver, url, report):
    mark = driver.mark
    driver.run('open', 'open', url + '/apply_form.html?run=' + mark + '&consent=1&parse=200', mark)

    # --- trap: guard cannot see a position:fixed modal at all ---
    # Root cause of the 反馈7 miss: guard's `offsetParent !== null` test is always false for
    # fixed elements, which is what every real modal overlay uses. Recorded as pending 105.
    guard = json.loads(driver.marked('guard_consent', 'exec', str(BROWSER_DIR / 'guard.js')).stdout)
    seen = driver.read_json(
        'consent_visible',
        '(() => { const m=document.querySelector(".fx-mask"); return m ? {'
        'offsetParent: m.offsetParent !== null, rects: m.getClientRects().length, '
        'checkVisibility: m.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}), '
        'position: getComputedStyle(m).position} : null; })()')
    report.check('隐私弹窗确实挡在页面上（rects>0 且 checkVisibility 为真）',
                 seen and seen['rects'] > 0 and seen['checkVisibility']
                 and seen['position'] == 'fixed',
                 json.dumps(seen, ensure_ascii=False))
    # 这里是 pending 105 的回归点：遮罩是 fixed，offsetParent 恒为假，所以 guard 必须改用
    # checkVisibility 才看得见它；选择器也必须按通用词匹配，不能只枚举几个框架前缀。
    report.check('guard 看得见这个 fixed 遮罩（offsetParent 恒为假，必须靠 checkVisibility）',
                 seen and seen['offsetParent'] is False and guard['visibleModals'] >= 1,
                 'offsetParent=' + str(seen and seen['offsetParent'])
                 + ' visibleModals=' + str(guard['visibleModals']))
    report.check('guard 报出弹窗正文，用户能看到它说的是什么',
                 any('个人信息保护隐私政策' in t for t in (guard.get('modalText') or [])),
                 json.dumps(guard.get('modalText'), ensure_ascii=False))

    # The overlay also swallows every real mouse click, so it has to go before anything else.
    # That is the real-world consequence of not detecting it: the agent clicks into a dead page.
    driver.marked('consent_agree', 'click', '#agree')
    gone = driver.read_json('consent_gone', '!document.querySelector(".fx-mask")')
    report.check('同意后遮罩消失，后续点击才能落到表单上', gone is True, 'gone=' + str(gone))

    # --- trap: probe.required is false although the page shows a red asterisk ---
    probe = json.loads(driver.marked('probe', 'exec', str(BROWSER_DIR / 'probe.js')).stdout)
    by_label = {c['label']: c for c in probe['controls']}
    name_control = next((c for c in probe['controls'] if c['label'].startswith('姓名')), None)
    starred = driver.read_json('starred',
                               '[...document.querySelectorAll(".fx-form-item--must > label")].length')
    report.check('页面有必填星号但 probe.required=false（复刻反馈7 probe 必填漏报）',
                 starred > 0 and name_control is not None and name_control['required'] is False,
                 'starred=' + str(starred) + ' name.required='
                 + str(name_control and name_control['required']))

    # --- trap: the disabled account-level field is reported as such ---
    phone = next((c for c in probe['controls'] if c.get('disabled')), None)
    report.check('账号级手机号字段 disabled 被探出',
                 phone is not None, 'disabled control label=' + str(phone and phone['label']))

    # --- trap: the sensitive field reports length only, never content ---
    driver.js('fill_idcard',
              '(() => { const el=document.getElementById("idcard"); '
              'const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set; '
              'setter.call(el,"110101200001011234"); '
              'el.dispatchEvent(new Event("input",{bubbles:true})); '
              'el.dispatchEvent(new FocusEvent("blur")); return "set"; })()')
    probe2 = json.loads(driver.marked('probe_secret', 'exec', str(BROWSER_DIR / 'probe.js')).stdout)
    idcard = next((c for c in probe2['controls'] if '证件' in c['label']), None)
    report.check('证件号只报长度不报内容',
                 idcard is not None and idcard['valueLen'] == 18
                 and '1101' not in idcard['valuePreview'],
                 'len=' + str(idcard and idcard['valueLen'])
                 + ' preview=' + str(idcard and idcard['valuePreview']))

    # --- trap: the three character limits disagree with each other ---
    statement = next((c for c in probe2['controls'] if '自我描述' in c['label']), None)
    report.check('长文本三层限制互不一致（属性 2000 / 明文 200-1000 / 校验 500）',
                 statement is not None and statement['maxlength'] == '2000'
                 and statement['hintLimit'] == {'min': 200, 'max': 1000},
                 'maxlength=' + str(statement and statement['maxlength'])
                 + ' hintLimit=' + str(statement and statement['hintLimit']))
    long_text = '测' * 600
    driver.js('fill_statement',
              '(() => { const el=document.getElementById("statement"); '
              'const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set; '
              'setter.call(el,' + json.dumps(long_text) + '); '
              'el.dispatchEvent(new Event("input",{bubbles:true})); '
              'el.dispatchEvent(new FocusEvent("blur")); return "set"; })()')
    error = driver.read_json('statement_error', 'document.getElementById("statement-error").textContent')
    report.check('maxlength 属性拦不住脚本写入，真正的 500 字校验在失焦时才报',
                 len(long_text) == 600 and '500' in error, 'error=' + error)

    # --- trap: attached React fiber points at a stale branch after an odd commit ---
    driver.js('fill_name',
              '(() => { const el=document.getElementById("name"); '
              'const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set; '
              'setter.call(el,"瞿某某"); '
              'el.dispatchEvent(new Event("input",{bubbles:true})); '
              'el.dispatchEvent(new FocusEvent("blur")); return "set"; })()')
    naive = driver.read_json(
        'fiber_naive',
        '(() => { const el=document.getElementById("name"); '
        'const key=Object.keys(el).find(k=>k.startsWith("__reactFiber$")); '
        'let f=el[key]; for (let n=0; f && n<16; f=f.return, n++) '
        'if (f.memoizedProps && "value" in f.memoizedProps) return f.memoizedProps.value; '
        'return null; })()')
    active = driver.read_json(
        'fiber_active',
        '(() => { const host=document.getElementById("form"); '
        'const ck=Object.keys(host).find(k=>k.startsWith("__reactContainer$")); '
        'const el=document.getElementById("name"); '
        'let node=host[ck].stateNode.current.child; '
        'while (node) { if (node.stateNode === el) return node.memoizedProps.value; node=node.sibling; } '
        'return null; })()')
    dom_value = driver.read_json('name_dom', 'document.getElementById("name").value')
    report.check('附着 fiber 读到旧值、从 root.current 找活动 fiber 读到新值（复刻反馈7姓名假阳性）',
                 dom_value == '瞿某某' and active == '瞿某某' and naive != '瞿某某',
                 'dom=' + repr(dom_value) + ' attached=' + repr(naive) + ' active=' + repr(active))

    audit = driver.read_json('audit_fiber', 'window.fixtureAudit()')
    report.check('审计能看出附着 fiber 不是当前树里那个',
                 audit['attachedFiberIsCurrent']['name'] is False,
                 'attachedFiberIsCurrent=' + json.dumps(audit['attachedFiberIsCurrent']))

    # --- trap: page-script .click() cannot open the date panel; a real mouse event can ---
    # The panel listens on mousedown, which el.click() never dispatches. This is the
    # "some components only accept mousedown" case in pitfalls.md.
    driver.js('date_synthetic', '(() => { document.getElementById("birth").click(); return "clicked"; })()')
    after_synthetic = driver.read_json('date_panels_synthetic', 'window.fixtureAudit().openPanels')
    driver.marked('date_real', 'click', '#birth')
    after_real = driver.read_json('date_panels_real', 'window.fixtureAudit().openPanels')
    report.check('只读日期框：页面脚本 el.click() 打不开面板，真实鼠标事件才打开',
                 after_synthetic == 0 and after_real == 1,
                 'synthetic=' + str(after_synthetic) + ' real=' + str(after_real))
    driver.marked('date_pick', 'click', 'js:document.querySelector(\'.fx-panel[data-owner="birth"] .fx-select-item\')')
    birth = driver.read_json('birth_value', 'window.fixtureTruth().birth')
    report.check('日期面板选中后收起且写入真值',
                 birth == '2001-02-14'
                 and driver.read_json('panels_after_date', 'window.fixtureAudit().openPanels') == 0,
                 'birth=' + repr(birth))

    # --- trap: a sticky panel stays open until the field's own label is clicked ---
    driver.marked('gender_open', 'click', 'js:document.querySelector(\'[data-dropdown="gender"] .fx-select-input\')')
    driver.marked('gender_pick', 'click', 'js:document.querySelector(\'.fx-panel[data-owner="gender"] .fx-select-item\')')
    still_open = driver.read_json('gender_panels', 'window.fixtureAudit().openPanels')
    report.check('选完值后面板仍开着（不自动收起的那类控件）',
                 still_open == 1, 'openPanels=' + str(still_open))
    driver.marked('gender_close', 'click', 'js:document.querySelector(\'.field[data-key="gender"] > label\')')
    closed = driver.read_json('gender_panels_after', 'window.fixtureAudit().openPanels')
    report.check('点该字段自己的标签能收起面板，整页面板归零',
                 closed == 0, 'openPanels=' + str(closed))

    # --- trap: a searchable dropdown needs the option clicked, typing alone is not selection ---
    driver.marked('city_type', 'type', '#city-search', '北京')
    typed_only = driver.read_json('city_typed', 'window.fixtureTruth().city')
    report.check('可搜索下拉：只打字不点选项，值不算选中',
                 typed_only == '', 'city=' + repr(typed_only))
    driver.marked('city_pick', 'click', 'js:document.querySelector(\'.fx-panel[data-owner="city"] .fx-select-item\')')
    picked = driver.read_json('city_picked', 'window.fixtureTruth().city')
    search_box = driver.read_json('city_search_box', 'document.getElementById("city-search").value')
    report.check('点了选项才算选中，且搜索框清空、值只在显示元素上',
                 picked == '北京市' and search_box == '', 'city=' + repr(picked) + ' box=' + repr(search_box))

    # --- trap: a cascader's second level only appears after the first is clicked ---
    driver.marked('dept_open', 'click', 'js:document.querySelector(\'[data-cascader="dept"] .fx-select-input\')')
    first_only = driver.read_json('dept_cols', 'document.querySelectorAll(".fx-cascader-col").length')
    driver.marked('dept_first', 'click', 'js:document.querySelector(\'.fx-panel[data-owner="dept"] .fx-select-item\')')
    both = driver.read_json('dept_cols2', 'document.querySelectorAll(".fx-cascader-col").length')
    report.check('级联第二级要点过第一级才出现',
                 first_only == 1 and both == 2, 'cols ' + str(first_only) + ' -> ' + str(both))
    driver.marked('dept_leaf', 'click',
                  'js:document.querySelectorAll(\'.fx-panel[data-owner="dept"] .fx-cascader-col\')[1].querySelector(\'.fx-select-item\')')
    dept = driver.read_json('dept_value', 'window.fixtureTruth().dept')
    report.check('级联选到叶子才写入，显示值带两级',
                 dept == '技术线 / 平台研发', 'dept=' + repr(dept))

    # --- trap: a consequential checkbox is already checked by the page ---
    transfer = driver.read_json('transfer', 'window.fixtureTruth().transfer')
    report.check('有后果的开关页面默认已勾选（复刻"接受其他职位调剂"）',
                 transfer is True, 'transfer=' + repr(transfer))

    # --- trap: upload parses, badly, and only into empty fields ---
    sample = driver.out / '虚构简历.pdf'
    sample.write_bytes(b'%PDF-1.4\n% local fixture sample, not a real resume\n')
    driver.marked('upload', 'upload', '#file', str(sample))
    deadline = time.monotonic() + 8
    parsed = False
    while time.monotonic() < deadline:
        if driver.read_json('upload_audit', 'window.fixtureAudit().parsed'):
            parsed = True
            break
        time.sleep(.2)
    after = driver.read_json('after_parse', 'window.fixtureSnapshot()')
    report.check('代传触发上传与解析',
                 parsed and after['truth']['resume'] == '虚构简历.pdf',
                 'parsed=' + str(parsed) + ' resume=' + repr(after['truth']['resume']))
    report.check('解析不覆盖已填字段（姓名保持我们写入的值）',
                 after['dom']['name'] == '瞿某某', 'name=' + repr(after['dom']['name']))
    report.check('解析填进空字段且质量很差，只能当占位（邮箱全大写）',
                 after['dom']['email'] == 'ZHANG.MOU@EXAMPLE.COM', 'email=' + repr(after['dom']['email']))

    # --- trap: stash writes a draft that survives a reload ---
    driver.marked('stash', 'click', '#stash')
    driver.js('reload', 'location.reload(); "reload"')
    deadline = time.monotonic() + 8
    restored = None
    while time.monotonic() < deadline:
        try:
            restored = driver.read_json('after_reload', 'window.fixtureSnapshot()')
            if restored['truth']['name']:
                break
        except (RuntimeError, ValueError):
            pass
        time.sleep(.2)
    report.check('暂存后刷新，值从草稿里恢复（保存回读这条路能走通）',
                 restored is not None and restored['truth']['name'] == '瞿某某'
                 and restored['truth']['city'] == '北京市'
                 and restored['truth']['dept'] == '技术线 / 平台研发',
                 json.dumps(restored and restored['truth'], ensure_ascii=False)[:200])

    # --- trap: the submit button is never pressed by the harness ---
    final_audit = driver.read_json('final_audit', 'window.fixtureAudit()')
    report.check('全程没有点过投递按钮',
                 final_audit['submitClicked'] == 0, 'submitClicked=' + str(final_audit['submitClicked']))
    report.check('结束时打开的面板为零',
                 final_audit['openPanels'] == 0, 'openPanels=' + str(final_audit['openPanels']))
    return driver.read_json('final_snapshot', 'window.fixtureSnapshot()')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='artifact directory, outside this repo')
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args(argv)
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
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    report = Report()
    proc = None
    driver = None
    # Chrome keeps writing into its profile as it exits, so a context manager's cleanup races
    # with it and raises "Directory not empty". Remove it ourselves, after the process is gone.
    profile = tempfile.mkdtemp(prefix='campus-apply-fixture-')
    try:
        if True:
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
                url = 'http://127.0.0.1:' + str(server.server_address[1])
                driver = Driver(port, out, 'fixture-check')
                snapshot = None
                try:
                    snapshot = check_traps(driver, url, report)
                except Exception as error:
                    # A crash mid-way is itself a finding; keep the partial report.
                    report.check('检查跑完（没有中途异常）', False, repr(error))
                (out / 'report.json').write_text(json.dumps(
                    dict(browser=version, traps=report.rows, calls=driver.calls,
                         call_count=len(driver.calls), snapshot=snapshot),
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
        import shutil
        shutil.rmtree(profile, ignore_errors=True)

    passed = len(report.rows) - len(report.failed)
    calls = len(driver.calls) if driver else 0
    print('\n' + str(passed) + '/' + str(len(report.rows)) + ' 个坑按预期复现；'
          + str(calls) + ' 次工具调用。明细：' + str(out / 'report.json'), flush=True)
    return 1 if report.failed else 0


if __name__ == '__main__':
    sys.exit(main())
