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

## 工具位置
浏览器脚本在本 skill 的 `scripts/browser/`：`list_tabs.sh`（列出标签页给用户选）、`claim_tab.sh <窗口号> <标签号>`（认领：往页面写运行 ID，输出 ID 与 URL，之后一律 `TAB_MARK=<ID>`）、`open_tab.sh <URL>`（我们自己新开并认领第二个标签页）、`chrome_exec.sh`（按 TAB_MARK 或 TAB_MATCH 找标签页执行 JS）、`run_stage.sh`、`read_urls.sh`（按列表逐个读页面，带间隔与 guard）、`guard.js`、`probe.js`、`read_page.js`、`lib_antd3.js`。前提：macOS + Google Chrome，菜单栏 显示→开发者→勾选"允许 Apple 事件中的 JavaScript"。
