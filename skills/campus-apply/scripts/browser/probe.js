// probe.js —— 只读探测：列出页面里可见的表单控件（标签、类型、上限、必填、当前值长度），按最近的标题分组。返回 JSON 字符串。
// 结果是启发式的静态分类；分不出类型的控件按 apply-fill 的细则做一次无害的行为探测再定。
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
    const val = ('value' in el && typeof el.value === 'string') ? el.value : clean(box.innerText);
    const label = labelOf(box);
    controls.push({ i: controls.length, heading: headingOf(box), label, kind: kind(box), maxlength: el.getAttribute('maxlength'),
      required: !!(box.closest('.ant-form-item-required, [class*="required"]') || /\*/.test(label)),
      valueLen: val.length, valuePreview: val.slice(0, 30), tag: box.tagName.toLowerCase(), cls: String(box.className || '').slice(0, 80) });
  }
  const headings = [...new Set([...document.querySelectorAll('h1,h2,h3,h4,[class*="title"],[class*="header"]')].filter(vis).map(h => clean(h.innerText)).filter(t => t && t.length < 40))].slice(0, 60);
  return JSON.stringify({ url: location.href, title: document.title, headings, controls });
})()
