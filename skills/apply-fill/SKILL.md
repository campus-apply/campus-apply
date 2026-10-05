---
name: apply-fill
description: "Use when an application form or online resume page is open in the dedicated browser and the user wants it filled from their tailored resume; triggers: 填网申 / 帮我填表 / 陪我投 / 这页怎么填 / fill the application。"
---

# apply-fill：陪跑式填网申

## 前提

**投递目录里必须已有 `resume.md` 和渲染好的简历 PDF，没有就不开始这个 skill**，先去走 resume-tailor。
这条没有例外：志愿选择、账号信息这类页面也一样等着（原因见 `references/upload-and-parse.md`）。

专用浏览器已启动（`chrome_cdp.py launch`），用户已登录并打开网申页面。

## 不可逆的几条

- **最终的提交、投递、确认投递永远由用户点。** 本身不投递的入口按钮我可以点，点之前确认它不提交，拿不准就问。
  "暂存""保存草稿"默认不点。
- **不填、不读、不写证件号、密码、验证码、银行卡号**，也不解验证码。回读只记"有值 / 长度"，用户自己填过的也不抄。
- **判不出不等于不成立。** 回读报 `valueUnknown` 的字段一律不许补填、清空或覆盖，先只读确认它到底有没有值，
  确认不了就列给用户。把"判断不出 X"当成"X 不成立"，是这个工具唯一能弄坏用户真实数据的方式。
- **整页非空就不动页面**，探测退化成只读：恢复不干净就是在动用户的数据。
- **刷新或导航前先确认用户已保存，并把当前值回读留底。** 用户每点一次保存或暂存，立刻刷新、重新探测、逐字段比对，
  通过前这一页不算完成；发现任何不是我们写入的改动就停下，把改前改后贴给用户。提交前全字段回读成表、
  用户点预览、我读预览页比对、用户点提交。
- **替用户说话的文本要用户过目。** 自述类字段只能用 `form.md` 里按 resume-tailor 第 8 步写出的文本，没有就先走那一步；
  简历上的一句话自评、旧网申文本、站点解析件不能直接贴入。
- **遇到这些就停**：验证码、跳登录、同一字段连续两次写入无效、不是我们触发的弹窗。说清楚、等用户说"继续"；
  出了事故先说发生了什么、影响多大、打算怎么补，再动手。
- **证件照、成绩单、作品集这类材料问用户要文件再传**，猜错了传的是用户的真实材料。简历附件默认由我代传（`upload`），
  用户说"我自己传"就交给用户。
- 只操作认领的那个标签页；不批量投递；一次一岗；不把自动解析的结果当成已填好。

## 探完再填

这一页的顺序是死的：**探完 → 问完 → 填完**；要用户定的事在写入任何字段之前一次问清。
**填写阶段不再探测**——没探到的字段说明探测没做完，回探测阶段补，不边填边看。

## 怎么做

开工先把 `references/checklist.md` 的清单复制到投递目录，做到哪勾到哪。

- 开场四步、每页循环、"探完"的四条定义 → `references/page-loop.md`
- 认领标签页与登录 → `references/claim-and-tabs.md`；传附件与解析 → `references/upload-and-parse.md`
- 收集用户要定的事、开关分三类 → `references/collect-table.md`
- 探测、字段范围、字数限制、收面板、回读、分步表单 → `references/on-site-principles.md`
- 控件写入与点法 → `references/controls.md`；搞不定与事故 → `references/control-failure.md`
- 保存与提交 → `references/save-and-submit.md`；已知的坑 → `references/pitfalls.md`
- 说话与停顿 → `../campus-apply/references/talking-to-the-user.md`；该停的念头 → `../campus-apply/references/red-flags.md`
- 资料复用与交接 → `../campus-apply/references/workflow-state.md`
