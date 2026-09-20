# campus-apply

国内校招网申全流程 skill：事实库、筛岗、改简历、填网申。它在你自己登录的浏览器标签页里现场操作，不调站点接口，不替你提交。

Campus-recruitment application skills for Chinese job sites, for Claude Code, Codex, CodeBuddy Code and DeepSeek Harness (see Install). Everything happens inside your own logged-in browser tab; it never submits on your behalf.

## 它做什么，不做什么 / What it does and does not

它做四件事：把你的经历、口径、求职偏好和个人档案整理成带来源的本地文件；在公司招聘页上按你的偏好筛岗，全量清单和每个岗位的硬要求先给你看；对照岗位描述（JD）在你现有的简历 docx 上原地改出一页，并写网申长文本和自述；陪你逐页走完网申，每页先说清哪些它填、哪些要你做，按节奏填并回读。

它不做：批量投递、自动提交、解验证码、上传文件、填证件号和密码、调用招聘站点的接口、跨站抓取岗位。

It keeps a sourced fact base with your preferences, screens jobs on a company's own careers page (full list and each posting's hard requirements shown to you first), tailors your existing resume docx in place, writes application essays, and walks you through the form page by page, telling you what it will fill and what you must do yourself, reading each page back. It never mass-applies, submits, solves captchas, uploads files, touches ID or password fields, calls site APIs, or scrapes across sites.

## 五个 skill / Skills

| skill | 做什么 |
|---|---|
| `campus-apply` | 入口：看工作目录状态，指到下一步；所有 skill 共用的边界和说话规矩 |
| `resume-facts` | 初始化工作目录，建事实库，口径访谈、求职偏好访谈、个人档案访谈 |
| `job-screen` | 在公司招聘页上列全量岗位、逐个读详情、出三档筛选表和排除清单，同时出一份 Excel |
| `resume-tailor` | 对照岗位出素材方案、写定稿文字、原地改 docx、写网申长文本与自述，写完过去 AI 味清单 |
| `apply-fill` | 陪跑式填表：认领标签页、探测控件、逐页填写与回读、保存后核对、提交前比对预览 |

顺序：`resume-facts`（一次）→ `job-screen` → `resume-tailor` → `apply-fill`。已有 JD 可以跳过筛岗。

Flow: facts once, then screen, tailor, fill. Skip screening when you already have a job description.

## 安装 / Install

需要 Claude Code、Codex、CodeBuddy Code 或 DeepSeek Harness 其中一个，macOS 和 Windows 都可以。最省事的是对你用的 agent 说一句"帮我安装 GitHub 上 campus-apply/campus-apply 这个 skill"，它会按下面对应的一段替你执行。装完新开一个会话就能看到五个 skill，先让它跑一下 `doctor.py`。

**Claude Code** 三种装法任选其一：

