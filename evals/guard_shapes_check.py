#!/usr/bin/env python3
"""Check that guard says "blocked" only when something is actually blocking.

guard 的四个判断（人机验证 / 要不要登录 / 压着几层弹窗 / 浏览器层面被挡住）决定流程停不停。
误报的代价是停下来等用户处理一件并不存在的事；漏报的代价是在被挡住的页面上继续填。
两头都踩过，样本记在待处理 #16。这一套把那些样本做成判据：

  形状 1  正文提到验证字样，但页上没有任何验证控件，而且人已经登录 → 不该报 captcha
  形状 2  真的在做人机验证（fixed 滑块盖住页面）                   → 必须报 captcha
  形状 3  常驻登录入口 + 头像和"退出登录"                          → 不该报要登录
  形状 4  有密码框、有登录字样、没有身份迹象                        → 必须报要登录
  形状 5  遮罩与弹窗体是兄弟节点、遮罩无文字                        → 一个弹窗，不是两个

**判的是"应该报什么"，不是"现在报什么"**，所以在判据改好之前这个脚本是红的，这是故意的。

  python3 evals/guard_shapes_check.py --out /private/guard-shapes [--headless]

Exit 0 = 每种形状都报对了。No models, no recruitment sites; isolated profile and port.
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

# 每个 case：fixture 的查询参数，以及 guard 必须报成什么。
# requires_login 不是 guard 的字段名——guard 现在只有 loginRedirect，而那个名字说的是
# "这个页面是登录页/有登录入口"，不是"站点要求你登录"。判据按后者写，字段名由实现决定，
# 下面的 read 函数负责把它映射过来。
CASES = [
    dict(name='形状 1：正文提到验证字样，页上没有验证控件',
         query='case=mentions-verify',
         expect=dict(captcha=False, requires_login=False, loggedIn=True, visibleModals=0),
         regression='captcha'),
    dict(name='形状 2：真的在做人机验证',
         query='case=real-captcha',
         expect=dict(captcha=True, requires_login=False, loggedIn=True, visibleModals=0)),
    dict(name='形状 3：常驻登录入口，人已经登录了',
         query='case=resident-login',
         expect=dict(captcha=False, requires_login=False, loggedIn=True, visibleModals=0),
         regression='loginRedirect'),
    dict(name='形状 4：真的要登录',
         query='case=real-login',
         expect=dict(captcha=False, requires_login=True, loggedIn=False, visibleModals=0)),
    dict(name='形状 5：遮罩与弹窗体是兄弟节点',
         query='case=modal',
         expect=dict(captcha=False, requires_login=False, loggedIn=True, visibleModals=1)),
    # 这一条守的是"不许为了治误报而制造漏报"：验证码整层在 iframe 里、容器 class 不含验证字样，
    # 控件选择器够不到，正文里的词是唯一线索。词 + 页上真的压着一层东西，必须报。
    dict(name='形状 6：验证码在 iframe 里，容器 class 不含验证字样',
         query='case=iframe-captcha',
         expect=dict(captcha=True, requires_login=False, loggedIn=True)),
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


def requires_login_of(report):
    """guard 报的"这一页要不要登录"。

    `loginRedirect` 只说明"当前这个页面是登录页或有登录入口"——2026-10-04 的教训是
    agent 自己点了登录按钮跳过去，再看见这个字段为真，就当成站点要求登录。
    所以"要不要登录"要同时看身份证据：有身份就说明不用再登录一次。
    实现可以直接给一个 requiresLogin 字段，没有就按这个式子算。
    """
    if 'requiresLogin' in report:
        return bool(report['requiresLogin'])
    return bool(report.get('loginRedirect')) and not report.get('loggedIn')


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
    profile = tempfile.mkdtemp(prefix='campus-apply-guardshape-')
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
            base = 'http://127.0.0.1:' + str(server.server_address[1]) + '/guard_shapes.html?'
            env = dict(os.environ, CA_CDP_PORT=str(port))
            env.pop('TAB_MARK', None)
            env.pop('TAB_MATCH', None)

            def cdp(case_dir, phase, *cdp_args, timeout=60):
                result = subprocess.run([sys.executable, str(CDP), *cdp_args],
                                        env=env, capture_output=True, text=True, timeout=timeout)
                (case_dir / (phase + '.out')).write_text(
                    result.stdout + ('\n--- stderr ---\n' + result.stderr if result.stderr else ''),
                    encoding='utf-8')
                return result

            for index, case in enumerate(CASES):
                mark = 'guard-%02d' % index
                case_dir = out / mark
                case_dir.mkdir(parents=True, exist_ok=True)
                cdp(case_dir, 'open', 'open', base + case['query'] + '&run=' + mark, mark)
                time.sleep(.3)
                raw = cdp(case_dir, 'guard', '--mark', mark, 'exec',
                          str(BROWSER_DIR / 'guard.js')).stdout.strip()
                try:
                    report = json.loads(raw)
                except ValueError:
                    report = {}
                truth_raw = cdp(case_dir, 'truth', '--mark', mark, 'exec',
                                str(write_truth_js(case_dir))).stdout.strip()
                try:
                    truth = json.loads(truth_raw)
                except ValueError:
                    truth = {}

                problems = []
                if not report:
                    problems.append('guard 没返回 JSON：' + raw[:120])
                else:
                    got = dict(captcha=bool(report.get('captcha')),
                               requires_login=requires_login_of(report),
                               loggedIn=bool(report.get('loggedIn')),
                               visibleModals=report.get('visibleModals'))
                    for key, want in case['expect'].items():
                        if got.get(key) != want:
                            problems.append('%s 报成 %r，应当是 %r' % (key, got.get(key), want))
                    # fixture 自己记的真值要和 case 的期望一致，否则是 fixture 写错了
                    for key, field in (('captcha', 'captcha'), ('requires_login', 'requiresLogin'),
                                       ('loggedIn', 'loggedIn')):
                        if field in truth and case['expect'].get(key) != truth[field]:
                            problems.append('fixture 真值和期望不一致：%s truth=%r expect=%r'
                                            % (key, truth[field], case['expect'].get(key)))

                rows.append(dict(name=case['name'], mark=mark, ok=not problems,
                                 problems=problems, guard=report, truth=truth))
                print('  %s %s' % ('ok  ' if not problems else 'FAIL', case['name']), flush=True)
                for problem in problems:
                    print('       - %s' % problem, flush=True)
                if problems and case.get('regression'):
                    print('       （这一条是待处理 #16 记的已知误报：%s）'
                          % case['regression'], flush=True)
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
    print('\n%d/%d 种形状报对了。明细：%s' % (good, len(rows), report_path), flush=True)
    return 0 if good == len(rows) else 1


def write_truth_js(case_dir):
    path = case_dir / 'truth.js'
    path.write_text('JSON.stringify(window.fixtureTruth())', encoding='utf-8')
    return path


if __name__ == '__main__':
    sys.exit(main())
