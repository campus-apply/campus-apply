#!/usr/bin/env python3
"""通过 Chrome DevTools Protocol 操作一个专用调试浏览器里的标签页。只用标准库，macOS / Windows 通用。

用法：
  chrome_cdp.py launch [URL]            用专用配置目录启动一个带远程调试端口的 Chrome/Edge（已在跑就只报版本）
  chrome_cdp.py list [关键字]           列出标签页：序号<TAB>标题<TAB>URL<TAB>targetId（给了关键字只列标题或 URL 含它的）
  chrome_cdp.py claim <序号|targetId> [运行ID]   认领：往该页 sessionStorage 写 __caClaim=<运行ID>，输出 运行ID<TAB>URL
  chrome_cdp.py open <URL> [运行ID]      新开标签页打开 URL，等加载完写入认领标记，输出 运行ID<TAB>URL
  TAB_MARK=<运行ID> chrome_cdp.py exec <js文件>     在认领的标签页里执行 JS 文件，输出最后一个表达式的值
  TAB_MATCH=<url片段> chrome_cdp.py exec <js文件>   按 URL 子串找第一个匹配的标签页（兜底）
  TAB_MARK=<运行ID> chrome_cdp.py screenshot <输出.png>   把认领的标签页切到前台并截页面（只截网页内容）
  TAB_MARK=<运行ID> chrome_cdp.py stage <stage.js> [--libs a.js b.js] [--max 秒]
        把库和 stage 拼成一个脚本注入。stage 写成 (async () => {...})()，用 window.__ca.L() 记日志，结束时 L('DONE')，
        出错 L('ERR ...')；每次运行发一个 ID，只有本次运行能写全局日志；本命令每 2 秒轮询日志到 DONE / ERR / 超时（默认 90 秒）。
  TAB_MARK=<运行ID> chrome_cdp.py read-urls <列表文件> <输出目录> [起始行] [结束行]
        列表每行 id<TAB>url。逐个把认领的标签页导航过去，等 PACE_MIN–PACE_MAX 秒（默认 1–2，登录后的页面建议 2–4），
        用 read_page.js 读正文存 <输出目录>/<id>.json；每 GUARD_EVERY（默认 5）个跑一次 guard.js，遇验证码/跳登录打印 STOP 并停。
        页面 URL 不含 id 或正文太短打印 MISS <id>；结束打印 done 成功数/总数。

环境变量：CA_CDP_PORT 调试端口（默认 9222）；CA_CDP_TIMEOUT 单个标签页应答超时秒数（默认 10）；
  CA_BROWSER 浏览器可执行文件路径（不设则按平台找 Chrome / Edge）；CA_CHROME_PROFILE 专用配置目录（默认 ~/campus-apply-chrome）。
启动后第一次要在这个专用配置里重新登录招聘站；新版 Chrome 不允许在默认配置目录上开远程调试。
输出约定：找不到调试浏览器 ERR_NO_CDP（退出码 2）；没找到标签页 NO_MATCHING_TAB（1）；JS 抛异常 ERR_JS: …（1）。
返回值是字符串就原样打印，其他类型打成 JSON。
"""
import base64, json, os, platform, random, shutil, socket, struct, subprocess, sys, time, urllib.request, urllib.error, urllib.parse

PORT = int(os.environ.get('CA_CDP_PORT', '9222'))
HOST = '127.0.0.1'
TIMEOUT = float(os.environ.get('CA_CDP_TIMEOUT', '10'))
PROBE_JS = "(function(){try{return sessionStorage.getItem('__caClaim')||''}catch(e){return ''}})()"
HERE = os.path.dirname(os.path.abspath(__file__))
NO_CDP = 'ERR_NO_CDP: 端口 {port} 没有可调试的浏览器，请先运行 chrome_cdp.py launch'


class TabError(Exception):
    """标签页连不上、不应答或协议层出错。"""


