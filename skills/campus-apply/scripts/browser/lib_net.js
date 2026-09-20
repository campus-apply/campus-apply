// lib_net.js —— 观察页面自己发出的请求，并在同一标签页里复发同样的请求（window.__caNet）。
// 用法：chrome_cdp.py sniff 会自动注入；stage 脚本用 --libs 引入后调用 __caNet.capture / __caNet.fetchJson。
// 规矩：只复发页面自己发过的地址和请求体，不改参数、不用页面没用过的接口；间隔由调用方给。
window.__caNet = window.__caNet || (() => {
  const log = [];                                  // 页面发出的每个 XHR / fetch：方法、地址、请求体、状态、响应类型、响应全文（text）
  const clip = (s, n) => s == null ? null : String(s).slice(0, n);
  const abs = u => { try { return new URL(u, location.href).href; } catch (e) { return String(u); } };
  let hooked = false;
  function hook() {
    if (hooked) return log.length;
    hooked = true;
    const O = XMLHttpRequest.prototype.open, S = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, u) { this.__caM = m; this.__caU = abs(u); return O.apply(this, arguments); };
    XMLHttpRequest.prototype.send = function (body) {
      const rec = { kind: 'xhr', method: (this.__caM || 'GET').toUpperCase(), url: this.__caU, body: clip(body, 500), t: Date.now() };
      this.addEventListener('load', () => {
        rec.status = this.status; rec.respType = this.getResponseHeader('content-type');
        const txt = this.responseType === '' || this.responseType === 'text' ? this.responseText : '';
        rec.text = txt; rec.respLen = txt.length; rec.done = true;
      });
      this.addEventListener('error', () => { rec.status = 0; rec.done = true; });
      log.push(rec);
      return S.apply(this, arguments);
    };
    const F = window.fetch;
    window.fetch = async function (u, init) {
      const rec = { kind: 'fetch', method: ((init && init.method) || 'GET').toUpperCase(), url: abs(u instanceof Request ? u.url : u),
        body: init && init.body != null ? clip(init.body, 500) : null, t: Date.now() };
      log.push(rec);
      try {
        const r = await F.apply(this, arguments);
        rec.status = r.status; rec.respType = r.headers.get('content-type');
        try { const txt = await r.clone().text(); rec.text = txt; rec.respLen = txt.length; } catch (e) {}
        rec.done = true;
        return r;
      } catch (e) { rec.status = 0; rec.done = true; throw e; }
    };
    return log.length;
  }
  // 给外面看的记录：响应只留开头 600 字（resp），全文在 log[i].text 里
  const seen = from => log.slice(from || 0).map(({ text, ...r }) => ({ ...r, resp: clip(text, 600) }));
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const paced = (min, max) => sleep(min * 1000 + Math.random() * Math.max(0, max - min) * 1000);
  // 调用页面自己的函数（如翻页），截住它这次收到的响应正文；请求由页面发，永远合法。
  async function capture(fn, wait = 8) {
    const from = hook();
    await fn();
    for (let k = 0; k < wait * 10; k++) {
      const done = log.slice(from).filter(r => r.done);
      if (done.length) { await sleep(150); const all = log.slice(from).filter(r => r.done); return all.map(r => ({ ...r, json: parse(r.text) })); }
      await sleep(100);
    }
    return [];
  }
  const parse = s => { try { return JSON.parse(s); } catch (e) { return null; } };
  // 复发一个观察到的请求：地址、方法、请求体原样；返回解析后的 JSON（不是 JSON 就返回文本）。
  async function fetchJson(url, { method = 'GET', body = null, headers = {} } = {}) {
    const h = Object.assign({}, headers);
    if (body != null && !Object.keys(h).some(k => k.toLowerCase() === 'content-type')) h['Content-Type'] = 'application/json';
    const r = await fetch(url, { method, body, headers: h, credentials: 'same-origin' });
    const txt = await r.text();
    const j = parse(txt);
    return { status: r.status, ok: r.ok, type: r.headers.get('content-type'), data: j == null ? txt : j };
  }
  return { log, hook, seen, capture, fetchJson, paced, sleep };
})();
