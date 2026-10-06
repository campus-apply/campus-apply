# 浏览器工具

脚本在 `scripts/browser/`，只用 Python 标准库，macOS / Windows 通用。命令写作 `python3 chrome_cdp.py …`（Windows 用探到的解释器，通常是 `py`）；选项都是命令行参数，Bash 和 PowerShell 里写法一样。它只操作一个带远程调试端口、用专用配置目录启动的 Chrome 或 Edge（专用浏览器），和用户日常的浏览器互不影响。

## 子命令
- `launch [URL]`：启动专用浏览器（已在跑就只报版本）。第一次用要请用户在里面登录招聘站。启动参数里关掉了后台标签页的定时器减速，脚本在后台标签页里也按正常速度跑；用户自己用别的办法起的浏览器没有这个效果，长脚本会慢十倍，遇到就请用户改用 `launch`。
- `list [关键字]`：列标签页（序号、标题、URL、targetId），认领前给用户看。stderr 报告端口上的浏览器版本；报"无界面（Headless）浏览器"说明端口被别的工具占了，换 `CA_CDP_PORT` 或请用户关掉它。
- `claim <序号|targetId> [运行ID]`：认领，往页面写运行 ID，输出 ID 与 URL，之后每条命令都带 `--mark <ID>`。工作目录里已有这个域名的 `site-notes/<域名>.md` 时多打印一行 `NOTE site-notes/<域名>.md`，先读它再动手（`open` 同样）。跨域跳转会丢标记，`NO_MATCHING_TAB` 时重新 `list` 和 `claim`。证书错误页、浏览器内部页不允许写存储，报 `ERR_CLAIM`，先请用户把页面弄正常再认领。
- `open <URL> [运行ID]`：自己新开并认领第二个标签页。
- `exec <js文件>`：在认领的标签页执行 JS，输出最后一个表达式的值（字符串原样，其他打成 JSON）。**单次求值上限 10 秒**（`CA_CDP_TIMEOUT` 可调），超了报 `ERR_CDP` 而页内已经执行的部分**不回滚**。探测脚本要拆成多次小批调用，别写一个跑二十秒的大脚本——整页探测用 `survey`，它在页内一次做完。
> **探完再填针对当前已显露阶段。** survey观察候选 → agent判断控件与动作、用probe-options --only读现场选项 → 集中确认当前目标 → plan-skeleton生成坐标，agent填kind/value与必要的selector → fill。
> 真实填写后needs_observation表示节点/字段变化，已执行结果保留，剩余旧计划未跑；重新survey补增量计划。不要试选假值去预测全部分支。报告矛盾或控件含义不明就主动screenshot并看图，精确值从DOM读。

- `survey <输出.json>`：**进了一个表单页先跑它**。只读地一次把这页摸清：渲染稳没稳（连探到控件数不变）、整页字段与它们的语义坐标、probe 的控件属性、五路找上传位（直接的 `input[type=file]`、shadow DOM 递归、带 `accept` 的元素、正文关键词、iframe）。摘要打到屏幕上，明细写进输出文件。不点击、不写入、不开面板——会开面板的行为探测是另一回事，要先跟用户说一声。
  探测慢不在浏览器，在命令之间的往返和抄表：真正动页面的只有几秒。能一次读完的就别分十几次读。
- `probe-options <输出.json> [--only 字段1,字段2]`：默认只列控件证据，原生select只读native_options；其余控件由agent确认目标和动作后点名。--only可以批量给语义key或标签。只开/读/关，不选择第一项、不试填、不清空恢复；已有内容可在已授权动作下读选项。
  报告options-observed不是控件类型结论，kind_hint/option_groups也只是观察；agent决定kind。多个面板带完整candidates和option_nodes，不按相同文字表合并身份。closed=null及close_candidates表示关闭后出现新候选，主动看图判断，不凭账本0宣称全页无面板。
- `plan-skeleton <输出.json> [--skip-ok <上次的报告.json>]`：**生成坐标与证据骨架，agent填目标及判断**。字段的语义坐标由代码从 DOM 读出来（板块 / 第几条记录 / 字段标签 / 同标签第几个），每个字段的 `value` 留成 `null`，原生标准语义之外的`kind`由agent确定；`kind_hint`只是线索，`agent_decision_required`项需自己看证据。`disabled` 的字段不列入，敏感字段标注出来。
  `--skip-ok` 指向上一次的 `fill` 报告：标 `filled` 的字段这次不再列出，只补没填成的那些，不必为了几个失败字段把整页长文本重写一遍。
  不要自己手写一张控件下标表。整页一百多个字段时，手抄一遍、写计划时再按新下标算一遍，是实测里最大的两段纯等待；而且加一组条目全局下标就变了，要重新映射一遍。
