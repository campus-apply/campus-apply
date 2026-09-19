---
name: resume-tailor
description: 对照一份 JD 产出针对该岗位的简历定稿文字、一页 docx 和网申长文本，没有 JD 时产出通用版底稿。Use when the user has a target job (JD) and wants to tailor their resume or write application-form essays; triggers: 改简历 / 针对这个岗位 / 写网申内容 / tailor resume.
---

# resume-tailor：对照 JD 改简历与网申文本

## 前提
- 当前目录有 `campus-apply.json`（没有先用 resume-facts）。
- 有一份 JD：在 `applications/<公司>-<岗位>/jd.md`（job-screen 建的），或用户现给的文本/链接（先存成 jd.md）。
- 没有 JD 也能走"通用版"：用户要先填某个站点的在线简历 / 候选人档案页，或想要一份不针对岗位的底稿。通用版跳过第 2、3 步，第 4 步以 `campus-apply.json` 里偏好的岗位类型定主线、所有经历按事实库全量写，产物放 `applications/_工作区/resume.md`；站点有自述类字段时第 8 步照走，写一版按偏好岗位类型的通用自述放 `form.md`，标明"通用版，投具体岗位时重写"。先告诉用户这是通用版、和针对岗位的版本有什么区别。

## 步骤
1. 读：`jd.md`、`campus-apply.json` 里列的全部事实库、`rules.json`、`references/style-rules.md`；如果 `applications/` 里有以前的投递，读最近一份 `resume.md` 作为起点。
2. 出"素材对照方案"给用户看，等确认后再写：一张表（JD 要求 → 对应经历 → 证据在事实库哪条）、主案例选谁、板块顺序、删掉哪些经历、哪些 JD 要求事实库覆盖不了。
3. 只问这份 JD 新引出的口径问题（`../resume-facts/references/interview.md` 的"单次投递题库"），一轮最多 5 题，一次问完；答案写回事实库（【用户口述 日期】）或 `jd.md` 末尾"本次口径"。
4. 写 `resume.md`（格式见 `templates/resume.template.md`），遵守 `style-rules.md`；一页篇幅的经验值是要点总数 14–18 条、每条 60–110 字。
5. 检查：`python3 <本skill>/scripts/check_content.py resume.md --rules rules.json --facts <事实库…>`；ERR 必须改到零，WARN 逐条列给用户确认。
6. 渲染：
   - 用户有 docx（`campus-apply.json` 的 `resume_docx`，除非用户说不用）：先复制到投递目录、`docx_dump.py` 看结构；标题带横线（L）、抬头带制表位（T）、要点带项目符号（N）的模板直接 `python3 <本skill>/scripts/render_inplace.py resume.md 复制件.docx 输出.docx`（板块按顺序对应，数量不等会报错）；不符合这种结构的按 `references/docx-inplace.md` 在投递目录另写 `render.py`。然后 `docx_helpers.export_pdf_via_word` 导 PDF、`pdf_pages` 核页数、`pdftoppm -png -r 70` 出图自己看一眼版面；超页就压文字，不动字号边距，通常要压三四轮。成品 docx 和 PDF 放在工作目录根（命名 `简历_<姓名>_<公司><岗位简称>.docx/.pdf`），投递目录只留 `resume.md`、模板副本、预览图和改动清单。把 PDF 路径给用户，并在对话里逐条说明和基准简历相比改了什么：哪几条换了顺序、哪几条改写（改前改后各一句）、新增了什么、删了什么、为了压页删了哪些词；同时把逐段对比存成投递目录 `改动清单_<日期>.md`（用 python difflib 对比两份 docx 的段落文本即可）。
   - 没有 docx：`python3 <本skill>/scripts/render_basic.py resume.md 简历_<姓名>_<公司>.docx`。
7. 如果这站有网申长文本：先让 apply-fill 做入口探测和上传试探（站点会自动解析简历时，先看解析填到了哪里、剩下哪些要写），再按 `templates/form.template.md` 写 `form.md`，字段名以 `fill-log.md` 里的探测结果为准，字数按 `limits.json`（每项可带 min / max / unit，来源是 apply-fill 探测出的页面明文和校验结果，与属性不一致时由用户定过）；与页面无关的内容（岗位要求的自述、证明材料段落）可以先起草给用户过目。写完跑 `check_content.py form.md --limits limits.json`。
8. 自我描述、自我评价、求职信这类替用户说话的自由文本：按 `references/self-statement.md` 的四步走——结构表给用户确认 → 初稿（观点段先要用户口述）→ 按 `references/humanizer.md` 逐条改并写改动总结与评分 → 全文加总结加评分给用户。简历要点和网申经历描述写完也过一遍 `humanizer.md`。不要一上来就写整段。
9. 在工作目录 `log.txt` 追加：日期、岗位、主案例、问过什么、产出文件。

## 不做
不上网查公司；不编事实库没有的数字或经历；不替用户点任何网页。

## 执行清单（复制到 `<投递目录>/resume-tailor-执行清单_<日期>.md`）
```
- [ ] 1 读 jd.md、事实库、rules.json、style-rules、上次 resume.md（通用版：无 JD，跳过 2、3）
- [ ] 2 素材对照方案 —— 等用户回复：
- [ ] 3 口径问题 ≤5 题一次问完（可与 2 合并成一条消息）—— 等用户回复：
- [ ] 4 写 resume.md（要点 14–18 条）
- [ ] 5 check_content：ERR 清零；WARN 列给用户 —— 等用户回复：
- [ ] 6 渲染 docx + PDF；核页数；改动清单；逐条说明改了什么 —— 等用户回复：
- [ ] 7 form.md + limits.json（在 apply-fill 探测与上传试探之后）
- [ ] 8 自述四步：结构表 —— 等用户回复：；观点段口述 —— 等用户回复：；初稿 → humanizer 改稿总结与评分；全文 —— 等用户回复：
- [ ] 9 log.txt
```
