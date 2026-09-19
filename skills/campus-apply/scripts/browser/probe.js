// probe.js —— 只读探测：列出页面里可见的表单控件（标签、类型、上限、必填、禁用/只读、当前值长度），按最近的标题分组。返回 JSON 字符串。
// 结果是启发式的静态分类；kind 带问号（dropdown?）表示只是像下拉，按 apply-fill 的细则做一次无害的行为探测再定。
// 证件号、密码、验证码、手机、邮箱这类字段只报长度，不输出内容。
(() => {
  const vis = el => el && el.offsetParent !== null && getComputedStyle(el).visibility !== 'hidden';
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const WRAP = '.ant-form-item, .ant-row, .el-form-item, [class*="form-item"], [class*="formItem"], [class*="FormItem"], li, tr';
  const labelOf = el => {
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l && clean(l.innerText)) return clean(l.innerText); }
    const wrap = el.closest(WRAP);
    if (wrap) { const l = wrap.querySelector('label, .ant-form-item-label, [class*="label"], [class*="Label"]'); if (l && clean(l.innerText)) return clean(l.innerText).slice(0, 40); }
    return clean(el.getAttribute('aria-label') || el.getAttribute('placeholder') || '');
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
    let val = ('value' in el && typeof el.value === 'string') ? el.value : clean(box.innerText);
    const label = labelOf(box);
    let k = kind(box);
    // 自定义下拉的通用特征：输入框旁有显示值元素 / 下拉箭头图标 / aria 弹出属性；命中就标"疑似下拉"，值取显示值
    // 字段容器不认框架 class：从输入框往上找，直到祖先里出现第二个输入控件为止
    let wrap = box, n = box.parentElement;
    for (let d = 0; n && n !== document.body && d < 5 && n.querySelectorAll('input:not([type=hidden]), textarea, select').length <= 1; d++) { wrap = n; n = n.parentElement; }
    const disp = wrap.querySelector('[class*="display-value"], [class*="selected-value"], [class*="selection-item"], [class*="selected-item"]');
    const dispText = disp ? clean(disp.innerText) : '';
    const hasCaret = !!wrap.querySelector('[class*="caret"], [class*="arrow"], [class*="Arrow"], [class*="icon-down"], [class*="iconDown"], [class*="chevron"]');
    const hasPopup = el.hasAttribute('aria-haspopup') || el.hasAttribute('aria-expanded') || el.getAttribute('role') === 'combobox';
    if (k === 'text' && (hasPopup || dispText || (hasCaret && (el.readOnly || !val)))) k = 'dropdown?';
    if (dispText && !val) val = dispText;
    const secret = /证件|身份证|护照|密码|password|验证码|captcha|银行卡|card|手机|电话|phone|邮箱|email/i.test(label + ' ' + headingOf(box));
    controls.push({ i: controls.length, heading: headingOf(box), label, kind: k, maxlength: el.getAttribute('maxlength'),
      required: !!(box.closest('.ant-form-item-required, [class*="required"]') || /\*/.test(label)),
      disabled: !!el.disabled, readonly: !!el.readOnly,
      valueLen: val.length, valuePreview: secret ? (val ? '【已隐藏】' : '') : val.slice(0, 30), tag: box.tagName.toLowerCase(), cls: String(box.className || '').slice(0, 80) });
  }
  const headings = [...new Set([...document.querySelectorAll('h1,h2,h3,h4,[class*="title"],[class*="header"]')].filter(vis).map(h => clean(h.innerText)).filter(t => t && t.length < 40))].slice(0, 60);
  return JSON.stringify({ url: location.href, title: document.title, headings, controls });
})()
