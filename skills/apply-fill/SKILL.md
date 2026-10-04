---
name: apply-fill
description: "陪用户逐页填写招聘网站的网申表单和在线简历，能填的填、该用户做的等用户做，不点提交。Use when the user has an application form or online resume page open in the dedicated browser and wants it filled from their tailored resume; triggers: 填网申 / 帮我填表 / 陪我投 / fill the application."
---

# apply-fill：陪跑式填网申

网申流程不固定。本 skill 是一个循环：**看这一页 → 说清楚 → 该用户做的等用户 → 该我做的做完回读 → 记一笔 → 下一页**。细则按步骤看 `references/`，别凭记忆。资料复用、清单更新和工具结束后的交接按 `../campus-apply/references/workflow-state.md`。

## 前提
- **投递目录里必须已有 `resume.md` 和渲染好的简历 PDF，没有就不开始这个 skill。** 没有就告诉用户"先针对这个岗位改一版简历，改完再来填表"，然后去走 resume-tailor；填表期间不补这一步。这条没有例外：志愿选择、账号信息这类不需要简历文本的字段也一样等着，因为申请页第一件事是传附件、等站点解析、再逐字段重写，顺序颠倒就要返工（见 `references/upload-and-parse.md`）。长文本字段还要 `form.md` + `limits.json`，这两样在第 4 步传完附件、探过字段之后回到 resume-tailor 第 7、8 步产出。
- 专用浏览器已启动（`chrome_cdp.py launch`），用户已在里面登录并打开网申相关页面。
- 浏览器操作用 `../campus-apply/scripts/browser/chrome_cdp.py`（见总控 skill 的 `references/browser-tools.md`）；控件写法 `references/controls.md`，硬规矩 `references/pitfalls.md`。

## 开始
1. 认领标签页，把文末的执行清单复制成 `<投递目录>/apply-fill-执行清单_<日期>.md`，建 `fill-log.md`（`templates/fill-log.template.md`）。→ `references/claim-and-tabs.md`
2. 读 `site-notes/<域名>.md`；跑 guard，要登录就请用户登录。→ `references/claim-and-tabs.md`
3. 只读探测入口页，把已知、未知、建议顺序和代价告诉用户，等用户同意再动。→ `references/upload-and-parse.md`
4. 进了申请页，**第一件事是传简历 PDF 附件**（默认由我代传，用户说"我自己传"就等他），等站点解析完做前后对比，再开始填字段。页面上没有上传位就记一笔继续。`form.md` 在这一步之后写——先看解析把哪些字段填掉了，剩下哪些长文本要自己写。→ `references/upload-and-parse.md`

## 循环（每一页都走一遍）
A. **看**：guard → probe → 需要时 read_page，判断这是什么页，把每个控件的类型探清楚（文本、纯下拉、可搜索下拉、日期面板、级联），仅对页面明示有范围的字段记限制原文与来源（如荣誉级别、经历类型、时间范围、条目上限），普通字段不额外建规则；长文本字段把 `maxlength`、页面明文的字数要求、校验结果三样都探出来。→ `references/on-site-principles.md`
B. **说**：这页有哪些板块字段；我能填哪些、从 `resume.md`/`form.md` 哪段取；哪些必须用户做（登录、验证码、下一步/提交）；简历附件默认由我传、用户可以说"我自己传"；要用户给值的列表逐行收集，下拉先探选项；有后果的开关单独列。等用户说"可以"（或"这一页直接填"）。→ `references/collect-table.md`
C. **等**：轮到用户做的节点，说清"请你现在做 X，做完告诉我"，什么都不动；用户说完回到 A，把变化记进 `fill-log.md`。
D. **填**：初填、追加和恢复都先按已探明的字段范围筛选素材；“全部补齐”不能视为已知情的范围例外，处理办法见 `references/on-site-principles.md`。文本按 `references/controls.md` 的标准序列写入（含 blur），回读三层。自我描述、自我评价、个人简介、求职动机这类自述字段，内容只能来自 `form.md` 里按 resume-tailor 第 8 步（结构表 → 用户确认 → 初稿 → 去 AI 味改稿 → 全文过目）写出的文本；`form.md` 里没有就停下来先走那一步，把四步作为子步骤加进执行清单；简历上的一句话自评、旧网申的文本、站点解析件都不能直接贴入。用户要求沿用旧文本时，先说明网申自述和简历自评的区别、这个流程会产出什么，再照用户的决定办，并在报告里记"用户选择沿用旧文本"。写入走 `chrome_cdp.py --mark <ID> fill <计划.json>`：在投递目录 `stages/` 写这一页的计划 JSON（字段名、选择器、控件类型、目标值；长度自己守 `limits.json`，不指望 `maxlength` 拦），一条命令把整页填完并返回逐字段报告——三层回读、错误提示、面板是否收干净都在报告里。不要为每个字段现写脚本；现场写脚本只用于探测。**一份计划只写当前激活步骤里的字段**，分步表单一步一份、翻页是单独的动作（`fill` 不点下一步）。报告里有字段没填成，先看原因：说"不可见"或"找不到控件"的多半是下一步才出现的字段，翻页后另出一份计划，不要整页重跑；其余按 `references/control-failure.md` 处理，两次仍不对就停。→ `references/on-site-principles.md`、`references/control-failure.md`
E. **记**：`fill-log.md` 追加这一页：探测摘要、我填了什么、用户做了什么、回读结果、异常。
F. **下一页**：点前 guard，点后等页面稳定再回到 A。

