#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量出一份简历的版面预算：一页能放多少行、每个板块占了几行、哪些行不能删。

用法：
  python3 line_budget.py <基准简历.docx> [预算.json] [--width-chars N]

为什么要先量再写：原来的做法是写完定稿、改进 docx、导 PDF 核页数，超页了回头删、删完再核，
可能来回几轮——页数是最后才知道的。拿一份**已经确认是一页**的简历当标尺，先知道版面有多少行、
各板块历史上占几行，写的时候每段就带着行数上限，不会写完才发现超了。

按纸张高度除行高算出来的是理论值，真实 docx 有段间距、制表位、项目符号缩进，理论值和实际差得远。
所以这里不算理论值，只量既有版面。

压缩优先级也在输出里：每个条目的第一行（机构、身份、时间那一行）不可删，正文至少留一行，
其余是可砍的。超页时按这个顺序砍，不用每次重新判断删哪里。
"""
import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# 一行大致放多少个中文字符。默认值按常见的一页版简历（宋体 10.5 号、左右边距各约 1.2cm）量得，
# 版面不同就用 --width-chars 改。英文和数字按半个字算。
DEFAULT_WIDTH = 46


def visual_width(text):
    """中文算 1，英文数字标点算 0.5——折行估算用。"""
    total = 0.0
    for ch in text:
        total += 1.0 if ord(ch) > 0x2E80 else 0.5
    return total


def wrapped_lines(text, width):
    """这段文字实际占几行。空段落占一行（它在版面上也占位置）。"""
    if not text.strip():
        return 1
    return max(1, int(visual_width(text) / width) + (1 if visual_width(text) % width else 0))


def analyse(path, width):
    from docx import Document
    from docx.shared import Pt
    doc = Document(path)

    def marks(para):
        xml = para._p.xml
        return ('L' if 'w:pict' in xml or 'bottom' in xml else '',
                'T' if '<w:tab/>' in xml or '\t' in para.text else '',
                'N' if para.style.name.startswith('List') else '')

    sections, other = [], 0
    current = None
    for para in doc.paragraphs:
        text = para.text
        lines = wrapped_lines(text, width)
        has_rule, has_tab, is_list = marks(para)
        # 板块标题：挂横线、短、不带制表位
        if has_rule and text.strip() and not has_tab and visual_width(text) <= 12:
            current = dict(name=text.strip(), lines=lines, entries=[])
            sections.append(current)
            continue
        if current is None:
            other += lines
            continue
        current['lines'] += lines
        if has_tab:
            # 条目首行：机构、身份、时间。这一行不能删
            current['entries'].append(dict(head=text.strip()[:40], head_lines=lines,
                                           body_lines=0, bodies=[]))
        elif current['entries']:
            entry = current['entries'][-1]
            entry['body_lines'] += lines
            entry['bodies'].append(dict(lines=lines, chars=int(visual_width(text))))
        else:
            # 板块标题之后、第一个条目之前的行（少见）
            current['lines'] += 0

    for section in sections:
        for entry in section['entries']:
            # 第一行加至少一行正文不可删，其余可砍
            first_body = entry['bodies'][0]['lines'] if entry['bodies'] else 0
            entry['keep_lines'] = entry['head_lines'] + first_body
            entry['cuttable_lines'] = max(0, entry['body_lines'] - first_body)

    total = sum(s['lines'] for s in sections) + other
    return dict(source=os.path.basename(path), width_chars=width,
                total_lines=total, other_lines=other, sections=sections)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('docx', help='一份已经确认是一页的简历，当版面标尺')
    parser.add_argument('out', nargs='?', help='预算写到哪（给 JSON 路径）')
    parser.add_argument('--width-chars', type=int, default=DEFAULT_WIDTH,
                        help='一行大致放多少个中文字（默认 %d）' % DEFAULT_WIDTH)
    args = parser.parse_args(argv)

    if not os.path.isfile(args.docx):
        print('ERR_NO_FILE ' + args.docx)
        return 2
    try:
        data = analyse(args.docx, args.width_chars)
    except ImportError:
        print('ERR_DEP: 要装 python-docx（pip install python-docx）')
        return 2
    except Exception as e:                                   # docx 读坏了
        print('ERR_DOCX: 读不出这份 docx：%s' % e)
        return 2

    if args.out:
        try:
            with open(args.out, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except OSError as e:
            print('ERR_WRITE %s：%s' % (args.out, e.strerror or e))
            return 1

    print('版面总计 %d 行（按一行 %d 个中文字估折行）'
          % (data['total_lines'], data['width_chars']))
    if data['other_lines']:
        print('抬头（姓名、学校、联系方式等）占 %d 行' % data['other_lines'])
    keep = cut = 0
    for section in data['sections']:
        heads = len(section['entries'])
        k = sum(e['keep_lines'] for e in section['entries'])
        c = sum(e['cuttable_lines'] for e in section['entries'])
        keep += k
        cut += c
        print('%s\t%d 行\t%d 个条目\t不可删 %d 行\t可砍 %d 行'
              % (section['name'], section['lines'], heads, k, c))
    print('---')
    print('不可删合计 %d 行（每个条目的首行加一行正文），可砍 %d 行' % (keep, cut))
    print('写之前按这张表给每个板块分配行数；超页就从"可砍"里砍，'
          '条目首行和每条的第一行正文不动')
    if args.out:
        print('明细 → ' + args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
