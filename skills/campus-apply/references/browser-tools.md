# 浏览器工具

脚本在 `scripts/browser/`，只用 Python 标准库，macOS / Windows 通用。命令写作 `python3 chrome_cdp.py …`（Windows 用探到的解释器，通常是 `py`）；选项都是命令行参数，Bash 和 PowerShell 里写法一样。它只操作一个带远程调试端口、用专用配置目录启动的 Chrome 或 Edge（专用浏览器），和用户日常的浏览器互不影响。

## 子命令
- `launch [URL]`：启动专用浏览器（已在跑就只报版本）。第一次用要请用户在里面登录招聘站。启动参数里关掉了后台标签页的定时器减速，脚本在后台标签页里也按正常速度跑；用户自己用别的办法起的浏览器没有这个效果，长脚本会慢十倍，遇到就请用户改用 `launch`。
- `list [关键字]`：列标签页（序号、标题、URL、targetId），认领前给用户看。stderr 报告端口上的浏览器版本；报"无界面（Headless）浏览器"说明端口被别的工具占了，换 `CA_CDP_PORT` 或请用户关掉它。
- `claim <序号|targetId> [运行ID]`：认领，往页面写运行 ID，输出 ID 与 URL，之后每条命令都带 `--mark <ID>`。工作目录里已有这个域名的 `site-notes/<域名>.md` 时多打印一行 `NOTE site-notes/<域名>.md`，先读它再动手（`open` 同样）。跨域跳转会丢标记，`NO_MATCHING_TAB` 时重新 `list` 和 `claim`。证书错误页、浏览器内部页不允许写存储，报 `ERR_CLAIM`，先请用户把页面弄正常再认领。
- `open <URL> [运行ID]`：自己新开并认领第二个标签页。
- `exec <js文件>`：在认领的标签页执行 JS，输出最后一个表达式的值（字符串原样，其他打成 JSON）。
- `stage <stage.js> [--libs …] [--max 秒]`：把库和 stage 脚本拼起来注入，每 2 秒轮询 `window.__calog` 到 DONE / ERR / 超时；注入只等注入本身，脚本在页内继续跑，超时后仍可用 `exec` 读日志。
- `read-urls <列表> <输出目录> [起始行] [结束行] [--pace 最短-最长] [--guard-every N] [--stop-file 文件]`：按 `id<TAB>url` 列表逐个导航并读正文，带间隔与 guard；只适用于详情有独立 URL 的站点。几个标签页并行读时各进程给同一个 `--stop-file`：谁的 guard 报验证码或跳登录就写这个文件，其他进程读下一条前看到它就停并打印 `STOP stop-file`。
- `type <选择器|js:表达式> <文本|@文件>`：像人打字一样写入一个文本框：真实鼠标点击取得焦点 → 全选 → 浏览器自己的输入路径写入 → 补 input / change / blur / focusout → 回读比对，一致输出 `typed <标签> <n>字 回读 <n>字 一致`，不一致 `ERR_TYPE`。文本以 `@` 开头就读文件（长文本、含换行或引号时用）。是 setter 写法三层回读不过时的兜底，见 apply-fill 的 controls.md。
- `upload <选择器> <文件路径>`：把本地文件设到 `<input type=file>` 上（浏览器原生路径，触发 change），回读 `input.files` 的文件名；找不到控件 `NO_ELEMENT`，文件不存在 `ERR_NO_FILE`。只在用户明确要求代传时用。
- `sniff <选择器|js:表达式|x,y> [--wait 秒]`：观察页面自己发出的请求。先往认领的标签页注入 `lib_net.js` 装记录钩子，再做触发动作（选择器和坐标是发真实鼠标事件点一下；`js:` 是直接执行表达式，通常用来调页面自己的翻页函数——注意和 `click` 的 `js:` 不同，那里是求值得到元素再点），等 `--wait` 秒（默认 3，响应都回来了会提前结束），打印 `SNIFF <请求数>`、每个请求一行（方法、地址、请求体开头、状态、响应类型、响应长度）、一行 `---`、完整 JSON（响应只留开头 600 字）。哪条请求返回 JSON、JSON 里有没有岗位正文，看响应开头判断。
- `screenshot <输出.png>`：把认领的标签页切到前台、只截网页内容。会把专用浏览器提到前台，用户正在打字时先说一声。
- `click <选择器|js:表达式|x,y>`：发真实鼠标事件点一下，元素先滚到视口中间、位置稳定后再点；页面脚本 `el.click()` 点不开的日期面板、级联菜单用它。目标是一个参数，`js:` 表达式里有空格要整体加引号，不然会被拆开、报 `ERR_USAGE click`。

## 配套脚本
- `guard.js`：验证码 / 登录跳转或登录弹窗 / 可见弹窗 / 浏览器错误页与上网认证跳转检测，返回 JSON；`blocked` 为 `browser-error`（证书错误、连不上）或 `captive-portal`（校园网、酒店网认证）时脚本无能为力，直接请用户在专用浏览器里处理。
- `probe.js`：控件探测：标签、类型（`dropdown?` 表示像下拉，要行为探测定型）、`maxlength`、页面明文的字数要求 `hintLimit`、必填、`disabled` / `readonly`、当前值长度；证件、密码、验证码、手机、邮箱只报长度。
- `read_page.js`：正文文本与同站链接。
- `lib_antd3.js`：控件操作的参考实现（`window.__ca`），stage 脚本用 `--libs` 引入。
- `lib_net.js`：`window.__caNet`，stage 脚本用 `--libs` 引入：`hook()` 装记录钩子（幂等）；`seen(起始序号)` 取记录；`capture(fn)` 调用页面自己的函数并截住它这次收到的响应（返回记录数组，每条带解析好的 `json`）；`fetchJson(url, {method, body})` 在同一标签页里复发一个观察到的请求，返回 `{status, type, data}`；`paced(最短秒, 最长秒)` 随机停顿。规矩：只复发页面自己发过的地址和请求体、只改页码，不加参数、不改每页条数、不用页面没用过的接口。

## 出错约定
`python3 chrome_cdp.py --help` 打印全部子命令的用法。`ERR_NO_CDP` 没有专用浏览器，直接 `launch`，不必重试；`NO_MATCHING_TAB` 认领的标签页找不到；`ERR_USAGE <子命令>` 参数不对；`ERR_CLAIM` 页面不允许写存储；`ERR_JS` 页内脚本抛异常；`ERR_CDP` 协议层出错或超时；`ERR_WRITE` 输出文件没写成（磁盘满、目录不可写）。都不吐 Traceback。

## 环境变量
`CA_CDP_PORT`（端口，默认 9222）、`CA_CDP_TIMEOUT`（单次应答超时秒数）、`CA_BROWSER`（浏览器可执行文件）、`CA_CHROME_PROFILE`（专用配置目录，默认 `~/campus-apply-chrome`）。
