import importlib.util, os
from docx import Document
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..', 'skills', 'resume-tailor', 'scripts', 'render_basic.py')
spec = importlib.util.spec_from_file_location('render_basic', P); R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)

MD = """# 张三
电话 | 邮箱 | 北京

## 教育背景
### 某大学 | 硕士，金融学 | 08/2025-06/2027
- 主修课程

## 实习经历
### 某公司 | 产品实习生 | 05/2026-09/2026
- 做了一件事
- 做了另一件事
"""


def test_parse_sections():
    doc = R.parse(MD)
    assert doc['name'] == '张三' and doc['contact'] == '电话 | 邮箱 | 北京'
    assert [s['title'] for s in doc['sections']] == ['教育背景', '实习经历']
    assert doc['sections'][1]['entries'][0]['bullets'] == ['做了一件事', '做了另一件事']


def test_render_writes_docx_with_headings_and_bullets(tmp_path):
    out = tmp_path / 'r.docx'; R.render(MD, str(out))
    texts = [p.text for p in Document(out).paragraphs]
    assert '张三' in texts[0] and '教育背景' in texts and any('某公司' in t and '\t' in t for t in texts)
    assert sum(1 for t in texts if t.startswith('•')) == 3
