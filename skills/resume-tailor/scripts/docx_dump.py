#!/usr/bin/env python3
"""列出 docx 的段落和表格结构，供在现有简历上原地改字前查看。
用法：python3 docx_dump.py 简历.docx [--runs] [--raw]
表格排版的简历（学校模板基本都是）内容全在表格里，段落和表格按文档顺序交错列出。
默认把手机号、邮箱打码（避免联系方式进日志），--raw 才原样显示。
每行：序号 | 样式 | 标记（L=挂有横线图形 T=有制表位 N=有编号/项目符号，表格行标 TBL）| 文字（制表符与单元格分隔显示为 ⇥）。"""
import re, sys
from docx import Document
from docx.oxml.ns import qn

try:
    sys.stdout.reconfigure(encoding='utf-8')  # Windows 终端默认不是 UTF-8，中文会乱码
except AttributeError:
    pass


def flags(p):
    pp = p._p; f = ''
    if pp.find('.//' + qn('w:drawing')) is not None or any(e.tag.endswith('}AlternateContent') for e in pp.iter()): f += 'L'
    ppr = pp.pPr
    if ppr is not None and ppr.find(qn('w:tabs')) is not None: f += 'T'
    if ppr is not None and ppr.find(qn('w:numPr')) is not None: f += 'N'
    return f or '-'


def run_fonts(p):
    out = []
    for r in p.runs:
        rf = r._r.rPr.rFonts if (r._r.rPr is not None and r._r.rPr.rFonts is not None) else None
        a = rf.get(qn('w:ascii')) if rf is not None else '?'
        e = rf.get(qn('w:eastAsia')) if rf is not None else '?'
        out.append(f'{a}/{e}{" B" if r.bold else ""}')
    return ', '.join(out)


MASK = [(re.compile(r'(?<!\d)1\d{10}(?!\d)'), '1**********'), (re.compile(r'[\w.+-]+@[\w-]+(\.[\w-]+)+'), '***@***')]


def mask(t):
    for rx, rep in MASK:
        t = rx.sub(rep, t)
    return t


def row_cells(row):
    """一行里的文字，合并单元格造成的重复去掉——python-docx 会把合并后的格重复返回。"""
    out = []
    for cell in row.cells:
        text = cell.text.strip()
        if text and text not in out:
            out.append(text)
    return out


def dump(path, runs=False, raw=False):
    """按文档顺序把段落和表格都走一遍。

    学校和学院发的简历模板基本是表格排版（整份简历装在一个三十几行的表里，第一列时间、
    第二列内容）。只扫 doc.paragraphs 的话，这类简历只能列出几个空段落——改之前看不到
    现在写了什么，原地改字也无从下手。
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(path); lines = []
    s = doc.sections[0]
    lines.append('页面 %.2fcm x %.2fcm；边距 上%.2f 下%.2f 左%.2f 右%.2f' % (s.page_width.cm, s.page_height.cm, s.top_margin.cm, s.bottom_margin.cm, s.left_margin.cm, s.right_margin.cm))
    i = 0
    for child in doc.element.body.iterchildren():
        tag = child.tag.split('}')[-1]
        if tag == 'p':
            para = Paragraph(child, doc)
            txt = para.text.replace('\t', '⇥')[:90]
            lines.append('%3d | %-12s | %-3s | %s' % (i, para.style.name[:12], flags(para), txt if raw else mask(txt)))
            if runs and para.runs: lines.append('      runs: ' + run_fonts(para))
            i += 1
        elif tag == 'tbl':
            table = Table(child, doc)
            lines.append('    + 表格 %d 行 x %d 列' % (len(table.rows), len(table.columns)))
            for r, row in enumerate(table.rows):
                cells = row_cells(row)
                if not cells:
                    continue
                txt = ' ⇥ '.join(cells)[:90]
                lines.append('%3d | 表格 r%-7d | TBL | %s' % (i, r, txt if raw else mask(txt)))
                i += 1
    return '\n'.join(lines)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument('docx'); ap.add_argument('--runs', action='store_true'); ap.add_argument('--raw', action='store_true')
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    a = ap.parse_args()
    print(dump(a.docx, a.runs, a.raw))