1. 自己输入 `/plugin marketplace add campus-apply/campus-apply`，再输入 `/plugin install campus-apply@campus-apply`。
2. 让 agent 执行上面两条。
3. 电脑上没有 Git（从 GitHub 安装要靠它）：到 [Releases](https://github.com/campus-apply/campus-apply/releases) 下载 zip 解压，`/plugin marketplace add <解压后的目录>`，再 `/plugin install campus-apply@campus-apply`；这一步也可以让 agent 做。

更新：`/plugin marketplace update campus-apply` 再 `/plugin update campus-apply@campus-apply`，然后 `/reload-plugins` 或新开会话（对 agent 说"把 campus-apply 插件更新到最新版"也行，`/reload-plugins` 要你自己输）。`doctor.py` 末尾会报本地版本，能联网时有新版也会提一句；没网就只报本地版本。想自动更新，在 `/plugin` 的 Marketplaces 页对 campus-apply 开 auto-update；第三方 marketplace 默认不自动更新。用 zip 装的要重新下载解压覆盖再更新。

**CodeBuddy Code**：插件机制和命令都与 Claude Code 相同，`/plugin marketplace add campus-apply/campus-apply` 再 `/plugin install campus-apply@campus-apply`（它兼容 `.claude-plugin/` 清单），更新也一样。不用插件的话，clone 仓库后运行 `./install.sh codebuddy`，装到它的用户级目录 `~/.codebuddy/skills`。

**Codex**：clone 仓库后运行 `./install.sh codex`，装到 `$CODEX_HOME/skills`（默认 `~/.codex/skills`；主目录不是 `~/.codex` 就先 `export CODEX_HOME=<主目录>`）。它的沙箱默认不开网络、连不上本机调试端口，要在 `config.toml`（`$CODEX_HOME/config.toml`）的 `[sandbox_workspace_write]` 下加一行 `network_access = true`。更新时重新拉仓库再跑一遍脚本。

**DeepSeek Harness**：clone 仓库后运行 `./install.sh agents`，装到它读取的 `~/.agents/skills`（也认 `~/.dsh/skills` 和项目里的 `.agents/skills`）。它没有 marketplace，"让 agent 装"就是让它 clone 仓库再跑这个脚本。更新时重新拉仓库再跑一遍脚本。

开发模式（软链接到仓库，改动即时生效）：

```
./install.sh claude      # ~/.claude/skills
./install.sh codex       # $CODEX_HOME/skills
./install.sh codebuddy   # ~/.codebuddy/skills
./install.sh agents      # ~/.agents/skills（DeepSeek Harness）
./install.sh all         # 只装到已存在的目录；加 --copy 改为复制
```

## 依赖与平台 / Requirements and platforms

- 装好 skill 后先让 agent 跑 `doctor.py`（在 campus-apply skill 的 `scripts/` 里）：逐项检查 Python、pip 包、浏览器、Git、Word，缺什么给出这台机器上的安装命令，pip 包可以由 agent 直接装。手动准备的话：Python 3.9 以上，`pip install python-docx openpyxl pypdf`（核页数也可以用 poppler 的 `pdfinfo`）。
- 改简历导 PDF 需要 Microsoft Word：macOS 直接可用；Windows 再装 `pip install docx2pdf`。没有 Word 就跳过核页数。
- 浏览器操作（筛岗、填表）通过 Chrome DevTools 协议，macOS 与 Windows 都可以：skill 会用专用配置目录启动一个带调试端口的 Chrome 或 Edge（`chrome_cdp.py launch`），和你日常的浏览器互不影响，第一次要在里面登录招聘站。也可以自己启动：macOS `open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir=$HOME/campus-apply-chrome`，Windows `chrome.exe --remote-debugging-port=9222 --user-data-dir=%USERPROFILE%\campus-apply-chrome`（Edge 同参数）。这个专用配置目录存放招聘站的登录态和缓存，不在工作目录里，几百 MB，求职结束可以整个删掉。
- Windows：按上面的装法安装即可；开发模式可在 Git Bash 里 `bash install.sh claude --copy`（Windows 建软链接需要管理员权限，直接复制更省事）。Python 命令通常是 `py`（`python` 可能是应用商店的占位程序，没有输出）；没装 Git for Windows 时 Claude Code 用 PowerShell 执行命令，skill 的命令都是普通的 `py … --mark …` 形式，两种 shell 都能跑。
- Harness：Claude Code 与 Codex 都跑过从事实库到网申的全流程（Codex 到志愿页提交，简历录入页未填完）；CodeBuddy Code 2.95 上跑过安装、doctor、认领标签页、探测、guard 与 stage 注入，它的 Bash 沙箱默认不开，本机调试端口直接可达；DeepSeek Harness 0.1.5（预览版）上验证过安装与 skill 目录格式，它在 Web UI 里对话（`npx @deepseek-ai/dsh web`），要先在"设置 → 模型"里填 DeepSeek API key，默认权限模式是 workspace-write、沙箱只管文件不管网络，本机调试端口可达。Codex 的沙箱设置见安装一节。

Browser automation (screening and form filling) drives Chrome or Edge over the DevTools protocol on macOS and Windows: the skill starts a separate browser profile with a debugging port (`chrome_cdp.py launch`); log in to the job site there once. That profile directory holds the job sites' login state and cache, lives outside your workspace and can be deleted when you are done. PDF export on Windows needs Word plus `docx2pdf`. The full flow is verified on Claude Code and on Codex (up to submitting the job choice; the online-resume pages were not completed there). On CodeBuddy Code 2.95 the install, doctor, tab claim, probe, guard and stage injection were exercised; its Bash sandbox is off by default, so the local debugging port is reachable. On DeepSeek Harness 0.1.5 (developer preview) the install and the skill package format were verified; it runs in a Web UI (`npx @deepseek-ai/dsh web`), needs a DeepSeek API key under Settings → Models, defaults to the workspace-write permission mode, and its sandbox confines files only, so the local debugging port is reachable. Codex's sandbox needs `network_access = true` under `[sandbox_workspace_write]` in its `config.toml` (`$CODEX_HOME/config.toml`, default `~/.codex/config.toml`) to reach the local debugging port; set `CODEX_HOME` before `install.sh codex` if your Codex home is elsewhere.

## 工作目录 / Workspace

你打开哪个文件夹，哪个就是工作目录，桌面上一个"简历"文件夹也行。初始化只写一个标记文件 `campus-apply.json`（事实库路径、规则路径、默认简历、求职偏好、个人档案）、一份 `rules.json`（口径红线）和一份 `.gitignore`，不挪你已有的文件。之后按需出现 `applications/<公司>-<岗位>/`（岗位描述、定稿文字、网申文本、填写日志与报告）、`site-notes/<域名>.md`（脱敏的站点笔记），成品简历和筛选表放在工作目录根。

## 数据与隐私 / Data

个人数据全部留在你的工作目录，仓库里只有流程、模板、脚本。证件号、密码、验证码永远不经手，也不写进任何文件。站点笔记不记账号、不记个人信息。工作目录不要放进公开仓库。

想反馈问题：对 agent 说"打一个反馈包"，它会运行 `feedback_bundle.py`，把执行清单、日志、站点笔记、填写报告、筛选表收到桌面一个文件夹并自动打码（手机、邮箱、证件号、出生日期、姓名、路径里的用户名），不收事实库、简历、网申正文，不压缩也不发送；你自己翻一遍再发。agent 不会主动打包。

## 致谢与许可 / Credits and license

访谈方法改编自 grilling（Matt Pocock，MIT），去 AI 味清单改编自 Humanizer-zh（歸藏，MIT），详见 `THIRD_PARTY_NOTICES.md`。本仓库 MIT。
