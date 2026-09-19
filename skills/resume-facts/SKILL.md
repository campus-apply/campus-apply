---
name: resume-facts
description: 初始化 campus-apply 工作目录、建立带来源的个人经历事实库、做口径访谈生成 rules.json、做求职偏好访谈写进 campus-apply.json。Use when the user starts job hunting, wants to set up their fact base / resume workspace, or says 建事实库 / 初始化 / 整理经历 / 定口径 / 我想投什么.
---

# resume-facts：工作目录、事实库、口径、偏好

## 什么时候用
用户第一次用 campus-apply；当前目录没有 `campus-apply.json`；或用户要补充经历、改口径、改求职偏好。

## 原则
- 工作目录就是用户打开的这个文件夹（可能只是桌面上一个"简历"文件夹）。不挪用户已有文件，需要就复制。
- 事实库是人写人读的 markdown，每条带来源；数字没来源就放"待核对"。
- 手机号、证件号、住址不进事实库。
- 访谈里的推荐答案要按用户背景调（见 `references/interview.md` 开头），不照抄。

## 步骤
1. 看当前目录：有没有 `campus-apply.json`、已有的简历（docx/pdf）、已有的事实类文档。列给用户看，问哪份简历作为默认模板（`resume_docx`）、哪些文件当事实库。
2. 运行初始化（脚本在本 skill 的 `scripts/`）：
   `python3 <skill目录>/scripts/init_workspace.py --dir . --facts <文件…> --resume-docx <简历.docx>`
   没有事实库时不传 `--facts`，脚本会从模板新建 `个人经历事实库.md`。
3. 事实库是新建的话：读用户简历，把每条经历、数字、奖项抄进事实库，来源标【简历 文件名】；然后按 `references/interview.md` 的方法，把简历里没写清的（起止月份、数字口径、角色边界）攒成一轮问用户，答案标【用户口述 日期】。
4. 通用口径访谈：按 `references/interview.md`"通用口径题库"一次问完 8 题（每题带推荐答案），把答案写进 `rules.json`（`sensitive_terms`、`banned_words`、`forbidden_claims`、`max_numbers_per_bullet`、`style_notes` 等）和事实库"边界"行。
5. 求职偏好访谈：按"求职偏好题库"一次问完 7 题（投什么、岗位类型要与不要、地点、海外线、语言、提前入职、其他约束），答案写进 `campus-apply.json` 的 `preferences`。job-screen 靠它做粗筛，所以"坚决不投的岗位类型"要问到明确的词（如"培训生""销售"）。
6. 个人档案访谈：按"个人档案题库"一次问完，写进 `campus-apply.json` 的 `profile`（证件号、密码不存）。
7. 在工作目录 `log.txt` 追加一行：日期、做了什么、定了什么。
8. 告诉用户下一步：有公司岗位页就用 job-screen，已有 JD 就用 resume-tailor。

## 不做
不生成简历、不碰浏览器、不上网查用户信息。
