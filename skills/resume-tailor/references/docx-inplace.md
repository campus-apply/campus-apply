# 在用户现有 docx 上原地改字

目标：保留用户简历的页面、字体、标题横线、项目符号、制表位，只换文字和段落顺序。工具在 `scripts/docx_helpers.py`，先用 `scripts/docx_dump.py` 看结构。

## 流程
1. 把用户的 docx 复制到投递目录（不动原件）。
2. `python3 docx_dump.py 复制件.docx --runs`：记下每个板块标题段（标记含 L 的是带横线的标题）、一个抬头段（标记 T 或文字里有 ⇥ 的）、一个要点段（标记 N）的序号，作为模板段。
3. 在投递目录写 `render.py`：`Document(复制件)` → 用 `entry_header(模板抬头, 机构, 职位, 日期)`、`bullet(模板要点, 文字)` 造新段，`set_text(标题段, 新标题, bold=True)` 改标题（会自动保住横线）→ `rebuild_body(doc, 顺序列表)` → `doc.save(out)`。
4. `export_pdf_via_word(out, pdf)` + `pdf_pages(pdf)` 核页数；`pdftoppm -png -r 60 pdf 前缀` 出图看一眼版面。超页就逐条压缩文字，不改字号和边距。

## 已知的坑
- 标题横线是挂在某个段落上的 drawing run；`clear_runs` 会把它一起删掉，所以改标题文字必须用 `set_text`（先取走 drawing run，写完文字再放回，且要放在 pPr 之后，放段尾会多出一行空白）。
- 横线有时挂在标题的前一段（原作者手工排版的结果）；用 `take_drawing_runs(前一段)` + `give_drawing_runs(标题段, runs)` 挪回来。
- 抬头"机构 职位 日期"用制表位对齐（`set_tabs`：左 6000 / 右 10585 twips 适用于 A4、左边距 1.27cm、右边距 1.09cm；其他版式先看 dump 的页面行再算），不要用空格凑。
- 新 run 统一 `ascii/hAnsi/cs = Times New Roman`、`eastAsia = 宋体`、`hint = eastAsia`、10.5 号；否则中文引号会变西文字形。
- 中英文之间不加空格；docx 里"08/2025-今"这类日期照用户原来的写法。
- Word 导 PDF 用 osascript：`open (POSIX file p)` 后要 `set d to active document`（Word 的 open 不返回文档对象，`set d to open …` 会报“变量 d 没有定义”）。没有 Word 时跳过页数核对，明确告诉用户"未核页数"。
- 压页顺序：先合并短行（语言+爱好一行）、再删要点里的修饰词、最后才考虑删要点；每轮只改两三处，重新导 PDF 看页数，一页里最后一行空出一点余量。
- python-docx 不认 `w:AlternateContent` 里的图形，dump 的 L 标记已经把这种情况算进去。
- dump 会原样打印联系方式那一行；日志和站点笔记里别抄。
