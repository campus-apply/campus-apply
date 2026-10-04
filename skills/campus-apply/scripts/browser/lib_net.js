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
  // 逐页拉清单并按 ID 去重，缺的页自动重拉。
  //
  // 为什么要在库里：2026-10-04 这段逻辑是现场写的，194 条响应只有 192 个唯一 ID，脚本退出 1，
  // 然后靠人工核对 8/9/19/20 四页补回 2 条。分页边界重复在翻页接口里很常见（服务端排序不稳
  // 就会出现），不该每次都把流程停下来让人介入。
  //
  //   pageFn(n)  第 n 页的拉取函数，返回 {items, total?, pages?}；items 是这一页的记录数组
  //   idOf(item) 从一条记录里取唯一 ID；取不到的记录会被单独报出来，不混进去重
  //   opts: {pages, total, min, max, retries, log}
  //
  // 返回 {items, ids, pagesRead, expected, missingPages, retried, noId, duplicates}。
  // 自己不抛错：补齐了就把 duplicates 当一条异常记下来，调用方决定怎么报。
  async function collect(pageFn, idOf, opts = {}) {
    const min = opts.min == null ? 0.3 : opts.min;
    const max = opts.max == null ? 0.6 : opts.max;
    const retries = opts.retries == null ? 2 : opts.retries;
    const byId = new Map();
    const noId = [];
    const duplicates = [];
    const pageIds = new Map();        // 页码 → 这一页拿到的 ID
    let expected = opts.total == null ? null : opts.total;
    let pages = opts.pages == null ? null : opts.pages;

    const take = async (n) => {
      const got = await pageFn(n);
      const items = (got && got.items) || [];
      if (expected == null && got && got.total != null) expected = got.total;
      if (pages == null && got && got.pages != null) pages = got.pages;
      const ids = [];
      for (const item of items) {
        const id = idOf(item);
        if (id == null || id === '') { noId.push(item); continue; }
        const key = String(id);
        ids.push(key);
        if (byId.has(key)) duplicates.push({ id: key, page: n });
        else byId.set(key, item);
      }
      pageIds.set(n, ids);
      return items.length;
    };

    let n = 1;
    while (true) {
      const count = await take(n);
      if (opts.log) opts.log(`PAGE ${n} 拿到 ${count} 条，累计唯一 ${byId.size}`);
      if (pages != null && n >= pages) break;
      if (pages == null && count === 0) break;
      if (n > 500) break;             // 兜底，别被坏的 pages 带进死循环
      n += 1;
      await paced(min, max);
    }
    const pagesRead = n;

    const firstPassDuplicates = duplicates.length;

    // 去重后比接口自报的总数少：按页重拉，优先重拉出现过重复的页（重复多半出在分页边界）。
    // 重复分两种，这里都要兜住：服务端排序不稳导致的偶发重复，重拉一次就补回来了；
    // 真·确定性重复（每次拉同一页都返回同样的重叠）重拉多少次都没用——所以一轮下来没拿到
    // 任何新 ID 就立刻停，不白跑，也不假装成功。
    let retried = 0;
    const suspect = [...new Set(duplicates.map(d => d.page))];
    const order = suspect.length ? suspect : [...pageIds.keys()];
    for (let round = 0; expected != null && byId.size < expected && round < retries; round++) {
      const before = byId.size;
      for (const page of order) {
        if (byId.size >= expected) break;
        const had = byId.size;
        await paced(min, max);
        await take(page);
        retried += 1;
        if (opts.log && byId.size > had) opts.log(`RETRY 第 ${page} 页补到 ${byId.size - had} 条`);
      }
      if (byId.size === before) {
        if (opts.log) opts.log('RETRY 这一轮一条新的都没拿到，重复是确定性的，不再重试');
        break;
      }
    }
    const missingPages = expected != null && byId.size < expected
      ? { expected, got: byId.size, short: expected - byId.size } : null;
    return { items: [...byId.values()], ids: [...byId.keys()], pagesRead, expected,
             missingPages, retried, noId, duplicates: firstPassDuplicates,
             duplicatePages: suspect };
  }

  return { log, hook, seen, capture, fetchJson, paced, sleep, collect };
})();
