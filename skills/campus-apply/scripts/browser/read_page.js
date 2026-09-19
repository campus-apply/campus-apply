// read_page.js —— 只读：返回页面正文文本与同站链接。先设 window.__caReadLimit 可改最大字数（默认 60000）。
(() => {
  const limit = window.__caReadLimit || 60000;
  const links = [...document.querySelectorAll('a[href]')]
    .map(a => ({ text: (a.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 80), href: a.href }))
    .filter(l => l.text && l.href.startsWith(location.origin)).slice(0, 500);
  return JSON.stringify({ url: location.href, title: document.title, text: (document.body.innerText || '').slice(0, limit), links });
})()
