// lib_antd3.js —— antd 3.x 表单控件操作库（注入到已登录页面）。
window.__ca = (() => {
  // ---- 站点选择器：下面的值只是一个示例，换站点在 stage 里 Object.assign(window.__ca.SITE, {...}) ----
  const SITE = {
    section: 'div[class*=gridContainer]',      // 一个板块的容器（内含标题文本 + 若干条目 + 添加按钮）
    entry: 'div[class*=formGroupItem]',        // 板块内的一条经历
    addBtn: 'a[class*=addBtn]',                // 板块内"+ 添加"
    deleteBtn: 'div[class*=deleteBtn]',        // 条目内"删除"
    confirmModal: '.am-modal',                 // 删除确认弹窗（antd-mobile）
    confirmText: '确认',
    confirmMatch: /确认删除/,
  };
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const pace = () => sleep(300 + Math.floor(Math.random() * 500));  // 字段之间的随机停顿
  const log = [];
  const myRun = window.__caRun;
  const L = (...a) => { log.push(a.join(' ')); if (window.__caRun === myRun) window.__calog = log.join('\n'); };
  const section = title => [...document.querySelectorAll(SITE.section)].find(s => (s.innerText || '').trim().startsWith(title));
  const entries = sec => [...sec.querySelectorAll(SITE.entry)];
  function setInput(el, val) {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, val);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  const visible = el => el && el.offsetParent !== null && getComputedStyle(el).display !== 'none';
  const panelFor = inp => {
    const r = inp.getBoundingClientRect();
    return [...document.querySelectorAll('.ant-calendar-picker-container')].filter(visible)
      .map(p => ({ p, q: p.getBoundingClientRect() }))
      .filter(x => Math.abs(x.q.left - r.left) < 60 && (Math.abs(x.q.top - r.bottom) < 80 || Math.abs(x.q.bottom - r.top) < 80))
      .map(x => x.p)[0];
  };
  async function setDate(inp, val) {
    let panel = panelFor(inp);
    if (!panel) { inp.click(); await sleep(450); panel = panelFor(inp); }
    if (!panel) { L('date: no panel for input'); return false; }
    const cin = panel.querySelector('input.ant-calendar-input');
    if (!cin) { L('date: no calendar input'); return false; }
    setInput(cin, val);
    await sleep(250);
    inp.click();                                   // 收起
    for (let k = 0; k < 12 && panelFor(inp); k++) await sleep(250);
    if (panelFor(inp)) L('date: panel still open after close attempt');
    return inp.value === val;
  }
  const openDropdowns = () => [...document.querySelectorAll('.ant-select-dropdown')].filter(d => !d.classList.contains('ant-select-dropdown-hidden') && visible(d));
  function ddFor(sel) {
    const r = sel.getBoundingClientRect();
    return openDropdowns().map(d => ({ d, q: d.getBoundingClientRect() }))
      .filter(x => Math.abs(x.q.left - r.left) < 40 && (Math.abs(x.q.top - r.bottom) < 60 || Math.abs(x.q.bottom - r.top) < 60))
      .sort((a, b) => Math.min(Math.abs(a.q.top - r.bottom), Math.abs(a.q.bottom - r.top)) - Math.min(Math.abs(b.q.top - r.bottom), Math.abs(b.q.bottom - r.top))).map(x => x.d)[0];
  }
  async function openSelect(selEl) {
    const sel = selEl.querySelector('.ant-select-selection') || selEl;
    let dd = ddFor(sel);
    if (!dd) { sel.click(); await sleep(500); dd = ddFor(sel); }
    return { sel, dd };
  }
  async function pickSelect(selEl, text, contains) {
    const { sel, dd } = await openSelect(selEl);
    if (!dd) { L('select: no dropdown for', text); return false; }
    const items = [...dd.querySelectorAll('li.ant-select-dropdown-menu-item')];
    let it = items.find(li => li.innerText.trim() === text);
    if (!it && contains) it = items.find(li => li.innerText.includes(text));
    if (!it) { L('select: option not found:', text, '| options:', items.slice(0, 40).map(i => i.innerText.trim()).join('/')); return false; }
    it.click();
    await sleep(500);
    return true;
  }
  async function selectOptions(selEl) {
    const { dd } = await openSelect(selEl);
    return dd ? [...dd.querySelectorAll('li.ant-select-dropdown-menu-item')].map(i => i.innerText.trim()) : [];
  }
  async function searchSelect(selEl, query, text) {
    const sel = selEl.querySelector('.ant-select-selection') || selEl;
    sel.click(); await sleep(400);
    const sf = selEl.querySelector('input.ant-select-search__field');
    if (!sf) { L('searchSelect: no search field'); return false; }
    setInput(sf, query); await sleep(1200);
    const dd = ddFor(sel);
    if (!dd) { L('searchSelect: no dropdown'); return false; }
    const items = [...dd.querySelectorAll('li.ant-select-dropdown-menu-item')];
    const it = items.find(li => li.innerText.trim() === text) || items.find(li => li.innerText.includes(text));
    if (!it) { L('searchSelect: not found', text, '| options:', items.slice(0, 20).map(i => i.innerText.trim()).join('/')); return false; }
    it.click(); await sleep(500);
    return true;
  }
  function radio(container, text) {
    const lab = [...container.querySelectorAll('label.ant-radio-wrapper')].find(l => l.innerText.trim() === text);
    if (!lab) { L('radio not found', text); return false; }
    lab.click(); return true;
  }
  async function add(sec) { const b = sec.querySelector(SITE.addBtn); b.click(); await sleep(500); }
  async function del(entry) {
    const b = entry.querySelector(SITE.deleteBtn); if (!b) return false;
    b.click(); await sleep(500);
    const modals = () => [...document.querySelectorAll(SITE.confirmModal)].filter(m => m.offsetParent !== null && SITE.confirmMatch.test(m.innerText));
    const m = modals().pop();
    if (!m) { L('del: no confirm modal'); return false; }
    const ok = [...m.querySelectorAll('.am-modal-button, button, a')].find(x => x.innerText.trim() === SITE.confirmText);
    if (!ok) { L('del: no confirm button'); return false; }
    ok.click(); await sleep(900);
    return true;
  }
  async function clearDate(inp) {
    const clr = inp.parentElement.querySelector('.ant-calendar-picker-clear');
    if (clr) { clr.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); clr.click(); await sleep(400); if (!inp.value) return true; }
    let panel = panelFor(inp);
    if (!panel) { inp.click(); await sleep(450); panel = panelFor(inp); }
    if (!panel) { L('clearDate: no panel'); return false; }
    const cb = panel.querySelector('.ant-calendar-clear-btn, a.ant-calendar-clear-btn');
    if (cb) { cb.click(); await sleep(400); }
    else { const cin = panel.querySelector('input.ant-calendar-input'); if (cin) { setInput(cin, ''); await sleep(300); } inp.click(); }
    for (let k = 0; k < 10 && panelFor(inp); k++) await sleep(250);
    return !inp.value;
  }
  const ctl = entry => {
    const dates = [...entry.querySelectorAll('input.ant-calendar-picker-input')];
    const texts = [...entry.querySelectorAll('input.ant-input:not(.ant-calendar-picker-input):not(.ant-select-search__field)')];
    const areas = [...entry.querySelectorAll('textarea')];
    const selects = [...entry.querySelectorAll('.ant-select')];
    const radios = [...entry.querySelectorAll('.ant-radio-group')];
    return { dates, texts, areas, selects, radios };
  };
  const dump = entry => { const c = ctl(entry); return JSON.stringify({ dates: c.dates.map(d => d.value), texts: c.texts.map(t => t.value), areas: c.areas.map(a => a.value.length + '字'), selects: c.selects.map(s => (s.querySelector('.ant-select-selection-selected-value') || {}).innerText || ''), radios: c.radios.map(r => (r.querySelector('.ant-radio-wrapper-checked') || {}).innerText || '') }); };
  return { SITE, sleep, pace, L, section, entries, setInput, setDate, pickSelect, selectOptions, searchSelect, radio, add, del, clearDate, ctl, dump, log };
})();
;
