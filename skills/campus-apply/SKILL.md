---
name: campus-apply
description: "Use when the user brings up job hunting without naming a specific step, or when you need to tell where a campus-apply workspace stands and what comes next; triggers: 求职 / 投简历 / 校招 / 网申 / 下一步做什么 / job hunting."
---

# campus-apply：入口与路线

只做一件事：看清现状，指到下一个 skill。四个功能 skill 都能单独用。
名词约定：岗位描述统一叫 JD；`launch` 起的那个浏览器叫专用浏览器。

## 不可逆的几条（所有 skill 共用）

- **四步有先后：事实库 → 筛岗 → 改简历 → 填网申，改简历没做完不开始填表。**
  先填志愿页、简历一会儿补，等于拿没改过的简历占掉这家公司的名额，投出去撤不回。
- **不点最终提交、投递、确认投递**，永远由用户点；不碰验证码。
- **证件号、密码、验证码、银行卡号这类字段不填、不读、不写进任何文件**：
  探测和回读脚本遇到它们只记"有值 / 长度"，用户自己填过的也不抄。
- **只信用户看得见的文本，数字和结论要有出处。** 隐藏节点、前端模板占位都不算数；
  找不到就写"未见"而不是猜——猜出来的规则会让用户按错的方式投。
- **自述类文本**（自我描述、自我评价、个人简介、求职动机、个人陈述）**只能由 resume-tailor
  的自述流程产出**，不搬简历上的一句话自评、不搬旧网申、不搬站点解析件；
  用户坚持沿用旧文本时先说明区别再照办并记录。替用户说出去的话收不回来。
- **不脱离浏览器调站点接口**：不在浏览器外发请求，不伪造参数，不用页面自己没发过的地址。
  例外与可做的事见 `references/routing.md`。
- **简历附件默认由 agent 代传**（用户可以说自己传），**其余材料问用户要文件**——
  猜错了传的是用户的真实材料。一次一岗，不批量投递。
- **不主动找公司、不替用户挑公司，不替用户决定投哪个。**
- 每个"给用户看、等用户说"的停顿不许跳过；需要用户操作的步骤（登录、上传、验证码、提交）
  显式列出并等待。只操作我们认领的标签页，不复用用户自己打开的页面。

## 怎么做

- 当前目录怎么判、路由到哪个 skill、共用的执行约定与工具位置 → `references/routing.md`
- 对用户怎么说、停顿怎么安排、"依据"是什么 → `references/talking-to-the-user.md`
- 出现"这个站简单，不用建清单了"这类念头 → `references/red-flags.md`
- 执行清单怎么建、怎么勾 → `references/checklists.md`
- 状态更新、资料复用与交接 → `references/workflow-state.md`
- 第一次在这台机器上用（探 Python、跑 doctor）→ `references/first-run.md`
- 浏览器工具用法与常见报错 → `references/browser-tools.md`
