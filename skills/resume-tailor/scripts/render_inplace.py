#!/usr/bin/env python3
"""在用户现有 docx 上原地改字：把 resume.md 的内容渲染进一份"标题带横线（drawing）、抬头用制表位、要点用项目符号"的简历模板。
用法：python3 render_inplace.py resume.md 模板.docx 输出.docx
规则：
- 模板里每个"挂有横线图形（dump 标记 L）且有文字"的段落是一个板块标题；resume.md 的 ## 板块按顺序一一对应，数量不等就报错并列出两边。
- 标题之前的段落（姓名、联系方式等）原样保留，resume.md 的 # 姓名和联系行不写入 docx。
- 每个板块的抬头模板 = 该标题之后、下一标题之前第一个带制表位（T）的段落；要点模板 = 第一个带编号/项目符号（N）的段落；找不到就用全文第一个。
- 文字全部替换，字体沿用 docx_helpers 的设定（Times New Roman / 宋体 / 10.5 号）。
先用 docx_dump.py 看模板结构；不符合上面规则的 docx 需要在投递目录另写 render.py。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx import Document
from docx.oxml.ns import qn
from docx_helpers import bullet, entry_header, rebuild_body, set_text
from render_basic import parse


def has_drawing(p):
    pp = p._p
    return pp.find('.//' + qn('w:drawing')) is not None or any(e.tag.endswith('}AlternateContent') for e in pp.iter())


def has_tabs(p):
    ppr = p._p.pPr
    return ppr is not None and ppr.find(qn('w:tabs')) is not None


def has_num(p):
    ppr = p._p.pPr
    return ppr is not None and ppr.find(qn('w:numPr')) is not None


def render(md_text, template_path, out_path):
    d = parse(md_text)
    doc = Document(template_path)
    P = list(doc.paragraphs)
    titles = [i for i, p in enumerate(P) if has_drawing(p) and p.text.strip()]
    if len(titles) != len(d['sections']):
        raise SystemExit('板块数不一致：docx 标题 %s；resume.md 板块 %s' % ([P[i].text.strip() for i in titles], [s['title'] for s in d['sections']]))
    g_hdr = next((p for p in P if has_tabs(p)), None)
    g_bul = next((p for p in P if has_num(p) and not has_drawing(p)), None)
    order = [P[i] for i in range(titles[0])]          # 标题前的抬头段原样保留
    for k, (ti, sec) in enumerate(zip(titles, d['sections'])):
        end = titles[k + 1] if k + 1 < len(titles) else len(P)
        seg = P[ti + 1:end]
        hdr = next((p for p in seg if has_tabs(p)), g_hdr)
        bul = next((p for p in seg if has_num(p) and not has_drawing(p)), g_bul)
        order.append(set_text(P[ti], sec['title'], bold=True))
        for e in sec['entries']:
            if e['org'] or e['role'] or e['date']:
                if hdr is None: raise SystemExit('模板里没有带制表位的抬头段')
                order.append(entry_header(hdr, e['org'], e['role'], e['date']))
            for b in e['bullets']:
                if bul is None: raise SystemExit('模板里没有带项目符号的要点段')
                order.append(bullet(bul, b))
    rebuild_body(doc, order)
    doc.save(out_path)
    return out_path


if __name__ == '__main__':
    render(open(sys.argv[1], encoding='utf-8').read(), sys.argv[2], sys.argv[3])
    print('saved', sys.argv[3])
