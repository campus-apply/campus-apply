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
    // 字段容器里的 label：从控件往上找，直到祖先里出现第二个输入控件为止
    let wrap = el, node = el.parentElement;
    for (let d = 0; node && node !== document.body && d < 5
         && node.querySelectorAll('input:not([type=hidden]),textarea,select').length <= 1; d++) {
      wrap = node; node = node.parentElement;
    }
    const own = wrap !== el ? wrap.querySelector('label') : null;
    if (own && clean(own.innerText)) return clean(own.innerText).slice(0, 60);
    return clean(el.getAttribute && (el.getAttribute('title') || el.getAttribute('placeholder')) || '');
  };

  // 面板候选：下拉、级联、日期面板多半挂在 body 下，class 带发版哈希，所以按角色和常见词兜一层，
  // 再用几何位置和"点击后才出现"两个条件筛，避免把页面本来就有的列表当面板。
  const PANEL_SEL = '[role="listbox"],[role="menu"],[role="dialog"],[role="tree"],'
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

  const register = el => {
    for (const [id, known] of store) if (known === el) return id;
    const id = next++; store.set(id, el); return id;
  };
  const get = id => {
    const el = store.get(id);
    return el && el.isConnected ? el : null;
  };

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
               panels: api.panels().length };
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

    // 当前可见的面板。几何信息一并带回来，调用方按"和输入框横向重叠、纵向紧挨"配对。
    panels() {
      const out = [];
      for (const el of document.querySelectorAll(PANEL_SEL)) {
        if (!visible(el)) continue;
        if (out.some(p => get(p.handle) && get(p.handle).contains(el))) continue;  // 只留最外层
        const r = rectOf(el);
        if (r.w < 20 || r.h < 10) continue;
        out.push({ handle: register(el), cls: clean(el.className).slice(0, 80), rect: r });
      }
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
        // 没给显示值选择器时，在字段容器里找显示值元素（纯下拉的 input.value 常常是空的）
        let wrap = el.parentElement;
        for (let d = 0; wrap && wrap !== document.body && d < 3; d++) {
          const shown = wrap.querySelector('[class*="display-value"],[class*="selected-value"],'
            + '[class*="selection-item"],[class*="selected-item"]');
          if (shown && visible(shown)) { display = clean(shown.innerText); break; }
          wrap = wrap.parentElement;
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
