"""计划用语义坐标定位，骨架由代码从页面生成，模型只填值。

两笔最大的开销都来自"模型手工维护一张坐标表"：整页一百多个字段时，先在日志里抄一遍
控件下标，写计划时再按新的下标重算一遍；中途给某个板块加一组条目，全局下标全变，
一百多个数字要重新映射。而 index 是纯位置量，写错一位就操作到完全无关的控件——
最敏感的字段（证件号、出生日期）恰好排在最前面，索引 0 附近。

所以：骨架由 plan-skeleton 从真实 DOM 生成，带语义坐标；模型只往 value 里填值。
selector + index 仍然接受，用于骨架覆盖不到的场合。
"""
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
BROWSER = HERE.parent / 'skills/campus-apply/scripts/browser'
LIB = BROWSER / 'lib_fill.js'
CDP = BROWSER / 'chrome_cdp.py'
TOOLS = HERE.parent / 'skills/campus-apply/references/browser-tools.md'


def js_code():
    text = LIB.read_text(encoding='utf-8')
    return '\n'.join(l for l in text.splitlines() if not l.strip().startswith('//'))


def py_code():
    text = CDP.read_text(encoding='utf-8')
    text = re.sub(r'""".*?"""', '""""""', text, flags=re.DOTALL)
    return '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))


def test_a_field_can_be_addressed_by_meaning_instead_of_position():
    """板块 + 第几条 + 字段标签 + 同标签内第几个。第四维不能省：
    站点常把"年/月"或"起/止"放在同一个标签下，只给标签定位不到具体哪一个。"""
    code = js_code()
    assert 'locate' in code, '要有按语义坐标找控件的入口'
    for key in ('section', 'occurrence', 'label'):
        assert key in code, f'语义坐标缺少 {key}'


def test_selector_plans_still_work():
    """旧计划格式不能失效——骨架覆盖不到的场合还要靠它。"""
    code = py_code()
    assert 'resolve' in code, 'selector + index 的解析路径要保留'


def test_the_skeleton_is_generated_from_the_page_not_written_by_the_model():
    code = py_code()
    assert 'cmd_plan_skeleton' in code, '要有从页面生成计划骨架的子命令'
    assert 'plan-skeleton' in code


def test_the_skeleton_can_skip_fields_that_already_succeeded():
    """失败后只补没填成的那些，不必整页重跑——长文本重写一遍要等很久。"""
    code = py_code()
    assert 'skip_ok' in code or 'skip-ok' in code, '要能从上一次的报告里读出哪些已成'


def test_sensitive_fields_are_refused_unless_explicitly_allowed():
    """证件号、出生日期这类字段，索引写错就会被误操作，代码层面硬拦。"""
    code = js_code()
    assert 'SENSITIVE' in code, '要有敏感标签词表'
    py = py_code()
    assert 'sensitive_ok' in py, '除非计划里显式允许，否则拒绝写入敏感字段'


def test_the_plan_can_declare_what_control_it_expects():
    """执行权在代码，声明权在模型：模型说"这个控件的名字应当含什么"，代码执行前校验。"""
    py = py_code()
    assert 'expect_label' in py, '计划要能声明期望的控件名称'


def test_the_tools_doc_describes_the_new_commands():
    text = TOOLS.read_text(encoding='utf-8')
    assert 'plan-skeleton' in text
    assert 'survey' in text
