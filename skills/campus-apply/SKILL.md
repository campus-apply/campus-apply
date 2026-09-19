---
name: campus-apply
description: 国内校招求职全流程的入口：看工作目录状态，告诉用户下一步该用 resume-facts / job-screen / resume-tailor / apply-fill 哪一个。Use when the user mentions 求职 / 投简历 / 校招 / 网申 / job hunting without naming a specific step.
---

# campus-apply：入口与路线

## 做什么
只做一件事：看清现状，指到下一个 skill。四个功能 skill 都能单独用。

## 判断顺序
1. 当前目录没有 `campus-apply.json` → 用 resume-facts 初始化（先看目录里有没有简历、事实类文件，列给用户）。
2. 有标记文件，用户给了公司招聘页/已在 Chrome 打开岗位列表 → job-screen。
3. 用户已有 JD（文本、链接或 `applications/<公司>-<岗位>/jd.md`）但没有 `resume.md` → resume-tailor。
4. 有 `resume.md`，用户打开了网申表单页 → apply-fill。
5. 列一下 `applications/` 里每个投递目录的状态（有 jd / resume / form / fill-report 哪几样），让用户挑。

## 边界（所有 skill 共用）
- 每个功能 skill 通过 skill 机制载入其 SKILL.md 再执行，不凭记忆跑；开始时把步骤抄成执行清单 `applications/<公司>/<skill>-执行清单_<日期>.md`（复选框，做到哪勾到哪，停顿行写"等用户回复：时间"），跳步会留空格。
- 每个"给用户看、等用户说"的停顿不许跳过；需要用户操作的步骤（登录、上传、验证码、提交）显式列出并等待；页面要求登录时停下请用户登录。
- 只操作我们认领的浏览器标签页，不复用用户自己打开的页面；需要第二个页面时自己新开并认领。
- 不调站点接口；不点提交；不碰验证码、文件上传、证件号、密码；一次一岗；数字要在事实库有出处。

## 对用户说话的规矩（所有 skill 共用）
- 每条消息末尾固定一个"需要你做的"块，最多三项，每项一句；没有就写"这一步不需要你做什么"。
- 要用户选的一律编号表格（候选、我的建议），不埋在段落里；回读结果用表格，不用长段落；正文不超过四段。
- 等用户决定的事写进 `<投递目录>/待你决定.md`（模板 `templates/待你决定.template.md`），只要有未决项，每条消息末尾复述，直到用户答完。
- 内部产物名、任务编号、文件路径只进日志，不进对用户说的话，除非用户要看文件。
- 用户叫停、换话题、或新 session 接手时，先从执行清单、填写日志、待你决定文件里整理一段"当前状态"（哪些页面填了未保存、哪些等用户定、下一步是什么），再谈别的。

## 第一次在这台机器上用
- 先探 Python：`python3 --version`（Windows `python --version`）。没有或低于 3.9，把安装命令给用户（Windows `winget install Python.Python.3.12`，macOS `brew install python`，或 python.org），等用户装完再继续；Python 都没有，后面的检查脚本跑不了。
- 有 Python 就跑 `python3 <本skill>/scripts/doctor.py`，每行是"状态、项目、说明、修复命令"。缺 pip 包：问一句"缺 X、Y，我现在装？"，用户同意就 `doctor.py --install`（只装缺的），装完把结果给用户看。缺浏览器、Git：把那一行的命令原样给用户，等用户装完说一声再重跑 doctor。Word 是可选项，没有就照常走，改简历时说明"未核页数"。
- 全部必需项 OK 之后才进 resume-facts；同一台机器之后不用再跑，除非报错像是缺依赖。

## 工具位置
浏览器操作走本 skill 的 `scripts/browser/chrome_cdp.py`（Python 标准库，macOS / Windows 通用；命令写作 `python3 chrome_cdp.py …`，Windows 用 `python`；选项都是命令行参数，Bash 和 PowerShell 里写法一样）。它只操作一个带远程调试端口、用专用配置目录启动的 Chrome 或 Edge，和用户日常的浏览器互不影响：
- `launch [URL]`：启动专用浏览器（已在跑就只报版本）。第一次用要请用户在里面登录招聘站。
- `list [关键字]`：列标签页（序号、标题、URL、targetId），认领前给用户看。
- `claim <序号|targetId> [运行ID]`：认领，往页面写运行 ID，输出 ID 与 URL，之后每条命令都带 `--mark <ID>`。
- `open <URL> [运行ID]`：自己新开并认领第二个标签页。
- `exec <js文件>`：在认领的标签页执行 JS，输出最后一个表达式的值（字符串原样，其他打成 JSON）。
- `stage <stage.js> [--libs …] [--max 秒]`：把库和 stage 脚本拼起来注入，轮询日志到 DONE / ERR / 超时。
- `read-urls <列表> <输出目录> [起始行] [结束行] [--pace 最短-最长] [--guard-every N]`：按列表逐个读页面，带间隔与 guard。
- `screenshot <输出.png>`：把认领的标签页切到前台、只截网页内容。
同目录的 `guard.js`（验证码 / 登录 / 弹窗检测）、`probe.js`（控件探测）、`read_page.js`（正文与同站链接）、`lib_antd3.js`（控件操作参考实现）配合使用。`list` 和 `launch` 会在 stderr 报告端口上的浏览器版本；报"无界面（Headless）浏览器"说明端口被别的工具占了，换 `CA_CDP_PORT` 或请用户关掉它。
