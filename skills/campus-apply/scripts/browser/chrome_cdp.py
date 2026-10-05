#!/usr/bin/env python3
"""通过 Chrome DevTools Protocol 操作一个专用浏览器里的标签页。只用标准库，macOS / Windows 通用。

用法：
  chrome_cdp.py launch [URL]            用专用配置目录启动一个带远程调试端口的 Chrome/Edge（已在跑就只报版本）
  chrome_cdp.py list [关键字]           列出标签页：序号<TAB>标题<TAB>URL<TAB>targetId（给了关键字只列标题或 URL 含它的）
  chrome_cdp.py claim <序号|targetId> [运行ID]   认领：往该页 sessionStorage 写 __caClaim=<运行ID>，输出 运行ID<TAB>URL
  chrome_cdp.py open <URL> [运行ID]      新开标签页打开 URL，等加载完写入认领标记，输出 运行ID<TAB>URL
  chrome_cdp.py --mark <运行ID> exec <js文件>      在认领的标签页里执行 JS 文件，输出最后一个表达式的值
  chrome_cdp.py --match <url片段> exec <js文件>    按 URL 子串找第一个匹配的标签页（兜底）
  chrome_cdp.py --mark <运行ID> screenshot <输出.png>   把认领的标签页切到前台并截页面（只截网页内容）
  chrome_cdp.py --mark <运行ID> click <目标>       发真实鼠标事件点一下（页面脚本里 el.click() 点不开的日期面板、级联菜单用它）。
        目标三种写法：CSS 选择器（取第一个可见匹配）；`x,y` 视口坐标；`js:<表达式>`（求值得到元素）。
        元素会先滚到视口中间再按中心点点击；输出 clicked <标签> <x>,<y>；找不到输出 NO_ELEMENT。
  chrome_cdp.py --mark <运行ID> stage <stage.js> [--libs a.js b.js] [--max 秒]
        把库和 stage 拼成一个脚本注入。stage 写成 (async () => {...})()，用 window.__ca.L() 记日志，结束时 L('DONE')，
        出错 L('ERR ...')；每次运行发一个 ID，只有本次运行能写全局日志；本命令复用连接轮询日志到 DONE / ERR / 超时（默认总预算 90 秒）；失败退出非零。
  chrome_cdp.py --mark <运行ID> survey <输出.json>
        只读地把这一页摸清楚，一条命令抵十几次往返：确认渲染稳定（连探到控件数不变）、整页字段与语义坐标、
        probe 的控件属性、五路找上传位（直接的 input[type=file] / shadow DOM 递归 / 带 accept 的元素 /
        正文关键词 / iframe）。不点击、不写入、不开面板。摘要打到 stdout，明细写进输出文件。
  chrome_cdp.py --mark <运行ID> probe-options <输出.json> [--only 字段1,字段2]
        逐个打开面板类控件、读回全部选项、收起来、验证已关，结论写进一个文件。**这条会动页面**
        （点开再收起），动手之前跟用户说一声；已经有值的字段自动跳过，不去碰它。
        十几个下拉逐个探是十几次往返，在页内连着做完只要几秒——省的是往返之间浏览器干等的时间。
  chrome_cdp.py --mark <运行ID> plan-skeleton <输出.json> [--skip-ok <上次的报告.json>]
        从页面生成计划骨架：字段的语义坐标（板块 / 第几条 / 标签 / 同标签第几个）由代码从 DOM 读出来，
        每个字段的 value 留成 null，模型只填值，不用自己维护一张下标表。disabled 的字段不列入，
        敏感字段标注出来。--skip-ok 指向上一次的 fill 报告，标 filled 的字段这次不再列出（只补没填成的）。
  chrome_cdp.py --mark <运行ID> fill <计划.json> [--max 秒] [--allow-selector]
        按计划把一整页字段连续填完，一次调用一份报告：解析选择器拿 handle → 开面板 → 按条件等面板和选项出现
        → 选中 → 收面板并验证已关 → 三层回读 → 下一个字段（字段间留 pace 间隔）。不用为每个字段写脚本。
        计划 JSON：{"fields": [{...}], "pace": {"min":0.3,"max":0.8}, "panel_wait":2, "option_wait":2}
        定位默认用**语义坐标** section / occurrence / label / nth（板块、第几条记录、字段标签、同一条里
        同名标签的第几个——"年/月"或"起/止"共用标签时第四维不能省），由 plan-skeleton 生成。
        **selector + index 是降级路径，默认关闭**：要用得在计划里写 "addressing": "selector" 或者加
        --allow-selector，否则退出非零。语义坐标加条目不失效、写错了只是找不到，而 index 是纯位置量，
        错一位就操作到完全无关的控件，最敏感的字段往往恰好排在最前面。
        可选 expect_label：声明这个控件的可访问名称应当含什么，执行前校验，对不上就不动它。
        证件号、出生日期这类敏感字段一律跳过，除非该字段写了 sensitive_ok。
        每个 field：key / label（报告里显示）、selector（CSS）、index（同选择器第几个，默认 0）、
        kind 取 text|dropdown|search|cascader|date|checkbox|native-select、value（级联是数组，逐级点）、
        可选 term（可搜索下拉先打的词）、display_selector（值显示在别处时指明）、max（文本字数上限）、display（级联回读用的显示值）。
        计划里的内容只当数据，不拼进 JS 执行；元素由 lib_fill.js 按 handle 持有，不让计划产出可执行代码。
        全部填成且面板为零才打印 DONE 并退出 0；有字段没填成退出 1 并逐行说明原因，面板没收干净 ERR_PANELS。
  chrome_cdp.py --mark <运行ID> read-urls <列表文件> <输出目录> [起始行] [结束行] [--pace 最短-最长] [--guard-every N] [--stop-file 文件]
        列表每行 id<TAB>url。逐个把认领的标签页导航过去，等 --pace 秒（默认 1-2；公开页建议 0.3-0.6，登录后的页面 0.8-1.5），
        用 read_page.js 读正文存 <输出目录>/<id>.json；每 --guard-every（默认 5）个跑一次 guard.js，遇验证码/跳登录打印 STOP 并停。
        页面 URL 不含 id 或正文太短打印 MISS <id>；结束打印 done 成功数/总数。
        --stop-file：几个标签页并行读时给同一个文件；任何一个的 guard 报验证码/跳登录就写这个文件，其他进程读下一条前看到它就停（STOP stop-file）。
  chrome_cdp.py --mark <运行ID> type <选择器|js:表达式> <文本|@文件>
        往一个文本框里像人打字一样写入：发真实鼠标事件点它取得焦点 → 全选 → 用浏览器自己的输入路径（Input.insertText）写入文本
        → 派发 input / change / blur / focusout → 回读。文本以 @ 开头就读那个文件的内容（长文本、含换行或引号时用）。
        输出 typed <标签> <n>字 回读 <m>字 一致；不一致输出 ERR_TYPE 并退出 1。是原型 setter 写法三层回读不过时的兜底，不是默认写法。
  chrome_cdp.py --mark <运行ID> upload <选择器> <文件路径>
        把本地文件设到一个 <input type=file> 上（DOM.setFileInputFiles，浏览器原生路径，会触发 change），再回读 input.files 里的文件名。
        只在用户明确同意由 agent 代传时用；默认仍由用户自己上传。
  chrome_cdp.py --mark <运行ID> sniff <触发目标> [--wait 秒]
        观察页面自己发出的请求：先在认领的标签页装上记录钩子（lib_net.js），再做一个触发动作，等 --wait 秒（默认 3），
        打印这期间页面发出的 XHR / fetch：方法、地址、请求体、状态、响应类型、响应长度，然后一行 --- 和完整 JSON。
        触发目标三种写法：CSS 选择器（发真实鼠标事件点它）；`x,y` 视口坐标；`js:<表达式>`（直接执行，例如调用页面自己的翻页函数）。
        输出的第一行是 SNIFF <请求数>。哪些请求返回 JSON、JSON 里有没有岗位正文，由调用方看响应判断。

选项可以放在子命令前后任意位置：--mark、--match、--port（调试端口，默认 9222）、--pace、--guard-every、--stop-file、--wait。
同义的环境变量：TAB_MARK、TAB_MATCH、CA_CDP_PORT、PACE_MIN / PACE_MAX、GUARD_EVERY、STOP_FILE、SNIFF_WAIT；命令行选项优先。
其他环境变量：CA_CDP_TIMEOUT 单个标签页应答超时秒数（默认 10）；CA_BROWSER 浏览器可执行文件路径（不设则按平台找 Chrome / Edge）；
  CA_CHROME_PROFILE 专用配置目录（默认 ~/campus-apply-chrome）；CA_TIMING_FILE 可选 JSONL 计时输出文件，只有命令/状态/秒数。
启动后第一次要在这个专用配置里重新登录招聘站；新版 Chrome 不允许在默认配置目录上开远程调试。
输出约定：找不到调试浏览器 ERR_NO_CDP（退出码 2）；没找到标签页 NO_MATCHING_TAB（1）；JS 抛异常 ERR_JS: …（1）。
返回值是字符串就原样打印，其他类型打成 JSON。
"""
import base64, io, json, math, os, platform, random, re, shutil, socket, struct, subprocess, sys, time, urllib.request, urllib.error, urllib.parse

from http.client import HTTPConnection, HTTPResponse

PORT = int(os.environ.get('CA_CDP_PORT', '9222'))
HOST = '127.0.0.1'
TIMEOUT = float(os.environ.get('CA_CDP_TIMEOUT', '10'))
PROBE_JS = "(function(){try{return sessionStorage.getItem('__caClaim')||''}catch(e){return ''}})()"
HERE = os.path.dirname(os.path.abspath(__file__))
NO_CDP = 'ERR_NO_CDP: 端口 {port} 没有可调试的浏览器，请先运行 chrome_cdp.py launch'


class TabError(Exception):
    """标签页连不上、不应答或协议层出错。"""


class StageDeadline(TabError):
    """一次 stage 的总时间预算已用完。"""


def remaining_timeout(deadline, limit=TIMEOUT):
    if deadline is None:
        return limit
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise StageDeadline('stage deadline exceeded')
    return min(limit, remaining)


