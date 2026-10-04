// lib_fill.js —— 填写执行器的页内原语。由 chrome_cdp.py 的 fill 子命令注入并驱动，不单独用。
//
// 两条规矩，整个文件都围着它们写：
//   1. 元素由代码持有：选择器只在 resolve() 里解析一次，拿到一个数字 handle；后面所有动作都按 handle
//      找元素，不再用字符串重新查。计划里来的东西只当数据，永远不进 eval / new Function。
//   2. 可见性不用 offsetParent：它对 position:fixed 的元素恒为假（真实站点的遮罩和下拉面板基本都是
//      fixed 或挂在 body 下的绝对定位），改用 checkVisibility，退路是 getClientRects().length。
(() => {
  if (window.__caFill) return;

  const store = new Map();          // handle → 元素
  let next = 1;

  const visible = el => {
    if (!el || !el.isConnected) return false;
    if (el.closest('[aria-hidden="true"],[inert]')) return false;
    if (typeof el.checkVisibility === 'function')
      return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
    const style = getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden'
      && el.getClientRects().length > 0;
  };
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();

  // 可访问名称：aria-labelledby → aria-label → 关联 label → 子文本 → title → placeholder，递归防环。
  // 比按框架 class 猜标签稳，同一套算法也给 probe 用（待处理 90）。
  const nameOf = (el, seen) => {
    seen = seen || new Set();
    if (!el || seen.has(el)) return '';
    seen.add(el);
    const ref = (el.getAttribute && el.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => nameOf(document.getElementById(id), seen)).filter(Boolean).join(' ');
    if (ref) return clean(ref);
    const aria = el.getAttribute && el.getAttribute('aria-label');
    if (aria) return clean(aria);
    const labels = el.labels ? [...el.labels].map(l => clean(l.innerText)).filter(Boolean) : [];
    if (labels.length) return clean(labels.join(' '));
    // 字段容器里的 label：从控件往上找，找到第一个带 label 的祖先就用它。
    // 不能一见到"第二个输入控件"就停——站点常把年/月、起/止两个框放在同一个 label 底下，
    // 那样会一个标签都取不到，而空标签既定位不了字段，也会把按标签分组的逻辑带偏。
    // 共用同一个 label 的控件拿到相同的名字是对的，靠语义坐标的第四维区分它们。
    for (let node = el.parentElement, d = 0; node && node !== document.body && d < 5;
         node = node.parentElement, d++) {
      const own = node.querySelector(':scope > label, :scope > * > label');
      if (own && !own.contains(el) && clean(own.innerText))
        return clean(own.innerText).slice(0, 60);
    }
    return clean(el.getAttribute && (el.getAttribute('title') || el.getAttribute('placeholder')) || '');
  };

  // 面板怎么找：**按点击前后谁新出现了**，不按 class 清单猜。
  //
  // 按 class 全局列举再几何配对，两头都会失手：有的站真面板的祖先也命中同一个选择器，
  // "只留最外层"会把真面板吞掉；有的站面板盖在输入框上，"必须紧贴若干像素内"会把它扔掉。
  // 而行内常驻的下拉容器天天命中选择器，于是整页填完也数出一堆"开着的面板"。
  //
  // 点击前装观察器、点击后收新增节点，站点无关：面板是点出来的，它一定是新的。
  // 下面这个选择器只用来在多个候选里排序（更像面板的排前面），**不淘汰任何东西**。
  const PANEL_HINT = '[role="listbox"],[role="menu"],[role="dialog"],[role="tree"],'
    + '[class*="dropdown"],[class*="Dropdown"],[class*="select-panel"],[class*="picker"],'
    + '[class*="Picker"],[class*="cascader"],[class*="Cascader"],[class*="calendar"],'
    + '[class*="Calendar"],[class*="menus"],[class*="popper"],[class*="popover"],[class*="panel"]';
  const OPTION_SEL = '[role="option"],[role="menuitem"],[role="treeitem"],li,'
    + '[class*="select-item"],[class*="option"],[class*="Option"],[class*="menu-item"],'
    + '[class*="cascader-item"],td[class*="cell"],td';

  const rectOf = el => {
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height,
             cx: r.x + r.width / 2, cy: r.y + r.height / 2 };
  };

  // 写错一个下标就会操作到完全无关的控件，而这几类字段恰好排在表单最前面（索引 0 附近）。
  // 命中就拒绝写入和点击，除非计划里为这个字段显式写了 sensitive_ok。
  const SENSITIVE = /证件|身份证|护照|军官证|港澳|台胞|密码|password|验证码|captcha|银行卡|开户|账号|card|出生|生日|birth/i;
  const isSensitive = el => SENSITIVE.test(nameOf(el) + ' '
    + ['name', 'id', 'placeholder', 'autocomplete', 'aria-label']
        .map(a => el.getAttribute && el.getAttribute(a) || '').join(' '));

  const register = el => {
    for (const [id, known] of store) if (known === el) return id;
    const id = next++; store.set(id, el); return id;
  };
  const get = id => {
    const el = store.get(id);
    return el && el.isConnected ? el : null;
  };

  // 点击前后的变化观察。面板有两种出法：新插一个节点（挂 body 或 portal 下），
  // 或者本来就在 DOM 里、靠改样式显形。两种都要认，所以既看新增节点也看属性变化。
  let watcher = null, appeared = new Set();
  const watchStart = () => {
    watchStop();
    appeared = new Set();
    watcher = new MutationObserver(records => {
      for (const rec of records) {
        for (const node of rec.addedNodes)
          if (node.nodeType === 1) appeared.add(node);
        // 本来就在 DOM 里、改 class 或 style 显形的（常见于把 display:none 去掉）
        if (rec.type === 'attributes' && rec.target.nodeType === 1) appeared.add(rec.target);
      }
    });
    watcher.observe(document.documentElement, {
      childList: true, subtree: true,
      attributes: true, attributeFilter: ['class', 'style', 'hidden', 'aria-hidden'],
    });
  };
  const watchStop = () => {
    if (watcher) { watcher.takeRecords(); watcher.disconnect(); watcher = null; }
  };
  // 取走这一轮新出现、且现在可见、够大的节点。同一棵树里只留最外层那个——这里按
  // "谁是谁的祖先"去重是安全的，因为两个都是这一轮新出现的，不会误伤常驻容器。
  const watchTake = () => {
    if (watcher) watcher.takeRecords().forEach(rec => {
      for (const node of rec.addedNodes) if (node.nodeType === 1) appeared.add(node);
      if (rec.type === 'attributes' && rec.target.nodeType === 1) appeared.add(rec.target);
    });
    const fresh = [...appeared].filter(el => el.isConnected && visible(el));
    const out = [];
    for (const el of fresh) {
      if (fresh.some(other => other !== el && other.contains(el))) continue;
      const r = rectOf(el);
      if (r.w < 20 || r.h < 10) continue;
      out.push(el);
    }
    return out;
  };

  // 自己点开过、还没收掉的面板。整页收尾只看这一本账，不看"页面上有多少节点像面板"——
  // 行内常驻容器永远像面板，拿它当失败判据会让某些站永远填不完。
  const openedByUs = new Map();       // handle → 面板元素

  const api = {
    // 整页控件表：一次调用读完，别一个字段一次往返。
    snapshot() {
      const out = [];
      const Q = 'input:not([type=hidden]),textarea,select,[contenteditable="true"],'
        + '[role="combobox"],[role="checkbox"],[role="switch"]';
      for (const el of document.querySelectorAll(Q)) {
        if (!visible(el)) continue;
        const r = rectOf(el);
        out.push({ handle: register(el), tag: el.tagName.toLowerCase(),
                   type: el.getAttribute('type') || '', name: nameOf(el),
                   disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
                   readonly: !!el.readOnly || el.getAttribute('aria-readonly') === 'true',
                   maxlength: el.getAttribute('maxlength'),
                   valueLen: typeof el.value === 'string' ? el.value.length : null,
                   checked: typeof el.checked === 'boolean' ? el.checked : null,
                   rect: r });
      }
      return { url: location.href, title: document.title, controls: out,
               openPanels: openedByUs.size };
    },

    // 整页的语义骨架：每个控件配一组"人能看懂的坐标"——在哪个板块、是这个板块的第几条
    // 记录、字段标签是什么、同一标签在这条记录里的第几个。
    //
    // 为什么要第四维：站点常把"年/月"或"起/止"放在同一个标签底下，只给到标签定位不到
    // 具体哪一个。为什么不用全局下标：加一组条目，后面所有下标都变，一百多个数字要重算，
    // 而且写错一位就操作到无关控件。语义坐标加条目不失效，写错了也只是找不到。
    //
    // 板块按"控件前面最近的标题"认，条目组按 DOM 结构认（每条记录各有一个容器），
    // 都不依赖任何站点的 class 命名。
    outline() {
      const Q = 'input:not([type=hidden]),textarea,select,[contenteditable="true"],'
        + '[role="combobox"],[role="checkbox"],[role="switch"]';
      const HEAD = 'h1,h2,h3,h4,h5,legend,[class*="title"],[class*="Title"],'
        + '[class*="header"],[class*="Header"],[class*="block-name"]';
      // 板块：往前（文档序）找最近的一个短标题。
      const heads = [...document.querySelectorAll(HEAD)]
        .filter(h => visible(h) && clean(h.innerText) && clean(h.innerText).length < 40);
      const sectionOf = el => {
        let best = '';
        for (const h of heads) {
          if (h.contains(el)) continue;
          if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) best = clean(h.innerText);
        }
        return best;
      };
      const rows = [];
      for (const el of document.querySelectorAll(Q)) {
        if (!visible(el)) continue;
        rows.push({ el, section: sectionOf(el), label: nameOf(el) });
      }
      // 条目序号按 DOM 结构认，不按"标签重复"认：两个控件共用一个 label 是常事
      // （年/月、起/止），拿标签重复当换条目的信号，会把同一条记录劈成两条。
      //
      // 一条记录长什么样：同一层上有几个兄弟节点，各自装着一组**标签相同**的控件。
      // 所以从控件往上走，走到某一层，它的兄弟里出现了和自己标签集合重合的那一组，
      // 那一层就是记录容器；一直走到顶都没有，说明这个板块只有一条记录。
      // 一条记录的容器要同时满足两件事：同层有若干个标签集合相同的兄弟（说明是重复结构），
      // 而且自己装着**至少两个不同的标签**。第二条不能省：年/月两个框共用一个标签时，
      // 它们各自也是"标签集合相同的兄弟"，只看第一条会把一条记录劈成两条。
      const labelsIn = (node, peers) => peers.filter(r => node.contains(r.el)).map(r => r.label);
      const recordNo = new Map();                // 控件 → 这是本板块第几条记录
      const bySection = new Map();
      for (const row of rows) {
        if (!bySection.has(row.section)) bySection.set(row.section, []);
        bySection.get(row.section).push(row);
      }
      for (const [, list] of bySection) {
        let containers = [];
        let node = list[0].el;
        for (let d = 0; node && node.parentElement && d < 8; d++) {
          const mine = labelsIn(node, list);
          if (new Set(mine).size > 1) {
            const key = mine.join('\u0000');
            const same = [...node.parentElement.children].filter(c =>
              list.some(r => c.contains(r.el)) && labelsIn(c, list).join('\u0000') === key);
            if (same.length > 1) { containers = same; break; }
          }
          node = node.parentElement;
        }
        for (const row of list) {
          const at = containers.findIndex(c => c.contains(row.el));
          recordNo.set(row.el, at < 0 ? 1 : at + 1);
        }
      }
      const counters = new Map();                // "板块 条目 标签" → 已出现几个
      const out = [];
      for (const row of rows) {
        const sec = row.section;
        const occurrence = recordNo.get(row.el) || 1;
        // 同一条记录里同名标签的第几个（年/月、起/止）
        const n = (counters.get(sec + ' ' + occurrence + ' ' + row.label) || 0) + 1;
        counters.set(sec + ' ' + occurrence + ' ' + row.label, n);
        const r = rectOf(row.el);
        out.push({ handle: register(row.el), section: sec, occurrence,
                   label: row.label, nth: n, tag: row.el.tagName.toLowerCase(),
                   type: row.el.getAttribute('type') || '',
                   disabled: !!row.el.disabled || row.el.getAttribute('aria-disabled') === 'true',
                   readonly: !!row.el.readOnly || row.el.getAttribute('aria-readonly') === 'true',
                   maxlength: row.el.getAttribute('maxlength'),
                   sensitive: isSensitive(row.el),
                   valueLen: typeof row.el.value === 'string' ? row.el.value.length : null,
                   rect: r });
      }
      return { url: location.href, title: document.title, fields: out };
    },

    // 按语义坐标找控件。四维都给才唯一，缺的维度按"只有一个候选才算数"处理。
    locate(section, occurrence, label, nth) {
      const all = api.outline().fields;
      const hit = all.filter(f =>
        (section == null || f.section === section)
        && (occurrence == null || f.occurrence === occurrence)
        && (label == null || f.label === label)
        && (nth == null || f.nth === nth));
      if (!hit.length) {
        const near = all.filter(f => label != null && f.label === label)
          .map(f => ({ section: f.section, occurrence: f.occurrence, nth: f.nth })).slice(0, 8);
        return { error: 'not-found', sameLabel: near };
      }
      if (hit.length > 1)
        return { error: 'ambiguous', count: hit.length,
                 candidates: hit.slice(0, 8).map(f => ({ section: f.section,
                   occurrence: f.occurrence, label: f.label, nth: f.nth })) };
      const f = hit[0], el = get(f.handle);
      return { handle: f.handle, tag: f.tag, name: f.label, visible: !!el && visible(el),
               disabled: f.disabled, readonly: f.readonly, sensitive: f.sensitive,
               rect: f.rect, matched: 1 };
    },

    // 这个 handle 指向的控件是不是敏感字段，以及它现在的可访问名称。
    // 执行前用它核对"模型以为自己在操作什么"和"实际会操作什么"是不是一回事。
    identify(handle) {
      const el = get(handle);
      if (!el) return { error: 'gone' };
      return { name: nameOf(el), sensitive: isSensitive(el) };
    },

    // 选择器只在这里解析，之后一律按 handle。找不到返回 null，不抛。
    resolve(selector, index) {
      let list;
      try { list = [...document.querySelectorAll(selector)]; } catch (e) { return { error: 'bad-selector' }; }
      const shown = list.filter(visible);
      const pick = shown.length ? shown : list;
      const el = pick[index || 0];
      if (!el) return { error: 'not-found', matched: list.length, visible: shown.length };
      return { handle: register(el), tag: el.tagName.toLowerCase(), name: nameOf(el),
               visible: visible(el), disabled: !!el.disabled, readonly: !!el.readOnly,
               rect: rectOf(el), matched: list.length };
    },

    // 点击前的几何与遮挡检查：元素还在、可见、视口内、中心点上压着的是它自己。
    // 借 jev 的做法——执行前再校验一次，别拿上一轮的坐标点。
    aim(handle) {
      const el = get(handle);
      if (!el) return { ok: false, why: 'gone' };
      if (!visible(el)) return { ok: false, why: 'hidden' };
      if (el.matches(':disabled') || el.closest('[aria-disabled="true"],[inert]'))
        return { ok: false, why: 'disabled' };
      const r = rectOf(el);
      if (!r.w || !r.h) return { ok: false, why: 'zero-size' };
      if (r.cx < 0 || r.cy < 0 || r.cx >= innerWidth || r.cy >= innerHeight)
        return { ok: false, why: 'offscreen', rect: r };
      const top = document.elementFromPoint(r.cx, r.cy);
      if (!el.contains(top) && !(top && top.contains(el)))
        return { ok: false, why: 'covered', by: top ? clean(top.className) || top.tagName : '?', rect: r };
      return { ok: true, rect: r };
    },

    scrollTo(handle) {
      const el = get(handle);
      if (!el) return false;
      el.scrollIntoView({ block: 'center', inline: 'center' });
      return true;
    },

    // 这个控件所在字段容器里的 label。收面板的第二招要点它：自定义下拉的 label 多半没有 for=
    // （连了 for= 浏览器会把点击转发回输入框，刚关的面板又开了），所以只能按容器找。
    labelOf(handle) {
      const el = get(handle);
      if (!el) return { error: 'gone' };
      let wrap = el.parentElement;
      for (let d = 0; wrap && wrap !== document.body && d < 5; d++) {
        for (const label of wrap.querySelectorAll(':scope > label')) {
          if (visible(label) && !label.contains(el))
            return { handle: register(label), text: clean(label.innerText).slice(0, 40) };
        }
        wrap = wrap.parentElement;
      }
      return { error: 'no-label' };
    },

    // 开始盯着页面的变化。点开面板之前调一次。
    watchStart() { watchStart(); return true; },

    // 取这一轮点击之后新出现的候选，按"更像面板"排序后返回。排序只影响先试哪个，
    // 不会把任何候选排除掉——某个站的面板既不在输入框上方也不在下方，而是盖在它身上。
    appeared(anchorHandle) {
      const anchor = anchorHandle ? get(anchorHandle) : null;
      const box = anchor ? rectOf(anchor) : null;
      const scored = watchTake().map(el => {
        const r = rectOf(el);
        let score = 0;
        if (el.matches(PANEL_HINT)) score += 4;                  // 像面板的词
        if (el.querySelector(OPTION_SEL)) score += 3;            // 里面有能点的选项
        const pos = getComputedStyle(el).position;
        if (pos === 'fixed' || pos === 'absolute') score += 2;   // 浮层多半脱离文档流
        if (box) {
          const overlapX = Math.min(r.x + r.w, box.x + box.w) - Math.max(r.x, box.x);
          if (overlapX > 0) score += 2;                          // 和输入框横向有重叠
          const gap = Math.min(Math.abs(r.y - (box.y + box.h)), Math.abs(box.y - (r.y + r.h)));
          score += Math.max(0, 3 - gap / 40);                    // 离得越近越像，但远也不淘汰
        }
        return { el, score, rect: r };
      }).sort((a, b) => b.score - a.score);
      return scored.map(s => ({ handle: register(s.el), rect: s.rect,
                               score: Math.round(s.score * 100) / 100,
                               cls: clean(s.el.className).slice(0, 80) }));
    },

    // 记下"这个字段开出来的面板是它"，以及收掉之后销账。
    noteOpen(fieldHandle, panelHandle) {
      const panel = get(panelHandle);
      if (panel) openedByUs.set(fieldHandle, panel);
      return true;
    },
    noteClosed(fieldHandle) { openedByUs.delete(fieldHandle); return true; },

    // 自己开过、现在仍然可见的面板。这是整页收尾唯一该看的数。
    stillOpen() {
      const out = [];
      for (const [fieldHandle, panel] of openedByUs) {
        if (!panel.isConnected || !visible(panel)) { openedByUs.delete(fieldHandle); continue; }
        out.push({ field: fieldHandle, handle: register(panel),
                   cls: clean(panel.className).slice(0, 80) });
      }
      watchStop();
      return out;
    },

    // 在某个面板里按文本找选项。exact 为真要求完全相等（菜单没过滤完时，"唯一项"往往不是目标值）。
    option(panelHandle, text, exact) {
      const panel = get(panelHandle);
      if (!panel) return { error: 'panel-gone' };
      const want = clean(text);
      const hits = [];
      for (const el of panel.querySelectorAll(OPTION_SEL)) {
        if (!visible(el)) continue;
        if (el.querySelector(OPTION_SEL)) continue;          // 只要叶子节点
        const label = clean(el.innerText);
        if (exact ? label === want : label.includes(want)) hits.push({ el, label });
      }
      if (!hits.length) {
        const all = [...panel.querySelectorAll(OPTION_SEL)].filter(visible)
          .filter(e => !e.querySelector(OPTION_SEL)).map(e => clean(e.innerText))
          .filter(Boolean).slice(0, 40);
        return { error: 'no-option', available: all };
      }
      return { handle: register(hits[0].el), label: hits[0].label, count: hits.length };
    },

    // 文本写入的标准序列：原型 setter → input → change → blur → focusout。
    // 受控组件常常只在失焦时才把值交给表单模型，少一个事件就会"显示对了、存下来是空的"。
    write(handle, text) {
      const el = get(handle);
      if (!el) return { ok: false, why: 'gone' };
      if (el.disabled) return { ok: false, why: 'disabled' };
      if (el.readOnly) return { ok: false, why: 'readonly' };
      const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
        : el instanceof HTMLInputElement ? HTMLInputElement.prototype : null;
      if (proto) {
        const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        setter.call(el, text);
      } else if (el.isContentEditable) {
        el.innerText = text;
      } else {
        return { ok: false, why: 'not-writable' };
      }
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      el.dispatchEvent(new FocusEvent('blur'));
      el.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
      return { ok: true };
    },

    toggle(handle, want) {
      const el = get(handle);
      if (!el) return { ok: false, why: 'gone' };
      const now = typeof el.checked === 'boolean' ? el.checked
        : el.getAttribute('aria-checked') === 'true';
      if (now === !!want) return { ok: true, changed: false, checked: now };
      el.click();
      const after = typeof el.checked === 'boolean' ? el.checked
        : el.getAttribute('aria-checked') === 'true';
      return { ok: after === !!want, changed: true, checked: after };
    },

    nativeSelect(handle, value) {
      const el = get(handle);
      if (!el || el.tagName !== 'SELECT') return { ok: false, why: 'not-select' };
      const option = [...el.options].find(o => clean(o.text) === clean(value) || o.value === value);
      if (!option) return { ok: false, why: 'no-option',
                            available: [...el.options].map(o => clean(o.text)).slice(0, 40) };
      el.value = option.value;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      return { ok: clean(el.options[el.selectedIndex].text) === clean(option.text) };
    },

    // 三层回读。模型层（React fiber / Vue）按 pending 100 的决定只作参考，不单独否决：
    // 从 root.current 往下找 stateNode 是这个元素的 fiber 才是活动分支——节点上挂的那个
    // __reactFiber$ 在奇数次提交后指向旧分支，直接读它会把写对的值判成没写进去。
    readback(handle, displaySelector) {
      const el = get(handle);
      if (!el) return { error: 'gone' };
      const dom = typeof el.value === 'string' ? el.value : null;
      let display = null;
      if (displaySelector) {
        let shown = null;
        try { shown = document.querySelector(displaySelector); } catch (e) { shown = null; }
        if (shown) display = clean(shown.tagName === 'INPUT' ? shown.value : shown.innerText);
      }
      if (display === null) {
        // 没给显示值选择器时，在字段容器里找显示值元素（纯下拉的 input.value 常常是空的）。
        //
        // 往上找要当心：站点常把"年/月/起/止"几个控件放进同一个字段容器，一路上溯再取
        // 第一个显示值元素，会把隔壁控件的值当成自己的——"月"读成"年"，一整页假不一致。
        // 所以先定界到这个控件自己的最小容器，上溯时还要校验找到的显示值和本控件同一行。
        const DISP = '[class*="display-value"],[class*="selected-value"],'
          + '[class*="selection-item"],[class*="selected-item"]';
        const mine = rectOf(el);
        const sameRow = node => {
          const r = rectOf(node);
          const overlap = Math.min(r.y + r.h, mine.y + mine.h) - Math.max(r.y, mine.y);
          return overlap > Math.min(r.h, mine.h) * 0.5;   // 纵向重叠过半才算同一行
        };
        // 先在控件自己的最小容器里找：往上走，一旦祖先里出现第二个输入控件就停。
        let ownBox = el;
        for (let node = el.parentElement, d = 0;
             node && node !== document.body && d < 4
             && node.querySelectorAll('input:not([type=hidden]),textarea,select').length <= 1;
             node = node.parentElement, d++) ownBox = node;
        const own = [...ownBox.querySelectorAll(DISP)].find(visible);
        if (own) display = clean(own.innerText);
        if (display === null) {
          let wrap = ownBox.parentElement;
          for (let d = 0; wrap && wrap !== document.body && d < 3; d++) {
            const shown = [...wrap.querySelectorAll(DISP)].find(n => visible(n) && sameRow(n));
            if (shown) { display = clean(shown.innerText); break; }
            wrap = wrap.parentElement;
          }
        }
      }
      return { dom, display, model: api.modelValue(handle) };
    },

    modelValue(handle) {
      const el = get(handle);
      if (!el) return { found: false, why: 'gone' };
      // React：从挂载容器拿 root.current，遍历活动树找 stateNode === el
      let container = null;
      for (const node of [document.body, ...document.body.children]) {
        const key = Object.keys(node).find(k => k.startsWith('__reactContainer$'));
        if (key) { container = node[key]; break; }
      }
      if (!container) {
        for (const node of document.querySelectorAll('div,form,main,section')) {
          const key = Object.keys(node).find(k => k.startsWith('__reactContainer$'));
          if (key) { container = node[key]; break; }
        }
      }
      if (container) {
        const root = container.stateNode && container.stateNode.current
          ? container.stateNode.current : container;
        const seen = new Set();
        const walk = fiber => {
          while (fiber) {
            if (seen.has(fiber)) return null;
            seen.add(fiber);
            if (fiber.stateNode === el && fiber.memoizedProps && 'value' in fiber.memoizedProps)
              return { found: true, via: 'react-active', value: fiber.memoizedProps.value };
            const down = fiber.child ? walk(fiber.child) : null;
            if (down) return down;
            fiber = fiber.sibling;
          }
          return null;
        };
        const hit = walk(root.child || root);
        if (hit) return hit;
      }
      // Vue
      const vue = el.__vue__ || el.__vueParentComponent;
      if (vue) {
        const props = vue.props || (vue.$props) || {};
        if ('value' in props || 'modelValue' in props)
          return { found: true, via: 'vue', value: 'value' in props ? props.value : props.modelValue };
      }
      // 退路：节点上挂的 fiber 沿 return 往上找。可能读到旧分支，所以标明出处。
      const key = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
      if (key) {
        let f = el[key];
        for (let n = 0; f && n < 16; f = f.return, n++)
          if (f.memoizedProps && 'value' in f.memoizedProps)
            return { found: true, via: 'react-attached', value: f.memoizedProps.value,
                     note: 'may be a stale branch' };
      }
      return { found: false, why: 'no-framework' };
    },

    // 写入后新冒出来的错误提示。校验提示可能滞后，所以只作"写入可能失败"的线索。
    errors(handle) {
      const el = get(handle);
      if (!el) return [];
      let wrap = el.parentElement, out = [];
      for (let d = 0; wrap && wrap !== document.body && d < 4; d++) {
        for (const node of wrap.querySelectorAll('[class*="error"],[class*="Error"],[role="alert"]')) {
          if (!visible(node)) continue;
          const text = clean(node.innerText);
          if (text && !out.includes(text)) out.push(text);
        }
        if (out.length) break;
        wrap = wrap.parentElement;
      }
      return out.slice(0, 4);
    },

    // 页内合成点击。面板类控件常常只认真实鼠标事件，那种由 Python 侧发 CDP 事件。
    softClick(handle) {
      const el = get(handle);
      if (!el) return { ok: false, why: 'gone' };
      el.click();
      return { ok: true };
    },
  };

  window.__caFill = api;
})();