- `fill <计划.json> [--max 秒]`：**写入表单字段的默认办法**。agent产出当前阶段的计划 JSON，这一条命令按已声明目标连续执行：解析选择器拿 handle → 开面板 → 按条件等面板和选项出现 → 选中 → 收面板并验证已关 → 三层回读 → 下一个字段（字段间留 pace 间隔）。不要再为每个字段现写 stage 脚本。
  计划形状：`{"fields": [...], "pace": {"min":0.3,"max":0.8}, "panel_wait":2, "option_wait":2}`（裸数组等于只给 fields）。每个字段：`key` / `label`（报告里显示）、`kind` 取 `text` / `dropdown` / `search` / `cascader` / `date` / `checkbox` / `native-select`、`value`（级联给数组，逐级点）；可选 `term`（可搜索下拉先打的词）、`display_selector`（值显示在别处时指明）、`max`（文本字数上限，取自 `limits.json`）、`display`（级联回读用的显示值）。
  **定位默认用语义坐标**：`section` / `occurrence` / `label` / `nth`（板块、第几条记录、字段标签、同一条记录里同名标签的第几个），由 `plan-skeleton` 生成。语义坐标加条目不失效、写错了只是找不到。`selector` + `index` 是降级路径，默认关闭：骨架覆盖不到的场合需要在计划里写 `"addressing": "selector"` 或命令行加 `--allow-selector` 才能使用，否则退出非零并报"这份计划用了位置坐标但没开开关"。`index` 是纯位置量，错一位就操作到完全无关的控件，而最敏感的字段往往恰好排在最前面——这是它需要显式开启的原因。
  可选 `expect_label`：声明这个控件的可访问名称应当含什么，执行前校验，对不上就报"控件身份校验不通过"并且不动它。**声明权在模型，执行权在代码。** 实际证件号、密码、验证码、银行卡等禁填内容不使用`sensitive_ok`绕过；它只用于agent有证据确认普通字段被误报的情形。原生密码类型不可覆盖。
  逐行打印 `OK` / `FAIL` / `SKIP` 和原因，再打一行 `---` 和完整 JSON 报告。
  报告的字段含义（**照这里看，不要去读 `lib_fill.js` 的源码**——那是实现，改了你也不会知道）：
  顶层 `total` / `filled` 是计划条数和填成几个；`open_panels` 是我们自己点开、收尾时仍可见的面板数（不是页面上有多少节点像面板）；`open_panel_fields` 是哪几个字段的面板没收掉；`close_trick` 是本页试出来的收面板办法；`context_lost` 非空说明页面在填写过程中导航了，逐字段结果是变化之前的状态；`elapsed_seconds` 是这一轮的秒数。
  每个字段：`status` 取 `filled` / `failed` / `skipped`（客观写不进，如账号级 disabled 字段）/ `not-started`（撞上时间预算）；`why` 是失败原因的人话；`via` 是 `semantic` 还是 `selector`；`resolved` 是解析到的控件（标签名、可访问名称、可见性）；`panel` 是开出来的面板 class 前 40 字；`closed_by` 是这个字段用哪招收的面板；`readback` 里 `visible_ok` 是显示值与 DOM 一致（**这是判据**）、`model_ok` 是框架模型值一致（**只作参考，不单独否决**）、`errors` 是页面新冒出来的错误提示。有`needs_observation`/`structure_changes`时，已填结果保持filled，剩余not-started，先重新观察；`panel_status_unknown`/`close_candidates`表示关闭未确认，不能重填来代替判断。`display_unknown`/`display_candidates`表示显示值未选定，先只读查证并指定display_selector。完成当前计划且无未知状态才打印 `DONE` 退出 0；有字段没填成退出 1，面板没收干净 `ERR_PANELS`，计划本身有问题 `ERR_PLAN`，页面在填写过程中导航或重渲染 `ERR_CONTEXT`（逐字段报告仍会打出来，但那是页面变化之前的状态）。**一份计划只写当前激活步骤里的字段**：在 DOM 里但不可见的控件（未激活的分步页、折叠板块）会被拒绝并说明原因，因为隐藏控件写得进去、回读还会通过，报成功就是假的。`fill` 不点下一步、保存、暂存、提交。
  两条设计约束：计划里的字段名、选择器、目标值只当数据传进页面，不拼进 JS 执行；元素由 `lib_fill.js` 按 handle 持有，执行每个动作前重新校验元素还在、可见、没被遮住。可见性判定用 `checkVisibility`，不用 `offsetParent`（后者对 `position:fixed` 的元素恒为假）。
  fill是默认写入工具；特殊控件无法表达时，可在已授权范围内用现有click/type/exec/stage现场处理，保留来源、动作身份和回读。本地测试台见 `evals/fixtures/apply_form.html` 与 `evals/fill_benchmark.py`。
  **显式选择**：面板多候选填panel_selector，选项重名填option_selector（原生select也适用）；级联用panel_selectors/option_selectors数组，长度等于步骤数，每项字符串或null，null只走唯一候选路径。单数与同类数组不能并存，后一级可在原面板。selector只表达agent对本页DOM的判断，不写进代码形成站点规则。
  判断后把所选候选的options和来源写入字段，来源门禁才能接回执行。旧handle只作证据，每次重开后实时唯一解析。display_selector必须唯一；不匹配/多匹配不退回首项。原生select有native_options显示文字与编码value，两者不等时按实际选项验证，不把写对报错。
