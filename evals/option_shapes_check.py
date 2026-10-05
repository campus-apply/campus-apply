#!/usr/bin/env python3
"""Check that options get found when they carry no class and no role, and that clicking a
plain text box is not mistaken for opening a panel.

`panel_shapes.html` asks "can the panel be found at all". These two defects sit on either
side of that question and both zero out a whole page, yet no existing fixture can see them.

  形状 D  选项节点不带任何 class 和 role（待处理 145）
     年份是 div.x-aside-item、月份是裸 span。OPTION_SEL 是一张按 class/role 列举的清单，
     实测 panel.querySelectorAll(OPTION_SEL).length === 0——两列一个都不命中。
     optionsIn 返回空数组，fill 如实报「第 1 级没有「2024」」：它确实什么都没看见。
     这正是 PANEL_SEL 那层已经推翻过的错误，选项层没跟着改。
  形状 E  一个面板里并排两级（同上）
     年份列和月份格同时在一个浮层里，不是逐级点开逐级出现。cascader 假设的是后者。
  形状 F  点普通文本框被当成开出了面板（待处理 143）
     真实点击让包装容器加聚焦态 class，而 watchStart 把属性变化的节点自身收进候选，
     于是那个 286×41 的包装 div 被当成面板。它收不掉，所以 probe-options 停在第一个控件，
     而且脏账留在 openedByUs 里，之后每条命令都报 ERR_PANELS。

**每个 case 判的是"应该怎样"，不是"现在怎样"**：选项找得到、字段填成、面板收干净、退出 0；
文本框不该开出任何面板。所以在这两处改好之前这个脚本是红的，这是故意的。红的时候会把当时
的失败原文和 `regression` 里记的真站签名比一遍：对得上就是复现了已知的坑，对不上就是出现了
新的死法，两种都会打出来。

  python3 evals/option_shapes_check.py --out /private/option-shapes [--headless]

Exit 0 = 两处都按"应该怎样"跑通了。No models, no recruitment sites; isolated profile and port.
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

# 选项层的结构证据。纯 DOM，不调执行器的内部接口——那套接口正是要改的东西，证据脚本不能跟着
# 它一起变。OPTION_LISTING 是"按 class/role 列举选项"的那种选择器（老 OPTION_SEL 的形状）：
# 这里不是在测某一版代码，而是在证明 fixture 真的有那个结构——选项一个都不命中那套词。
DIAGNOSE_JS = r'''
JSON.stringify((() => {
  const OPTION_LISTING = '[role="option"],[role="menuitem"],[role="treeitem"],li,'
    + '[class*="select-item"],[class*="option"],[class*="Option"],[class*="menu-item"],'
    + '[class*="cascader-item"],td[class*="cell"],td';
  const shown = el => el.isConnected
    && el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const big = el => {
    const r = el.getBoundingClientRect();
    return r.width >= 20 && r.height >= 10;
  };
  const panel = document.querySelector('#start-panel');
  const years = document.querySelector('#start-years');
  const months = document.querySelector('#start-months');
  const leaves = root => root ? [...root.querySelectorAll('*')]
      .filter(e => e.children.length === 0 && (e.textContent || '').trim()) : [];
  const rect = el => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height)};
  };
  const wrap = document.querySelector('#name-wrap');
  return {
    panelOpen: !!panel && shown(panel),
    // 按 class/role 列举时，面板里能收下几个选项——真站实测 0
    listedInPanel: panel ? panel.querySelectorAll(OPTION_LISTING).length : null,
    // 而"无子元素且有可见文本"的叶子有多少个：这是改后判据能取到的数
    leavesInPanel: panel ? leaves(panel).filter(shown).length : null,
    yearLeafSample: leaves(years).slice(0, 3).map(e => ({
      tag: e.tagName, cls: (e.className || '').toString().slice(0, 40),
      role: e.getAttribute('role'), txt: (e.textContent || '').trim()})),
    monthLeafSample: leaves(months).slice(0, 3).map(e => ({
      tag: e.tagName, cls: (e.className || '').toString().slice(0, 40),
      role: e.getAttribute('role'), txt: (e.textContent || '').trim()})),
    // 形状 E：两级并排——年份列和月份格同时可见，且横向不重叠（并排而非层叠）
    twoLevelsSideBySide: !!(years && months) && shown(years) && shown(months)
      && (() => {
        const a = years.getBoundingClientRect(), b = months.getBoundingClientRect();
        return a.x + a.width <= b.x + 1;
      })(),
    panelRect: rect(panel), yearsRect: rect(years), monthsRect: rect(months),
    // 形状 F：文本框的包装容器——可见、够大，聚焦时只是多一个 class
    nameWrapRect: rect(wrap),
    nameWrapVisibleAndBig: !!wrap && shown(wrap) && big(wrap),
  };
})())
'''

# 点一下文本框，看执行器自己的观察器收到了什么。用的是 lib_fill.js 对外的 appeared()，
# 因为形状 F 考的恰恰是这个接口的判据，不是 DOM 事实。lib_fill 只在 fill / probe-options 这类
# 子命令里注入，裸 exec 拿不到，所以这里把它拼在前面自己注入一次。
APPEARED_JS = r'''
JSON.stringify((() => {
  const input = document.querySelector('#name');
  if (!window.__caFill) return {error: 'lib_fill 未注入'};
  const snap = window.__caFill.snapshot();
  const me = (snap.controls || []).find(f => (f.name || '').trim() === '姓名');
  if (!me) return {error: '快照里找不到姓名框',
                   names: (snap.controls || []).map(f => f.name)};
  window.__caFill.watchStart();
  input.focus();                      // 聚焦态 class 就是这样加上去的
  const found = window.__caFill.appeared(me.handle) || [];
  return {
    handle: me.handle,
    appearedCount: found.length,
    appeared: found.map(p => ({cls: p.cls, rect: p.rect, score: p.score})),
    stillOpen: (window.__caFill.stillOpen() || []).length,
  };
})())
'''

CASES = [
    dict(name='形状 D+E：选项无 class 无 role、两级并排在一个面板里',
         # display 是必须的：级联的两级拼起来是"2024 / 9月"，而控件上显示的是 2024-09。
         # 回读按 display 比，不按拼接值比——这一条也顺带验证 display 参数真的管用。
         fields=[dict(key='start', label='开始时间', kind='cascader',
                      selector='#start', value=['2024', '9月'], display='2024-09'),
                 dict(key='end', label='结束时间', kind='cascader',
                      selector='#end', value=['2027', '6月'], display='2027-06')],
         expect_keys=['start', 'end'],
         expect_truth={'start': '2024-09', 'end': '2027-06'},
         regression='第 1 级没有',
         evidence=[('listedInPanel', 0, '按 class/role 列举在这个面板里收下的选项数'),
                   ('twoLevelsSideBySide', True, '年份列和月份格并排同时可见')]),
    dict(name='形状 F：点普通文本框不该开出面板',
         fields=[dict(key='name', label='姓名', kind='text',
                      selector='#name', value='张测试'),
                 dict(key='phone', label='手机号', kind='text',
                      selector='#phone', value='13000000000')],
         expect_keys=['name', 'phone'],
         expect_truth={'name': '张测试', 'phone': '13000000000'},
         regression='面板收不起来',
         evidence=[('nameWrapVisibleAndBig', True, '文本框的包装容器可见且够大')],
         check_appeared=True),
]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def browser_path():
    env = os.environ.get('CA_BROWSER')
    if env and Path(env).exists():
        return env
    for candidate in (
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    ):
        if Path(candidate).exists():
            return candidate
    return shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('msedge')


def fill_report(stdout):
    start = stdout.find('{')
    if start < 0:
        return {}
    try:
        return json.loads(stdout[start:stdout.rfind('}') + 1])
    except ValueError:
        return {}


def row_of(report, key):
    return next((r for r in (report.get('fields') or []) if r.get('key') == key), {})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
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
    profile = tempfile.mkdtemp(prefix='campus-apply-optionshape-')
    try:
        command = [browser, '--user-data-dir=' + profile, '--remote-debugging-port=' + str(port),
                   '--no-first-run', '--no-default-browser-check',
                   '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
                   '--disable-backgrounding-occluded-windows', '--window-size=1100,900',
                   'about:blank']
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
            base = 'http://127.0.0.1:' + str(server.server_address[1]) + '/option_shapes.html'
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

            for index, case in enumerate(CASES):
                mark = 'opt-%02d' % index
                case_dir = out / mark
                case_dir.mkdir(parents=True, exist_ok=True)
                cdp(case_dir, 'open', 'open', base + '?run=' + mark, mark, timeout=60)

                # fixture 真的有这个结构吗。日期面板要先点开才量得到，所以先开一下再量。
                cdp(case_dir, 'open_panel', '--mark', mark, 'click', '#start', timeout=60)
                time.sleep(.3)
                evidence = js(case_dir, mark, 'diagnose', DIAGNOSE_JS) or {}
                # 量完收掉，别让它干扰正式填写
                cdp(case_dir, 'close_panel', '--mark', mark, 'click', 'h1', timeout=60)
                time.sleep(.2)

                appeared = None
                if case.get('check_appeared'):
                    lib = (BROWSER_DIR / 'lib_fill.js').read_text(encoding='utf-8')
                    appeared = js(case_dir, mark, 'appeared', lib + '\n' + APPEARED_JS) or {}

                plan = case_dir / 'plan.json'
                plan.write_text(json.dumps({'fields': case['fields'],
                                            'pace': {'min': .02, 'max': .05},
                                            'addressing': 'selector',
                                            'options_unverified': True},
                                           ensure_ascii=False, indent=1), encoding='utf-8')
                result = cdp(case_dir, 'fill', '--mark', mark, 'fill', str(plan), '--max', '40')
                output = result.stdout + result.stderr
                report = fill_report(result.stdout)
                truth = js(case_dir, mark, 'truth', 'JSON.stringify(window.fixtureTruth())') or {}
                audit = js(case_dir, mark, 'audit', 'JSON.stringify(window.fixtureAudit())') or {}

                # ---- 判据：应该怎样 ----
                problems = []
                if result.returncode != 0:
                    problems.append('退出码 %s，期望 0' % result.returncode)
                for key in case['expect_keys']:
                    row = row_of(report, key)
                    if row.get('status') != 'filled':
                        problems.append('%s 没填成：%s %s' % (
                            key, row.get('status'), row.get('why') or ''))
                for key, want in (case.get('expect_truth') or {}).items():
                    got = truth.get(key)
                    if got != want:
                        problems.append('%s 的真值是 %r，期望 %r' % (key, got, want))
                if 'ERR_PANELS' in output:
                    problems.append('报了 ERR_PANELS：面板没收干净')
                if audit.get('panelsOpenNow'):
                    problems.append('结束时还有 %s 个面板开着' % audit['panelsOpenNow'])

                # 形状 F 专属：点文本框不该被认成开出了面板
                if appeared is not None:
                    if appeared.get('error'):
                        problems.append('取 appeared 失败：%s' % appeared['error'])
                    elif appeared.get('appearedCount'):
                        problems.append('点文本框后认出了 %s 个"面板"，期望 0：%s' % (
                            appeared['appearedCount'],
                            json.dumps(appeared.get('appeared'), ensure_ascii=False)[:200]))
                    if appeared.get('stillOpen'):
                        problems.append('脏账进了 openedByUs：stillOpen=%s' % appeared['stillOpen'])

                # ---- fixture 自己有没有复刻对那个结构 ----
                shape_ok = True
                for name, want, why in case['evidence']:
                    got = evidence.get(name)
                    if got != want:
                        shape_ok = False
                        problems.append('fixture 没复刻对（%s）：%s=%r，期望 %r' % (why, name, got, want))

                # ---- 红的时候：复现的是已知的坑，还是新的死法 ----
                matched_regression = case['regression'] in output

                rows.append(dict(name=case['name'], mark=mark, ok=not problems,
                                 problems=problems, exit=result.returncode,
                                 shape_evidence_ok=shape_ok, evidence=evidence,
                                 appeared=appeared, truth=truth, audit=audit,
                                 matched_known_signature=matched_regression,
                                 tail=output.strip().splitlines()[-1:] or ['']))

                status = 'ok  ' if not problems else 'FAIL'
                print('  %s %s' % (status, case['name']), flush=True)
                for problem in problems:
                    print('       - %s' % problem, flush=True)
                if problems:
                    if matched_regression:
                        print('       （复现的是已知的坑：输出里有 %r）' % case['regression'], flush=True)
                    else:
                        print('       （出现了新的死法：输出里没有 %r，末行 %s）'
                              % (case['regression'], rows[-1]['tail']), flush=True)
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        server.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    good = sum(1 for r in rows if r['ok'])
    report_path = out / 'report.json'
    report_path.write_text(json.dumps(dict(browser=version, cases=rows),
                                      ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n%d/%d 项按"应该怎样"跑通了。明细：%s' % (good, len(rows), report_path), flush=True)
    return 0 if good == len(rows) else 1


if __name__ == '__main__':
    sys.exit(main())
