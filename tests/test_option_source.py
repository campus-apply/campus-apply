"""选项的来源要能查，不能凭印象写；选项本身按结构找，不按 class 列举。

三件事同源，都来自 2026-10-05 在一个真实站点上的实测：

1. 选项节点可能既没有 class 也没有 role（年份是 div 带自家 class、月份是裸 span）。
   按 class/role 列举时命中 0 个，于是"面板里没有这一项"，而面板里明明写着那几个字。
   面板那一层已经为同样的理由推翻过按 class 列举，选项层当时没跟着改。

2. 点一下普通文本框，不该算"开出了一个面板"。真实点击必然让包装容器加聚焦态 class，
   而把它当成面板的后果是整页归零：它收不掉，脏账还留在账本里，之后每条命令都报 ERR_PANELS。

3. 探测一失败，模型就会退回"按常识编一个值"。所以面板类字段的值必须有来源，
   而且要在**点开任何面板之前**就拦下来——否则报出来的是"面板里没有这一项"，
   读着像站点的毛病，而真问题是这个值没有来源。
"""
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BROWSER = HERE.parent / 'skills/campus-apply/scripts/browser'
LIB = BROWSER / 'lib_fill.js'
CDP = BROWSER / 'chrome_cdp.py'
FIXTURE = HERE.parent / 'evals/fixtures/option_shapes.html'
CHECK = HERE.parent / 'evals/option_shapes_check.py'


def js_code():
    text = LIB.read_text(encoding='utf-8')
    return '\n'.join(l for l in text.splitlines() if not l.strip().startswith('//'))


def py_code():
    text = CDP.read_text(encoding='utf-8')
    text = re.sub(r'""".*?"""', '""""""', text, flags=re.DOTALL)
    return '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))


# ---- 1. 选项按结构找，不按 class 列举 ----

def test_options_are_found_by_structure_not_by_class_list():
    code = js_code()
    assert 'optionLeaves' in code, '要有一个按结构找选项的函数'
    # 判据是"叶子 + 有文字 + 可见"，不是命中某张 class 清单
    leaf_fn = code[code.index('const optionLeaves'):]
    leaf_fn = leaf_fn[:leaf_fn.index('\n  };')]
    assert 'children.length' in leaf_fn, '要按"没有子元素"认叶子'
    assert 'textContent' in leaf_fn, '要求选项有文字'
    assert 'visible(' in leaf_fn, '要求选项可见'


def test_option_class_list_only_sorts_and_never_eliminates():
    code = js_code()
    assert 'OPTION_SEL' not in code, '淘汰式的 OPTION_SEL 不该再存在'
    assert 'OPTION_HINT' in code, 'class 清单降级成排序提示，名字也要跟着改'
    # 排序提示只能出现在排序和打分里，不能出现在 querySelectorAll 的过滤位置
    for line in code.splitlines():
        if 'OPTION_HINT' in line and 'const OPTION_HINT' not in line:
            assert 'querySelectorAll' not in line, \
                '排序提示不该拿去 querySelectorAll 过滤选项：' + line.strip()


def test_options_in_and_option_both_go_through_the_leaf_finder():
    code = js_code()
    for name in ('optionsIn(panelHandle)', 'option(panelHandle, text, exact)'):
        body = code[code.index(name):]
        body = body[:body.index('\n    },')]
        assert 'optionLeaves(' in body, name + ' 要走按结构找选项那条路'


# ---- 2. 聚焦态不是面板 ----

def test_attribute_change_counts_as_appearing_only_if_it_became_visible():
    code = js_code()
    take = code[code.index('const watchTake'):]
    take = take[:take.index('\n  };')]
    assert 'wasVisible' in take, '要和"点击前可不可见"那份快照比'
    assert '!wasVisible.has(' in take, '只有点击前不可见的才算显形'


def test_visibility_snapshot_is_taken_before_the_click_not_in_the_callback():
    """回调跑的时候属性已经改完了，那时读 visible() 读到的是变化之后的状态。"""
    code = js_code()
    start = code[code.index('const watchStart'):]
    start = start[:start.index('\n  };')]
    assert 'querySelectorAll' in start and 'wasVisible.add' in start, \
        '开始观察时就要把全页可见性记一份快照'
    callback = start[start.index('new MutationObserver'):]
    assert 'wasVisible.add' not in callback, \
        '不能在 MutationObserver 回调里判可见性：那时属性已经改完了'


def test_the_clicked_controls_own_tree_is_never_a_panel():
    code = js_code()
    body = code[code.index('appeared(anchorHandle)'):]
    body = body[:body.index('\n    },')]
    assert 'contains(anchor)' in body and 'anchor.contains(' in body, \
        '候选是被点控件自己那棵树时要排除掉'


