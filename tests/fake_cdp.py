"""测试用的假 Chrome DevTools 端点：/json/version、/json/list、PUT /json/new 与每个标签页的 WebSocket。

实现 Runtime.evaluate、Page.bringToFront、Page.captureScreenshot、Input.dispatchMouseEvent / insertText / dispatchKeyEvent、
DOM.getDocument / querySelector / setFileInputFiles；输入与 DOM 调用只记录参数供断言。
Runtime.evaluate 不跑 JS，而是按表达式查表：
- 含 `sessionStorage.getItem('__caClaim')` 的探测表达式 → 返回该标签页的 mark
- 含 `sessionStorage.setItem('__caClaim','X')` 的认领表达式 → 记下 mark，返回 'ok'
- `document.readyState` → 'complete'；`location.href` → 该标签页 url
- 其他表达式按 tab.answers 精确匹配；没有则返回 exceptionDetails。
"""
import base64, hashlib, json, socket, struct, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


class FakeTab:
    def __init__(self, tid, title, url, ttype='page'):
        self.id, self.title, self.url, self.type = tid, title, url, ttype
        self.mark = None
        self.answers = {}      # 表达式 → 返回值（Python 值）
        self.responder = None  # 可选：函数(表达式) → 返回值；返回 NotImplemented 表示不处理
        self.evaluated = []    # 收到过的表达式，供断言
        self.front = 0
        self.mouse = []        # 收到的 Input.dispatchMouseEvent 参数
        self.inserted = []     # 收到的 Input.insertText 文本
        self.keys = []         # 收到的 Input.dispatchKeyEvent 参数
        self.dom_nodes = {}    # 选择器 → nodeId（DOM.querySelector 查表，没有返回 0）
        self.files = []        # 收到的 DOM.setFileInputFiles 参数
        self.slow_promise = False  # 模拟长时间不 resolve 的 Promise：awaitPromise=True 时拖 2.5 秒再回
        self.await_flags = []  # 每次 Runtime.evaluate 的 awaitPromise 值，供断言
        self.hang = False      # 模拟连上就不回话的标签页
        self.deny_storage = False  # 模拟不允许写 sessionStorage 的页面（证书错误页、沙箱页）

    def info(self, port):
        return {'id': self.id, 'type': self.type, 'title': self.title, 'url': self.url,
                'webSocketDebuggerUrl': f'ws://127.0.0.1:{port}/devtools/page/{self.id}'}


