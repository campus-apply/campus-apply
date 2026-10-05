---
name: job-screen
description: "Use when the user points at a company recruitment site and asks which positions fit, or faces more openings than they can read; triggers: 筛岗位 / 看看哪些岗位适合我 / 这家公司在招什么 / 岗位太多了 / screen jobs。"
---

# job-screen：在公司招聘页上筛岗位

## 不可逆的几条

- **不批量投递，不替用户决定投哪个。** 筛岗只产出分档和理由，圈哪几个岗永远是用户的事。
- **不登录、不碰验证码、不填密码。** 页面要求登录就停下，请用户在认领的那个标签页里自己登。
- **不脱离浏览器调站点接口**：不在浏览器外发请求，不伪造参数，不用页面自己没发过的地址。
- **只信用户看得见的文本。** 隐藏节点和模板占位里的值不算数；页面自己请求返回的 JSON 要先抽几条和
  展开后的可见文本比对一致才算数。
- **数字和结论要有出处**（哪个页面、哪一段原话），没找到就写"未见"而不是猜：猜出来的"能投三个岗"
  会让用户按错的规则投，投错了撤不回来。两处说法不一致的两条都列出来让用户定。
- **不把用户打开的页面当成用户的意向**；只操作我们自己认领的标签页，不复用用户日常浏览器里的页面。

## 交接

收尾时明确说下一步是针对这个岗位改一版简历（resume-tailor），产出是这个岗位专用的 `resume.md` 和简历 PDF；
**填网申要等它跑完**。不要直接跳到填表，也不要承诺"先把志愿页填上、简历一会儿补"。

## 怎么做

- 前提、开场怎么讲清两步走、0 到 10 步的流程 → `references/steps.md`
- 清单与详情怎么读（接口 / 页面函数 / DOM）、节奏与并行、时间预算、预估报哪两个数 → `references/listing-and-details.md`
- 三份产物的格式、排除清单、提问三条件 → `references/screen-output.md`
- 对用户说话的规矩、停顿怎么安排 → `../campus-apply/references/talking-to-the-user.md`
- 出现"接口返回得挺全，抽样比对就免了"这类念头 → `../campus-apply/references/red-flags.md`
- 清单、待决和关联记录更新及交接 → `../campus-apply/references/workflow-state.md`

开工先把 `references/checklist.md` 的清单复制成 `applications/<公司>/job-screen-执行清单_<日期>.md`，做到哪勾到哪。