def test_note_open_refuses_to_record_the_controls_own_wrapper():
    """一次误判进了账本就再也销不掉：控件自身永远 isConnected 且 visible。"""
    code = js_code()
    body = code[code.index('noteOpen(fieldHandle, panelHandle)'):]
    body = body[:body.index('\n    },')]
    assert 'return false' in body, '记不了要明确返回 false，不能假装记上了'
    assert 'contains(field)' in body or 'field.contains(' in body, \
        '记账之前要再过一遍血缘'


# ---- 3. 面板类字段的值必须有来源 ----

def test_fill_refuses_panel_fields_whose_value_has_no_source():
    code = py_code()
    assert 'options_unverified' in code, '要有一个显式绕过的开关'
    assert '没有来源' in code, '拦下来的时候要说清是来源问题'


def test_the_source_gate_runs_before_anything_touches_the_page():
    """报错必须发生在点开面板之前，否则读起来像站点的毛病。"""
    code = py_code()
    gate = code.index('没有来源')
    # 门禁要在 _with_claimed_tab 之前——也就是在拿到标签页、注入库之前
    body = code[:gate]
    assert body.rindex('def cmd_fill') < gate, '门禁要在 cmd_fill 里'
    after = code[gate:code.index('def ', gate + 10)]
    assert 'return 2' in after, '来源不明要退出 2（用法错误），不是跑一半失败'


def test_plan_skeleton_can_carry_the_probed_options_into_the_plan():
    code = py_code()
    assert '--from-options' in CDP.read_text(encoding='utf-8'), '要有 --from-options'
    assert 'options_from' in code, '带进计划的选项要标出来源'
    body = code[code.index('def cmd_plan_skeleton'):]
    body = body[:body.index('\ndef ', 1)]
    assert "item['options']" in body, '探到的选项要塞进对应字段'
    assert "item['kind']" in body, 'kind 要按探测结果校正：探到选项说明它是面板类控件'


def test_a_searchable_dropdown_can_opt_out_per_field():
    """可搜索下拉的选项要打字才出来，整页一刀切会把它们全拦死。"""
    code = py_code()
    body = code[code.index('def cmd_fill'):]
    body = body[:body.index('没有来源')]
    assert "item.get('options_unverified')" in body, '单个字段也要能绕过'


# ---- fixture 与评测脚本的契约 ----

def test_fixture_reproduces_options_without_class_or_role():
    html = FIXTURE.read_text(encoding='utf-8')
    assert 'x-aside-item' in html, '年份节点用自家 class，不含 option 这类词'
    assert "createElement('span')" in html, '月份节点是裸 span'
    assert 'x-input-focus' in html, '要复刻聚焦态 class'


def test_fixture_keeps_two_levels_side_by_side_in_one_panel():
    html = FIXTURE.read_text(encoding='utf-8')
    assert 'x-aside' in html and 'x-months' in html, '年份列和月份格在同一个面板里'
    assert 'display: flex' in html, '两级并排而不是层叠'


def test_fixture_puts_a_plain_text_box_first():
    """纯文本框排在第一个，复刻真站上的次序——probe-options 就是在第一个控件上停的。"""
    html = FIXTURE.read_text(encoding='utf-8')
    name_at = html.index('id="name"')
    start_at = html.index('id="start"')
    assert name_at < start_at, '文本框要排在日期框前面'


def test_fixture_exposes_only_read_only_judging_hooks():
    html = FIXTURE.read_text(encoding='utf-8')
    assert 'window.fixtureTruth' in html and 'window.fixtureAudit' in html
    assert 'fixtureTruth = () =>' in html, '判卷接口只读，不提供写入口'


def test_check_script_asserts_the_right_behaviour_not_the_current_one():
    code = CHECK.read_text(encoding='utf-8')
    assert 'expect_truth' in code, '要断言真值，不只看报告说填成了'
    assert 'ERR_PANELS' in code, '要断言面板收干净'
    assert 'appearedCount' in code, '要断言点文本框后认出 0 个面板'
    assert '--out' in code and 'outside the repository' in code, '产物不许落在仓库里'


def test_check_script_runs_without_models_or_recruitment_sites():
    code = CHECK.read_text(encoding='utf-8')
    assert '127.0.0.1' in code, '只连本地 HTTP server'
    assert 'tempfile.mkdtemp' in code, '用隔离的浏览器配置目录'
    for banned in ('talent.baidu', 'zhaopin.', 'moka', 'Moka'):
        assert banned not in code, '评测脚本里不许出现真实站点：' + banned