class FakeCDP:
    def __init__(self):
        self.tabs = []
        self.port = None
        self._srv = None
        self._thread = None
        self.new_calls = []
        self.png = base64.b64encode(b'\x89PNG fake').decode()
        self.ua = 'Mozilla/5.0 Chrome/999.0 Safari/537.36'

    def add(self, tid, title, url, ttype='page'):
        t = FakeTab(tid, title, url, ttype)
        self.tabs.append(t)
        return t

    def start(self):
        cdp = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, obj, code=200):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.startswith('/devtools/page/'):
                    return self._ws()
                if self.path == '/json/version':
                    return self._json({'Browser': 'Chrome/999.0', 'Protocol-Version': '1.3', 'User-Agent': cdp.ua})
                if self.path in ('/json', '/json/list'):
                    return self._json([t.info(cdp.port) for t in cdp.tabs])
                if self.path.startswith('/json/new'):
                    return self._json({'error': 'use PUT'}, 405)
                self._json({'error': 'not found'}, 404)

            def do_PUT(self):
                if self.path.startswith('/json/new'):
                    url = urllib.parse.unquote(self.path.split('?', 1)[1]) if '?' in self.path else 'about:blank'
                    cdp.new_calls.append(url)
                    t = cdp.add(f'new{len(cdp.tabs)}', '', url)
                    return self._json(t.info(cdp.port))
                self._json({'error': 'not found'}, 404)

            def _ws(self):
                tid = self.path.rsplit('/', 1)[1]
                tab = next((t for t in cdp.tabs if t.id == tid), None)
                key = self.headers.get('Sec-WebSocket-Key', '')
                accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
                self.wfile.write(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                                 b'Sec-WebSocket-Accept: ' + accept.encode() + b'\r\n\r\n')
                self.wfile.flush()
                conn = self.connection
                if tab is None or tab.hang:
                    try:
                        conn.settimeout(30)
                        conn.recv(65536)
                    except OSError:
                        pass
                    return
                while True:
                    msg = _recv_frame(conn)
                    if msg is None:
                        return
                    req = json.loads(msg)
                    resp = cdp._dispatch(tab, req)
                    _send_frame(conn, json.dumps(resp))

        self._srv = HTTPServer(('127.0.0.1', 0), H)
        self.port = self._srv.server_address[1]
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._srv.shutdown()
        self._srv.server_close()

    def _dispatch(self, tab, req):
        m, p, rid = req.get('method'), req.get('params', {}), req.get('id')
        if m == 'Page.bringToFront':
            tab.front += 1
            return {'id': rid, 'result': {}}
        if m == 'Page.captureScreenshot':
            return {'id': rid, 'result': {'data': self.png}}
        if m == 'Input.dispatchMouseEvent':
            tab.mouse.append(p)
            return {'id': rid, 'result': {}}
        if m == 'Input.insertText':
            tab.inserted.append(p.get('text', ''))
            return {'id': rid, 'result': {}}
        if m == 'Input.dispatchKeyEvent':
            tab.keys.append(p)
            return {'id': rid, 'result': {}}
        if m == 'DOM.getDocument':
            return {'id': rid, 'result': {'root': {'nodeId': 1}}}
        if m == 'DOM.querySelector':
            return {'id': rid, 'result': {'nodeId': tab.dom_nodes.get(p.get('selector'), 0)}}
        if m == 'DOM.setFileInputFiles':
            tab.files.append(p)
            return {'id': rid, 'result': {}}
        if m != 'Runtime.evaluate':
            return {'id': rid, 'error': {'code': -32601, 'message': f"'{m}' wasn't found"}}
        expr = p.get('expression', '')
        tab.evaluated.append(expr)
        tab.await_flags.append(bool(p.get('awaitPromise')))
        if tab.slow_promise and p.get('awaitPromise') and '(async' in expr:
            import time as _t
            _t.sleep(2.5)
        if "sessionStorage.getItem('__caClaim')" in expr:
            return _val(rid, tab.mark or '')
        if "sessionStorage.setItem('__caClaim'," in expr:
            if tab.deny_storage:
                return _val(rid, 'denied')
            tab.mark = expr.split("sessionStorage.setItem('__caClaim','", 1)[1].split("'", 1)[0]
            return _val(rid, 'ok')
        if expr.strip() == 'document.readyState':
            return _val(rid, 'complete')
        if expr.strip() == 'location.href':
            return _val(rid, tab.url)
        if tab.responder is not None:
            v = tab.responder(expr)
            if v is not NotImplemented:
                return _val(rid, v)
        if expr in tab.answers:
            v = tab.answers[expr]
            if isinstance(v, Exception):
                return {'id': rid, 'result': {'result': {'type': 'object', 'subtype': 'error'},
                        'exceptionDetails': {'text': 'Uncaught', 'exception': {'description': str(v)}}}}
            return _val(rid, v)
        return {'id': rid, 'result': {'result': {'type': 'object', 'subtype': 'error'},
                'exceptionDetails': {'text': 'Uncaught', 'exception': {'description': 'ReferenceError: unknown expression'}}}}


def _val(rid, v):
    if v is None:
        return {'id': rid, 'result': {'result': {'type': 'undefined'}}}
    t = 'string' if isinstance(v, str) else 'boolean' if isinstance(v, bool) else 'number' if isinstance(v, (int, float)) else 'object'
    return {'id': rid, 'result': {'result': {'type': t, 'value': v}}}


def _recv_exact(conn, n):
    buf = b''
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def _recv_frame(conn):
    """读一条客户端帧（客户端帧必须带掩码）；close 帧返回 None。"""
    hdr = _recv_exact(conn, 2)
    if hdr is None:
        return None
    b1, b2 = hdr
    op = b1 & 0x0F
    ln = b2 & 0x7F
    if ln == 126:
        ln = struct.unpack('>H', _recv_exact(conn, 2))[0]
    elif ln == 127:
        ln = struct.unpack('>Q', _recv_exact(conn, 8))[0]
    mask = _recv_exact(conn, 4) if b2 & 0x80 else None
    data = _recv_exact(conn, ln) if ln else b''
    if mask:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    if op == 8:
        return None
    if op == 9:
        _send_frame(conn, data, op=10)
        return _recv_frame(conn)
    return data.decode('utf-8')


def _send_frame(conn, payload, op=1):
    data = payload.encode('utf-8') if isinstance(payload, str) else payload
    hdr = bytes([0x80 | op])
    n = len(data)
    if n < 126:
        hdr += bytes([n])
    elif n < 65536:
        hdr += bytes([126]) + struct.pack('>H', n)
    else:
        hdr += bytes([127]) + struct.pack('>Q', n)
    conn.sendall(hdr + data)
