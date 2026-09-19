import importlib.util, os
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..', 'skills', 'resume-tailor', 'scripts', 'docx_helpers.py')
spec = importlib.util.spec_from_file_location('docx_helpers', P); H = importlib.util.module_from_spec(spec); spec.loader.exec_module(H)


def make_doc():
    d = Document(); d.add_paragraph('标题'); d.add_paragraph('抬头 模板'); d.add_paragraph('要点模板'); return d


def test_entry_header_has_two_tabs_and_bold():
    d = make_doc(); p = H.entry_header(d.paragraphs[1], '机构', '职位', '01/2026-04/2026')
    assert p.text == '机构\t职位\t01/2026-04/2026'
    assert all(r.bold for r in p.runs if r.text)
    assert p._p.pPr.find(qn('w:tabs')) is not None


def test_bullet_clones_template_and_sets_font():
    d = make_doc(); p = H.bullet(d.paragraphs[2], '新要点')
    assert p.text == '新要点'
    rf = p.runs[0]._r.rPr.rFonts
    assert rf.get(qn('w:eastAsia')) == '宋体' and rf.get(qn('w:ascii')) == 'Times New Roman'


def test_set_text_keeps_drawing_run():
    d = make_doc(); p = d.paragraphs[0]
    r = OxmlElement('w:r'); r.append(OxmlElement('w:drawing')); p._p.append(r)
    H.set_text(p, '新标题', bold=True)
    assert p.text == '新标题' and p._p.find('.//' + qn('w:drawing')) is not None


def test_rebuild_body_reorders(tmp_path):
    d = make_doc(); ps = d.paragraphs
    H.rebuild_body(d, [ps[2], ps[0]])
    out = tmp_path / 'o.docx'; d.save(out)
    assert [p.text for p in Document(out).paragraphs] == ['要点模板', '标题']