class Tab:
    """一个页面目标的 DevTools 连接：标准库实现的最小 WebSocket 客户端，只发文本帧。"""

    def __init__(self, target, deadline=None):
        self.deadline = deadline
        self.target = target
        self._id = 0
        ws = target['webSocketDebuggerUrl']
        path = '/' + ws.split('/', 3)[3]
        self.sock = socket.create_connection((HOST, PORT), timeout=remaining_timeout(deadline))
        try:
            key = base64.b64encode(os.urandom(16)).decode()
            self.sock.sendall((f'GET {path} HTTP/1.1\r\nHost: {HOST}:{PORT}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                               f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
            head = b''
            while b'\r\n\r\n' not in head:
                self.sock.settimeout(remaining_timeout(self.deadline))
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise TabError('握手时连接被关闭')
                head += chunk
            if not head.startswith(b'HTTP/1.1 101'):
                raise TabError('握手失败: ' + head.split(b'\r\n', 1)[0].decode(errors='replace'))
            self._buf = head.split(b'\r\n\r\n', 1)[1]
        except (OSError, TabError):
            self.sock.close()
            raise

    def close(self):
        try:
            if self.deadline is None or time.monotonic() < self.deadline:
                self.sock.settimeout(remaining_timeout(self.deadline))
                self._send(b'', op=8)
        except (OSError, StageDeadline):
            pass
        finally:
            self.sock.close()

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
            self.sock.settimeout(remaining_timeout(self.deadline))
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
        self.sock.settimeout(remaining_timeout(self.deadline))
        self._id += 1
        self._send(json.dumps({'id': self._id, 'method': method, 'params': params}).encode('utf-8'))
        while True:
            remaining_timeout(self.deadline)
            try:
                msg = json.loads(self._recv_message())
            except socket.timeout:
                raise TabError(f'{method} 超过 {TIMEOUT} 秒无应答')
            if msg.get('id') != self._id:
                continue  # 事件或别的消息
            if 'error' in msg:
                raise TabError(f"{method}: {msg['error'].get('message')}")
            return msg.get('result', {})

    def evaluate(self, expression, await_promise=True):
        """执行表达式，默认等待 Promise；返回 (值, 异常描述或 None)。注入长脚本时传 await_promise=False，只等注入本身。"""
        r = self.call('Runtime.evaluate', expression=expression, returnByValue=True, awaitPromise=await_promise)
        if 'exceptionDetails' in r:
            ex = r['exceptionDetails']
            desc = ex.get('exception', {}).get('description') or ex.get('text') or 'JS 异常'
            return None, desc
        return r.get('result', {}).get('value'), None


class _DeadlineReader(io.RawIOBase):
    """每次实际 socket 读取前收紧预算，包含 HTTP 状态行和 headers。"""

    def __init__(self, raw, sock, deadline):
        self.raw, self.sock, self.deadline = raw, sock, deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        self.sock.settimeout(remaining_timeout(self.deadline, 5))
        return self.raw.readinto(buffer)

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class _DeadlineSocket:
    """只供 HTTPResponse 建立文件流；不替换系统 socket 或全局 opener。"""

    def __init__(self, sock, deadline):
        self.sock, self.deadline = sock, deadline

    def makefile(self, mode):
        raw = self.sock.makefile(mode, buffering=0)
        return io.BufferedReader(_DeadlineReader(raw, self.sock, self.deadline))


def http(path, method='GET', deadline=None):
    url = f'http://{HOST}:{PORT}{path}'
    if deadline is None:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode('utf-8'))
    # urlopen 的 timeout 是空闲超时；持续分片会延长 header/body 的实际总时间。
    # 仅有 deadline 的本地 CDP 请求走逐次读取预算，普通命令保持旧路径。
    connection = HTTPConnection(HOST, PORT, timeout=remaining_timeout(deadline, 5))
    connection.response_class = lambda sock, **kw: HTTPResponse(_DeadlineSocket(sock, deadline), **kw)
    response = None
    try:
        connection.connect()
        connection.sock.settimeout(remaining_timeout(deadline, 5))
        connection.request(method, path)
        remaining_timeout(deadline)
        response = connection.getresponse()
        remaining_timeout(deadline)
        if not 200 <= response.status < 300:
            raise urllib.error.HTTPError(url, response.status, response.reason, response.headers, None)
        chunks = []
        while True:
            remaining_timeout(deadline)
            chunk = response.read1(65536)
            remaining_timeout(deadline)
            if not chunk:
                break
            chunks.append(chunk)
        value = json.loads(b''.join(chunks).decode('utf-8'))
        remaining_timeout(deadline)
        return value
    finally:
        if response is not None:
            response.close()
        connection.close()


def page_targets(deadline=None):
    """/json/list 里 type 为 page 的目标，保持 Chrome 给的顺序。连不上时返回 None。"""
    try:
        targets = http('/json/list', deadline=deadline)
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


def no_tab_report(mark='', match='', deadline=None):
    """认领的标签页找不到了——把"到底是什么情况"一次说清，别让调用方反复重试。

    三种情况后续动作完全不同：浏览器整个关了（重开要用户同意，草稿多半已经没了）、
    浏览器还在但那一页被关了、页面还在只是跳了域名丢了标记（重新认领就行）。
    2026-10-04 的教训是只打印一行 NO_MATCHING_TAB，agent 分不清，就停在原地。
    """
    lines = ['NO_MATCHING_TAB']
    try:
        tabs = page_targets(deadline=deadline)
    except (OSError, TabError, StageDeadline):
        tabs = None
    if tabs is None:
        lines.append('BROWSER_GONE 专用浏览器已经不在了（端口 %d 没有响应）。'
                     '没保存的内容多半已经没了；要继续就先问用户，再 launch 重开并请他重新登录。' % PORT)
        return '\n'.join(lines), 'browser-gone'
    if not tabs:
        lines.append('NO_PAGES 浏览器还开着，但一个标签页都没有。先问用户发生了什么，不要自己开新页。')
        return '\n'.join(lines), 'no-pages'
    lines.append('OTHER_TABS 浏览器里还有 %d 个标签页：' % len(tabs))
    for i, t in enumerate(tabs[:8], 1):
        lines.append('  %d\t%s\t%s' % (i, (t.get('title') or '')[:40], (t.get('url') or '')[:90]))
    lines.append('认领的那一页被关了或跳了域名丢了标记。先把上面这些列给用户确认是哪一个，'
                 '再 claim 重新认领；不要默认挑第一个，也不要反复重试同一条命令。')
    return '\n'.join(lines), 'other-tabs'


def connect(target, deadline=None):
    try:
        return Tab(target, deadline=deadline)
    except StageDeadline:
        raise
    except (OSError, TabError):
        return None


def find_tab(mark, match, deadline=None):
    """按认领标记（探测 sessionStorage）或 URL 子串找标签页；返回已连接的 Tab 或 None。不应答的标签页跳过。"""
    tabs = page_targets(deadline=deadline)
    if tabs is None:
        return 'ERR_NO_CDP'
    for t in tabs:
        remaining_timeout(deadline)
        if match and not mark:
            if match in t.get('url', ''):
                tab = connect(t, deadline=deadline)
                if tab:
                    return tab
            continue
        if not t.get('url', '').startswith('http'):
            continue
        tab = connect(t, deadline=deadline)
        if not tab:
            continue
        try:
            v, _ = tab.evaluate(PROBE_JS)
        except TabError:
            tab.close()
            remaining_timeout(deadline)
            continue
        if v == mark:
            return tab
        tab.close()
    remaining_timeout(deadline)
    return None


def new_run_id():
    return 'ca' + str(int(time.time()))[-5:]


def claim_js(run_id):
    """写认领标记；证书错误页、沙箱页这类不允许写存储的页面返回 'denied' 而不是抛异常。"""
    return f"(function(){{try{{sessionStorage.setItem('__caClaim','{run_id}');return 'ok'}}catch(e){{return 'denied'}}}})()"


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
        v, err = tab.evaluate(claim_js(run_id))
    finally:
        tab.close()
    if err:
        print(f'ERR_JS: {err}')
        return 1
    if v != 'ok':
        print(f"ERR_CLAIM: 这一页不允许写存储（证书错误页、沙箱页或浏览器内部页），先处理这一页或换一页再认领：{target.get('url', '')}")
        return 1
    print(f"{run_id}\t{target.get('url', '')}")
    note_hint(target.get('url', ''))
    return 0


def note_hint(url):
    """工作目录里已有这个域名的站点笔记就多打印一行，让调用方先读。"""
    host = urllib.parse.urlparse(url).hostname or ''
    rel = os.path.join('site-notes', host + '.md')
    if host and os.path.isfile(rel):
        print('NOTE ' + rel.replace(os.sep, '/'))


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
        v, err = tab.evaluate(claim_js(run_id))
        url_now, _ = tab.evaluate('location.href')
    finally:
        tab.close()
    if err:
        print(f'ERR_JS: {err}')
        return 1
    if v != 'ok':
        print(f'ERR_CLAIM: 这一页不允许写存储（证书错误页、沙箱页或浏览器内部页），先处理这一页再认领：{url_now or url}')
        return 1
    print(f"{run_id}\t{url_now or target.get('url', url)}")
    note_hint(url_now or target.get('url', url))
    return 0


RECT_JS = """(() => {{ const el = {expr}; if (!el) return null;
  el.scrollIntoView({{block: 'center', behavior: 'instant'}});
  const r = el.getBoundingClientRect();
  return JSON.stringify({{x: r.left + r.width / 2, y: r.top + r.height / 2, tag: el.tagName}}); }})()"""


def with_tab(fn):
    """找到 TAB_MARK / TAB_MATCH 指定的标签页，交给 fn(tab) 处理；错误行统一在这里打印。"""
    mark, match = os.environ.get('TAB_MARK', ''), os.environ.get('TAB_MATCH', '')
    if not (mark or match):
        print('ERR_NEED_TAB_MARK_OR_TAB_MATCH')
        return 2
    tab = find_tab(mark, match)
    if tab == 'ERR_NO_CDP':
        print(NO_CDP.format(port=PORT))
        return 2
    if tab is None:
        print(no_tab_report(mark, match)[0])
        return 1
    try:
        return fn(tab)
    except TabError as e:
        print(f'ERR_CDP: {e}')
        return 1
    finally:
        tab.close()


def mouse_click(tab, x, y):
    tab.call('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y)
    tab.call('Input.dispatchMouseEvent', type='mousePressed', x=x, y=y, button='left', clickCount=1)
    tab.call('Input.dispatchMouseEvent', type='mouseReleased', x=x, y=y, button='left', clickCount=1)


def click_target(tab, target, js_is_element=True):
    """点一个目标：`x,y` 坐标、CSS 选择器、或 js: 表达式（js_is_element 为真时表达式求值得到元素再点，否则直接执行）。
    返回 (退出码, 说明行)。"""
    m = re.fullmatch(r'\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*', target)
    if m:
        mouse_click(tab, float(m.group(1)), float(m.group(2)))
        return 0, f'clicked {m.group(1)},{m.group(2)}'
    if target.startswith('js:') and not js_is_element:
        expr = target[3:]
        _, err = tab.evaluate(expr)
        return (1, f'ERR_JS: {err}') if err else (0, f'called {expr[:80]}')
    expr = element_expr(target)
    v, err = tab.evaluate(RECT_JS.format(expr=expr))
    if err:
        return 1, f'ERR_JS: {err}'
    if not v:
        return 1, f'NO_ELEMENT {target}'
    r = json.loads(v)
    for _ in range(8):  # 滚动或布局还在动时位置会变；连续两次测得同一位置才点，最多等约 2 秒
        time.sleep(0.25)
        v2, _ = tab.evaluate(RECT_JS.format(expr=expr))
        r2 = json.loads(v2) if v2 else r
        if (r2['x'], r2['y']) == (r['x'], r['y']):
            break
        r = r2
    mouse_click(tab, r['x'], r['y'])
    return 0, f"clicked {r['tag']} {r['x']:g},{r['y']:g}"


def cmd_click(target):
    def go(tab):
        code, msg = click_target(tab, target)
        print(msg)
        return code
    return with_tab(go)


def cmd_sniff(target):
    """装上请求钩子 → 触发动作 → 等一会 → 打印页面这期间发出的请求。"""
    wait = float(os.environ.get('SNIFF_WAIT', '3'))
    with open(os.path.join(HERE, 'lib_net.js'), encoding='utf-8') as f:
        lib = f.read()

    def go(tab):
        start, err = tab.evaluate(lib + '\n; window.__caNet.hook()')
        if err:
            print(f'ERR_JS: {err}')
            return 1
        start = int(start or 0)
        code, msg = click_target(tab, target, js_is_element=False)
        if code:
            print(msg)
            return code
        read = f'JSON.stringify(window.__caNet.seen({start}))'
        recs, stable, t0 = [], 0, time.time()
        while True:
            v, err = tab.evaluate(read)
            if not err and v:
                new = json.loads(v)
                stable = stable + 1 if len(new) == len(recs) and new and all(r.get('done') for r in new) else 0
                recs = new
            elapsed = time.time() - t0
            if elapsed >= wait or (stable >= 2 and elapsed >= 1):
                break
            time.sleep(0.5)
        print(f'SNIFF {len(recs)} 请求（触发：{msg}）')
        for r in recs:
            body = (r.get('body') or '').replace('\n', ' ')[:120]
            print(f"{r.get('method')} {r.get('url')}" + (f'  请求体 {body}' if body else '')
                  + f"  → {r.get('status', '…')} {r.get('respType') or ''} {r.get('respLen', 0)}字")
        print('---')
        print(json.dumps(recs, ensure_ascii=False, indent=1))
        return 0
    return with_tab(go)


TYPE_SELECT_JS = """(() => {{ const el = {expr}; if (!el) return null; window.__caTypeSelect = 1;
  el.focus();
  if (typeof el.select === 'function') el.select();
  else if (el.isContentEditable) {{ const r = document.createRange(); r.selectNodeContents(el); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }}
  return el.tagName; }})()"""
TYPE_READ_JS = """(() => {{ const el = {expr}; if (!el) return null; window.__caTypeRead = 1;
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  el.dispatchEvent(new FocusEvent('blur'));
  el.dispatchEvent(new FocusEvent('focusout', {{ bubbles: true }}));
  return typeof el.value === 'string' ? el.value : (el.innerText || ''); }})()"""


def element_expr(target):
    """click / type 共用的目标写法：js: 表达式求值得到元素，否则是 CSS 选择器（取第一个可见匹配）。

    可见性不用 offsetParent：它对 position:fixed 的元素恒为假，而弹窗里的按钮、挂在 body 下的
    下拉面板项几乎都是 fixed 或绝对定位，用它会点不到。
    """
    if target.startswith('js:'):
        return target[3:]
    return (f'[...document.querySelectorAll({json.dumps(target)})].find(e => '
            "typeof e.checkVisibility === 'function' "
            '? e.checkVisibility({checkOpacity:true, checkVisibilityCSS:true}) '
            ': e.getClientRects().length > 0)')


def cmd_type(target, text):
    if text.startswith('@'):
        path = text[1:]
        if not os.path.isfile(path):
            print(f'ERR_NO_FILE {path}')
            return 2
        with open(path, encoding='utf-8') as f:
            text = f.read()

    def go(tab):
        code, msg = click_target(tab, target)
        if code:
            print(msg)
            return code
        expr = element_expr(target)
        tag, err = tab.evaluate(TYPE_SELECT_JS.format(expr=expr))
        if err or not tag:
            print(f'ERR_JS: {err}' if err else f'NO_ELEMENT {target}')
            return 1
        tab.call('Input.insertText', text=text)
        v, err = tab.evaluate(TYPE_READ_JS.format(expr=expr))
        if err:
            print(f'ERR_JS: {err}')
            return 1
        v = v or ''
        if v != text:
            print(f'ERR_TYPE 回读 {len(v)}字 ≠ 输入 {len(text)}字：{v[:40]!r}')
            return 1
        print(f'typed {tag} {len(text)}字 回读 {len(v)}字 一致')
        return 0
    return with_tab(go)


UPLOAD_READ_JS = """(() => {{ const el = document.querySelector({sel}); window.__caUploadRead = 1;
  return JSON.stringify(el && el.files ? [...el.files].map(f => f.name) : []); }})()"""

# 上传成功的佐证要从页面上找，不能只看 input.files：站点在 change 回调里取走文件、
# 随即清空控件是常规做法（防重复提交、释放引用），越规范的站点越会这么干。回读为空
# 只说明"读不出来了"，不说明没传成——而把它当成失败会诱发重传，有的站点重传会二次
# 弹出破坏性确认框。所以另外看：页面上有没有出现这个文件名、有没有新的弹窗或进度条。
UPLOAD_EVIDENCE_JS = """(() => {{ const name = {name}; const stem = {stem};
  const text = document.body ? (document.body.innerText || '') : '';
  const vis = el => el && el.isConnected && (typeof el.checkVisibility === 'function'
    ? el.checkVisibility({{ checkOpacity: true, checkVisibilityCSS: true }})
    : el.getClientRects().length > 0);
  const words = ['上传中', '解析中', '上传成功', '解析完成', '已上传', '上传失败', '正在上传'];
  return JSON.stringify({{
    fileNameOnPage: text.includes(name) || (stem.length >= 4 && text.includes(stem)),
    statusWords: words.filter(w => text.includes(w)),
    progressBars: [...document.querySelectorAll(
      'progress, [role=progressbar], [class*="progress"], [class*="Progress"]')]
      .filter(vis).length,
    dialogs: [...document.querySelectorAll(
      '[role=dialog], [role=alertdialog], dialog[open], [aria-modal="true"]')]
      .filter(vis).length,
  }}); }})()"""


def cmd_upload(selector, path):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        print(f'ERR_NO_FILE {path}')
        return 2

    def go(tab):
        root = tab.call('DOM.getDocument')
        node = tab.call('DOM.querySelector', nodeId=root['root']['nodeId'], selector=selector).get('nodeId', 0)
        if not node:
            print(f'NO_ELEMENT {selector}')
            return 1
        try:
            tab.call('DOM.setFileInputFiles', files=[path], nodeId=node)
        except TabError as e:
            print(f'ERR_UPLOAD 文件没送进控件：{e}')
            return 1
        # 走到这里说明浏览器已经把文件交给了控件。后面读到什么都只是佐证，不是判据。
        base = os.path.basename(path)
        v, err = tab.evaluate(UPLOAD_READ_JS.format(sel=json.dumps(selector)))
        names = [] if err else json.loads(v or '[]')
        ev, ev_err = tab.evaluate(UPLOAD_EVIDENCE_JS.format(
            name=json.dumps(base), stem=json.dumps(os.path.splitext(base)[0])))
        evidence = {} if ev_err else json.loads(ev or '{}')
        if names:
            print(f"uploaded {base} → input.files {len(names)} 个：{'、'.join(names)}")
        else:
            hints = []
            if evidence.get('fileNameOnPage'):
                hints.append('页面上出现了文件名')
            if evidence.get('statusWords'):
                hints.append('页面状态文字：' + '、'.join(evidence['statusWords']))
            if evidence.get('progressBars'):
                hints.append(f"{evidence['progressBars']} 个进度条")
            if evidence.get('dialogs'):
                hints.append(f"{evidence['dialogs']} 个弹窗（可能是确认框，先读它再动）")
            print(f'uploaded {base} → 控件已被站点清空（取走文件后清空是常规做法，不是失败）'
                  + ('；' + '，'.join(hints) if hints else
                     '；页面上暂时看不到佐证，接下来只读核对上传区再决定下一步'))
        print('不要因为回读不到文件名就重传——有的站点重传会弹出破坏性确认框')
        return 0
    return with_tab(go)


FILL_KINDS = ('text', 'dropdown', 'search', 'cascader', 'date', 'checkbox', 'native-select')


def as_limit(value):
    """把"可能是数字"的东西读成一个正整数上限；读不出就返回 None（当作没有上限）。

    页面上的数字属性是字符串，不保证是数字：真实表单里见过 `maxlength="Infinity"`，浏览器
    按"没有上限"对待，而 `int("Infinity")` 会抛异常。计划里的 `max` 同理——那是模型写的。
    这里统一兜住：取不出有限正整数就当没给，绝不让整条命令因为一个属性值退出。
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return int(number)


def _fill_call(tab, expr):
    """调一次 __caFill 的方法，返回解析好的结果；页内抛异常算 TabError。"""
    v, err = tab.evaluate('JSON.stringify(' + expr + ')', await_promise=False)
    if err:
        raise TabError(err)
    return json.loads(v) if v else None


def _wait_for(tab, expr, want, budget):
    """按条件等，不按秒等：反复求值直到满足 want(值)，或超过 budget 秒。返回 (是否满足, 最后的值)。
    借 jev-ultrafast 的做法——真实站点的面板和建议项要等，但等的是状态而不是固定时长。"""
    deadline = time.monotonic() + budget
    value = None
    while True:
        value = _fill_call(tab, expr)
        if want(value):
            return True, value
        if time.monotonic() >= deadline:
            return False, value
        time.sleep(0.03)


def _panel_for(tab, handle, budget):
    """找这次点击开出来的面板：取点击之后新出现的节点，按"更像面板"排序取第一个。

    不按 class 全局列举，也不用几何淘汰。两个真实站点给过两种相反的死法：一个站的真面板
    被同样命中选择器的祖先容器吞掉，另一个站的面板盖在输入框上、被"必须紧贴若干像素"的
    配对规则扔掉。面板是点出来的，所以"这一轮新出现"才是它的本质特征，几何只用于排序。
    """
    expr = 'window.__caFill.appeared(%d)' % handle
    ok, found = _wait_for(tab, expr, lambda v: bool(v), budget)
    if not ok or not found:
        return None
    panel = found[0]
    _fill_call(tab, 'window.__caFill.noteOpen(%d, %d)' % (handle, panel['handle']))
    return panel


def _panel_still_open(tab, handle):
    """这个字段的面板还开着吗。只问我们记过账的那一个，不扫全页。"""
    open_now = _fill_call(tab, 'window.__caFill.stillOpen()') or []
    return any(p.get('field') == handle for p in open_now)


def _panel_closed_within(tab, handle, budget=0.4):
    """收面板的动作发出之后，等它真的消失——按条件等，不按秒等。

    收起来往往不是同步的：组件要跑一段过渡动画或者等一轮 React 提交，这期间面板仍在 DOM 里。
    瞬时查一次会把"正在收"读成"没收掉"，于是一招接一招地试下去，最后判成收不起来——
    真实站点上第一个延迟收的下拉就会卡住整轮探测。budget 用完仍在就是真没收掉。
    """
    expr = 'window.__caFill.stillOpen()'
    closed, _ = _wait_for(tab, expr,
                          lambda v: not any(p.get('field') == handle for p in (v or [])),
                          budget)
    return closed


# 收面板的几招。顺序不写死：哪一招在本页奏效就记下来，后面的字段先试它。
# 两个真实站点的结论正好相反——一个站"再点一次输入框"十次全中、"点字段标题"十次全不中，
# 另一个站反过来。所以这是要现场试出来的，不是可以定在代码里的偏好。
CLOSE_TRICKS = ('click-input-again', 'click-field-label', 'click-section-title',
                'soft-click-label')


def _close_panels(tab, handle, budget, learned=None):
    """收面板，第一个奏效就停。返回 (用的哪一招, 是否收干净)。

    learned 是本页已经试出来的那一招，有就先试它。禁止 document.body.click()，禁止键盘事件。
    budget 是整个收面板环节的预算，每一招分到其中一份：收起来常有过渡动画或一轮 React
    提交的延迟，发完动作立刻查会把"正在收"读成"没收掉"。
    """
    if not _panel_still_open(tab, handle):
        _fill_call(tab, 'window.__caFill.noteClosed(%d)' % handle)
        return 'already-closed', True
    per_trick = max(0.2, min(0.6, (budget or 0) / len(CLOSE_TRICKS)))
    actions = {
        'click-input-again': lambda: _real_click(tab, handle),
        'click-field-label': lambda: _click_own_label(tab, handle),
        'click-section-title': lambda: _click_section_title(tab, handle),
        'soft-click-label': lambda: _soft_click_label(tab, handle),
    }
    order = list(CLOSE_TRICKS)
    if learned in actions:                                  # 本页已知有效的先试
        order.remove(learned)
        order.insert(0, learned)
    for name in order:
        try:
            actions[name]()
        except TabError:
            continue
        if _panel_closed_within(tab, handle, per_trick):
            _fill_call(tab, 'window.__caFill.noteClosed(%d)' % handle)
            return name, True
    return 'none', False


def _own_label(tab, handle):
    found = _fill_call(tab, f'window.__caFill.labelOf({handle})')
    if not found or not found.get('handle'):
        raise TabError('没找到该字段的标签')
    return found['handle']


def _click_own_label(tab, handle):
    """发真实鼠标事件点这个控件所在字段容器里的 label（自定义下拉常常只认这一招）。"""
    return _real_click(tab, _own_label(tab, handle))


def _soft_click_label(tab, handle):
    """对标签派发合成点击（有的组件只在 mousedown/click 冒泡到容器时才收面板）。"""
    return _fill_call(tab, f'window.__caFill.softClick({_own_label(tab, handle)})')


def _click_section_title(tab, handle):
    """点这个控件所在板块的标题。有的组件只在点到板块外的静态文字时才收面板——
    点字段自己的标签反而会把面板重新打开。两个真实站点的有效招式正好相反。"""
    found = _fill_call(tab, f'window.__caFill.sectionTitle({handle})')
    if not found or not found.get('handle'):
        raise TabError('没找到所在板块的标题')
    return _real_click(tab, found['handle'])


def _real_click(tab, handle):
    """发真实鼠标事件点一个 handle：执行前重新校验几何与遮挡，必要时先滚进视口。"""
    aim = _fill_call(tab, f'window.__caFill.aim({handle})')
    if aim and not aim['ok'] and aim.get('why') in ('offscreen', 'covered'):
        _fill_call(tab, f'window.__caFill.scrollTo({handle})')
        time.sleep(0.05)
        aim = _fill_call(tab, f'window.__caFill.aim({handle})')
    if not aim or not aim['ok']:
        raise TabError('点不了：' + (aim or {}).get('why', '未知') + (
            '（被 ' + aim['by'] + ' 挡住）' if aim and aim.get('by') else ''))
    r = aim['rect']
    mouse_click(tab, r['cx'], r['cy'])
    return True


def _verify(tab, handle, want, display_selector, kind):
    """三层回读。显示值与 DOM 一致即通过；模型层只作参考，不单独否决。"""
    back = _fill_call(tab, 'window.__caFill.readback(%d, %s)'
                      % (handle, json.dumps(display_selector) if display_selector else 'null'))
    errors = _fill_call(tab, f'window.__caFill.errors({handle})') or []
    dom, display, model = back.get('dom'), back.get('display'), back.get('model') or {}
    if kind in ('dropdown', 'search', 'cascader', 'date'):
        visible_ok = display == want                        # 这些控件的值在显示元素上，input.value 常常是空的
    elif kind == 'checkbox':
        visible_ok = True                                   # toggle 自己回读过
    else:
        visible_ok = dom == want
    model_ok = (not model.get('found')) or model.get('value') == want
    return dict(ok=bool(visible_ok) and not errors, visible_ok=bool(visible_ok),
                model_found=bool(model.get('found')), model_ok=bool(model_ok),
                model_via=model.get('via'), dom_len=len(dom) if isinstance(dom, str) else None,
                display=display, errors=errors)


def _fill_one(tab, item, waits, learned=None):
    """按一个字段的计划动作到位。返回 (是否成功, 记录字典)。不抛到外面。

    learned 是本页已经试出来的收面板办法，由调用方在字段之间传下去。
    """
    kind, selector = item.get('kind', 'text'), item.get('selector', '')
    # label 是定位用的字段标签（要和页面上的一致）；报告里显示的名字另给 title，
    # 没给就退回 label。两者混用会让"把显示名写顺口一点"变成定位失败。
    want = item.get('value')
    label = item.get('title') or item.get('label') or item.get('key') or selector
    record = dict(key=item.get('key') or label, kind=kind, label=label, status='failed')
    if kind not in FILL_KINDS:
        record['why'] = 'kind 不认识：' + str(kind)
        return False, record
    # 定位：给了语义坐标就按语义找，否则退回 selector + index。两条路都在报告里标明
    # 走的哪条——位置量写错一位就会操作到完全无关的控件，出了事要能一眼看出是哪种寻址。
    # 判据不能把 label 算进去：老计划普遍用 label 当显示名，拿它当语义寻址的信号会让
    # 每一份老计划都走错路。给了 selector 就按 selector 走，语义寻址要 section/occurrence/nth。
    via = 'selector'
    if not selector and any(item.get(k) is not None
                            for k in ('section', 'occurrence', 'nth', 'label')):
        via = 'semantic'
        info = _fill_call(tab, 'window.__caFill.locate(%s, %s, %s, %s)' % (
            json.dumps(item.get('section')) if item.get('section') is not None else 'null',
            int(item['occurrence']) if item.get('occurrence') is not None else 'null',
            json.dumps(item.get('label')) if item.get('label') is not None else 'null',
            int(item['nth']) if item.get('nth') is not None else 'null'))
        if info and info.get('error') == 'ambiguous':
            record['why'] = ('语义坐标不唯一，匹配到 %d 个：' % info.get('count', 0)
                             + json.dumps(info.get('candidates'), ensure_ascii=False))
            return False, record
        if info and info.get('error') == 'not-found':
            near = info.get('sameLabel') or []
            record['why'] = ('按语义坐标找不到这个字段'
                             + ('，同名标签出现在：' + json.dumps(near, ensure_ascii=False)
                                if near else ''))
            return False, record
    else:
        info = _fill_call(tab, 'window.__caFill.resolve(%s, %d)'
                          % (json.dumps(selector), int(item.get('index', 0) or 0)))
    record['via'] = via
    if not info or info.get('error'):
        record['why'] = {'not-found': '找不到控件', 'bad-selector': '选择器不合法'}.get(
            (info or {}).get('error'), str((info or {}).get('error')))
        return False, record
    handle = info['handle']
    # 身份校验：声明权在模型，执行权在代码。模型说这个控件的名字应当含什么，
    # 对不上就不动它——比事后发现写错了再回滚便宜得多。
    ident = _fill_call(tab, f'window.__caFill.identify({handle})') or {}
    expect = item.get('expect_label')
    if expect and expect not in (ident.get('name') or ''):
        record['why'] = (f'控件身份校验不通过：计划期望名称含「{expect}」，'
                         f'实到「{ident.get("name")}」，没有动它')
        return False, record
    if ident.get('sensitive') and not item.get('sensitive_ok'):
        # 算失败不算跳过：skipped 是"客观写不进"（账号级 disabled 字段），
        # 这里是计划明确要求了而我们拒绝执行，调用方必须知道这个字段没写成。
        record['why'] = (f'敏感字段（「{ident.get("name")}」）不写入；'
                         f'确有必要请在计划里写 sensitive_ok 并由用户确认')
        return False, record
    record['resolved'] = dict(tag=info['tag'], name=info.get('name'),
                              matched=info.get('matched'), visible=info.get('visible'))
    if info.get('disabled'):
        record.update(status='skipped', why='控件 disabled，写不进（账号级字段去账号设置页改）')
        return False, record
    # 在 DOM 里但不可见：多半是未激活的分步页、折叠板块或条件字段。这种控件写得进去、
    # 三层回读还会通过（读到的就是刚写的值），但用户看不见，站点换步时也可能丢——
    # 所以必须在这里拦住，否则报告会显示 OK 而实际上什么都没发生在用户眼前。
    # 一份计划只写当前激活步骤的字段；下一步的字段等翻页后用新计划填。
    if not info.get('visible'):
        record['why'] = '控件在 DOM 里但不可见（多半在未激活的分步页或折叠板块里），没有写入'
        return False, record

    try:
        if kind == 'text':
            limit = as_limit(item.get('max'))
            if limit and isinstance(want, str) and len(want) > limit:
                record.update(why=f'文本 {len(want)} 字超过本字段上限 {limit} 字，没有写入')
                return False, record
            wrote = _fill_call(tab, 'window.__caFill.write(%d, %s)' % (handle, json.dumps(want)))
            if not wrote.get('ok'):
                record['why'] = '写不进：' + wrote.get('why', '未知')
                return False, record

        elif kind == 'native-select':
            got = _fill_call(tab, 'window.__caFill.nativeSelect(%d, %s)' % (handle, json.dumps(want)))
            if not got.get('ok'):
                record['why'] = ('没有这个选项，页面上有：' + '、'.join(got.get('available', [])[:12])
                                 if got.get('why') == 'no-option' else '选不上：' + str(got.get('why')))
                return False, record

        elif kind == 'checkbox':
            got = _fill_call(tab, 'window.__caFill.toggle(%d, %s)'
                             % (handle, 'true' if want else 'false'))
            if not got.get('ok'):
                record['why'] = '勾选状态没改成：' + str(got.get('why') or got.get('checked'))
                return False, record
            record['changed'] = got.get('changed')

        else:
            # 面板类：装观察器 → 开面板 → 收新出现的节点 → 选 → 收面板 → 销账
            steps = want if kind == 'cascader' and isinstance(want, list) else [want]
            _fill_call(tab, 'window.__caFill.watchStart()')   # 必须在点击之前
            if kind == 'search':
                _real_click(tab, handle)
                term = item.get('term') or (steps[0] if isinstance(steps[0], str) else '')
                wrote = _fill_call(tab, 'window.__caFill.write(%d, %s)' % (handle, json.dumps(term)))
                if not wrote.get('ok'):
                    record['why'] = '搜索词写不进：' + wrote.get('why', '未知')
                    return False, record
            else:
                _real_click(tab, handle)
            panel = _panel_for(tab, handle, waits['panel'])
            if panel is None:
                record['why'] = f"点了之后 {waits['panel']:g} 秒内没出现面板"
                return False, record
            record['panel'] = panel['cls'][:40]
            for depth, step in enumerate(steps):
                # 级联每点一级，下一级可能才渲染出来，所以每级都重新等选项
                ok, got = _wait_for(
                    tab, 'window.__caFill.option(%d, %s, true)' % (panel['handle'], json.dumps(step)),
                    lambda v: bool(v and v.get('handle')), waits['option'])
                if not ok:
                    available = (got or {}).get('available', [])
                    record['why'] = (f'第 {depth + 1} 级没有「{step}」'
                                     + ('，面板里有：' + '、'.join(available[:12]) if available else ''))
                    _close_panels(tab, handle, waits['panel'], learned)
                    return False, record
                _real_click(tab, got['handle'])
                # 级联的下一级可能新开一个面板，也可能就在当前面板里追加一列。
                # 取不到新节点不是失败，继续用当前这个。
                if depth + 1 < len(steps):
                    panel = _panel_for(tab, handle, waits['panel']) or panel
            how, closed = _close_panels(tab, handle, waits['panel'], learned)
            record['closed_by'] = how
            if not closed:
                record['why'] = '选完了但面板收不起来'
                return False, record
            if kind == 'cascader' and isinstance(want, list):
                want = item.get('display') or ' / '.join(want)

    except TabError as e:
        record['why'] = str(e)
        return False, record

    check = _verify(tab, handle, want, item.get('display_selector'), kind)
    record['readback'] = check
    if not check['ok']:
        record['why'] = ('回读不一致：显示/DOM 读到 '
                         + repr(check['display'] if kind != 'text' else check['dom_len'])
                         + (('；页面报错：' + '、'.join(check['errors'])) if check['errors'] else ''))
        return False, record
    record['status'] = 'filled'
    return True, record


def _uses_selector_addressing(item):
    """这一条是不是走 selector + index。判据和执行时的分流保持一致：给了 selector 就按
    selector 走，语义坐标也在也不改路——所以门禁要拦的就是"有 selector"这一个条件。"""
    return bool(item.get('selector'))


def cmd_fill(plan_path, max_seconds=120, allow_selector=False):
    """按计划 JSON 在页内连续填完一页：开面板、按条件等、选中、收面板、三层回读，一次调用一份报告。

    计划里的字段名、选择器、目标值只当数据用，不拼进 JS 执行；元素由 lib_fill.js 按 handle 持有。
    """
    try:
        max_seconds = float(max_seconds)
        if not (max_seconds > 0 and math.isfinite(max_seconds)):
            raise ValueError
    except (TypeError, ValueError):
        print('ERR_USAGE fill: --max 需要一个有限正数秒数')
        return 2
    if not os.path.isfile(plan_path):
        print(f'ERR_NO_FILE {plan_path}')
        return 2
    try:
        with open(plan_path, encoding='utf-8') as f:
            plan = json.load(f)
    except (OSError, ValueError) as e:
        print(f'ERR_PLAN: 读不出计划 JSON：{e}')
        return 2
    if not isinstance(plan, (dict, list)):
        print('ERR_PLAN: 计划要么是 {"fields": [...]}，要么直接是字段数组')
        return 2
    if isinstance(plan, list):
        plan = {'fields': plan}                             # 裸数组是 {"fields": [...]} 的简写
    items = plan.get('fields')
    if not isinstance(items, list) or not items:
        print('ERR_PLAN: 计划里没有 fields 数组')
        return 2
    if not all(isinstance(item, dict) for item in items):
        print('ERR_PLAN: fields 里每一项都要是对象')
        return 2
    # 位置坐标默认不许用：index 写错一位就操作到完全无关的控件，而最敏感的字段往往恰好
    # 排在最前面。要用得显式开——计划里写 "addressing": "selector"，或者命令行加
    # --allow-selector。门禁只认"有没有 selector"，和执行时的分流判据是同一个条件。
    if not (allow_selector or plan.get('addressing') == 'selector'):
        offenders = [item.get('key') or item.get('label') or '(未命名)'
                     for item in items if _uses_selector_addressing(item)]
        if offenders:
            print('ERR_PLAN: 这份计划用了位置坐标但没开开关。'
                  f'共 {len(offenders)} 个字段给了 selector：'
                  + '、'.join(str(k) for k in offenders[:8])
                  + ('…' if len(offenders) > 8 else ''))
            print('  默认只认语义坐标（section / occurrence / label / nth），由 plan-skeleton 生成。')
            print('  骨架覆盖不到、确实要用 selector + index 时，在计划里加 "addressing": "selector"，'
                  '或者命令行加 --allow-selector。')
            return 2
    pace = plan.get('pace') if isinstance(plan.get('pace'), dict) else {}
    try:
        lo = float(pace.get('min', os.environ.get('PACE_MIN') or 0.3))
        hi = float(pace.get('max', os.environ.get('PACE_MAX') or 0.8))
        waits = {'panel': float(plan.get('panel_wait', 2.0)),
                 'option': float(plan.get('option_wait', 2.0))}
    except (TypeError, ValueError):
        print('ERR_PLAN: pace / panel_wait / option_wait 要是数字')
        return 2
    if not all(0 <= v < 60 for v in (lo, hi, waits['panel'], waits['option'])) or hi < lo:
        print('ERR_PLAN: pace 与等待秒数要在 0 到 60 之间，且 pace.max 不小于 pace.min')
        return 2
    started = time.monotonic()
    deadline = started + max_seconds

    def go(tab):
        with open(os.path.join(HERE, 'lib_fill.js'), encoding='utf-8') as f:
            lib = f.read()
        _, err = tab.evaluate(lib + '\n; !!window.__caFill', await_promise=False)
        if err:
            print(f'ERR_JS: 注入填写库失败：{err}')
            return 1
        records, filled, learned = [], 0, None
        for item in items:
            if time.monotonic() >= deadline:
                records.append(dict(key=item.get('key') or item.get('selector'), status='not-started',
                                    why=f'到了 {max_seconds:g} 秒预算，这个字段没开始'))
                continue
            try:
                ok, record = _fill_one(tab, item, waits, learned)
            except TabError as e:
                ok, record = False, dict(key=item.get('key') or item.get('selector'),
                                         status='failed', why=f'ERR_CDP: {e}')
            # 哪一招收得掉面板是一页一个样，试出来就记住，后面的字段先用它
            if record.get('closed_by') in CLOSE_TRICKS:
                learned = record['closed_by']
            records.append(record)
            filled += 1 if ok else 0
            time.sleep(random.uniform(lo, hi))              # 字段间留间隔，节奏照 skill 的两档规矩
        # 收尾的只读检查不能把账本烧掉：页面在填写期间导航过的话 window.__caFill 随旧文档消失，
        # 这一行会抛异常。先把逐字段报告打出去，再报告上下文丢了。
        lost, still = None, []
        try:
            still = _fill_call(tab, 'window.__caFill.stillOpen()') or []
        except TabError as e:
            lost = str(e)
        left = None if lost else len(still)
        report = dict(plan=os.path.basename(plan_path), total=len(items), filled=filled,
                      open_panels=left, open_panel_fields=[p.get('field') for p in still],
                      close_trick=learned, context_lost=lost,
                      elapsed_seconds=round(time.monotonic() - started, 3), fields=records)
        for r in records:
            mark = {'filled': 'OK  ', 'skipped': 'SKIP', 'not-started': '----'}.get(r['status'], 'FAIL')
            print(f"{mark} {r.get('label') or r.get('key')}"
                  + (('  ' + r['why']) if r.get('why') else ''))
        print('---')
        print(json.dumps(report, ensure_ascii=False, indent=1))
        bad = [r for r in records if r['status'] not in ('filled', 'skipped')]
        if lost:
            print(f'ERR_CONTEXT 页面在填写过程中变了（导航或重渲染），面板状态未知：{lost}')
            print('上面逐字段的结果是页面变化之前的，先只读核对当前页面再决定补填哪些')
            return 1
        if left:
            print(f'ERR_PANELS 我们开的面板还有 {left} 个没收掉')
            return 1
        if bad:
            print(f'ERR_FILL {len(bad)}/{len(items)} 个字段没填成')
            return 1
        print(f'DONE {filled}/{len(items)} 个字段已填并回读一致，面板 0')
        return 0

    return _with_claimed_tab(go, deadline)


def cmd_plan_skeleton(out_path, skip_ok=None):
    """从当前页面生成一份计划骨架：字段的语义坐标由代码从 DOM 读出来，模型只往 value 里填值。

    为什么不让模型自己写坐标：整页一百多个字段时，模型要先抄一遍控件下标、写计划时再按
    新下标重算一遍；给某个板块加一组条目，全局下标全变，一百多个数字要重新映射。这两笔
    是实测里最大的两段浏览器空置时间，而它们产出的东西页面自己就知道。

    skip_ok 指向上一次的 fill 报告，里面标 filled 的字段这次不再列出——只补没填成的那些，
    不必为了几个失败字段把整页长文本重写一遍。
    """
    done = set()
    if skip_ok:
        try:
            with open(skip_ok, encoding='utf-8') as f:
                prior = json.load(f)
        except (OSError, ValueError) as e:
            print(f'ERR_PLAN: 读不出上一次的报告：{e}')
            return 2
        for r in (prior.get('fields') or []):
            if r.get('status') == 'filled':
                done.add(r.get('key'))

    def go(tab):
        with open(os.path.join(HERE, 'lib_fill.js'), encoding='utf-8') as f:
            lib = f.read()
        _, err = tab.evaluate(lib + '\n; !!window.__caFill', await_promise=False)
        if err:
            print(f'ERR_JS: 注入填写库失败：{err}')
            return 1
        outline = _fill_call(tab, 'window.__caFill.outline()')
        fields, skipped = [], 0
        for f in outline['fields']:
            key = ' / '.join(str(x) for x in
                             (f['section'], f['occurrence'], f['label'], f['nth']) if x != '')
            if key in done:
                skipped += 1
                continue
            if f['disabled']:
                continue                                    # 账号级字段写不进，不占计划位置
            kind = 'checkbox' if f['type'] in ('checkbox', 'radio') else (
                'native-select' if f['tag'] == 'select' else 'text')
            item = dict(key=key, label=f['label'], section=f['section'],
                        occurrence=f['occurrence'], nth=f['nth'],
                        kind=kind, value=None)
            limit = as_limit(f['maxlength'])
            if limit is not None:
                item['max'] = limit
            if f['sensitive']:
                item['note'] = '敏感字段，默认不写；确需填写要加 sensitive_ok 并经用户确认'
            fields.append(item)
        plan = dict(source=outline['url'], fields=fields)
        try:
            with open(out_path, 'w', encoding='utf-8') as fh:
                json.dump(plan, fh, ensure_ascii=False, indent=1)
        except OSError as e:
            print(f'ERR_WRITE {out_path}：{e}')
            return 1
        by_section = {}
        for f in fields:
            by_section[f['section']] = by_section.get(f['section'], 0) + 1
        for section, n in by_section.items():
            print(f'{section or "（无标题板块）"}\t{n} 个字段')
        print('---')
        print(f'SKELETON {len(fields)} 个字段待填'
              + (f'，跳过上轮已成的 {skipped} 个' if skipped else '')
              + f' → {out_path}')
        print('每个字段的 value 现在是 null，填上值再交给 fill；kind 按实际控件改'
              '（dropdown / search / cascader / date）')
        return 0

    return _with_claimed_tab(go)


def _with_claimed_tab(go, deadline=None):
    """找到认领的标签页、跑 go(tab)、收尾关连接。几个子命令共用这段。"""
    mark, match = os.environ.get('TAB_MARK', ''), os.environ.get('TAB_MATCH', '')
    if not (mark or match):
        print('ERR_NEED_TAB_MARK_OR_TAB_MATCH')
        return 2
    tab = find_tab(mark, match, deadline=deadline)
    if tab == 'ERR_NO_CDP':
        print(NO_CDP.format(port=PORT))
        return 2
    if tab is None:
        print(no_tab_report(mark, match, deadline=deadline)[0])
        return 1
    try:
        return go(tab)
    except TabError as e:
        print(f'ERR_CDP: {e}')
        return 1
    finally:
        tab.close()


def cmd_survey(out_path):
    """只读地把这一页摸清楚，一条命令抵十几次往返。

    探测本身浏览器只动几秒，贵的是命令之间的往返和模型抄表：确认渲染稳定要探两次、
    字段结构要抄一遍、上传位要分几路找、长文本的限制要分别读属性和页面明文。
    这些都在页内一次做完，省掉的是空等。

    只读：不点击、不写入、不开面板。会开面板的那部分在 probe-options。
    """
    def go(tab):
        with open(os.path.join(HERE, 'lib_fill.js'), encoding='utf-8') as f:
            lib = f.read()
        _, err = tab.evaluate(lib + '\n; !!window.__caFill', await_promise=False)
        if err:
            print(f'ERR_JS: 注入填写库失败：{err}')
            return 1
        # 渲染稳定：表单常常分批出现，控件数不再变才算稳
        counts = []
        for _ in range(3):
            counts.append(len(_fill_call(tab, 'window.__caFill.outline()')['fields']))
            if len(counts) >= 2 and counts[-1] == counts[-2]:
                break
            time.sleep(1.2)
        stable = len(counts) >= 2 and counts[-1] == counts[-2]
        outline = _fill_call(tab, 'window.__caFill.outline()')
        with open(os.path.join(HERE, 'probe.js'), encoding='utf-8') as f:
            probe_src = f.read()
        probe_raw, err = tab.evaluate(probe_src, await_promise=False)
        probe = json.loads(probe_raw) if not err and probe_raw else None
        # 上传位：五路一起找，省得一路一次往返
        uploads = _fill_call(tab, '''(() => {
          const direct = [...document.querySelectorAll('input[type=file]')];
          const accept = [...document.querySelectorAll('[accept]')];
          const hosts = [...document.querySelectorAll('*')].filter(e => e.shadowRoot);
          const inShadow = [];
          const dig = (root, depth) => {
            if (depth > 6) return;
            for (const el of root.querySelectorAll('input[type=file]')) inShadow.push(el);
            for (const el of root.querySelectorAll('*')) if (el.shadowRoot) dig(el.shadowRoot, depth + 1);
          };
          hosts.forEach(h => dig(h.shadowRoot, 0));
          const words = ['上传', '附件', '简历文件', '导入简历', '解析', '选择文件', '拖拽', 'upload'];
          const text = document.body.innerText || '';
          const frames = [...document.querySelectorAll('iframe')]
            .map(f => ({ src: f.getAttribute('src'), visible: f.getClientRects().length > 0 }));
          return { directFileInputs: direct.length, shadowFileInputs: inShadow.length,
                   shadowHosts: hosts.length, acceptNodes: accept.length,
                   vocabHits: words.filter(w => text.includes(w)), iframes: frames,
                   textLength: text.length };
        })()''')
        # 页面上的按钮哪些会提交：点错一个就不可逆，所以在同一次探测里一并读出来，
        # 不要等到要点的时候再单独跑一趟。只读 DOM，不点任何东西。
        buttons = _fill_call(tab, '''(() => {
          const vis = el => el.isConnected && (typeof el.checkVisibility === 'function'
            ? el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })
            : el.getClientRects().length > 0);
          const clean = t => (t || '').replace(/\\s+/g, ' ').trim();
          const SUBMIT = ['提交', '投递', '确认投递', '立即投递', '申请职位', '确认提交'];
          const SAVE = ['保存', '暂存', '临时保存', '保存草稿'];
          const out = [];
          for (const el of document.querySelectorAll(
                 'button, [role=button], input[type=submit], a[class*="btn"], [class*="button"]')) {
            if (!vis(el)) continue;
            const text = clean(el.innerText || el.value);
            if (!text || text.length > 12) continue;
            const kind = SUBMIT.some(w => text.includes(w)) ? 'submit'
              : SAVE.some(w => text.includes(w)) ? 'save' : '';
            if (!kind) continue;
            if (out.some(o => o.text === text && o.kind === kind)) continue;
            out.push({ text, kind, tag: el.tagName.toLowerCase(),
                       type: el.getAttribute('type') || '' });
          }
          return out;
        })()''') or []
        report = dict(url=outline['url'], title=outline['title'],
                      stable=stable, field_counts=counts, buttons=buttons,
                      sections=sorted({f['section'] for f in outline['fields']}),
                      fields=outline['fields'],
                      probe=probe, upload=uploads)
        try:
            with open(out_path, 'w', encoding='utf-8') as fh:
                json.dump(report, fh, ensure_ascii=False, indent=1)
        except OSError as e:
            print(f'ERR_WRITE {out_path}：{e}')
            return 1
        print(f'SURVEY {len(outline["fields"])} 个可见字段，'
              f'{len(report["sections"])} 个板块，'
              + ('渲染已稳定' if stable else f'渲染还在变（{counts}），建议过几秒再跑一次'))
        has_upload = uploads['directFileInputs'] or uploads['shadowFileInputs']
        print('上传位：' + (f'有 {uploads["directFileInputs"]} 个直接的、'
                            f'{uploads["shadowFileInputs"]} 个在 shadow DOM 里'
                            if has_upload else
                            '本页没有。' + ('正文里出现过 ' + '、'.join(uploads['vocabHits'])
                                            + '，可能在别的页面' if uploads['vocabHits']
                                            else '正文里也没有上传相关的说法')))
        submits = [b['text'] for b in buttons if b['kind'] == 'submit']
        saves = [b['text'] for b in buttons if b['kind'] == 'save']
        if submits:
            print('不可逆的按钮（永远由用户点）：' + '、'.join(submits))
        if saves:
            print('保存类按钮（默认不点，用户说要点才点）：' + '、'.join(saves))
        sensitive = [f['label'] for f in outline['fields'] if f['sensitive']]
        if sensitive:
            print('敏感字段（默认不写）：' + '、'.join(dict.fromkeys(sensitive)))
        unknown = [c['label'] for c in (probe or {}).get('controls', []) if c.get('valueUnknown')]
        if unknown:
            print('值读不出的字段（不许据此补填）：' + '、'.join(dict.fromkeys(unknown)))
        print(f'明细 → {out_path}')
        return 0

    return _with_claimed_tab(go)


def cmd_probe_options(out_path, only=None):
    """逐个打开面板类控件、读全部选项、收起来、验证已关，结论写进一个文件。

    **这条命令会动页面**（点开控件、再收起来），和只读的 survey 分开就是为了这个：
    动页面之前要跟用户说一声，表单里已经有内容时尤其要先问。

    为什么值得单独做一条：十几个下拉逐个探，是十几次命令往返加十几次模型决策；
    在页内连着做完只要几秒，而中间那些往返的时间浏览器全程闲着。
    """
    wanted = [k.strip() for k in (only or '').split(',') if k.strip()]

    def go(tab):
        with open(os.path.join(HERE, 'lib_fill.js'), encoding='utf-8') as f:
            lib = f.read()
        _, err = tab.evaluate(lib + '\n; !!window.__caFill', await_promise=False)
        if err:
            print(f'ERR_JS: 注入填写库失败：{err}')
            return 1
        fields = _fill_call(tab, 'window.__caFill.outline()')['fields']
        out, learned = [], None
        for f in fields:
            key = ' / '.join(str(x) for x in
                             (f['section'], f['occurrence'], f['label'], f['nth']) if x != '')
            if wanted and key not in wanted and f['label'] not in wanted:
                continue
            if f['disabled'] or f['sensitive']:
                continue
            if f['tag'] == 'select':                         # 原生 select 不用点开
                got = _fill_call(tab, 'window.__caFill.nativeSelect(%d, %s)'
                                 % (f['handle'], json.dumps('\u0000')))
                opts = (got or {}).get('available') or []
                out.append(dict(key=key, label=f['label'], kind='native-select',
                                options=opts, count=len(opts)))
                continue
            if f['valueLen']:
                out.append(dict(key=key, label=f['label'], skipped='这个字段已经有值，没有去点它'))
                continue
            _fill_call(tab, 'window.__caFill.watchStart()')
            try:
                _real_click(tab, f['handle'])
            except TabError as e:
                out.append(dict(key=key, label=f['label'], error=str(e)))
                continue
            panel = _panel_for(tab, f['handle'], 2.0)
            if panel is None:
                out.append(dict(key=key, label=f['label'], kind='text?',
                                note='点了没出现面板，多半是普通文本框'))
                continue
            opts = _fill_call(tab, 'window.__caFill.optionsIn(%d)' % panel['handle']) or []
            # 选一个值看页面会不会多出字段：有的字段是选了某项才出现的（选了语言才出现
            # 考试和分数），不在这里触发出来，它们在整页计划里就是缺的，填完一轮才发现。
            revealed = []
            if opts and not f['valueLen']:
                before = {(x['section'], x['occurrence'], x['label'], x['nth'])
                          for x in _fill_call(tab, 'window.__caFill.outline()')['fields']}
                picked = _fill_call(tab, 'window.__caFill.option(%d, %s, true)'
                                    % (panel['handle'], json.dumps(opts[0])))
                if picked and picked.get('handle'):
                    try:
                        _real_click(tab, picked['handle'])
                        time.sleep(0.3)
                        after = _fill_call(tab, 'window.__caFill.outline()')['fields']
                        revealed = [dict(section=x['section'], occurrence=x['occurrence'],
                                         label=x['label'], nth=x['nth'], tag=x['tag'])
                                    for x in after
                                    if (x['section'], x['occurrence'],
                                        x['label'], x['nth']) not in before]
                    except TabError:
                        pass
            how, closed = _close_panels(tab, f['handle'], 2.0, learned)
            if how in CLOSE_TRICKS:
                learned = how
            out.append(dict(key=key, label=f['label'],
                            kind='search' if f['maxlength'] else 'dropdown',
                            options=opts[:200], count=len(opts),
                            probed_with=opts[0] if revealed else None,
                            revealed=revealed,
                            closed_by=how, closed=closed))
            if not closed:
                print(f'STOP 「{f["label"]}」的面板收不起来，先停下，不再往下探')
                break
            time.sleep(random.uniform(0.2, 0.5))
        still = _fill_call(tab, 'window.__caFill.stillOpen()') or []
        where = _fill_call(tab, 'location.href')
        report = dict(url=where, close_trick=learned,
                      open_panels=len(still), fields=out)
        try:
            with open(out_path, 'w', encoding='utf-8') as fh:
                json.dump(report, fh, ensure_ascii=False, indent=1)
        except OSError as e:
            print(f'ERR_WRITE {out_path}：{e}')
            return 1
        for row in out:
            if row.get('options') is not None:
                print(f"{row['label']}\t{row['count']} 项\t"
                      + '、'.join(row['options'][:8])
                      + ('…' if row['count'] > 8 else ''))
            else:
                print(f"{row['label']}\t{row.get('note') or row.get('skipped') or row.get('error')}")
        print('---')
        extra = [r for r in out if r.get('revealed')]
        for row in extra:
            print(f"选「{row['label']}」= {row['probed_with']} 之后多出 "
                  + '、'.join(x['label'] or '(无标签)' for x in row['revealed'])
                  + '  ← 这些字段要一起填，别漏')
        if extra:
            print('注意：上面这些是条件字段，探测时选的值已经留在控件里，'
                  '填写时要按真实值重写一遍')
        print(f'OPTIONS {len(out)} 个控件探过'
              + (f'，收面板用的是 {learned}' if learned else '')
              + f' → {out_path}')
        if still:
            print(f'ERR_PANELS 我们开的面板还有 {len(still)} 个没收掉')
            return 1
        return 0

    return _with_claimed_tab(go)


def cmd_screenshot(out_path):
    def go(tab):
        tab.call('Page.bringToFront')
        data = tab.call('Page.captureScreenshot', format='png')['data']
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with open(out_path, 'wb') as f:
                f.write(base64.b64decode(data))
        except OSError as e:
            print(f'ERR_WRITE: 截图没写成 {out_path}：{e.strerror or e}')
            return 1
        print(out_path)
        return 0
    return with_tab(go)


def format_value(v):
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def run_js(js_text, await_promise=True):
    """在 TAB_MARK / TAB_MATCH 指定的标签页执行一段 JS；返回 (退出码, 输出文本或 None)。出错时输出文本就是错误行。"""
    mark, match = os.environ.get('TAB_MARK', ''), os.environ.get('TAB_MATCH', '')
    if not (mark or match):
        return 2, 'ERR_NEED_TAB_MARK_OR_TAB_MATCH'
    tab = find_tab(mark, match)
    if tab == 'ERR_NO_CDP':
        return 2, NO_CDP.format(port=PORT)
    if tab is None:
        return 1, no_tab_report(mark, match)[0]
    try:
        v, err = tab.evaluate(js_text, await_promise)
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
    """旧 stage 表达式和文本日志保持可用；驱动按运行 ID、终态及实际时间判断。"""
    started = time.monotonic()
    timing = {'command': 'stage', 'status': 'error', 'locate_seconds': 0.0,
              'execute_seconds': 0.0, 'wait_seconds': 0.0}
    tab, out = None, ''
    phase = None
    phase_started = started

    def finish_phase():
        nonlocal phase, phase_started
        if phase:
            timing[phase + '_seconds'] += time.monotonic() - phase_started
        phase = None

    def begin_phase(name):
        nonlocal phase, phase_started
        finish_phase()
        phase, phase_started = name, time.monotonic()

    def timeout_result():
        timing['status'] = 'timeout'
        print(out)
        print(f'(timeout {max_seconds:g}s, last log above)')
        return 1

    try:
        try:
            max_seconds = float(max_seconds)
        except (ValueError, TypeError):
            max_seconds = 0
        if not math.isfinite(max_seconds) or max_seconds <= 0:
            timing['status'] = 'usage_error'
            print('ERR_USAGE stage: --max 必须是有限正数秒')
            return 2
        deadline = started + max_seconds
        sources = []
        for path in list(libs) + [stage_path]:
            if not os.path.isfile(path):
                print(f'ERR_NO_FILE {path}')
                return 2
            with open(path, encoding='utf-8') as f:
                sources.append(f.read())
        mark, match = os.environ.get('TAB_MARK', ''), os.environ.get('TAB_MATCH', '')
        if not (mark or match):
            print('ERR_NEED_TAB_MARK_OR_TAB_MATCH')
            return 2
        begin_phase('locate')
        found = find_tab(mark, match, deadline=deadline)
        tab = None if found == 'ERR_NO_CDP' else found
        remaining_timeout(deadline)
        if found == 'ERR_NO_CDP':
            tab = None
            print(NO_CDP.format(port=PORT))
            return 2
        if tab is None:
            print(no_tab_report(mark, match, deadline=deadline)[0])
            return 1
        run_id = os.urandom(12).hex()
        # 捕获本次表达式的同步/Promise 异常；不监听页面其他未处理异常。
        libraries = '\n;\n'.join(sources[:-1]) + '\n;'
        stage = sources[-1].rstrip().rstrip(';')
        prefix = f"(async function(){{window.__caRun='{run_id}'; window.__calog='';try{{\n{libraries}\n"
        suffix = ("\n}catch(error){"
                  f"if(window.__caRun==='{run_id}') window.__calog = (window.__calog||'') + "
                  "'\\nERR ' + String(error && error.stack || error);}})()")
        injection = prefix + f"await (\n{stage}\n);" + suffix
        begin_phase('execute')
        tab.call('Runtime.enable')
        remaining_timeout(deadline)
        compiled = tab.call('Runtime.compileScript', expression=injection,
                            sourceURL='', persistScript=False)
        remaining_timeout(deadline)
        if 'exceptionDetails' in compiled:
            # compileScript 只解析、不执行，故可安全改用旧多语句主体编译。
            # 不用 eval/new Function，也不监听全页面异常。未返回的子 Promise
            # 仍沿用旧 stage 的显式 ERR 日志协议；同步主体异常由 suffix 捕获。
            injection = prefix + sources[-1] + suffix
            compiled = tab.call('Runtime.compileScript', expression=injection,
                                sourceURL='', persistScript=False)
            remaining_timeout(deadline)
            if 'exceptionDetails' in compiled:
                details = compiled['exceptionDetails']
                err = details.get('exception', {}).get('description') or details.get('text') or 'JS 语法错误'
                print(f'ERR_JS: {err}')
                return 1
        _, err = tab.evaluate(injection, await_promise=False)
        remaining_timeout(deadline)
        if err:
            print(f'ERR_JS: {err}')
            return 1
        read = (f"/* __caStageSnapshot */ (window.__caRun==='{run_id}' ? "
                "{run_id:window.__caRun,log:window.__calog||''} : "
                "{run_id:window.__caRun||'',log:window.__calog||''})")
        reconnects = 0
        target = tab.target
        begin_phase('wait')
        while True:
            remaining_timeout(deadline)
            try:
                if tab is None:
                    tab = connect(target, deadline=deadline)
                    if tab is None:
                        raise TabError('连接恢复失败')
                snapshot, err = tab.evaluate(read)
                remaining_timeout(deadline)
            except StageDeadline:
                raise
            except (TabError, OSError):
                remaining_timeout(deadline)
                if tab:
                    tab.close()
                    tab = None
                reconnects += 1
                if reconnects > 2:
                    print(out)
                    print('ERR_CDP: stage 连接恢复失败')
                    return 1
                time.sleep(min(.2, remaining_timeout(deadline)))
                continue
            if err:
                print(f'ERR_JS: {err}')
                return 1
            if not isinstance(snapshot, dict):
                print('ERR_STAGE_STATE: 日志快照格式无效')
                return 1
            out = str(snapshot.get('log', ''))
            if snapshot.get('run_id') != run_id:
                timing['status'] = 'stale'
                print('STALE:' + out)
                print('ERR_STAGE_STALE: 本次运行已被替换或页面已重载')
                return 1
            lines = [line.strip() for line in out.splitlines()]
            if any(re.match(r'^ERR(?:[ _:]|$)', line) for line in lines):
                print(out)
                return 1
            if any(re.match(r'^DONE(?:\s|$)', line) for line in lines):
                timing['status'] = 'success'
                print(out)
                return 0
            time.sleep(min(.2, remaining_timeout(deadline)))
    except StageDeadline:
        return timeout_result()
    except (TabError, OSError) as error:
        if 'deadline' in locals() and time.monotonic() >= deadline:
            return timeout_result()
        print(f'ERR_CDP: {error}')
        return 1
    finally:
        finish_phase()
        if tab is not None:
            tab.close()
        timing['elapsed_seconds'] = time.monotonic() - started
        write_timing(timing)


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
    stop_file = os.environ.get('STOP_FILE', '')
    n = ok = 0
    for rid, url in rows:
        if stop_file and os.path.exists(stop_file):
            print(f'STOP stop-file {stop_file}')
            break
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
                if stop_file:
                    try:
                        with open(stop_file, 'w', encoding='utf-8') as f:
                            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {os.environ.get('TAB_MARK', '')} {g}\n")
                    except OSError:
                        pass
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
            '--no-first-run', '--no-default-browser-check',
            # 后台标签页的定时器会被浏览器压到每秒一次，填表脚本会慢十倍；这三个开关让脚本在后台也按正常速度跑
            '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows']
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


OPTIONS = {'--mark': 'TAB_MARK', '--match': 'TAB_MATCH', '--port': 'CA_CDP_PORT', '--guard-every': 'GUARD_EVERY',
           '--stop-file': 'STOP_FILE', '--wait': 'SNIFF_WAIT'}
USAGE = {
    'exec': 'exec <js文件>',
    'claim': 'claim <序号|targetId> [运行ID]',
    'open': 'open <URL> [运行ID]',
    'screenshot': 'screenshot <输出.png>',
    'click': 'click <选择器|js:表达式|x,y>（一个参数）',
    'stage': 'stage <stage.js> [--libs a.js b.js] [--max 秒]',
    'fill': 'fill <计划.json> [--max 秒] [--allow-selector]',
    'survey': 'survey <输出.json>',
    'plan-skeleton': 'plan-skeleton <输出.json> [--skip-ok <上次的报告.json>]',
    'probe-options': 'probe-options <输出.json> [--only key1,key2]',
    'read-urls': 'read-urls <列表文件> <输出目录> [起始行] [结束行]',
    'sniff': 'sniff <选择器|js:表达式|x,y>（一个参数）[--wait 秒]',
    'type': 'type <选择器|js:表达式> <文本|@文件>',
    'upload': 'upload <选择器> <文件路径>',
    'launch': 'launch [URL]',
}


def take_options(argv):
    """把 --mark/--match/--port/--pace/--guard-every/--stop-file/--wait 从任意位置摘出来写进环境变量，返回剩下的参数。"""
    global PORT
    rest, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a in OPTIONS and i + 1 < len(argv):
            os.environ[OPTIONS[a]] = argv[i + 1]
            i += 2
        elif a == '--pace' and i + 1 < len(argv):
            lo, _, hi = argv[i + 1].partition('-')
            os.environ['PACE_MIN'], os.environ['PACE_MAX'] = lo, hi or lo
            i += 2
        else:
            rest.append(a)
            i += 1
    PORT = int(os.environ.get('CA_CDP_PORT', PORT))
    return rest


def report_idle_gap(threshold=120.0):
    """看一眼上一条命令是什么时候跑完的，隔得久了就说一声。

    模型没有时钟概念，感知不到自己想了多久——"浏览器空置超过两分钟该说句话"这种规矩只写在
    文档里是落不了地的。时间只有工具知道，所以让工具报。打到 stderr，不混进 stdout 的数据。
    """
    path = os.environ.get('CA_TIMING_FILE', '')
    if not path:
        return
    last = None
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get('started_at') and row.get('elapsed_seconds') is not None:
                    done = row['started_at'] + row['elapsed_seconds']
                    if last is None or done > last:
                        last = done
    except OSError:
        return
    if last is None:
        return
    gap = time.time() - last
    if gap < threshold:
        return
    print('# 距上次操作浏览器已经过去 %.0f 分钟——这段时间页面一直就绪、没有命令在跑。'
          '要么现在动手，要么跟用户说一句在等什么。' % (gap / 60), file=sys.stderr)


def write_timing(record):
    """往 CA_TIMING_FILE 追一行 JSONL。只写命令、状态、秒数和墙钟时间，不写字段值或凭证。

    带墙钟时间戳是为了能算出命令**之间**的空当：浏览器加载好了、命令却还没发出来的那段，
    在实测里比命令本身长得多，而只记每条命令跑了多久是看不见它的。
    """
    path = os.environ.get('CA_TIMING_FILE', '')
    if not path:
        return
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    except OSError:
        print('# timing 未写成', file=sys.stderr)


def main(argv):
    if any(a in ('-h', '--help') for a in argv):
        print(__doc__)
        return 0
    argv = take_options(argv)
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
    if cmd == 'click' and len(args) == 1:
        return cmd_click(args[0])
    if cmd == 'sniff' and len(args) == 1:
        return cmd_sniff(args[0])
    if cmd == 'type' and len(args) == 2:
        return cmd_type(*args)
    if cmd == 'upload' and len(args) == 2:
        return cmd_upload(*args)
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
                if i + 1 >= len(args):
                    print('ERR_USAGE stage: --max 缺少秒数')
                    return 2
                max_s = args[i + 1]; i += 2
                continue
            rest.append(args[i]); i += 1
        if len(rest) == 1:
            return cmd_stage(rest[0], libs, max_s)
    if cmd == 'fill' and args:
        max_s, rest, allow_selector = 120, [], False
        i = 0
        while i < len(args):
            if args[i] == '--max':
                if i + 1 >= len(args):
                    print('ERR_USAGE fill: --max 缺少秒数')
                    return 2
                max_s = args[i + 1]; i += 2
                continue
            if args[i] == '--allow-selector':
                allow_selector = True; i += 1
                continue
            rest.append(args[i]); i += 1
        if len(rest) == 1:
            return cmd_fill(rest[0], max_s, allow_selector)
    if cmd == 'survey' and len(args) == 1:
        return cmd_survey(args[0])
    if cmd == 'probe-options' and args:
        only, rest = None, []
        i = 0
        while i < len(args):
            if args[i] == '--only':
                if i + 1 >= len(args):
                    print('ERR_USAGE probe-options: --only 缺少字段列表')
                    return 2
                only = args[i + 1]; i += 2
                continue
            rest.append(args[i]); i += 1
        if len(rest) == 1:
            return cmd_probe_options(rest[0], only)
    if cmd == 'plan-skeleton' and args:
        skip_ok, rest = None, []
        i = 0
        while i < len(args):
            if args[i] == '--skip-ok':
                if i + 1 >= len(args):
                    print('ERR_USAGE plan-skeleton: --skip-ok 缺少文件名')
                    return 2
                skip_ok = args[i + 1]; i += 2
                continue
            rest.append(args[i]); i += 1
        if len(rest) == 1:
            return cmd_plan_skeleton(rest[0], skip_ok)
    if cmd == 'read-urls' and 2 <= len(args) <= 4:
        return cmd_read_urls(*args)
    if cmd == 'launch' and len(args) <= 1:
        return cmd_launch(*args)
    if cmd in USAGE:
        print(f'ERR_USAGE {cmd}：{USAGE[cmd]}')
        if len(args) > 1:
            print('参数里有空格时要整体加引号，例如 click "js:[...document.querySelectorAll(\'a\')].find(e => e.innerText === \'下一页\')"')
        return 2
    print(f'ERR_UNKNOWN_COMMAND {cmd}')
    return 2


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    # 每条命令都记一行：什么时候开始、跑了多久、退出码多少。算"浏览器空置"要靠相邻两行的
    # 墙钟时间戳相减——上一条命令结束到下一条命令开始的那段，页面就在那里干等着。
    report_idle_gap()
    _started_wall, _started = time.time(), time.monotonic()
    _code = 1
    try:
        _code = main(sys.argv[1:])
        sys.exit(_code)
    finally:
        if os.environ.get('CA_TIMING_FILE'):
            write_timing(dict(command=(sys.argv[1:] or ['?'])[0],
                              started_at=round(_started_wall, 3),
                              elapsed_seconds=round(time.monotonic() - _started, 3),
                              exit_code=_code))
