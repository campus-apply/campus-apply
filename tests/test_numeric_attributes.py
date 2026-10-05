# -*- coding: utf-8 -*-
"""页面上的数字属性是字符串，不保证是数字。

真实表单里见过 `maxlength="Infinity"` 这种写法：浏览器按"没有上限"对待，而 `int("Infinity")`
直接抛 ValueError。一处没兜底，整条命令就退出——而它恰好是生成计划骨架的那条命令，塌了之后
模型只能手工搓一份一百多字段的计划，正是这套工具要消灭的事。

同一类问题有两个方向：读页面属性（可能是任何字符串），和读计划里的数字（模型可能写错类型）。
两边都要"取不出数字就当没给"，不能让整条命令死掉。
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CDP = HERE.parent / 'skills/campus-apply/scripts/browser/chrome_cdp.py'


def run(*args, env=None):
    e = dict(os.environ)
    e.pop('TAB_MARK', None)
    e.pop('TAB_MATCH', None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(CDP), *args],
                          capture_output=True, text=True, env=e, timeout=60)


def code():
    text = CDP.read_text(encoding='utf-8')
    text = re.sub(r'""".*?"""', '""""""', text, flags=re.DOTALL)
    return '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))


def test_page_attributes_are_never_converted_with_a_bare_int():
    """从页面读来的值不能直接 int()：真实站点的 maxlength 可能写成 Infinity。"""
    assert "int(f['maxlength'])" not in code(), \
        '直接 int(页面属性) 会在 maxlength="Infinity" 这类写法上整条命令崩'


def test_there_is_a_single_helper_for_reading_numbers():
    """一处兜底不够——读页面属性和读计划里的数字都要走同一个口子。"""
    assert 'def as_limit' in code(), '要有一个统一的"取不出数字就返回 None"的函数'


def test_a_plan_with_a_junk_max_still_runs(tmp_path):
    """计划里 max 写成非数字时，当作没给上限，不要让整页填写失败。"""
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'fields': [
        {'key': 'x', 'label': '自我描述', 'selector': '#x', 'kind': 'text',
         'value': '测试', 'max': 'Infinity'},
    ]}, ensure_ascii=False), encoding='utf-8')
    r = run('fill', str(plan), env={'TAB_MARK': 'nope'})
    # 找不到标签页是预期的（这里没有浏览器）；要的是它没有因为 max 的类型先崩
    assert 'ValueError' not in r.stderr and 'Traceback' not in r.stderr, \
        '计划里的 max 是脏值时不该抛异常：' + r.stderr[-400:]


def test_a_plan_with_junk_index_still_runs(tmp_path):
    """同理：index / occurrence / nth 是模型写的，也可能是脏值。"""
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'fields': [
        {'key': 'x', 'label': '姓名', 'selector': '#x', 'kind': 'text',
         'value': '甲', 'index': '一'},
    ]}, ensure_ascii=False), encoding='utf-8')
    r = run('fill', str(plan), env={'TAB_MARK': 'nope'})
    assert 'ValueError' not in r.stderr and 'Traceback' not in r.stderr, \
        '计划里的 index 是脏值时不该抛异常：' + r.stderr[-400:]