class Tab:
    """一个页面目标的 DevTools 连接：标准库实现的最小 WebSocket 客户端，只发文本帧。"""

    def __init__(self, target):
        self.target = target
        self._id = 0
        ws = target['webSocketDebuggerUrl']
        path = '/' + ws.split('/', 3)[3]
        self.sock = socket.create_connection((HOST, PORT), timeout=TIMEOUT)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET {path} HTTP/1.1\r\nHost: {HOST}:{PORT}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                           f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise TabError('握手时连接被关闭')
            head += chunk
        if not head.startswith(b'HTTP/1.1 101'):
            raise TabError('握手失败: ' + head.split(b'\r\n', 1)[0].decode(errors='replace'))
        self._buf = head.split(b'\r\n\r\n', 1)[1]

    def close(self):
        try:
            self._send(b'', op=8)
            self.sock.close()
        except OSError:
            pass

    def _send(self, data, op=1):
        mask = os.urandom(4)
        n = len(data)
        hdr = bytes([0x80 | op])
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack('>H', n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack('>Q', n)
        self.sock.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise TabError('连接被关闭')
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _recv_message(self):
        """收一条完整文本消息（合并分片；ping 自动回 pong；close 抛 TabError）。"""
        parts = []
        while True:
            b1, b2 = self._read(2)
            op, fin = b1 & 0x0F, b1 & 0x80
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack('>H', self._read(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            data = self._read(n) if n else b''
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 8:
                raise TabError('对方关闭连接')
            if op == 9:
                self._send(data, op=10)
                continue
            if op == 10:
                continue
            parts.append(data)
            if fin:
                return b''.join(parts).decode('utf-8')

    def call(self, method, **params):
        self._id += 1
        self._send(json.dumps({'id': self._id, 'method': method, 'params': params}).encode('utf-8'))
        while True:
            try:
                msg = json.loads(self._recv_message())
            except socket.timeout:
                raise TabError(f'{method} 超过 {TIMEOUT} 秒无应答')
            if msg.get('id') != self._id:
                continue  # 事件或别的消息
            if 'error' in msg:
                raise TabError(f"{method}: {msg['error'].get('message')}")
            return msg.get('result', {})

    def evaluate(self, expression):
        """执行表达式并等待 Promise；返回 (值, 异常描述或 None)。"""
        r = self.call('Runtime.evaluate', expression=expression, returnByValue=True, awaitPromise=True)
        if 'exceptionDetails' in r:
            ex = r['exceptionDetails']
            desc = ex.get('exception', {}).get('description') or ex.get('text') or 'JS 异常'
            return None, desc
        return r.get('result', {}).get('value'), None


def http(path, method='GET'):
    req = urllib.request.Request(f'http://{HOST}:{PORT}{path}', method=method)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode('utf-8'))


def page_targets():
    """/json/list 里 type 为 page 的目标，保持 Chrome 给的顺序。连不上时返回 None。"""
    try:
        targets = http('/json/list')
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return [t for t in targets if t.get('type') == 'page']


def browser_identity():
    """(版本字符串, 是否无界面)；连不上返回 (None, False)。"""
    try:
        v = http('/json/version')
    except (urllib.error.URLError, OSError, ValueError):
        return None, False
    ua = v.get('User-Agent', '')
    return v.get('Browser', '?'), 'Headless' in ua or 'Headless' in v.get('Browser', '')


def report_identity(browser, headless):
    """浏览器标识打到 stderr，不影响 stdout 的表格输出；接到别的工具的无界面浏览器时提醒换端口。"""
    print(f'# 端口 {PORT}: {browser}', file=sys.stderr)
    if headless:
        print(f'# 警告：端口 {PORT} 上是无界面（Headless）浏览器，不是 campus-apply 启动的；设 CA_CDP_PORT 换端口或先关掉它', file=sys.stderr)


def cmd_list(kw=''):
    tabs = page_targets()
    if tabs is None:
        print(NO_CDP.format(port=PORT))
        return 2
    report_identity(*browser_identity())
    for i, t in enumerate(tabs, 1):
        title, url = t.get('title', ''), t.get('url', '')
        if not kw or kw in title or kw in url:
            print(f"{i}\t{title}\t{url}\t{t['id']}")
    return 0


def connect(target):
    try:
        return Tab(target)
    except (OSError, TabError):
        return None


def find_tab(mark, match):
    """按认领标记（探测 sessionStorage）或 URL 子串找标签页；返回已连接的 Tab 或 None。不应答的标签页跳过。"""
    tabs = page_targets()
    if tabs is None:
        return 'ERR_NO_CDP'
    for t in tabs:
        if match and not mark:
            if match in t.get('url', ''):
                tab = connect(t)
                if tab:
                    return tab
            continue
        if not t.get('url', '').startswith('http'):
            continue
        tab = connect(t)
        if not tab:
            continue
        try:
            v, _ = tab.evaluate(PROBE_JS)
        except TabError:
            tab.close()
            continue
        if v == mark:
            return tab
        tab.close()
    return None


def new_run_id():
    return 'ca' + str(int(time.time()))[-5:]


def claim_js(run_id):
    return f"sessionStorage.setItem('__caClaim','{run_id}'); 'ok'"


def wait_loaded(tab, seconds=15):
    for _ in range(int(seconds * 2)):
        try:
            v, _ = tab.evaluate('document.readyState')
        except TabError:
            v = None
        if v == 'complete':
            return True
        time.sleep(0.5)
    return False


def claim(target, run_id):
    """给一个页面目标写认领标记，打印 运行ID<TAB>URL。"""
    tab = connect(target)
    if tab is None:
        print(f"ERR_CDP: 连不上标签页 {target.get('url', '')}")
        return 1
    try:
        _, err = tab.evaluate(claim_js(run_id))
    finally:
        tab.close()
    if err:
        print(f'ERR_JS: {err}')
        return 1
    print(f"{run_id}\t{target.get('url', '')}")
    return 0


def cmd_claim(which, run_id=None):
    tabs = page_targets()
    if tabs is None:
        print(NO_CDP.format(port=PORT))
        return 2
    target = None
    if which.isdigit() and 1 <= int(which) <= len(tabs):
        target = tabs[int(which) - 1]
    else:
        target = next((t for t in tabs if t['id'] == which), None)
    if target is None:
        print(f'ERR_NO_SUCH_TAB {which}（先 list 看序号或 targetId）')
        return 1
    return claim(target, run_id or new_run_id())


def cmd_open(url, run_id=None):
    run_id = run_id or new_run_id()
    try:
        # 片段（#/…）不会随 HTTP 请求发出去，必须整体转义，Chrome 会还原
        target = http('/json/new?' + urllib.parse.quote(url, safe=''), method='PUT')
    except (urllib.error.URLError, OSError, ValueError):
        print(NO_CDP.format(port=PORT))
        return 2
    tab = connect(target)
    if tab is None:
        print('ERR_CDP: 新标签页连不上')
        return 1
    try:
        wait_loaded(tab)
        time.sleep(1)  # 新标签页头几秒可能还是空白页，写了标记也没用
        _, err = tab.evaluate(claim_js(run_id))
        url_now, _ = tab.evaluate('location.href')
    finally:
        tab.close()
    if err:
        print(f'ERR_JS: {err}')
        return 1
    print(f"{run_id}\t{url_now or target.get('url', url)}")
    return 0


def cmd_screenshot(out_path):
    mark, match = os.environ.get('TAB_MARK', ''), os.environ.get('TAB_MATCH', '')
    if not (mark or match):
        print('ERR_NEED_TAB_MARK_OR_TAB_MATCH')
        return 2
    tab = find_tab(mark, match)
    if tab == 'ERR_NO_CDP':
        print(NO_CDP.format(port=PORT))
        return 2
    if tab is None:
        print('NO_MATCHING_TAB')
        return 1
    try:
        tab.call('Page.bringToFront')
        data = tab.call('Page.captureScreenshot', format='png')['data']
    except TabError as e:
        print(f'ERR_CDP: {e}')
        return 1
    finally:
        tab.close()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(base64.b64decode(data))
    print(out_path)
    return 0


def format_value(v):
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def run_js(js_text):
    """在 TAB_MARK / TAB_MATCH 指定的标签页执行一段 JS；返回 (退出码, 输出文本或 None)。出错时输出文本就是错误行。"""
    mark, match = os.environ.get('TAB_MARK', ''), os.environ.get('TAB_MATCH', '')
    if not (mark or match):
        return 2, 'ERR_NEED_TAB_MARK_OR_TAB_MATCH'
    tab = find_tab(mark, match)
    if tab == 'ERR_NO_CDP':
        return 2, NO_CDP.format(port=PORT)
    if tab is None:
        return 1, 'NO_MATCHING_TAB'
    try:
        v, err = tab.evaluate(js_text)
    except TabError as e:
        return 1, f'ERR_CDP: {e}'
    finally:
        tab.close()
    if err:
        return 1, f'ERR_JS: {err}'
    return 0, None if v is None else format_value(v)


def cmd_exec(js_path):
    if not os.path.isfile(js_path):
        print(f'ERR_NO_FILE {js_path}')
        return 2
    with open(js_path, encoding='utf-8') as f:
        code, out = run_js(f.read())
    if out is not None:
        print(out)
    return code


def cmd_stage(stage_path, libs=(), max_seconds=90):
    if not os.path.isfile(stage_path):
        print(f'ERR_NO_FILE {stage_path}')
        return 2
    run_id = str(int(time.time() * 1000))[-7:]
    parts = [f"window.__caRun='{run_id}'; window.__calog='';"]
    for lib in list(libs) + [stage_path]:
        with open(lib, encoding='utf-8') as f:
            parts.append(f.read())
        parts.append(';')  # 库文件末尾不一定有分号，没有的话下一段 (async…) 会被当成函数调用
    code, out = run_js('\n'.join(parts))
    if code:
        print(out)
        return code
    read = f"(window.__caRun==='{run_id}' ? (window.__calog||'') : 'STALE:'+(window.__calog||''))"
    waited, out = 0, ''
    while waited < max_seconds:
        time.sleep(2)
        waited += 2
        code, out = run_js(read)
        out = out or ''
        if code:
            continue  # 页面导航中探测不到标记之类的暂时失败，继续等到超时
        if 'DONE' in out or out.startswith('ERR') or 'ERR ' in out:
            break
    print(out)
    if waited >= max_seconds:
        print(f'(timeout {max_seconds}s, last log above)')
    return 0


def cmd_read_urls(list_path, out_dir, start=1, end=999999):
    if not os.path.isfile(list_path):
        print(f'ERR_NO_FILE {list_path}')
        return 2
    pmin, pmax = float(os.environ.get('PACE_MIN', '1')), float(os.environ.get('PACE_MAX', '2'))
    every = int(os.environ.get('GUARD_EVERY', '5'))
    with open(os.path.join(HERE, 'read_page.js'), encoding='utf-8') as f:
        read_js = f.read()
    with open(os.path.join(HERE, 'guard.js'), encoding='utf-8') as f:
        guard_js = f.read()
    os.makedirs(out_dir, exist_ok=True)
    with open(list_path, encoding='utf-8') as f:
        rows = [ln.rstrip('\n').split('\t') for ln in f]
    rows = [r for r in rows[int(start) - 1:int(end)] if len(r) >= 2 and r[0]]
    n = ok = 0
    for rid, url in rows:
        n += 1
        code, out = run_js(f"location.href='{url}'; 'nav'")
        if code:
            print(out)
            return code
        time.sleep(random.uniform(pmin, pmax))
        code, out = run_js(read_js)
        if code:
            print(out)
            return code
        path = os.path.join(out_dir, f'{rid}.json')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(out or '')
        try:
            d = json.loads(out or '')
            good = rid in d['url'] and len(d['text']) > 200
        except (ValueError, KeyError, TypeError):
            good = False
        if good:
            ok += 1
        else:
            print(f'MISS {rid}')
        if n % every == 0:
            code, g = run_js(guard_js)
            if code:
                print(g)
                return code
            try:
                gd = json.loads(g)
            except ValueError:
                gd = {}
            print(f"  progress {n} guard captcha {gd.get('captcha')} login {gd.get('loginRedirect')}")
            if gd.get('captcha') or gd.get('loginRedirect'):
                print(f'STOP guard: {g}')
                break
    print(f'done {ok}/{n}')
    return 0


def browser_candidates():
    home = os.path.expanduser('~')
    if sys.platform == 'darwin':
        return ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                f'{home}/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                '/Applications/Chromium.app/Contents/MacOS/Chromium']
    if sys.platform.startswith('win'):
        pf = os.environ.get('PROGRAMFILES', r'C:\Program Files')
        pf86 = os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')
        local = os.environ.get('LOCALAPPDATA', '')
        return [rf'{pf}\Google\Chrome\Application\chrome.exe', rf'{pf86}\Google\Chrome\Application\chrome.exe',
                rf'{local}\Google\Chrome\Application\chrome.exe',
                rf'{pf86}\Microsoft\Edge\Application\msedge.exe', rf'{pf}\Microsoft\Edge\Application\msedge.exe']
    return [p for p in (shutil.which(n) for n in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge')) if p]


def find_browser():
    env = os.environ.get('CA_BROWSER')
    if env:
        return env if os.path.isfile(env) else None
    return next((p for p in browser_candidates() if os.path.isfile(p)), None)


def launch_args(binary, port, profile_dir, url=None):
    args = [binary, f'--remote-debugging-port={port}', f'--user-data-dir={profile_dir}',
            '--no-first-run', '--no-default-browser-check']
    if url:
        args.append(url)
    return args


def cmd_launch(url=None):
    browser, headless = browser_identity()
    if browser and headless:
        print(f'ERR_PORT_IN_USE: 端口 {PORT} 上是无界面（Headless）浏览器 {browser}，不是 campus-apply 启动的；设 CA_CDP_PORT 换端口或先关掉它')
        return 1
    if browser:
        print(f'已有浏览器在端口 {PORT}：{browser}')
        return 0
    binary = find_browser()
    if not binary:
        print('ERR_NO_BROWSER: 没找到 Chrome / Edge，请设 CA_BROWSER=<可执行文件路径> 或手动带参数启动（见文件头说明）')
        return 2
    profile = os.environ.get('CA_CHROME_PROFILE') or os.path.join(os.path.expanduser('~'), 'campus-apply-chrome')
    args = launch_args(binary, PORT, profile, url)
    kw = {'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'stdin': subprocess.DEVNULL}
    if sys.platform.startswith('win'):
        kw['creationflags'] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw['start_new_session'] = True
    subprocess.Popen(args, **kw)
    for _ in range(40):
        time.sleep(0.5)
        try:
            v = http('/json/version')
            print(f"已启动：{v.get('Browser', '?')} 端口 {PORT} 配置目录 {profile}")
            print('第一次用这个配置目录时请在里面重新登录招聘站。')
            return 0
        except (urllib.error.URLError, OSError, ValueError):
            continue
    print(f'ERR_LAUNCH_TIMEOUT: 启动了 {binary} 但 20 秒内端口 {PORT} 没有响应')
    return 1


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == 'list':
        return cmd_list(args[0] if args else '')
    if cmd == 'exec' and len(args) == 1:
        return cmd_exec(args[0])
    if cmd == 'claim' and 1 <= len(args) <= 2:
        return cmd_claim(*args)
    if cmd == 'open' and 1 <= len(args) <= 2:
        return cmd_open(*args)
    if cmd == 'screenshot' and len(args) == 1:
        return cmd_screenshot(args[0])
    if cmd == 'stage' and args:
        libs, max_s, rest = [], 90, []
        i = 0
        while i < len(args):
            if args[i] == '--libs':
                i += 1
                while i < len(args) and not args[i].startswith('--'):
                    libs.append(args[i]); i += 1
                continue
            if args[i] == '--max':
                max_s = int(args[i + 1]); i += 2
                continue
            rest.append(args[i]); i += 1
        if len(rest) == 1:
            return cmd_stage(rest[0], libs, max_s)
    if cmd == 'read-urls' and 2 <= len(args) <= 4:
        return cmd_read_urls(*args)
    if cmd == 'launch' and len(args) <= 1:
        return cmd_launch(*args)
    print(f'ERR_UNKNOWN_COMMAND {cmd}')
    return 2


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    sys.exit(main(sys.argv[1:]))
