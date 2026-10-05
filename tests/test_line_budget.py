# -*- coding: utf-8 -*-
"""改简历要先知道版面还剩多少，不能写完才发现超页。

现在的流程是：读素材 → 出方案 → 写定稿 → 改 docx → 导 PDF 核页数 → 超页回头删 → 再核。
页数是最后才知道的，超了就要来回几轮。用户给的思路是反过来——先从已经确认是一页的那份简历
量出版面预算，按板块分配行数，写的时候每段就知道自己有几行可用。

压缩也要有优先级，不能每次重新判断删哪里：每段第一行（身份、机构、时间）不可删，
正文至少留一行，其余都可砍。
"""
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BUDGET = HERE.parent / 'skills/resume-tailor/scripts/line_budget.py'


def run(*args):
    return subprocess.run([sys.executable, str(BUDGET), *args],
                          capture_output=True, text=True, timeout=60)


def make_docx(path):
    """造一份两板块的简历，用真实简历的那套标记：

    板块标题挂下边框、条目首行带制表位、正文用 List Paragraph 样式。
    这三样正好对应"板块 / 不可删的首行 / 可砍的正文"。
    """
    from docx import Document

    def section(doc, name):
        para = doc.add_paragraph(name)
        # 挂一条下边框，和真实简历的板块标题一样
        pr = para._p.get_or_add_pPr()
        borders = pr.makeelement(
            '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pBdr', {})
        bottom = pr.makeelement(
            '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}bottom',
            {'{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val': 'single'})
        borders.append(bottom)
        pr.append(borders)
        return para

    doc = Document()
    doc.add_paragraph('某某')
    section(doc, '教育背景')
    doc.add_paragraph('某某大学\t金融学硕士\t2025.08-2027.06')
    doc.add_paragraph('主修课程：公司金融、资产定价', style='List Paragraph')
    section(doc, '实习经历')
    doc.add_paragraph('某公司\t产品实习生\t2026.05-2026.09')
    doc.add_paragraph('负责一条产品线的需求拆解与方案落地', style='List Paragraph')
    doc.add_paragraph('推动三个功能上线，覆盖两万名用户', style='List Paragraph')
    doc.save(str(path))
    return path


def test_budget_script_exists():
    assert BUDGET.is_file(), '要有一条命令量出版面预算'


def test_it_counts_lines_per_section(tmp_path):
    """按板块报出各占几行——这是分配预算的依据。"""
    docx = make_docx(tmp_path / 'r.docx')
    out = tmp_path / 'budget.json'
    r = run(str(docx), str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    names = [s['name'] for s in data['sections']]
    assert '教育背景' in names and '实习经历' in names, '板块没认出来：' + str(names)
    edu = next(s for s in data['sections'] if s['name'] == '教育背景')
    assert edu['lines'] >= 2, '板块行数要算上标题和内容'


def test_it_reports_the_total_capacity(tmp_path):
    """总量要报出来：这份已经确认是一页，它用了多少行就是一页的容量。"""
    docx = make_docx(tmp_path / 'r.docx')
    out = tmp_path / 'budget.json'
    run(str(docx), str(out))
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['total_lines'] >= 8
    assert data['total_lines'] == sum(s['lines'] for s in data['sections']) + data['other_lines']


def test_each_entry_marks_which_lines_cannot_be_cut(tmp_path):
    """压缩优先级要在数据里：每个条目的第一行不可删，正文至少留一行。"""
    docx = make_docx(tmp_path / 'r.docx')
    out = tmp_path / 'budget.json'
    run(str(docx), str(out))
    data = json.loads(out.read_text(encoding='utf-8'))
    intern = next(s for s in data['sections'] if s['name'] == '实习经历')
    entry = intern['entries'][0]
    assert entry['keep_lines'] >= 2, '第一行加至少一行正文不可删'
    assert entry['cuttable_lines'] >= 1, '多出来的正文行是可砍的'


def test_it_says_how_many_lines_are_left_for_a_target(tmp_path):
    """给定一个目标板块分配，要能算出还剩几行可用。"""
    docx = make_docx(tmp_path / 'r.docx')
    out = tmp_path / 'budget.json'
    r = run(str(docx), str(out))
    assert '行' in r.stdout, '摘要里要把行数报给人看'
    assert '不可删' in r.stdout or '可砍' in r.stdout, '摘要要讲清压缩优先级'
