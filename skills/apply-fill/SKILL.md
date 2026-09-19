---
name: apply-fill
description: 陪着用户走完一个网申流程：每到一页先说清这页是什么、哪些我能填、哪些要用户做（登录、上传、验证码、下一步、提交），用户做完再探测继续；能填的按节奏填并逐页回读，不点提交。Use when the user has an application form open in Chrome and wants help filling it from their tailored resume; triggers: 填网申 / 帮我填表 / 陪我投 / fill the application.
---

# apply-fill：陪跑式填网申

网申流程不固定。本 skill 是一个循环：**看这一页 → 说清楚 → 该用户做的等用户 → 该我做的做完回读 → 记一笔 → 下一页**。细则按步骤看 `references/`，别凭记忆。

## 前提
- 投递目录里有 `resume.md`（必需）、`form.md` + `limits.json`（有长文本字段时）。
- 专用调试浏览器已启动（`chrome_cdp.py launch`），用户已在里面登录并打开网申相关页面。
- 浏览器操作用 `../campus-apply/scripts/browser/chrome_cdp.py`（子命令见总控 skill 的"工具位置"）；控件写法 `references/controls.md`，硬规矩 `references/pitfalls.md`。

## 开始
1. 认领标签页，建执行清单 `<投递目录>/apply-fill-执行清单_<日期>.md` 和 `fill-log.md`（`templates/fill-log.template.md`）。→ `references/claim-and-tabs.md`
2. 读 `site-notes/<域名>.md`；跑 guard，要登录就请用户登录。→ `references/claim-and-tabs.md`
3. 只读探测入口页，把已知、未知、建议顺序和代价告诉用户，等用户同意再动；`form.md` 在探测与上传试探之后再写。→ `references/upload-and-parse.md`

## 循环（每一页都走一遍）
A. **看**：guard → probe → 需要时 read_page，判断这是什么页，把每个控件的类型探清楚（文本、纯下拉、可搜索下拉、日期面板、级联）。→ `references/on-site-principles.md`
B. **说**：这页有哪些板块字段；我能填哪些、从 `resume.md`/`form.md` 哪段取；哪些必须用户做（登录、上传、验证码、下一步/提交）；要用户给值的列表逐行收集，下拉先探选项。等用户说"可以"（或"这一页直接填"）。→ `references/collect-table.md`
C. **等**：轮到用户做的节点，说清"请你现在做 X，做完告诉我"，什么都不动；用户说完回到 A，把变化记进 `fill-log.md`。
D. **填**：自我描述、自我评价、个人简介、求职动机这类自述字段，内容只能来自 `form.md` 里按 resume-tailor 第 8 步（结构表 → 用户确认 → 初稿 → 去 AI 味改稿 → 全文过目）写出的文本；`form.md` 里没有就停下来先走那一步，把四步作为子步骤加进执行清单；简历上的一句话自评、旧网申的文本、站点解析件都不能直接贴入。用户要求沿用旧文本时，先说明网申自述和简历自评的区别、这个流程会产出什么，再照用户的决定办，并在报告里记"用户选择沿用旧文本"。在投递目录 `stages/` 现场写这一页的脚本（按板块写成能整页重跑的幂等函数），`chrome_cdp.py stage` 跑，回读以显示值为准，每个打开的面板同一步骤内关掉；两次仍不对就停。→ `references/on-site-principles.md`、`references/control-failure.md`
E. **记**：`fill-log.md` 追加这一页：探测摘要、我填了什么、用户做了什么、回读结果、异常。
F. **下一页**：点前 guard，点后等页面稳定再回到 A。

## 保存与提交
刷新或导航前先确认用户已保存并把当前值留底；用户保存后刷新回读核对字数；提交前全字段回读成表、用户点预览、我读预览页比对、用户点提交。→ `references/save-and-submit.md`

## 结束
写 `fill-report.md`（`templates/fill-report.template.md`）；写或更新 `site-notes/<域名>.md`（`templates/site-notes.template.md`，不写个人信息）；`log.txt` 追加一行。

## 遇到就停
验证码、跳登录、同一字段连续两次写入无效、不是我们触发的弹窗：停下、说清楚、等用户说"继续"。出了事故先说发生了什么、影响多大、打算怎么补，再动手。→ `references/control-failure.md`

## 不做
不点提交/投递；不上传文件；不填证件号、密码、验证码；不解验证码；不操作认领之外的标签页；不把自动解析的结果当成已填好。
