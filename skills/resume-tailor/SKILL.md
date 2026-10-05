---
name: resume-tailor
description: "Use when the user has picked a target job and the generic resume does not speak to it, or needs the long free-text answers an application form asks for; triggers: 改简历 / 针对这个岗位 / 写网申内容 / 自我描述 / 求职动机 / tailor resume。"
---

# resume-tailor：对照 JD 改简历与网申文本

## 不可逆的几条

- **不编事实库里没有的数字和经历**。每条要点的数字都要在事实库找得到；`check_content.py` 报的 ERR 必须改到零，
  它是唯一挡住虚构数字的机械闸门。编出来的内容一旦随简历投出去，面试时对不上，撤不回来。
- **不动用户的简历原件**：要在 docx 上改就先复制到投递目录，所有写入都对副本做。覆盖掉用户自己的那份是真正不可恢复的。
- **替用户说话的文本要用户过目才算定稿**。自我描述、自我评价、求职信这类自述，全文加改动总结给用户看过、
  用户认了才能用；不搬简历上的一句话自评、不搬旧网申、不搬站点解析件。用户坚持沿用旧文本时先说明区别再照办并记录。
- **来源冲突不自行覆盖**：列出不同说法和各自出处，等用户定。
- 不上网查公司；不替用户点任何网页。

## 怎么做

- 前提、九步流程、通用版（无 JD）怎么走 → `references/steps.md`
- 简历要点与网申经历描述的写法 → `references/style-rules.md`
- 自述四步（结构表 → 用户确认 → 初稿 → 去 AI 味改稿 → 全文过目）→ `references/self-statement.md`
- 写完逐条去 AI 味 → `references/humanizer.md`
- 在用户现有 docx 上原地改字 → `references/docx-inplace.md`
- 对用户说话的规矩、停顿怎么安排 → `../campus-apply/references/talking-to-the-user.md`
- 出现"用户说先用旧的自评，那就直接贴"这类念头 → `../campus-apply/references/red-flags.md`
- 清单、待决和关联记录更新及交接 → `../campus-apply/references/workflow-state.md`

开工先把 `references/checklist.md` 的清单复制到投递目录，做到哪勾到哪。

网申长文本（`form.md` + `limits.json`）要先看见页面才写，所以**不在这里做**，留到 apply-fill 传完附件、探过字段之后；
**第 6 步出了 PDF 就可以交给 apply-fill**，不必等 `form.md`。
