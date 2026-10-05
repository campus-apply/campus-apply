# -*- coding: utf-8 -*-
"""探测要一次探完整页，不能探一部分填一部分。

实测表现：填到语言水平那一栏才点开看选项、选了 CET-6 却不填分数就转去填别的板块、
最后语言和证书都没填全。根因是循环里没规定"探测必须一次做完"，于是条件字段
（选了英语才出现的"语言考试""考试分数"）在第一轮探测时根本不在页面上，必然要回头补。

正常人的做法是：上传简历，把所有条目组先点满，所有下拉先看一遍选项，然后一次问完、一次填完。
这里把那个顺序定成可检查的规矩。
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SKILL = ROOT / 'skills/apply-fill/SKILL.md'
PRINCIPLES = ROOT / 'skills/apply-fill/references/on-site-principles.md'
COLLECT = ROOT / 'skills/apply-fill/references/collect-table.md'
CDP = ROOT / 'skills/campus-apply/scripts/browser/chrome_cdp.py'
TOOLS = ROOT / 'skills/campus-apply/references/browser-tools.md'


def test_probing_must_finish_before_any_field_is_written():
    """一句硬规矩：写入任何字段之前，这一页的探测必须已经做完。"""
    text = SKILL.read_text(encoding='utf-8')
    assert '探完再填' in text, 'SKILL.md 要把"探完再填"写成这一页的硬顺序'


def test_repeated_record_groups_are_added_before_probing():
    """条目组要先点满再探：加一组会让后面所有字段的位置变，也会带出新的条件字段。"""
    text = PRINCIPLES.read_text(encoding='utf-8')
    assert '先点满' in text, '所有要加的条目组必须在探测阶段一次加到位'


def test_conditional_fields_are_triggered_during_probing():
    """选了某个值才出现的字段，要在探测阶段触发出来，不能等填完才发现。"""
    text = PRINCIPLES.read_text(encoding='utf-8')
    assert '条件字段' in text and '触发' in text, \
        '探测阶段要主动触发条件字段（选一个值看页面多出什么，再恢复）'


def test_filling_phase_may_not_probe():
    """填写阶段不许再探测——探到的不够就是探测没做完，回上一阶段。"""
    text = SKILL.read_text(encoding='utf-8')
    assert '填写阶段不再探测' in text, '要明确禁止边填边探'


def test_everything_the_user_decides_is_asked_once_before_writing():
    """所有要用户定的事一次问完，而且在写入任何字段之前。"""
    text = COLLECT.read_text(encoding='utf-8')
    assert '写入任何字段之前' in text, 'collect-table 要规定提问的时点，不只是"批成一次"'


def test_probe_options_reports_fields_that_appeared():
    """probe-options 开关下拉时，要顺带记下选了这个值之后页面多了哪些字段。"""
    text = CDP.read_text(encoding='utf-8')
    assert 'revealed' in text, 'probe-options 要报出被触发出来的新字段'


def test_tools_doc_explains_the_probe_then_fill_order():
    text = TOOLS.read_text(encoding='utf-8')
    assert '探完再填' in text, 'browser-tools 要说明这三条命令的使用顺序'
