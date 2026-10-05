#!/usr/bin/env python3
"""Check `fill` against the three panel shapes that real sites actually serve.

`fixtures/apply_form.html` only has one panel shape — body-mounted, 2px under the input,
removed on pick — and that happens to be the one shape the old executor could handle, so
no bug fixture built on it could ever fail. The shapes below came out of two real-site
regression runs on 2026-10-05, and each one broke the executor a different way:

  形状 A  真面板被同样命中选择器的祖先容器吞掉   实测报 点了之后 N 秒内没出现面板
  形状 B  面板盖在输入框上，被几何配对扔掉       实测报 点了之后 N 秒内没出现面板
  形状 C  行内常驻的假容器被当成面板             实测报 ERR_PANELS，数字等于假容器个数
  收面板   有效的那一招两站完全相反（待处理 124） 一站只认再点输入框，另一站只认点板块标题

**每个 case 判的是"应该怎样"，不是"现在怎样"**：面板找得到、字段填成、面板收干净、退出 0。
所以在面板逻辑改好之前这个脚本是红的，这是故意的。每条红的同时会把当时的失败原文和
`regression` 里记的真站签名比一遍：对得上就是"复现了已知的坑"，对不上就是出现了新的死法，
两种都会打出来。反过来，某个形状**意外变绿**也要看一眼——可能是真修好了，也可能是 fixture
没复刻出那个结构，所以脚本会连几何证据一起存进 report.json 供对账。

收面板那一组里有一个正例控件（只认"再点一次输入框"的那个）今天就该成功，它是护栏：
改面板逻辑时把它弄坏了，这里立刻能看见。

  python3 evals/panel_shape_check.py --out /private/panel-shapes [--headless]

Exit 0 = 四种形状都按"应该怎样"跑通了。No models, no recruitment sites: the only page it
opens is the local fixture.
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

FILLERS = 77            # 实测：行内常驻假容器在真实站点上就是 77 个，空表时也是 77 个

# 面板形状的几何证据。纯 DOM，不调执行器的任何内部接口——那套接口正是要改的东西，
# 证据脚本不能跟着它一起变，否则改完就对不了账。
#
# CLASS_LISTING 是"按 class 全局列举面板"的那种选择器（老 PANEL_SEL 的形状）。这里不是
# 在测某一版代码，而是在证明 fixture 真的有那个结构：真面板的祖先也命中同一套词。
DIAGNOSE_JS = r'''
JSON.stringify((() => {
  const CLASS_LISTING = '[role="listbox"],[role="menu"],[role="dialog"],[role="tree"],'
    + '[class*="dropdown"],[class*="Dropdown"],[class*="select-panel"],[class*="picker"],'
    + '[class*="Picker"],[class*="cascader"],[class*="Cascader"],[class*="calendar"],'
    + '[class*="Calendar"],[class*="menus"],[class*="popper"],[class*="popover"],[class*="panel"]';
  const big = el => {
    const r = el.getBoundingClientRect();
    return r.width >= 20 && r.height >= 10;
  };
  const shown = el => el.isConnected
    && el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const anchor = document.querySelector(ANCHOR);
  const real = REAL ? document.querySelector(REAL) : null;
  const a = anchor ? anchor.getBoundingClientRect() : null;
  const r = real ? real.getBoundingClientRect() : null;
  // 按 class 列举会收下多少个节点（可见且够大）——形状 C 的 ERR_PANELS 数字就是这个
  const listed = [...document.querySelectorAll(CLASS_LISTING)].filter(el => shown(el) && big(el));
  const outermost = listed.filter(el => !listed.some(o => o !== el && o.contains(el)));
  // 真面板是不是被某个"也命中同一套 class 词"的祖先顶掉的（形状 A 的致命一条）
  let swallowedBy = null;
  if (real) for (let up = real.parentElement; up && up !== document.body; up = up.parentElement) {
    if (up.matches(CLASS_LISTING) && shown(up) && big(up)) {
      swallowedBy = {cls: (up.className || '').replace(/\s+/g, ' ').trim().slice(0, 80)};
      break;
    }
  }
  // _panel_for 旧版几何配对的两个量：纵向 gap 与横向是否重叠
  const gap = (a && r) ? Math.min(Math.abs(r.y - (a.y + a.height)), Math.abs(a.y - (r.y + r.height))) : null;
  return {
    realPanelExists: !!real,
    realPanelVisible: !!real && shown(real) && big(real),
    // 按 class 列举时，真面板本身有没有被留下（形状 B 真站实测 keptItself:true）
    keptItself: !!real && outermost.includes(real),
    swallowedBy: swallowedBy,
    listedCount: listed.length,
    outermostCount: outermost.length,
    fakeContainers: document.querySelectorAll('[class*="sd-Dropdown-container"]').length,
    anchorRect: a ? {x: Math.round(a.x), y: Math.round(a.y),
                     w: Math.round(a.width), h: Math.round(a.height)} : null,
    panelRect: r ? {x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)} : null,
    gap: gap === null ? null : Math.round(gap),
    horizontalOverlap: (a && r) ? !(r.x > a.x + a.width || r.x + r.width < a.x) : null,
    panelCoversAnchorCentre: (a && r)
      ? (r.x <= a.x + a.width / 2 && r.x + r.width >= a.x + a.width / 2
         && r.y <= a.y + a.height / 2 && r.y + r.height >= a.y + a.height / 2) : null,
  };
})())
'''

# 每个 case：
#   query/fields   打开哪一组、拿什么计划去填
#   expect_keys    这些字段必须 status=filled（判据，不是现状）
#   regression     真站当时报的那句原文；红的时候用来确认"复现的是已知的坑"
#   shape_evidence fixture 真的有这个结构的几何证据；缺了就是 fixture 没复刻对
#   anchor/real    几何证据取哪两个元素
CASES = [
    dict(name='形状 A：真面板是常驻容器的后代',
         query='shape=a',
         fields=[dict(key='a-city', label='意向城市', kind='dropdown',
                      selector='#ps-a-city', value='上海市',
                      display_selector='[data-display="a-city"]')],
         expect_keys=['a-city'],
         regression='没出现面板',
         anchor='#ps-a-city', real='.sd-Dropdown-dropdown-1CigZ',
         shape_evidence=[
             ('真面板开得出来且可见', lambda d: d['realPanelExists'] and d['realPanelVisible']),
             ('真面板有个也命中 class 列举的祖先容器',
              lambda d: 'sd-Dropdown-container' in ((d['swallowedBy'] or {}).get('cls') or '')),
             ('按 class 列举时真面板被祖先顶掉（留下的是容器，不是它）',
              lambda d: not d['keptItself']),
         ]),
    dict(name='形状 B：面板盖在输入框上',
         query='shape=b',
         # sensitive_ok：出生日期被归进默认不写的敏感字段，这里的值是编的，而且这一组考的是
         # 面板几何不是敏感字段门槛，所以显式开。门槛本身另有测试守。
         fields=[dict(key='b-birth', label='出生日期', kind='date',
                      selector='#ps-b-birth', value='2002-07-03',
                      display_selector='[data-display="b-birth"]', sensitive_ok=True)],
         expect_keys=['b-birth'],
         regression='没出现面板',
         anchor='#ps-b-birth', real='.ant-calendar-picker-container',
         shape_evidence=[
             ('真面板开得出来且可见', lambda d: d['realPanelExists'] and d['realPanelVisible']),
             ('按 class 列举收得到它本身（真站实测 keptItself:true）', lambda d: d['keptItself']),
             # 实测 gap 正是 35：输入框 h=32 底边 475、面板 y=440，min(|440-475|,|443-781|)=35
             ('纵向 gap 是实测的 35（> 24，旧的几何配对会扔掉它）', lambda d: d['gap'] == 35),
             ('输入框尺寸是实测的 131×32', lambda d: (d['anchorRect'] or {}).get('w') == 131
                                                   and (d['anchorRect'] or {}).get('h') == 32),
             ('面板尺寸是实测的 280×341', lambda d: (d['panelRect'] or {}).get('w') == 280
                                                  and (d['panelRect'] or {}).get('h') == 341),
             ('面板盖住了输入框中心点', lambda d: d['panelCoversAnchorCentre'] is True),
         ]),
    dict(name='形状 C：行内常驻假容器 %d 个' % FILLERS,
         query='shape=c&fillers=%d' % FILLERS,
         fields=[dict(key='c-name', label='姓名', kind='text',
                      selector='#ps-c-name', value='张三')],
         expect_keys=['c-name'],
         regression='ERR_PANELS',
         anchor='#ps-c-name', real=None,
         shape_evidence=[
             ('页面上确实有 %d 个常驻假容器' % FILLERS, lambda d: d['fakeContainers'] == FILLERS),
             ('按 class 列举会把这 %d 个全收下' % FILLERS, lambda d: d['outermostCount'] == FILLERS),
         ]),
    dict(name='收面板脾气：两个控件认的招正好相反',
         query='shape=close',
         fields=[dict(key='close-reclick', label='第一志愿', kind='dropdown',
                      selector='#ps-close-reclick', value='产品运营岗',
                      display_selector='[data-display="close-reclick"]'),
                 dict(key='close-section', label='意向部门', kind='dropdown',
                      selector='#ps-close-section', value='商业线',
                      display_selector='[data-display="close-section"]')],
         expect_keys=['close-reclick', 'close-section'],
         regression='收不起来',
         anchor='#ps-close-section', real='.ant-select-dropdown',
         shape_evidence=[
             # 这一组的结构证据是"脾气真的相反"，在 check_temper() 里单独验：
             # 执行器知道的三招对 close-section 全废，而点板块标题一下就收掉。
         ]),
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


def fill_report(stdout):
    """fill 的 stdout 是逐字段的行 + 一行 --- + 完整 JSON。把 JSON 那段取出来。"""
    _, sep, tail = stdout.partition('\n---\n')
    if not sep:
        return {}
    try:
        return json.loads(tail[:tail.rindex('}') + 1])
    except (ValueError, IndexError):
        return {}


def row_of(report, key):
    return next((r for r in (report.get('fields') or []) if r.get('key') == key), {})


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

    server = ThreadingHTTPServer(('127.0.0.1', 0),
                                 functools.partial(QuietHandler, directory=str(HERE / 'fixtures')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    rows = []
    proc = None
    profile = tempfile.mkdtemp(prefix='campus-apply-panelshape-')
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
            base = 'http://127.0.0.1:' + str(server.server_address[1]) + '/panel_shapes.html?'
            env = dict(os.environ, CA_CDP_PORT=str(port))
            env.pop('TAB_MARK', None)
            env.pop('TAB_MATCH', None)

            def cdp(case_dir, phase, *cdp_args, timeout=120):
                result = subprocess.run([sys.executable, str(CDP), *cdp_args],
                                        env=env, capture_output=True, text=True, timeout=timeout)
                (case_dir / (phase + '.out')).write_text(
                    result.stdout + ('\n--- stderr ---\n' + result.stderr if result.stderr else ''),
                    encoding='utf-8')
                return result

            def js(case_dir, mark, phase, source):
                path = case_dir / (phase + '.js')
                path.write_text(source, encoding='utf-8')
                raw = cdp(case_dir, phase, '--mark', mark, 'exec', str(path), timeout=60).stdout.strip()
                try:
                    return json.loads(raw)
                except ValueError:
                    return None

            def diagnose(case_dir, mark, phase, case):
                source = DIAGNOSE_JS.replace('ANCHOR', json.dumps(case['anchor'])).replace(
                    'REAL', json.dumps(case['real']) if case['real'] else 'null')
                return js(case_dir, mark, phase, source) or {}

            def check_temper(case_dir, mark, audit, report, problems):
                """收面板那一组：正例必须成、反例的脾气必须真的相反。"""
                good, bad = row_of(report, 'close-reclick'), row_of(report, 'close-section')
                if good.get('closed_by') not in (None, 'click-input-again'):
                    problems.append('正例控件不是靠"再点一次输入框"收掉的：%s' % good.get('closed_by'))
                tries = (audit.get('closeTries') or {}).get('close-section') or {}
                # 反例身上，执行器知道的几招必须真的都试过（试了才知道无效）
                if bad.get('status') != 'filled' and not tries:
                    problems.append('反例控件上一招都没试过：%s' % json.dumps(tries, ensure_ascii=False))
                # fixture 自己的脾气：点板块标题必须一下就收掉，否则"两站相反"没做出来
                before = audit.get('openPanels')
                cdp(case_dir, 'click_section', '--mark', mark, 'click', '.ps-section-title', timeout=60)
                after = js(case_dir, mark, 'audit_after', 'JSON.stringify(window.fixtureAudit())') or {}
                worked = (after.get('closeTries') or {}).get('close-section') or {}
                return dict(close_tries_during_fill=tries, open_panels_after_fill=before,
                            close_tries_after_section_click=worked,
                            open_panels_after_section_click=after.get('openPanels'),
                            section_click_closes=bool(worked.get('click-section-title'))
                                                 and not after.get('openPanels'))

            for index, case in enumerate(CASES):
                mark = 'shape-%02d' % index
                case_dir = out / mark
                case_dir.mkdir(parents=True, exist_ok=True)
                cdp(case_dir, 'open', 'open', base + case['query'] + '&run=' + mark, mark, timeout=60)

                # 填之前先量一次：形状 C 的判据是"和开没开面板无关"，所以空表时的数要先记下来
                before = diagnose(case_dir, mark, 'diagnose_before', case)

                plan = case_dir / 'plan.json'
                plan.write_text(json.dumps({'fields': case['fields'],
                                            'pace': {'min': .02, 'max': .05},
                                            'addressing': 'selector'},
                                           ensure_ascii=False, indent=1), encoding='utf-8')
                result = cdp(case_dir, 'fill', '--mark', mark, 'fill', str(plan), '--max', '40')
                output = result.stdout + result.stderr
                report = fill_report(result.stdout)
                audit = js(case_dir, mark, 'audit', 'JSON.stringify(window.fixtureAudit())') or {}

                # ---- 判据：应该怎样 ----
                problems = []
                if result.returncode != 0:
                    problems.append('退出码 %s，期望 0' % result.returncode)
                for key in case['expect_keys']:
                    row = row_of(report, key)
                    if row.get('status') != 'filled':
                        problems.append('%s 没填成（status=%s%s）'
                                        % (key, row.get('status'),
                                           '，' + row['why'] if row.get('why') else ''))
                if report.get('open_panels'):
                    problems.append('收尾时还报 %s 个面板开着' % report['open_panels'])
                if audit.get('openPanels'):
                    problems.append('页面上真的还有 %s 个面板没收' % audit['openPanels'])
                if audit.get('submitClicked'):
                    problems.append('点过投递按钮')

                # ---- fixture 真的有这个形状吗 ----
                # 开着面板时量的那一份才看得到真面板，所以用"填之前"和"刚点开"两份里有证据的那份。
                evidence = before
                if case['real'] and not before.get('realPanelExists'):
                    # 面板选完就收了，事后量不到。重开一次页面、真实鼠标点一下输入框再量。
                    cdp(case_dir, 'reopen_page', 'open',
                        base + case['query'] + '&run=' + mark + '-ev', mark + '-ev', timeout=60)
                    cdp(case_dir, 'reopen_click', '--mark', mark + '-ev', 'click',
                        case['anchor'], timeout=60)
                    evidence = diagnose(case_dir, mark + '-ev', 'diagnose_open', case)
                shape_missing = [why for why, test in case['shape_evidence']
                                 if not test({**{'realPanelExists': False, 'realPanelVisible': False,
                                                 'keptItself': False, 'swallowedBy': None,
                                                 'listedCount': 0, 'outermostCount': 0,
                                                 'fakeContainers': 0, 'gap': None,
                                                 'panelCoversAnchorCentre': None}, **evidence})]

                temper = None
                if case['query'].startswith('shape=close'):
                    temper = check_temper(case_dir, mark, audit, report, problems)
                    if not temper['section_click_closes']:
                        shape_missing.append('点板块标题没把面板收掉，"两站相反"的脾气没做出来')

                passed = not problems and not shape_missing
                # 红的时候：这次的失败原文和真站签名对得上吗
                reproduced = (not passed) and case['regression'] in output
                rows.append(dict(case=case['name'], passed=passed,
                                 exit_code=result.returncode, problems=problems,
                                 fixture_shape_missing=shape_missing,
                                 regression=case['regression'], regression_reproduced=reproduced,
                                 open_panels_reported=report.get('open_panels'),
                                 fields=report.get('fields'), evidence=evidence,
                                 audit=audit, temper=temper, output=output))

                if passed:
                    print('  ok   ' + case['name'], flush=True)
                else:
                    print('  FAIL ' + case['name'] + '  — ' + '；'.join(problems + shape_missing),
                          flush=True)
                    if shape_missing:
                        print('       ↑ fixture 没复刻出这个结构，要调 fixture，不是放过它', flush=True)
                    print('       真站签名「%s」%s' % (case['regression'],
                                                       '复现了' if reproduced else '没复现，是个新的死法'),
                          flush=True)
                    for line in output.splitlines():
                        if line.startswith(('FAIL', 'ERR_', '----')):
                            print('       | ' + line, flush=True)
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
    lying = [r for r in rows if r['fixture_shape_missing']]
    print('\n%d/%d 种面板形状按"应该怎样"跑通了。明细：%s'
          % (len(rows) - len(bad), len(rows), out / 'report.json'), flush=True)
    if lying:
        print('其中 %d 种的 fixture 没复刻出真实结构，先调 fixture：%s'
              % (len(lying), '、'.join(r['case'] for r in lying)), flush=True)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
