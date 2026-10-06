// probe.js —— 只读探测：列出页面里可见的表单控件（标签、类型、maxlength、页面明文字数要求 hintLimit、必填、禁用/只读、当前值长度），按最近的标题分组。返回 JSON 字符串。
// 结果是启发式的静态分类；kind 带问号（dropdown?）表示只是像下拉，按 apply-fill 的细则做一次无害的行为探测再定。
// 证件号、密码、验证码、手机、邮箱这类字段只报长度，不输出内容；按标签、属性名（name/id/placeholder/autocomplete）和值的形态三路识别。
//
// 取值有一条硬规矩：**读不出值和确实是空，是两件事**。容器型控件（日期选择器、下拉）外层是
// span/div，值挂在内层 input 上或显示元素的文本里；按容器读 innerText 永远得到空串，于是整类
// 字段被报成"空"。下游看到"空"可能去补填，把用户填好的内容覆盖掉。所以取值分三层依次尝试，
// 用 valueFrom 说明读自哪一层；三层都拿不到就报 valueUnknown，不报长度 0。
(() => {
  // 可见性：不用 offsetParent —— 它对 position:fixed 的元素恒为假，而真实站点的遮罩、弹窗和
  // 下拉面板基本都是 fixed，拿它判会整类漏掉。
  // 优先用 checkVisibility（Chrome 105+ 一次把 display / visibility / opacity / content-visibility 都算上），
  // 老浏览器退回"有布局盒子 + 没被 display:none / visibility:hidden"。
  const vis = el => {
    if (!el || !el.isConnected) return false;
    if (typeof el.checkVisibility === 'function')
      return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0;
  };
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const labelOf = el => {
    if (!window.__caFill || !window.__caFill.describeLabel)
      throw new Error('probe 需要同源标签库，请用 chrome_cdp.py probe 或 exec 内置 probe.js');
    return window.__caFill.describeLabel(el).label;
  };
  const headingOf = el => {
    let n = el;
    while (n && n !== document.body) {
      let p = n.previousElementSibling;
      while (p) {
        if (/^H[1-6]$/.test(p.tagName) || /title|header|heading/i.test(String(p.className))) { const t = clean(p.innerText); if (t && t.length < 40) return t; }
        p = p.previousElementSibling;
      }
      n = n.parentElement;
    }
    return '';
  };
  const BOX = '.ant-select, .ant-calendar-picker, .ant-picker, .ant-cascader-picker, .el-select, .el-date-editor, .el-cascader';
  const kind = el => {
    if (el.matches('input[type=file]')) return 'file';
    if (el.matches('textarea')) return 'textarea';
    if (el.matches('input[type=radio], input[type=checkbox]')) return el.type;
    if (el.matches('select')) return 'select';
    if (el.matches('.ant-select, [role=combobox], .el-select')) return 'dropdown';
    if (el.matches('.ant-calendar-picker, .ant-picker, .el-date-editor')) return 'date';
    if (el.matches('.ant-cascader-picker, .el-cascader')) return 'cascader';
    if (el.matches('[contenteditable=true]')) return 'richtext';
    return 'text';
  };
  const Q = 'input:not([type=hidden]), textarea, select, ' + BOX + ', [role=combobox], [contenteditable=true]';
  const seen = new Set(); const controls = [];
  for (const el of document.querySelectorAll(Q)) {
    if (!vis(el)) continue;
    const box = el.closest(BOX) || el;
    if (seen.has(box)) continue; seen.add(box);
    // 值的第一、二层：控件自己的 value，或容器里那个真正存值的输入控件。
    // 容器型控件（antd3 的日期选择器外层是 span）走第二层；这里按 box 定界往里找，不往上找，
    // 往上会在"多个控件共用一个字段容器"的结构里抓到隔壁字段的值。
    const hasOwn = ('value' in el && typeof el.value === 'string');
    // 判据是"这个节点自己有没有 value"，不是"box 和 el 是不是同一个"：Q 会直接选中容器本身
    // （.ant-calendar-picker 这类），那时 box === el，而它恰恰正是最需要下钻的情形。
    const innerValueEl = hasOwn ? null
      : box.querySelector('input:not([type=hidden]), textarea, select');
    const sources = [];
    if (hasOwn) sources.push(['self', el.value]);
    else if (el.isContentEditable) sources.push(['contenteditable', clean(el.innerText)]);
    if (innerValueEl && typeof innerValueEl.value === 'string')
      sources.push(['inner-input', innerValueEl.value]);
    const label = labelOf(box);
    let k = kind(box);
    // 字段容器不认框架 class：从输入框往上找，直到祖先里出现第二个输入控件为止
    let wrap = box, n = box.parentElement;
    for (let d = 0; n && n !== document.body && d < 5 && n.querySelectorAll('input:not([type=hidden]), textarea, select').length <= 1; d++) { wrap = n; n = n.parentElement; }
    const disp = wrap.querySelector('[class*="display-value"], [class*="selected-value"], [class*="selection-item"], [class*="selected-item"]');
    const dispText = disp ? clean(disp.innerText) : '';
    const hasCaret = !!wrap.querySelector('[class*="caret"], [class*="arrow"], [class*="Arrow"], [class*="icon-down"], [class*="iconDown"], [class*="chevron"]');
    const hasPopup = el.hasAttribute('aria-haspopup') || el.hasAttribute('aria-expanded') || el.getAttribute('role') === 'combobox';
    // 自定义下拉的通用特征：旁边有显示值元素 / 下拉箭头图标 / aria 弹出属性。
    // 值的第三层：显示元素的文本（纯下拉选中后 input.value 常常仍是空的）。
    if (dispText) sources.push(['display', dispText]);
    // 取第一个非空的来源；全都空时，只有确实读到过某一层才敢说"空"。
    const got = sources.find(([, v]) => v !== '') || sources[0] || null;
    const valueUnknown = got === null;
    const val = got ? got[1] : '';
    const valueFrom = got ? got[0] : null;
    // maxlength 属性基本只出现在真文本框上；有它的多半不是下拉
    if (k === 'text' && !el.getAttribute('maxlength')
        && (hasPopup || dispText || (hasCaret && (el.readOnly || !val)))) k = 'dropdown?';
    // 敏感字段：标签、属性名、值的形态三路判断，标签为空的手机框也要认出来
    const attrs = ['name', 'id', 'placeholder', 'autocomplete', 'inputcolname', 'data-field', 'aria-label'].map(a => el.getAttribute(a) || '').join(' ');
    const secretByText = /证件|身份证|护照|密码|password|验证码|captcha|银行卡|card|手机|电话|phone|mobile|\btel|邮箱|email|mail/i.test(label + ' ' + headingOf(box) + ' ' + attrs);
    const digits = val.replace(/\D/g, '');
    const secretByValue = (/^\+?[\d\s-]{11,16}$/.test(val.trim()) && digits.length === 11) || /^\d{17}[\dXx]$/.test(val.trim()) || /^[\w.+-]+@[\w-]+\.[\w.-]+$/.test(val.trim());
    const secret = el.tagName === 'INPUT' && el.type === 'password' || secretByText || secretByValue;
    // 页面明文写的字数要求（"200-1000 字""不超过 500 字"），和 maxlength 属性分开报，两者常常不一致
    const hintText = clean(wrap.innerText || '').replace(clean(val), '');
    const hm = hintText.match(/(\d+)\s*[个]?字?\s*[-~～–—至到]\s*(\d+)\s*[个]?字|(?:不超过|最多|限|以内)\s*(\d+)\s*[个]?字|(\d+)\s*[个]?字以内/);
    const hintLimit = hm ? (hm[1] ? { min: +hm[1], max: +hm[2] } : { max: +(hm[3] || hm[4]) }) : null;
    controls.push({ i: controls.length, heading: headingOf(box), label, kind: k, maxlength: el.getAttribute('maxlength'),
      required: !!(box.closest('.ant-form-item-required, [class*="required"]') || /\*/.test(label)),
      disabled: !!el.disabled, readonly: !!el.readOnly, hintLimit,
      valueLen: valueUnknown ? null : val.length, valueUnknown, valueFrom,
      valuePreview: valueUnknown ? null : (secret ? (val ? '【已隐藏】' : '') : val.slice(0, 30)),
      tag: box.tagName.toLowerCase(), cls: String(box.className || '').slice(0, 80),
      // 字段容器的 class 常常自带控件类型线索（后缀 -Select- / date_info / string_info 之类）。
      // 只把线索带回来交给模型认，不在这里硬编码任何站点的后缀表。
      wrapCls: wrap === box ? '' : String(wrap.className || '').slice(0, 80) });
  }
  const headings = [...new Set([...document.querySelectorAll('h1,h2,h3,h4,[class*="title"],[class*="header"]')].filter(vis).map(h => clean(h.innerText)).filter(t => t && t.length < 40))].slice(0, 60);
  return JSON.stringify({ url: location.href, title: document.title, headings, controls });
})()