- `stage <stage.js> [--libs …] [--max 秒]`：把库和 stage 脚本拼起来注入，复用一次连接轮询本次运行的日志；`--max` 是定位、连接、注入及轮询的总时间预算，接受有限正数秒。只把终态日志行 `DONE` / `DONE …` 认作成功，错误、超时、旧运行或失联退出非零，不能只凭页面有值或退出0就省略内容回读。注入不等待脚本跑完；超时不撤销页内已执行的写入，先回读当前状态，不直接重跑。
- `read-urls <列表> <输出目录> [起始行] [结束行] [--pace 最短-最长] [--guard-every N] [--stop-file 文件]`：按 `id<TAB>url` 列表逐个导航并读正文，带间隔与 guard；只适用于详情有独立 URL 的站点。几个标签页并行读时各进程给同一个 `--stop-file`：谁的 guard 报验证码或跳登录就写这个文件，其他进程读下一条前看到它就停并打印 `STOP stop-file`。
- `type <选择器|js:表达式> <文本|@文件>`：像人打字一样写入一个文本框：真实鼠标点击取得焦点 → 全选 → 浏览器自己的输入路径写入 → 补 input / change / blur / focusout → 回读比对，一致输出 `typed <标签> <n>字 回读 <n>字 一致`，不一致 `ERR_TYPE`。文本以 `@` 开头就读文件（长文本、含换行或引号时用）。是 setter 写法三层回读不过时的兜底，见 apply-fill 的 controls.md。
- `upload <选择器> <文件路径>`：把本地文件设到 `<input type=file>` 上（浏览器原生路径，触发 change），回读 `input.files` 的文件名；找不到控件 `NO_ELEMENT`，文件不存在 `ERR_NO_FILE`。简历附件按skill默认代传，其他材料须取得用户确认的文件。
- `sniff <选择器|js:表达式|x,y> [--wait 秒]`：观察页面自己发出的请求。先往认领的标签页注入 `lib_net.js` 装记录钩子，再做触发动作（选择器和坐标是发真实鼠标事件点一下；`js:` 是直接执行表达式，通常用来调页面自己的翻页函数——注意和 `click` 的 `js:` 不同，那里是求值得到元素再点），等 `--wait` 秒（默认 3，响应都回来了会提前结束），打印 `SNIFF <请求数>`、每个请求一行（方法、地址、请求体开头、状态、响应类型、响应长度）、一行 `---`、完整 JSON（响应只留开头 600 字）。哪条请求返回 JSON、JSON 里有没有岗位正文，看响应开头判断。
- `screenshot <输出.png>`：把认领的标签页切到前台、只截网页内容。会把专用浏览器提到前台，用户正在打字时先说一声。
- `click <选择器|js:表达式|x,y>`：发真实鼠标事件点一下，元素先滚到视口中间、位置稳定后再点；页面脚本 `el.click()` 点不开的日期面板、级联菜单用它。目标是一个参数，`js:` 表达式里有空格要整体加引号，不然会被拆开、报 `ERR_USAGE click`。

