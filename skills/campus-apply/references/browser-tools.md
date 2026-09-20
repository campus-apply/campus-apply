# 浏览器工具

脚本在 `scripts/browser/`，只用 Python 标准库，macOS / Windows 通用。命令写作 `python3 chrome_cdp.py …`（Windows 用探到的解释器，通常是 `py`）；选项都是命令行参数，Bash 和 PowerShell 里写法一样。它只操作一个带远程调试端口、用专用配置目录启动的 Chrome 或 Edge（专用浏览器），和用户日常的浏览器互不影响。

## 子命令
- `launch [URL]`：启动专用浏览器（已在跑就只报版本）。第一次用要请用户在里面登录招聘站。启动参数里关掉了后台标签页的定时器减速，脚本在后台标签页里也按正常速度跑；用户自己用别的办法起的浏览器没有这个效果，长脚本会慢十倍，遇到就请用户改用 `launch`。
- `list [关键字]`：列标签页（序号、标题、URL、targetId），认领前给用户看。stderr 报告端口上的浏览器版本；报"无界面（Headless）浏览器"说明端口被别的工具占了，换 `CA_CDP_PORT` 或请用户关掉它。
- `claim <序号|targetId> [运行ID]`：认领，往页面写运行 ID，输出 ID 与 URL，之后每条命令都带 `--mark <ID>`。跨域跳转会丢标记，`NO_MATCHING_TAB` 时重新 `list` 和 `claim`。证书错误页、浏览器内部页不允许写存储，报 `ERR_CLAIM`，先请用户把页面弄正常再认领。
- `open <URL> [运行ID]`：自己新开并认领第二个标签页。
- `exec <js文件>`：在认领的标签页执行 JS，输出最后一个表达式的值（字符串原样，其他打成 JSON）。
- `stage <stage.js> [--libs …] [--max 秒]`：把库和 stage 脚本拼起来注入，每 2 秒轮询 `window.__calog` 到 DONE / ERR / 超时；注入只等注入本身，脚本在页内继续跑，超时后仍可用 `exec` 读日志。
- `read-urls <列表> <输出目录> [起始行] [结束行] [--pace 最短-最长] [--guard-every N]`：按 `id<TAB>url` 列表逐个导航并读正文，带间隔与 guard；只适用于详情有独立 URL 的站点。
- `screenshot <输出.png>`：把认领的标签页切到前台、只截网页内容。会把专用浏览器提到前台，用户正在打字时先说一声。
- `click <选择器|js:表达式|x,y>`：发真实鼠标事件点一下，元素先滚到视口中间、位置稳定后再点；页面脚本 `el.click()` 点不开的日期面板、级联菜单用它。目标是一个参数，`js:` 表达式里有空格要整体加引号，不然会被拆开、报 `ERR_USAGE click`。

## 配套脚本
- `guard.js`：验证码 / 登录跳转或登录弹窗 / 可见弹窗 / 浏览器错误页与上网认证跳转检测，返回 JSON；`blocked` 为 `browser-error`（证书错误、连不上）或 `captive-portal`（校园网、酒店网认证）时脚本无能为力，直接请用户在专用浏览器里处理。
- `probe.js`：控件探测：标签、类型（`dropdown?` 表示像下拉，要行为探测定型）、`maxlength`、页面明文的字数要求 `hintLimit`、必填、`disabled` / `readonly`、当前值长度；证件、密码、验证码、手机、邮箱只报长度。
- `read_page.js`：正文文本与同站链接。
- `lib_antd3.js`：控件操作的参考实现（`window.__ca`），stage 脚本用 `--libs` 引入。

## 出错约定
`python3 chrome_cdp.py --help` 打印全部子命令的用法。`ERR_NO_CDP` 没有专用浏览器，直接 `launch`，不必重试；`NO_MATCHING_TAB` 认领的标签页找不到；`ERR_USAGE <子命令>` 参数不对；`ERR_CLAIM` 页面不允许写存储；`ERR_JS` 页内脚本抛异常；`ERR_CDP` 协议层出错或超时；`ERR_WRITE` 输出文件没写成（磁盘满、目录不可写）。都不吐 Traceback。

## 环境变量
`CA_CDP_PORT`（端口，默认 9222）、`CA_CDP_TIMEOUT`（单次应答超时秒数）、`CA_BROWSER`（浏览器可执行文件）、`CA_CHROME_PROFILE`（专用配置目录，默认 `~/campus-apply-chrome`）。
