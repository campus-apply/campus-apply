---
name: resume-facts
description: "建立求职工作目录和带来源的个人经历事实库，并通过访谈确定口径、求职偏好与个人档案。Use when the user starts job hunting, wants to set up their fact base / resume workspace, or says 建事实库 / 初始化 / 整理经历 / 定口径 / 我想投什么."
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
0. 这台机器第一次用：按总控 skill"第一次在这台机器上用"跑 doctor，必需项齐了再往下。
1. 看当前目录：有没有 `campus-apply.json`、已有的简历（docx/pdf）、已有的事实类文档。列给用户看，问哪份简历作为默认模板（`resume_docx`）、哪些文件当事实库。
2. 运行初始化（脚本在本 skill 的 `scripts/`）：
   `python3 <skill目录>/scripts/init_workspace.py --dir . --facts <文件…> --resume-docx <简历.docx>`
   没有事实库时不传 `--facts`，脚本会从模板新建 `个人经历事实库.md`。
3. 事实库是新建的话：读用户简历，把每条经历、数字、奖项抄进事实库，来源标【简历 文件名】。PDF 用 pypdf 抽不出文字的是图片型（扫描件、网申导出），有 `pdftoppm` 就转成图看，没有就用 pypdf 把每页里的图片存出来逐张看，还不行就请用户截图或口述；然后按 `references/interview.md` 的方法，把简历里没写清的（起止月份、数字口径、角色边界）攒成一轮问用户，答案标【用户口述 日期】。
4. 通用口径访谈：按 `references/interview.md`"通用口径题库"一次问完 8 题（每题带推荐答案），把答案写进 `rules.json`（`sensitive_terms`、`banned_words`、`forbidden_claims`、`max_numbers_per_bullet`、`style_notes` 等）和事实库"边界"行。第 3 步的事实缺口题和这一轮分两条消息发，一条消息不超过 8 题；每题给推荐答案并说"照推荐就回'都按推荐'"。
5. 求职偏好访谈：按"求职偏好题库"一次问完 7 题（投什么、岗位类型要与不要、地点、海外线、语言、提前入职、其他约束），答案写进 `campus-apply.json` 的 `preferences`。job-screen 靠它做粗筛，所以"坚决不投的岗位类型"要问到明确的词（如"培训生""销售"）。
6. 个人档案访谈：按"个人档案题库"一次问完，写进 `campus-apply.json` 的 `profile`（证件号、密码不存）。第 5、6 步用户说"我自己填"时，把 `campus-apply.json` 里 `preferences` 和 `profile` 的字段名、每个字段填什么、可选值列成一张表给用户，用户填完（或直接改文件）由你校验格式与缺项，不再追问。
7. 在工作目录 `log.txt` 追加一行：日期、做了什么、定了什么。
8. 告诉用户下一步：有公司岗位页就用 job-screen，已有 JD 就用 resume-tailor。

## 不做
不生成简历、不碰浏览器、不上网查用户信息。

## 执行清单（复制到 `applications/_工作区/resume-facts-执行清单_<日期>.md`）
```
- [ ] 0 doctor 全部必需项 OK（缺 pip 包 —— 等用户回复：）
- [ ] 1 目录里的简历与事实类文件列给用户；定默认模板与事实库 —— 等用户回复：
- [ ] 2 init_workspace --dir <工作目录>
- [ ] 3 读简历写事实库（每条带来源）；事实缺口问题 —— 等用户回复：
- [ ] 4 通用口径 8 题（单独一条消息）—— 等用户回复：
- [ ] 5 求职偏好 7 题 —— 等用户回复：（用户自填 → 给字段表，填完校验）
- [ ] 6 个人档案 —— 等用户回复：
- [ ] 7 log.txt
- [ ] 8 指到下一步：有招聘页 → job-screen；有 JD → resume-tailor
```