## 配套脚本
- `guard.js`：验证码 / 登录跳转或登录弹窗 / 可见弹窗 / 浏览器错误页与上网认证跳转检测，返回 JSON；`blocked` 为 `browser-error`（证书错误、连不上）或 `captive-portal`（校园网、酒店网认证）时脚本无能为力，直接请用户在专用浏览器里处理。
- `probe.js`：控件探测：标签、类型（`dropdown?` 表示像下拉，要行为探测定型）、`maxlength`、页面明文的字数要求 `hintLimit`、必填、`disabled` / `readonly`、当前值长度、字段容器的 class（`wrapCls`，命名里常带控件类型线索）；证件、密码、验证码、手机、邮箱只报长度。
  取值分三层：控件自己的 `value` → 容器里的内层输入控件 → 显示元素的文本，`valueFrom` 报出读自哪一层（`self` / `inner-input` / `display`）。三层都拿不到时报 `valueUnknown: true` 且 `valueLen: null`——**这是"读不出"，不是"是空的"**，不能据此补填或清空（容器型日期控件的值在内层 input 上，按容器读必然是空）。
- `read_page.js`：正文文本与同站链接。
- `lib_antd3.js`：控件操作的参考实现（`window.__ca`），stage 脚本用 `--libs` 引入。
- `lib_fill.js`：`fill` 子命令的页内原语（`window.__caFill`），由 `fill` 自己注入，不用手动 `--libs`。里面有整页控件快照（一次调用读完，带可访问名称）、按 handle 的点击前校验、面板与选项查找、三层回读。回读模型层时从 React 的 `root.current` 找活动 fiber——元素上挂着的 `__reactFiber$` 在奇数次提交后指向旧分支，直接读它会把写对的值判成没写进去。
- `lib_net.js`：`window.__caNet`，stage 脚本用 `--libs` 引入：`hook()` 装记录钩子（幂等）；`seen(起始序号)` 取记录；`capture(fn)` 调用页面自己的函数并截住它这次收到的响应（返回记录数组，每条带解析好的 `json`）；`fetchJson(url, {method, body})` 在同一标签页里复发一个观察到的请求，返回 `{status, type, data}`；`paced(最短秒, 最长秒)` 随机停顿。规矩：只复发页面自己发过的地址和请求体、只改页码，不加参数、不改每页条数、不用页面没用过的接口。

## 出错约定
`python3 chrome_cdp.py --help` 打印全部子命令的用法。`ERR_NO_CDP` 没有专用浏览器，直接 `launch`，不必重试；`NO_MATCHING_TAB` 认领的标签页找不到；`ERR_USAGE <子命令>` 参数不对；`ERR_CLAIM` 页面不允许写存储；`ERR_JS` 页内脚本抛异常；`ERR_CDP` 协议层出错或超时；`ERR_WRITE` 输出文件没写成（磁盘满、目录不可写）。都不吐 Traceback。

一次执行同时保留stdout、stderr和退出码（工具返回或工作目录日志）。不要为分别查看输出、补报错原文而重新执行有写入效果的命令；明确失败后先只读核日志与当前值，有具体修正再按控件失败规矩有界尝试。同一失败stage未作修正时不重复跑。

## 环境变量
`CA_CDP_PORT`（端口，默认 9222）、`CA_CDP_TIMEOUT`（单次应答超时秒数）、`CA_BROWSER`（浏览器可执行文件）、`CA_CHROME_PROFILE`（专用配置目录，默认 `~/campus-apply-chrome`）。

可选 `CA_TIMING_FILE` 指向 JSONL 文件，**每条子命令**都追加一行（命令名、墙钟起点、耗时、退出码），stage 另加一行自己的分段。跑完用 `python3 scripts/idle_report.py <这个文件>` 算出"命令占用 / 浏览器空置"两个数和最长的几段空置——空置是浏览器已经就绪、却没有命令在跑的时间，压它比压命令本身有用得多。stage追加命令、终态和秒数：总耗时、定位（含连接）、编译及注入、等待。不会写字段值或凭证；未设置时不新增文件，普通日志输出不变。这是工具计时，不是模型推理或人工等待时间。

旧stage的单表达式和多语句均可注入：先做不执行的语法预检，最终只执行一次。单表达式返回的Promise异常可记为ERR；多语句内部未返回的异步任务仍需自己捕获并用`L('ERR …')`记日志。避免把用户填写的普通文本作为DONE/ERR终态行输出。
