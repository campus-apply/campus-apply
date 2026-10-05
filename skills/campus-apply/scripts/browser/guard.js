// guard.js —— 只读检测：人机验证 / 登录跳转 / 可见遮罩弹窗 / 浏览器错误页与上网认证跳转（blocked）。
// 单独注入时返回 JSON 字符串；作为 LIBS 引入时 stage 可调用 window.__caGuard()。
window.__caGuard = function () {
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
  // 已登录的迹象：页面上能看到这个账号的身份。有它就说明不用再登录一次——
  // 2026-10-04 的教训是反过来：agent 自己点了"登录"按钮跳到登录页，再看见 loginRedirect=true，
  // 就当成"站点要求登录"，其实是它自己造成的。所以两个字段要一起看：
  // loginRedirect 只说明"当前这个页面是登录页/有登录入口"，identity 才说明"到底登没登"。
  const accountSelectors = ['[class*="avatar"]', '[class*="Avatar"]', '[class*="user-name"]',
    '[class*="userName"]', '[class*="username"]', '[class*="nickname"]', '[class*="nickName"]',
    '[class*="user-info"]', '[class*="userInfo"]', '[class*="my-account"]', '[class*="logout"]',
    '[class*="signout"]', '[class*="sign-out"]'];
  const identityHits = accountSelectors.filter(s => [...document.querySelectorAll(s)].some(vis));
  const identityWords = ['退出登录', '安全退出', '我的简历', '我的投递', '我的申请', '个人中心', '账号设置']
    .filter(k => text.includes(k));
  const loggedIn = identityHits.length > 0 || identityWords.length > 0;
  // 弹窗：按通用词找候选，不枚举框架（antd 的 ant-modal-wrap、Element 的
  // el-dialog__wrapper、自定义 xx-mask 都要认；只枚举框架前缀，换个站就漏）。
  // 但光靠 class 含 "modal" 会把"打开弹窗"按钮、带 dialog 的说明
  // 文字都算进来，所以候选还要满足弹窗的形状：脱离文档流（fixed / absolute 定位或 <dialog>）
  // 且足够大（占视口两成以上宽高，或超过 200×120）。可见性判定见上面的 vis。
  const modalShape = el => {
    if (el.tagName === 'DIALOG') return true;
    const pos = getComputedStyle(el).position;
    if (pos !== 'fixed' && pos !== 'absolute') return false;
    const r = el.getBoundingClientRect();
    return (r.width >= innerWidth * 0.2 && r.height >= innerHeight * 0.2)
      || (r.width >= 200 && r.height >= 120);
  };
  const modalNodes = [...document.querySelectorAll(
    '[role=dialog], [role=alertdialog], dialog[open], [aria-modal="true"], ' +
    '[class*="modal"], [class*="Modal"], [class*="dialog"], [class*="Dialog"], ' +
    '[class*="mask"], [class*="Mask"], [class*="overlay"], [class*="Overlay"], ' +
    '[class*="popup"], [class*="Popup"]')].filter(el => vis(el) && modalShape(el));
  // 去重分两步。按包含关系只留最外层，去掉"遮罩套着弹窗体"那种嵌套；但遮罩和弹窗体
  // 常常是**兄弟节点**、互不包含（antd 的 mask 与 wrap 就是），按包含关系去不掉，
  // 于是一个弹窗数成两个，"是不是又弹了一个"这个判断就没法做了。
  // 第二步按内容：没有任何文本的那个是纯遮罩，不算一个弹窗。
  const hasText = el => ((el.innerText || '').replace(/\s+/g, '').length > 0);
  const outermost = modalNodes.filter(n => !modalNodes.some(o => o !== n && o.contains(n)));
  const withText = outermost.filter(hasText);
  // 全是空的（只有遮罩、内容还没渲染出来）时不要报零——那也是"页面上压着一层东西"。
  const outerModals = withText.length ? withText : outermost;
  const visibleModals = outerModals.length;
  const maskOnly = outermost.length - withText.length;
  const modalText = outerModals.map(n => (n.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 120));
  // 浏览器自己的错误页（证书、连不上）和校园网 / 酒店网的认证跳转：脚本什么都做不了，直接请用户处理
  const errorPage = /^chrome-error:\/\//.test(url) || /^(about|edge):/.test(url) && url !== 'about:blank';
  const errorWords = ['您的连接不是私密连接', '你的连接不是专用连接', 'Your connection is not private', 'NET::ERR_', '无法访问此网站', '找不到服务器', 'This site can’t be reached', 'This site can\'t be reached', 'ERR_CONNECTION', 'ERR_CERT'].filter(k => text.includes(k) || document.title.includes(k));
  const portalWords = ['校园网', '上网认证', '网络认证', 'Portal 认证', '认证登录', '宽带认证', 'captive portal', 'Wi-Fi 登录'].filter(k => text.slice(0, 3000).includes(k) || document.title.includes(k));
  const blocked = errorPage || errorWords.length > 0 ? 'browser-error' : portalWords.length > 0 ? 'captive-portal' : '';
  return { url, title: document.title, captcha: hits.length > 0 || words.length > 0, captchaHits: hits, captchaWords: words, loginRedirect, loginWords, loggedIn, identityHits, identityWords, visibleModals, modalText, maskOnly, blocked, blockedWords: errorWords.concat(portalWords), ts: Date.now() };
};
JSON.stringify(window.__caGuard());
