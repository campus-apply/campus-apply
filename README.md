# campus-apply

国内校招网申全流程 skill：事实库、筛岗、改简历、填网申。它在你自己登录的浏览器标签页里现场操作，不调站点接口，不替你提交。

Campus-recruitment application skills for Chinese job sites, built for Claude Code; the skill package format also loads in Codex and DeepSeek Harness (see Requirements). Everything happens inside your own logged-in browser tab; it never submits on your behalf.

## 它做什么，不做什么 / What it does and does not

它做四件事：把你的经历、口径、求职偏好和个人档案整理成带来源的本地文件；在公司招聘页上按你的偏好筛岗，全量清单和每个岗位的硬要求先给你看；对照岗位描述在你现有的简历 docx 上原地改出一页，并写网申长文本和自述；陪你逐页走完网申，每页先说清哪些它填、哪些要你做，按节奏填并回读。

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

顺序：`resume-facts`（一次）→ `job-screen` → `resume-tailor` → `apply-fill`。已有岗位描述可以跳过筛岗。

Flow: facts once, then screen, tailor, fill. Skip screening when you already have a job description.

## 安装 / Install

Claude Code：在 Claude Code 里执行 `/plugin marketplace add /path/to/campus-apply`，再 `/plugin install campus-apply@campus-apply`。

其他 harness 或开发模式：

```
./install.sh claude   # 软链接到 ~/.claude/skills
./install.sh codex    # ~/.codex/skills
./install.sh agents   # ~/.agents/skills（DeepSeek Harness 等）
./install.sh all      # 只装到已存在的目录；加 --copy 改为复制
```

## 依赖与平台 / Requirements and platforms

- Python 3.9 以上，`pip install python-docx openpyxl`；核页数需要 poppler 的 `pdfinfo`（macOS `brew install poppler`）或 `pip install pypdf`。
- 改简历导 PDF 需要 Microsoft Word：macOS 直接可用；Windows 再装 `pip install docx2pdf`。没有 Word 就跳过核页数。
- 浏览器操作（筛岗、填表）通过 Chrome DevTools 协议，macOS 与 Windows 都可以：skill 会用专用配置目录启动一个带调试端口的 Chrome 或 Edge（`chrome_cdp.py launch`），和你日常的浏览器互不影响，第一次要在里面登录招聘站。也可以自己启动：macOS `open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir=$HOME/campus-apply-chrome`，Windows `chrome.exe --remote-debugging-port=9222 --user-data-dir=%USERPROFILE%\campus-apply-chrome`（Edge 同参数）。这个专用配置目录存放招聘站的登录态和缓存，不在工作目录里，几百 MB，求职结束可以整个删掉。
- Windows 安装：用 Claude Code 的 `/plugin marketplace add`，或在 Git Bash 里 `bash install.sh claude --copy`（Windows 建软链接需要管理员权限，直接复制更省事）。
- Harness：全流程在 Claude Code 上验证；Codex 验证到"载入 skill、按总控说明列出专用浏览器标签页"这一步，DeepSeek Harness 只验证了目录格式。Codex 的沙箱默认不开网络、连不上本机调试端口，需在它的 `config.toml`（`$CODEX_HOME/config.toml`，默认 `~/.codex/config.toml`）加 `[sandbox_workspace_write]` 下的 `network_access = true`；Codex 主目录不是 `~/.codex` 时，先 `export CODEX_HOME=<主目录>` 再运行 `install.sh codex`。

Browser automation (screening and form filling) drives Chrome or Edge over the DevTools protocol on macOS and Windows: the skill starts a separate browser profile with a debugging port (`chrome_cdp.py launch`); log in to the job site there once. That profile directory holds the job sites' login state and cache, lives outside your workspace and can be deleted when you are done. PDF export on Windows needs Word plus `docx2pdf`. The full flow is verified on Claude Code; on Codex it is verified up to loading the skills and listing the debug browser's tabs, and DeepSeek Harness is only checked for package format. Codex's sandbox needs `network_access = true` under `[sandbox_workspace_write]` in its `config.toml` (`$CODEX_HOME/config.toml`, default `~/.codex/config.toml`) to reach the local debugging port; set `CODEX_HOME` before `install.sh codex` if your Codex home is elsewhere.

## 工作目录 / Workspace

你打开哪个文件夹，哪个就是工作目录，桌面上一个"简历"文件夹也行。初始化只写一个标记文件 `campus-apply.json`（事实库路径、规则路径、默认简历、求职偏好、个人档案）、一份 `rules.json`（口径红线）和一份 `.gitignore`，不挪你已有的文件。之后按需出现 `applications/<公司>-<岗位>/`（岗位描述、定稿文字、网申文本、填写日志与报告）、`site-notes/<域名>.md`（脱敏的站点笔记），成品简历和筛选表放在工作目录根。

## 数据与隐私 / Data

个人数据全部留在你的工作目录，仓库里只有流程、模板、脚本。证件号、密码、验证码永远不经手，也不写进任何文件。站点笔记不记账号、不记个人信息。工作目录不要放进公开仓库。

## 致谢与许可 / Credits and license

访谈方法改编自 grilling（Matt Pocock，MIT），去 AI 味清单改编自 Humanizer-zh（歸藏，MIT），详见 `THIRD_PARTY_NOTICES.md`。本仓库 MIT。
