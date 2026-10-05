// lib_fill.js —— 填写执行器的页内原语。由 chrome_cdp.py 的 fill 子命令注入并驱动，不单独用。
//
// 两条规矩，整个文件都围着它们写：
//   1. 元素由代码持有：选择器只在 resolve() 里解析一次，拿到一个数字 handle；后面所有动作都按 handle
//      找元素，不再用字符串重新查。计划里来的东西只当数据，永远不进 eval / new Function。
//   2. 可见性不用 offsetParent：它对 position:fixed 的元素恒为假（真实站点的遮罩和下拉面板基本都是
//      fixed 或挂在 body 下的绝对定位），改用 checkVisibility，退路是 getClientRects().length。
(() => {
  // 同一版重复注入直接返回（一次运行里多条命令都会注入，重建会把 handle 账本清空）；
  // 但**版本变了就让它重建** —— 否则改完这个文件必须开新标签页才能生效，而开新标签
  // 在真实站点上会丢登录态、会被会话限制挡（2026-10-06 在百度上实测到）。
  // 版本号跟着这个文件的语义走，改了判据就加一。
  const VERSION = 9;
  if (window.__caFill && window.__caFill.version === VERSION) return;

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
  // 任何类型都接：SVG 元素的 className 是 SVGAnimatedString 而不是字符串，
  // 对它调 .replace 会抛 TypeError。页面上到处是 SVG 图标，任何按结构（而不是按
  // 标签名名单）遍历节点的代码都会碰到它们。
  const clean = s => (s === null || s === undefined ? ''
    : typeof s === 'string' ? s
    : typeof s.baseVal === 'string' ? s.baseVal       // SVGAnimatedString
    : String(s)).replace(/\s+/g, ' ').trim();

  // ── 控件候选：判据只用跨站不变量，不用任何名单 ──────────────────────────────
  //
  // 为什么不能只认 NATIVE 那张选择器：它是**淘汰式**的——不在名单上就等于不存在。
  // 2026-10-06 实测，某招聘站在线简历页的下拉是纯 div 实现，祖先链
  //   brick-select-selection-placeholder → …-selected-wrap → …-selection → brick-select
  // 全是 DIV、**一个 role 属性都没有**，于是那两个下拉从来没进过字段表，而报告显示
  // "27 个控件探完、unsure: 0"——看上去一切正常，其实根本没看见它们。
  // 往名单里加 [class*="select"] 只是把名单加长，下一个站换个 class 前缀又失手：
  // class、role、自定义属性全是**开发者的命名约定**，各站不同、随时能改。
  //
  // 真正跨站的不变量，是那些**和人类用户的感知绑定、站点想改也不能改**的性质：
  //   可见            —— 用户要看得到
  //   够大            —— 用户要点得中
  //   cursor: pointer —— **站点自己声明"这里能点"**，不是我们猜的
  // 网站再千变万化，它必须让人类看懂、能操作，否则它自己就废了。这是强制的。
  //
  // NATIVE 留着，因为那是 W3C 标准语义而不是各站命名；role 只用于**加分**，
  // 不作为收候选的必要条件（那个站一个 role 都没有，照样是能用的表单）。
  const NATIVE = 'input:not([type=hidden]),textarea,select,[contenteditable="true"]';
  const ROLE_HINT = '[role="combobox"],[role="checkbox"],[role="switch"],[role="radio"],'
    + '[role="textbox"],[role="listbox"],[role="spinbutton"],[role="searchbox"]';
  // 用户点得中的最小尺寸。比面板判据（20×10）松：复选框、单选框本来就小。
  const TAPPABLE_W = 12, TAPPABLE_H = 12;

  // 这个元素看起来能让用户操作吗——只问不变量，一个 class 名都不看。
  const looksInteractive = el => {
    // input[type=file] 点了开系统文件选择器，不可逆也会阻塞。这是**类型事实**而不是
    // "长得像什么"的猜测，所以排除它不属于淘汰式判据（借 jev snapshot.js 的 safe()）。
    // 上传位由 survey 的五路查找专门处理，不走字段表。
    if (el.matches('input[type=file],input[type=password]')) return false;
    if (el.matches(NATIVE)) return true;              // W3C 标准语义，直接算
    const r = el.getBoundingClientRect();
    if (r.width < TAPPABLE_W || r.height < TAPPABLE_H) return false;   // 用户点不中
    const cs = getComputedStyle(el);
    // 站点自己声明"这里能点"。它为的是让用户看出可点，不是为了被我们认出来，
    // 所以它不随框架换代而变 —— 这正是它可靠的原因。
    if (cs.cursor === 'pointer') return true;
    if (el.matches(ROLE_HINT)) return true;           // 有 role 当然也算（只是不强求）
    if (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1') return true;
    return false;
  };

  // 点下去会把人带离这一页、或者打开一层新内容吗。**不是"什么不是控件"的淘汰规则**，
  // 而是"点它的代价不是填一个值"——页面一跳走，填到一半的表单和这一轮的 handle 全废；
  // 弹一层模态框则会挡住后面所有控件（实测连报七八个 covered）。
  // 所以不从候选里删，只打标记，由调用方决定（probe-options 不自动点，--only 点名照探）。
  //
  // 判据用 W3C 语义而不是从某个站反推：
  //   <a href> 指向别处  —— 标准的"离开本页"
  //   <a> 本身           —— 链接的语义就是"导航或打开新内容"，和"填一个值进去"是两回事。
  //                         实测某站的"申请须知"是 <a> 但**没有 href**（JS 开弹窗），
  //                         只看 href 拦不住它；而按 <a> 这个标签名拦就拦住了，
  //                         它仍留在报告里，agent 确认是下拉触发器就用 --only 点名探。
  const navigatesAway = el => {
    const a = el.closest('a');
    if (!a) return false;
    const href = a.getAttribute('href');
    if (href === null) return true;                    // <a> 无 href：JS 开弹窗或路由
    if (!href || href.startsWith('#')) return false;   // 页内锚点不算离开
    if (/^javascript:/i.test(href)) return true;       // 明摆着是 JS 行为
    return a.href !== location.href;
  };

  // 会弹系统文件选择器吗——壳是个普通 div，里面藏着 input[type=file]，
  // 点壳就等于点那个 input。排除 input[type=file] 本身挡不住它（被点的是壳）。
  // 判据仍是结构事实：这棵子树里有没有 file input，不看 class 叫什么。
  const opensFilePicker = el =>
    !!(el.querySelector && el.querySelector('input[type=file]'));

  // 收整页的控件候选。**宁可多收，不许少收**：多收的噪音由调用方看证据排除，
  // 少收的东西没人知道它存在（那两个 div 下拉就是这么消失的）。
  // 同一棵树里只留最外层那个非原生候选：brick-select 整块可点，它内部的
  // placeholder、箭头、wrap 往往也继承了 cursor:pointer，留最外层才对应"一个字段"。
  const controlCandidates = () => {
    const hits = [];
    for (const el of document.querySelectorAll('*')) {
      if (!visible(el)) continue;
      if (!looksInteractive(el)) continue;
      hits.push(el);
    }
    const out = [];
    for (const el of hits) {
      // 原生元素永远留着，哪怕它嵌在一个可点的壳里（真实的输入框常被包一层）。
      if (el.matches(NATIVE)) { out.push(el); continue; }
      if (hits.some(other => other !== el && other.contains(el) && !other.matches(NATIVE)))
        continue;
      out.push(el);
    }
    return out;
  };

  // 可访问名称：aria-labelledby → aria-label → 关联 label → 子文本 → title → placeholder，递归防环。
  // 比按框架 class 猜标签稳，同一套算法也给 probe 用。
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

  // ── 标签证据：代码不断定哪个是标签，把各路线索一起给出去 ────────────────────
  //
  // nameOf 在那个站上返回的是"请选择"——那是控件内部的**占位符**，不是字段标签。
  // 页面上明明写着"最高学历"，但它是个独立的 div，和控件没有 for / aria-labelledby
  // 关联，nameOf 只找 <label> 标签所以找不到。已选中值的情况更隐蔽：国籍那个控件
  // 内文字是"中国"，照 nameOf 读出来字段就叫"中国"。
  //
  // 修法不是"再加一条：占位符就往上找 div"——那又是拿一个站的结构反推规则。
  // 本质是**代码不该断定哪个是标签**：按不变量把线索都收齐、标明各自来源。
  //
  // 为什么"上方/左侧"是不变量：用户靠**位置**知道这是哪个字段——标签必须在控件
  // 附近，否则人就读不懂这张表。站点可以改 class、改标签用什么元素，但改不了这件事。
  const labelEvidence = el => {
    const ev = {};
    const r = el.getBoundingClientRect();
    // 1) 标准关联（W3C 语义，最可信，但很多自研组件库根本不用）
    const ref = (el.getAttribute && el.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => { const t = document.getElementById(id); return t ? clean(t.innerText) : ''; })
      .filter(Boolean).join(' ');
    if (ref) ev.ariaLabelledby = ref.slice(0, 60);
    const aria = el.getAttribute && el.getAttribute('aria-label');
    if (aria) ev.ariaLabel = clean(aria).slice(0, 60);
    if (el.labels && el.labels.length)
      ev.labelFor = clean([...el.labels].map(l => l.innerText).join(' ')).slice(0, 60);
    for (let node = el.parentElement, d = 0; node && node !== document.body && d < 5;
         node = node.parentElement, d++) {
      const own = node.querySelector(':scope > label, :scope > * > label');
      if (own && !own.contains(el) && clean(own.innerText)) {
        ev.ancestorLabel = clean(own.innerText).slice(0, 60);
        break;
      }
    }
    // 2) 控件内部的文字。**单独标出来**：它可能是占位符（"请选择"），也可能是已选中的
    //    值（"中国"），两者都不是字段标签。混进 label 正是那个站的毛病来源。
    const inner = clean(el.innerText || el.value || '');
    if (inner) ev.innerText = inner.slice(0, 60);
    const ph = el.getAttribute && el.getAttribute('placeholder');
    if (ph) ev.placeholder = clean(ph).slice(0, 60);
    // 3) 位置线索：上方和左侧最近的那块短文字。用户就是靠这个读懂表单的。
    //    只收**不包含该控件**的叶子文字节点，避免把控件自己的内容当成标签。
    const near = test => {
      let best = null, bestDist = Infinity;
      for (const n of document.querySelectorAll('span,label,div,p,dt,th,strong,b')) {
        if (n.children.length) continue;                 // 只要叶子
        if (n.contains(el) || el.contains(n)) continue;  // 不能是控件自己那块
        const t = clean(n.innerText);
        if (!t || t.length > 24) continue;               // 标签是短的
        if (!visible(n)) continue;
        const d = test(n.getBoundingClientRect(), r);
        if (d !== null && d < bestDist) { bestDist = d; best = t; }
      }
      return best;
    };
    // 上方：横向有重叠、底边在控件顶边之上，取最近的
    const above = near((nr, cr) => {
      if (Math.min(nr.right, cr.right) - Math.max(nr.left, cr.left) <= 0) return null;
      const gap = cr.top - nr.bottom;
      return (gap >= -2 && gap < 60) ? gap : null;
    });
    if (above) ev.above = above;
    // 左侧：纵向有重叠、右边在控件左边之左，取最近的
    const left = near((nr, cr) => {
      if (Math.min(nr.bottom, cr.bottom) - Math.max(nr.top, cr.top) <= 0) return null;
      const gap = cr.left - nr.right;
      return (gap >= -2 && gap < 80) ? gap : null;
    });
    if (left) ev.left = left;
    return ev;
  };

  // 从证据里挑一个最可能的标签，**供排序和显示用**；挑不准返回空串而不是硬猜。
  // 顺序：标准关联 > 位置线索 > 不要控件内文字。把 innerText/placeholder 排除在外，
  // 因为"请选择"这种占位符、"中国"这种已选值当标签会让 --only 和语义坐标全部对不上。
  const bestLabel = ev => clean(ev.ariaLabelledby || ev.ariaLabel || ev.labelFor
    || ev.ancestorLabel || ev.above || ev.left || '');

  // ── 可点 ≠ 是表单字段 ──────────────────────────────────────────────────────
  //
  // cursor:pointer 只说明"这里能点"：logo、导航项、卡片、按钮全算。2026-10-06 实测，
  // 只按"能点"收候选会把页头的 <img>（logo）和五个 <li>（首页/社会招聘/…）收成字段，
  // 而 probe-options 会**真的去点它们**——点一下页面就跳走了，不可逆。那几个导航项
  // 还是 JS 路由而不是 <a href>，拦 href 拦不住。
  //
  // 漏掉的那条不变量：表单字段除了能点，还得**能承载一个值**，而用户得知道这个值是给
  // 哪个问题填的 —— 所以**字段旁边必然有标签**。这是强制的：没有标签的输入框，人也不
  // 知道该填什么。实测对得上：那几个 div 下拉的 above 全是真标签（"最高学历"、
  // "国籍地区"…），而 logo 和导航项的 above / left 全是空。
  //
  // 但"没标签"**不等于不是字段**（只有占位符的搜索框是真实存在的形状），所以这里
  // 不淘汰任何东西，只**分成两组**：带标签线索的进字段表，其余列成 unlabeled 交给
  // agent 看。少收的东西没人知道它存在，分组则两边都看得见。
  const hasLabelClue = ev => !!(ev.ariaLabelledby || ev.ariaLabel || ev.labelFor
    || ev.ancestorLabel || ev.above || ev.left);

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
  // 选项也不按 class 列举，同一个道理。真站上见过的选项节点：div 带自家 class（不含
  // "option" 这类词）、裸 span 连 class 都没有——实测按 class/role 列举时命中 0 个，
  // 于是"面板里没有这一项"，而面板里明明写着那几个字。选项的本质是"面板里能点的叶子"：
  // 没有子元素、有可见文本、够大。下面这个选择器和 PANEL_HINT 一样只用来排序，**不淘汰**。
  const OPTION_HINT = '[role="option"],[role="menuitem"],[role="treeitem"],li,'
    + '[class*="select-item"],[class*="option"],[class*="Option"],[class*="menu-item"],'
    + '[class*="cascader-item"],td[class*="cell"],td';

  const rectOf = el => {
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height,
             cx: r.x + r.width / 2, cy: r.y + r.height / 2 };
  };

  // 面板里能点的叶子，按"更像选项"排序。判据是结构而不是 class：没有子元素（文字直接挂在
  // 它身上）、有可见文本、够大。一个面板里并排两级（年份一列、月份一格，两级同时在）也
  // 照样全收进来——逐级点开和并排两级的区别交给调用方，这里只负责"这个面板里有哪些能点的"。
  const optionLeaves = panel => {
    const out = [];
    for (const el of panel.querySelectorAll('*')) {
      if (el.children.length) continue;                  // 只要叶子
      if (!clean(el.textContent)) continue;              // 要有文字
      if (!visible(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 8 || r.height < 8) continue;         // 比面板判据松：选项格子可以很小
      out.push(el);
    }
    // 命中 OPTION_HINT 的排前面：有的面板里混着标题、箭头、"清空"这类叶子，
    // 真选项通常带得上那套词；但不命中也留着，否则就又回到按 class 列举了。
    return out.sort((a, b) => (b.matches(OPTION_HINT) ? 1 : 0) - (a.matches(OPTION_HINT) ? 1 : 0));
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

  // 点击前后的变化观察。面板有两种出法：新插一个节点（挂 body 或 portal 下），或者本来
  // 就在 DOM 里、靠改样式显形。两种都要认，所以新增节点和属性变化都收进候选池。
  // 这里只负责"把这一轮动过的节点收齐"，一个都不筛——判断在 appeared() 之后由调用方做。
  let watcher = null, appeared = new Set();
  const watchStart = () => {
    watchStop();
    appeared = new Set();
    watcher = new MutationObserver(records => {
      for (const rec of records) {
        for (const node of rec.addedNodes)
          if (node.nodeType === 1) appeared.add(node);
        if (rec.type === 'attributes' && rec.target.nodeType === 1)
          appeared.add(rec.target);
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
  // 取走这一轮动过、现在可见、够大的节点。同一棵树里只留最外层那个：两个都是这一轮动过的，
  // 按血缘去重不会误伤常驻容器。
  const watchTake = () => {
    if (watcher) watcher.takeRecords().forEach(rec => {
      for (const node of rec.addedNodes) if (node.nodeType === 1) appeared.add(node);
      if (rec.type === 'attributes' && rec.target.nodeType === 1) appeared.add(rec.target);
    });
    // 新插的节点和改过属性的节点都算候选，这里**不筛**。曾经按"点击前不可见、现在可见"
    // 筛过一道，那条规则会杀掉"面板本来就可见、点击后才填进选项"的站。
    const fresh = [...appeared].filter(el => el.isConnected && visible(el));
    // 这一轮动过的节点里，哪些够大到像个面板。
    //
    // 尺寸**不能只看节点自己的盒子**：真站上见过挂 body 下的 portal 容器自身高度是 0
    // （1200×0），面板是它里面那个 absolute 定位的子节点（286×264）。按自身盒子筛，
    // 这个 0 高容器被扔掉，里面真正的面板也跟着没了机会——**面板明明开着，却报没出现**。
    // 占不占地方要问这棵子树，这是几何事实，和站点怎么命名无关。
    const out = [];
    for (const el of fresh) {
      const r = rectOf(el);
      // 自己就有尺寸的：照旧只留最外层（同一棵树里外层代表这个面板）
      if (r.w >= 20 && r.h >= 10) {
        if (fresh.some(other => other !== el && other.contains(el)
                                && (() => { const o = rectOf(other);
                                            return o.w >= 20 && o.h >= 10; })())) continue;
        out.push(el);
        continue;
      }
      // 自己没尺寸的壳：**把里面有尺寸的那一层捞出来**，不要整个丢掉。
      // 真站上见过挂 body 下的 portal 容器自身 1200×0，面板是它里面那个
      // absolute 定位的 286×264 子节点。按自身盒子筛会把这一支整个扔掉——
      // 面板明明开着，却报"没出现候选"，而且连证据都没有。
      for (const kid of el.querySelectorAll('*')) {
        if (!visible(kid)) continue;
        const kr = kid.getBoundingClientRect();
        if (kr.width < 20 || kr.height < 10) continue;
        // 同一个壳会被 MutationObserver 记两次（新增节点 + 属性变化），两次都下沉到
        // 同一层就会把一个面板登记成两条一样的候选，分数相同 → 报"认不准"，
        // 而其实只有一个面板。按元素去重，不按记录条数。
        if (!out.includes(kid)) out.push(kid);
        break;                                     // 每个壳只取最外面那一层
      }
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
      const unlabeled = [];
      // 收控件用**跨站不变量**（controlCandidates），不用选择器名单：名单是淘汰式的，
      // 不在名单上的控件直接从字段表里消失，而报告看上去一切正常。
      //
      // 分两组：**可点 ≠ 是字段**。原生元素无条件算字段（W3C 语义已经说明它是输入
      // 控件）；非原生的要看旁边有没有标签 —— 有标签的是字段，没有的列进 unlabeled
      // **交给 agent 看**，不淘汰。logo 和导航项就是这么和真下拉分开的，
      // 而不用写一条"排除 img/li"的规则。
      for (const el of controlCandidates()) {
        if (!visible(el)) continue;
        const ev = labelEvidence(el);
        const row = { el, section: sectionOf(el), label: bestLabel(ev) || nameOf(el), labels: ev };
        if (el.matches(NATIVE) || hasLabelClue(ev)) rows.push(row);
        else unlabeled.push(row);
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
        const cs = getComputedStyle(row.el);
        out.push({ handle: register(row.el), section: sec, occurrence,
                   label: row.label, nth: n, tag: row.el.tagName.toLowerCase(),
                   type: row.el.getAttribute('type') || '',
                   // 下面五项是**证据**，给调用方和 agent 判断用，代码自己不据此淘汰：
                   // native 是不是 W3C 标准元素（原生的点击可逆、可以自动探）；
                   // cursor 是站点自己声明的"这里能点"；role 有就报（那个站一个都没有）；
                   // labels 各路标签线索连来源一起给——innerText 可能只是占位符或已选值；
                   // navigates / opensFilePicker 标的是**点击不可逆**，不是"不是控件"。
                   native: row.el.matches(NATIVE),
                   cursor: cs.cursor,
                   role: row.el.getAttribute('role') || '',
                   labels: row.labels,
                   navigates: navigatesAway(row.el),
                   opensFilePicker: opensFilePicker(row.el),
                   disabled: !!row.el.disabled || row.el.getAttribute('aria-disabled') === 'true',
                   readonly: !!row.el.readOnly || row.el.getAttribute('aria-readonly') === 'true',
                   maxlength: row.el.getAttribute('maxlength'),
                   sensitive: isSensitive(row.el),
                   valueLen: typeof row.el.value === 'string' ? row.el.value.length : null,
                   rect: r });
      }
      return { url: location.href, title: document.title, fields: out,
               // 可点但旁边没有标签线索的候选。**不是字段表的一部分，也没被扔掉**——
               // 调用方不去点它们（点 logo 会跳走），但 agent 看得到它们存在。
               // 真实表单里确实有只带占位符的搜索框，哪天需要就从这里取。
               unlabeled: unlabeled.slice(0, 40).map(row => ({
                 handle: register(row.el), tag: row.el.tagName.toLowerCase(),
                 cls: clean(row.el.className).slice(0, 48) || row.el.tagName,
                 cursor: getComputedStyle(row.el).cursor,
                 navigates: navigatesAway(row.el),
                 opensFilePicker: opensFilePicker(row.el),
                 innerText: (row.labels.innerText || '').slice(0, 24),
                 rect: rectOf(row.el),
               })) };
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
      // elementFromPoint 返回 null 说明那个坐标上什么都没有——元素不在视口里，不是被挡住。
      // 报成 covered 会把人带到错误的方向上（去查"谁挡住了它"，而答案是"它根本不在视口"）。
      // 中心点的 offscreen 检查漏得掉这种：元素跨在视口边缘，中心点算出来落在外面。
      if (!top) return { ok: false, why: 'offscreen', rect: r };
      // 挡住它的是不是它自己的皮肤。自定义下拉几乎都是这个结构：真正的 input 透明地铺在
      // 底下，上面盖一层显示选中值的节点（实测 ant-select-selection-item），两者是**兄弟**，
      // 所以 contains 两个方向都不成立，于是判成 covered——而人点上去是完全正常的。
      // 放宽到"同一个控件单元内"：从控件往上找最近的那个只含它一个输入控件的容器，
      // 命中的节点在这个容器里就算点到了它自己。超出这个范围的才是真的被别的东西挡住
      // （真遮挡要拦住：面板盖在后面的控件上、整页遮罩，那些点下去会点到不该点的东西）。
      let unit = el;
      for (let node = el.parentElement, d = 0;
           node && node !== document.body && d < 4
           && node.querySelectorAll('input:not([type=hidden]),textarea,select').length <= 1;
           node = node.parentElement, d++) unit = node;
      if (!(el.contains(top) || top.contains(el) || unit.contains(top)))
        return { ok: false, why: 'covered', by: clean(top.className) || top.tagName, rect: r };
      return { ok: true, rect: r };
    },

    scrollTo(handle) {
      const el = get(handle);
      if (!el) return false;
      // instant 而不是默认的平滑滚动：平滑滚动要好几帧才停，而调用方紧接着就要 aim 一次、
      // 再把坐标交给浏览器去点。滚动还在走的时候，aim 校验过的坐标到点击那一刻已经过期，
      // 于是点在了面板外面——真实的表现是"面板刚开就被自己点没了"，很难查。
      el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
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

    // 这个控件所在板块的标题。收面板的另一招要点它：有的组件只在"点到了板块外的静态文字"
    // 时才收面板，点自己的标签反而又把面板打开了。两个真实站点在这件事上的结论正好相反，
    // 所以两招都要有，哪招有效现场试。
    //
    // 要点板块的标题，不是字段自己的标签——字段标签的 class 常常也带 title 字样，
    // 先命中它就等于把"点标签"那一招又试了一遍。所以先圈出本字段的范围，再往外找。
    sectionTitle(handle) {
      const el = get(handle);
      if (!el) return { error: 'gone' };
      const HEAD = 'h1,h2,h3,h4,h5,legend,[class*="title"],[class*="Title"],'
        + '[class*="header"],[class*="Header"],[class*="block-name"]';
      // 本字段的范围：往上走到祖先里出现第二个输入控件为止
      let field = el;
      for (let node = el.parentElement, d = 0;
           node && node !== document.body && d < 5
           && node.querySelectorAll('input:not([type=hidden]),textarea,select').length <= 1;
           node = node.parentElement, d++) field = node;
      for (let node = field.parentElement, d = 0; node && node !== document.body && d < 8;
           node = node.parentElement, d++) {
        for (const head of node.querySelectorAll(HEAD)) {
          if (head.contains(el) || field.contains(head) || !visible(head)) continue;
          const text = clean(head.innerText);
          if (text && text.length < 40)
            return { handle: register(head), text: text.slice(0, 40) };
        }
      }
      return { error: 'no-title' };
    },

    // 开始盯着页面的变化。点开面板之前调一次。
    watchStart() { watchStart(); return true; },

    // 取这一轮点击之后新出现的候选，按"更像面板"排序后返回。排序只影响先试哪个，
    // 不会把任何候选排除掉——某个站的面板既不在输入框上方也不在下方，而是盖在它身上。
    // 点了之后页面上出现的候选，按"更像面板"排序，**连证据一起报出来**。
    //
    // 这里只观察和排序，不替调用方下"就是它"的结论——这是 2026-10-05 用六轮返工换来的分工。
    // 那六轮一直在往这里加淘汰规则（"属性变化要从不可见变可见"、"候选不能是控件自己那棵树"、
    // "自己是叶子的不算"、"必须是浮层"），每一条都是拿一个碰巧见到的形状反推"什么不是面板"。
    // 网页的花样是无穷的：淘汰规则每多一条，就多一种把下一个站的真面板错杀的方式——
    // 把下拉渲染在控件内部的站、选项异步加载刚打开时是空的站、面板本来就可见只是点击后才
    // 填进选项的站，分别会被上面几条各杀一次。而错杀是悄悄做错事，比报"认不准"坏得多。
    //
    // 1.0.0 的分工本来是对的（`lib_antd3.js` 开头："下面的值只是一个示例，换站点在 stage 里
    // 覆盖"）：代码给动作原语，"这个站的面板长什么样"由 agent 看一眼现场定。1.3.0 为了省掉
    // 浏览器空置，把这件事交给代码去猜，于是有了那六轮。现在合起来：**代码观察、排序、给证据，
    // 唯一候选就自己走（绝大多数站是这样，空置照样省），有歧义才把证据交给 agent**。
    //
    // 每个候选都带上判断用得上的事实，让看的人（或模型）自己定：
    //   optionCount  里面有几个可点的叶子——真面板 12、控件壳 0、校验提示 0、字段容器 2
    //   floating     脱离文档流或挂在 body 下（下拉浮层必然如此，字段容器必然不是）
    //   sampleTexts  前几个叶子的文字——是一排同类选项，还是"姓名 / 请输入姓名"这种标签加提示
    //   gapBelow     面板顶边离控件底边多远（负数表示盖在控件上，那也是真见过的形状）
    appeared(anchorHandle) {
      const anchor = anchorHandle ? get(anchorHandle) : null;
      const box = anchor ? rectOf(anchor) : null;
      const floatingOf = el => {
        const pos = getComputedStyle(el).position;
        return pos === 'fixed' || pos === 'absolute'
          || el.parentElement === document.body
          || el.parentElement === document.documentElement;
      };
      const scored = watchTake().map(el => {
        const r = rectOf(el);
        const leaves = optionLeaves(el);
        const floating = floatingOf(el);
        let score = 0;
        // 打分只影响"先试哪个"和"像不像"，不淘汰任何候选。
        if (leaves.length >= 2) score += 4;                      // 里面有一排能点的东西
        if (floating) score += 3;                                // 浮层，不是页面本身的一块
        if (el.matches(PANEL_HINT)) score += 2;                  // 命中那套常见的词
        if (box) {
          const overlapX = Math.min(r.x + r.w, box.x + box.w) - Math.max(r.x, box.x);
          if (overlapX > 0) score += 2;                          // 和控件横向有重叠
          const gap = Math.min(Math.abs(r.y - (box.y + box.h)), Math.abs(box.y - (r.y + r.h)));
          score += Math.max(0, 3 - gap / 40);                    // 离得越近越像，但远也不淘汰
        }
        return {
          el, score, rect: r, floating,
          optionCount: leaves.length,
          sampleTexts: leaves.slice(0, 4).map(x => clean(x.innerText).slice(0, 16)),
          gapBelow: box ? Math.round(r.y - (box.y + box.h)) : null,
        };
      }).sort((a, b) => b.score - a.score);
      return scored.map(s => ({
        handle: register(s.el), rect: s.rect,
        score: Math.round(s.score * 100) / 100,
        cls: clean(s.el.className).slice(0, 80) || s.el.tagName,
        floating: s.floating, optionCount: s.optionCount,
        sampleTexts: s.sampleTexts, gapBelow: s.gapBelow,
      }));
    },

    // 记下"这个字段开出来的面板是它"，以及收掉之后销账。
    //
    // 这里不再加"不能是控件自己那棵树"之类的血缘淘汰：有的站把下拉就渲染在控件内部
    // （antd 的 getPopupContainer 配一下就是这样），那条规则会让它永远记不上账。
    // 进这本账的面板由调用方挑定——挑准了是调用方的责任，这里只负责记。
    noteOpen(fieldHandle, panelHandle) {
      const panel = get(panelHandle);
      if (!panel) return false;
      openedByUs.set(fieldHandle, panel);
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

    // 面板里当前能看到的全部选项文本。探一次就把整张选项表拿回来，比逐个试便宜得多。
    optionsIn(panelHandle) {
      const panel = get(panelHandle);
      if (!panel) return [];
      const seen = [];
      for (const el of optionLeaves(panel)) {
        const text = clean(el.innerText);
        if (text && !seen.includes(text)) seen.push(text);
      }
      return seen;
    },

    // 这个面板里的选项分成几组并排的容器。两组以上说明是多级控件，而且两级同时在一个面板里
    // （年份一列、月份一格），不是"点了第一级才冒出第二级"的常规级联——这两种要分开对待，
    // 而计划里的 kind 该写 cascader 还是 dropdown 就看这个数。判据是结构，不是 class。
    optionGroups(panelHandle) {
      const panel = get(panelHandle);
      if (!panel) return 0;
      const groups = new Set();
      for (const el of optionLeaves(panel)) {
        // 往上找到 panel 的直接子节点那一层：同一组选项共享同一个这样的祖先
        let node = el;
        while (node.parentElement && node.parentElement !== panel) node = node.parentElement;
        if (node !== panel) groups.add(node);
      }
      // 只有一个叶子的组不算一级（箭头、标题这类）
      let real = 0;
      for (const g of groups) if (optionLeaves(g).length >= 2) real++;
      return real;
    },

    // 在某个面板里按文本找选项。exact 为真要求完全相等（菜单没过滤完时，"唯一项"往往不是目标值）。
    option(panelHandle, text, exact) {
      const panel = get(panelHandle);
      if (!panel) return { error: 'panel-gone' };
      const want = clean(text);
      const hits = [];
      for (const el of optionLeaves(panel)) {
        const label = clean(el.innerText);
        if (exact ? label === want : label.includes(want)) hits.push({ el, label });
      }
      if (!hits.length) {
        const all = optionLeaves(panel).map(e => clean(e.innerText)).filter(Boolean).slice(0, 40);
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

    // 三层回读。模型层（React fiber / Vue）只作参考，不单独否决：
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
        // 还是没有显示值元素：这个控件的值就写在它自己身上。日期框和一部分下拉是这样的
        // （点出来一个面板选，但选中的值回填进 input.value，页面上没有单独的显示节点）。
        // 不回落的话这类字段永远回读不过——而值明明已经填对了，报出来却是"显示值读到 None"。
        if (display === null && typeof dom === 'string' && dom !== '') display = dom;
        // 纯 div 实现的控件（没有 input，值就是控件内的那段文字）。
        // 上面那张 DISP 是 class 名单，命中不了自研组件库的命名——实测某站的值元素叫
        // `brick-select-selection-value`，四个词一个都不沾。而**控件自己显示出来的文字
        // 就是用户看到的值**，这是结构事实，不依赖它叫什么 class。
        // 不加这一条，这类字段写进去了也回读不出来，报"回读不一致"——又一次把
        // "我读不出来"说成"它没填上"。
        //
        // 但不能直接取 el.innerText：控件里还有装饰节点（下拉箭头 ⌄、清空叉、单位后缀），
        // 整块取会读成"硕士 ⌄"，和"硕士"比不相等。值和装饰在 DOM 里是分开的叶子，
        // 所以按叶子收、**挑最长的那个**——值是用户要读的信息，装饰是一两个符号。
        if (display === null && dom === null) {
          const leaves = [];
          for (const node of el.querySelectorAll('*')) {
            if (node.children.length) continue;
            if (!visible(node)) continue;
            const t = clean(node.innerText);
            if (t) leaves.push(t);
          }
          if (leaves.length) {
            display = leaves.reduce((a, b) => (b.length > a.length ? b : a));
          } else {
            const own = clean(el.innerText);     // 值直接挂在控件身上、没有子节点
            if (own) display = own;
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

  api.version = VERSION;            // 注入守卫按它判断要不要重建（见文件开头）
  window.__caFill = api;
})();