## 保存与提交
刷新或导航前先确认用户已保存并把当前值留底；用户每点一次保存或暂存，立刻刷新、重新探测、逐字段比对文本内容，通过前这一页不算完成，发现被改写就停；提交前全字段回读成表、用户点预览、我读预览页比对、用户点提交。→ `references/save-and-submit.md`

## 结束
写 `fill-report.md`（`templates/fill-report.template.md`）；写或更新 `site-notes/<域名>.md`（`templates/site-notes.template.md`，不写个人信息）；`log.txt` 追加一行；回到原清单勾选实际完成项，关闭已回答的待决原项并同步关联记录。最后交接已填未保存、限制和仍需用户决定的事项，然后等待。

## 遇到就停
验证码、跳登录、同一字段连续两次写入无效、不是我们触发的弹窗：停下、说清楚、等用户说"继续"。出了事故先说发生了什么、影响多大、打算怎么补，再动手。→ `references/control-failure.md`

## 不做
最终的提交、投递、确认投递永远由用户点；只把页面导航到表单、本身不产生投递的按钮（"立即投递""申请职位"这类进入表单的入口）可以由我点，点之前从站点笔记或页面代码确认它不提交，拿不准就问用户。简历附件默认由我代传（`upload`），用户说"我自己传"就交给用户；证件照、成绩单、作品集这类材料仍然问用户要文件再传。不填证件号、密码、验证码；不解验证码；不操作认领之外的标签页；不把自动解析的结果当成已填好。

## 执行清单（复制到 `<投递目录>/apply-fill-执行清单_<日期>.md`）
```
- [ ] 0 前提：投递目录有 resume.md 和简历 PDF（没有 → 停下，先走 resume-tailor）
- [ ] 1 list → claim；fill-log.md 建好；说明只操作这个标签页
- [ ] 2 站点笔记读过；guard；要登录 —— 等用户回复：
- [ ] 3 入口页只读探测；已知 / 未知 / 建议顺序 / 代价 —— 等用户回复：
- [ ] 4 上传前探一次留底 → 传简历 PDF 附件 → 等解析 → 前后对比写进 fill-log（页面没有上传位就记一笔）
每一页：
- [ ] A 看：guard、probe、控件类型；明示字段范围与来源；长文本三层限制
- [ ] B 说：能填 / 要用户做 / 收集表 / 有后果的开关 —— 等用户回复：
- [ ] C 等：用户操作（登录 / 证件号等自填 / 成绩单证件照等材料 / 下一步）—— 等用户回复：
- [ ] D 填：初填 / 追加 / 恢复复核字段范围；自述字段来自四步流程的 form.md（没有 → 先走 resume-tailor 第 8 步）；写计划 JSON → fill 跑整页；看报告里的三层回读、错误提示、面板 0
- [ ] E 记 fill-log
- [ ] F 下一页：点前 guard
保存与提交（每次点保存 / 暂存都走一遍）：
- [ ] 留底 → 用户点保存或暂存 —— 等用户回复：
- [ ] 立刻刷新、重新探测、逐字段比对文本内容；通过前这一页不算完成
- [ ] 全字段表 → 用户点预览（可能弹新窗口，先提醒）—— 等用户回复：
- [ ] 读预览页比对 → 用户点提交 —— 等用户回复：
- [ ] fill-report、站点笔记、log.txt
```
