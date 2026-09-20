// guard.js —— 只读检测：人机验证 / 登录跳转 / 可见遮罩弹窗 / 浏览器错误页与上网认证跳转（blocked）。
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
  // 弹窗式登录（没有跳转、没有密码框，只有手机号 + 验证码）：命中两个以上登录用词就算要求登录
  const loginWords = ['手机号登录', '邮箱登录', '获取验证码', '微信登录', '请输入手机号', '账号登录', '扫码登录'].filter(k => text.includes(k));
  const loginRedirect = /\/(login|signin|passport|sso|auth)\b/i.test(url) || (hasPwd && /登录|login/i.test(text.slice(0, 3000))) || loginWords.length >= 2;
  const visibleModals = [...document.querySelectorAll('.ant-modal-wrap, .am-modal, [role=dialog], .el-dialog__wrapper, .modal, [class*="Modal-container"], [class*="modal-container"]')].filter(vis).length;
  // 浏览器自己的错误页（证书、连不上）和校园网 / 酒店网的认证跳转：脚本什么都做不了，直接请用户处理
  const errorPage = /^chrome-error:\/\//.test(url) || /^(about|edge):/.test(url) && url !== 'about:blank';
  const errorWords = ['您的连接不是私密连接', '你的连接不是专用连接', 'Your connection is not private', 'NET::ERR_', '无法访问此网站', '找不到服务器', 'This site can’t be reached', 'This site can\'t be reached', 'ERR_CONNECTION', 'ERR_CERT'].filter(k => text.includes(k) || document.title.includes(k));
  const portalWords = ['校园网', '上网认证', '网络认证', 'Portal 认证', '认证登录', '宽带认证', 'captive portal', 'Wi-Fi 登录'].filter(k => text.slice(0, 3000).includes(k) || document.title.includes(k));
  const blocked = errorPage || errorWords.length > 0 ? 'browser-error' : portalWords.length > 0 ? 'captive-portal' : '';
  return { url, title: document.title, captcha: hits.length > 0 || words.length > 0, captchaHits: hits, captchaWords: words, loginRedirect, loginWords, visibleModals, blocked, blockedWords: errorWords.concat(portalWords), ts: Date.now() };
};
JSON.stringify(window.__caGuard());
