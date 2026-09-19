#!/usr/bin/env python3
"""列出 docx 的段落结构，供在现有简历上原地改字前查看。
用法：python3 docx_dump.py 简历.docx [--runs] [--raw]
默认把手机号、邮箱打码（避免联系方式进日志），--raw 才原样显示。
每行：序号 | 样式 | 标记（L=挂有横线图形 T=有制表位 N=有编号/项目符号）| 文字（制表符显示为 ⇥）。"""
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


def dump(path, runs=False, raw=False):
    doc = Document(path); lines = []
    s = doc.sections[0]
    lines.append('页面 %.2fcm x %.2fcm；边距 上%.2f 下%.2f 左%.2f 右%.2f' % (s.page_width.cm, s.page_height.cm, s.top_margin.cm, s.bottom_margin.cm, s.left_margin.cm, s.right_margin.cm))
    for i, p in enumerate(doc.paragraphs):
        txt = p.text.replace('\t', '⇥')[:90]
        lines.append('%3d | %-12s | %-3s | %s' % (i, p.style.name[:12], flags(p), txt if raw else mask(txt)))
        if runs and p.runs: lines.append('      runs: ' + run_fonts(p))
    return '\n'.join(lines)


if __name__ == '__main__':
    print(dump(sys.argv[1], '--runs' in sys.argv, '--raw' in sys.argv))
