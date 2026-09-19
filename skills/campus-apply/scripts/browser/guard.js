// guard.js —— 只读检测：人机验证 / 登录跳转 / 可见遮罩弹窗。
// 单独注入时返回 JSON 字符串；作为 LIBS 引入时 stage 可调用 window.__caGuard()。
window.__caGuard = function () {
  const vis = el => el && el.offsetParent !== null;
  const sels = ['#tcaptcha_iframe', 'iframe[src*="captcha"]', 'iframe[src*="geetest"]', '.geetest_holder', '.nc-container',
    '[class*="captcha"]', '[id*="captcha"]', '[class*="slider-verify"]', '[class*="verify-wrap"]', '[class*="sliderVerify"]'];
  const hits = sels.filter(s => [...document.querySelectorAll(s)].some(vis));
  const text = (document.body.innerText || '').slice(0, 20000);
  const words = ['滑动验证', '拖动滑块', '安全验证', '人机验证', '请完成验证', '验证码已发送', '图形验证码', '请输入验证码'].filter(k => text.includes(k));
  const url = location.href;
  const hasPwd = document.querySelectorAll('input[type=password]').length > 0;
  const loginRedirect = /\/(login|signin|passport|sso|auth)\b/i.test(url) || (hasPwd && /登录|login/i.test(text.slice(0, 3000)));
  const visibleModals = [...document.querySelectorAll('.ant-modal-wrap, .am-modal, [role=dialog], .el-dialog__wrapper, .modal')].filter(vis).length;
  return { url, title: document.title, captcha: hits.length > 0 || words.length > 0, captchaHits: hits, captchaWords: words, loginRedirect, visibleModals, ts: Date.now() };
};
JSON.stringify(window.__caGuard());
