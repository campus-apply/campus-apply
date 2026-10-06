---
name: apply-fill
description: "Use when an application form or online resume page is open in the dedicated browser and the user wants it filled from their tailored resume; triggers: 填网申 / 帮我填表 / 陪我投 / 这页怎么填 / fill the application。"
---

# apply-fill：陪跑式填网申

## 前提
投递目录已有 `resume.md` 和简历 PDF；没有不开始，先走 resume-tailor。使用专用浏览器，只操作认领标签页。

## 不可逆的几条
- 最终提交、投递、确认投递永远由用户点；保存草稿、暂存默认交用户。
- 不填、不读、不记录证件号、密码、验证码、银行卡号；用户已填的也只看有值/长度。验证码交用户。
- `valueUnknown` 不等于空；先确认当前值来源，再决定补填，不擅自清空或覆盖。
- 刷新/导航前先确认已保存并留底；保存后刷新逐字段比对，通过前不算完成。
- 自述只用 resume-tailor 四步产出、用户审阅的 `form.md`；简历自评、旧网申、解析件不直接搬。
- 简历附件默认代传，成绩单、证件照等其他材料问用户要文件；不猜材料、不批量投递。
- 两次写入无效、验证码、跳登录或非本操作触发的弹窗：说明现状，停下交接。

## 工作方式
**探完再填**针对当前已显露的字段：观察 → 集中确认目标 → 执行并回读；真实填写出现新字段/节点变化，回到观察，增量补计划。已有内容可按已授权目标补填，探测不试选假值、不清空恢复。

代码给候选、属性、位置和操作结果；**我判断哪个是字段、面板、选项及显示值**。看不清、报告与画面矛盾时主动截图，不等用户提醒；精确值仍从 DOM/文件读取。歧义可在计划中指定当前节点，工具不能表达的特殊控件可现场处理，保留来源与回读。

## 按需读取
- 执行清单与每页循环：`references/checklist.md`、`references/page-loop.md`
- 页面取证、截图、未知状态：`references/on-site-principles.md`
- 控件操作与失败处理：`references/controls.md`、`references/control-failure.md`
- 上传/解析、用户选择、保存/提交：`references/upload-and-parse.md`、`references/collect-table.md`、`references/save-and-submit.md`
- 工具参数与报告：`../campus-apply/references/browser-tools.md`
