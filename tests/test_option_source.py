"""选项的来源要能查，不能凭印象写；选项本身按结构找，不按 class 列举。

三件事同源，都来自 2026-10-05 在一个真实站点上的实测：

1. 选项节点可能既没有 class 也没有 role（年份是 div 带自家 class、月份是裸 span）。
   按 class/role 列举时命中 0 个，于是"面板里没有这一项"，而面板里明明写着那几个字。
   面板那一层已经为同样的理由推翻过按 class 列举，选项层当时没跟着改。

2. 点一下普通文本框，不该算"开出了一个面板"（聚焦态 class、校验提示都会被误当成面板，
   后果是整页归零：它收不掉，脏账还留在账本里，之后每条命令都报 ERR_PANELS）。
   治法不是为每种噪音写一条淘汰规则——那样每加一条就多一种错杀下一个站真面板的方式——
   而是用一条肯定式判据说清面板是什么：**里面有可点的选项**。详见第 2 节的说明。

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


# ---- 2. 面板是什么，用一条肯定式判据说清 ----
#
# 这几条原先守的是三条淘汰规则（"属性变化要从不可见变可见"、"候选不能是控件自己那棵树"、
# "自己是叶子的不算"）。那三条各自治了一个碰巧见到的误报，但每一条都是在列举"什么不是面板"，
# 而网页的花样是无穷的：淘汰规则每多一条，就多一种把下一个站的真面板错杀的方式。
# 一次把真站上所有候选连证据打出来看，真面板和噪音在一个维度上干净地分开了：
#   控件壳 ant-select…          可点叶子 0
#   真面板 ant-select-dropdown   可点叶子 12
#   校验提示 brick-field-hint    可点叶子 0
# 所以判据换成一条肯定式的：里面有可点的选项。断言跟着这个结论改，不是迁就代码。

def test_appeared_reports_evidence_and_does_not_decide():
    """页内只观察、排序、给证据——"就是它"这个结论不在这里下。"""
    code = js_code()
    body = code[code.index('appeared(anchorHandle)'):]
    body = body[:body.index('\n    },')]
    for field in ('optionCount', 'floating', 'sampleTexts', 'gapBelow'):
        assert field in body, '每个候选要带上判断用得上的事实：' + field
    assert '.filter(' not in body, \
        'appeared 不筛候选——筛了就是替调用方下结论，而它看不到截图也问不了用户'


def test_the_decision_is_one_place_and_can_say_it_cannot_tell():
    """浮层和大分差都不能代替唯一性；原源码门槛断言已被AGENTS纠正。"""
    import importlib.util
    source = HERE.parent / 'skills/campus-apply/scripts/browser/chrome_cdp.py'
    spec = importlib.util.spec_from_file_location('choice_verdict', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = [dict(handle=1, optionCount=2, floating=False, score=20),
            dict(handle=2, optionCount=2, floating=True, score=2)]
    chosen, why, candidates = module._pick_panel(rows)
    assert chosen is None and why == 'ambiguous'
    assert len(candidates) == 2


def test_an_unsure_field_does_not_stop_the_whole_page():
    """探测要一次做完：拿不准的字段标待定、继续往下探，不中断整页。
    每个拿不准的字段单独停一次，就倒回"反复探索反复请示"的老毛病了。"""
    code = py_code()
    body = code[code.index('def cmd_probe_options'):]
    body = body[:body.index('\ndef ', 1)]
    assert "'unsure'" in body, '待定要在报告里有自己的 kind'
    assert 'candidates=' in body, '待定项要把候选和证据交出去'
    assert 'continue' in body, '待定之后继续探后面的字段'


def test_no_elimination_rules_that_could_kill_a_real_panel():
    """淘汰规则是这里的红线：每加一条就多一种错杀下一个站的方式。"""
    code = js_code()
    body = code[code.index('appeared(anchorHandle)'):]
    body = body[:body.index('\n    },')]
    for banned, why in (
        ('wasVisible', '"点击前不可见"会杀掉本来就可见、点击后才填进选项的面板'),
        ('ownTree', '"不能是控件自己那棵树"会杀掉把下拉渲染在控件内部的站'),
        ('children.length === 0', '"自己是叶子不算"会杀掉只有一个选项的面板'),
    ):
        assert banned not in body, '不该再有这条淘汰规则：' + why


def test_the_candidate_pool_itself_filters_nothing():
    """收候选的那一步只负责收齐，判断留给一个地方做——两处都筛会很难查。"""
    code = js_code()
    take = code[code.index('const watchTake'):]
    take = take[:take.index('\n  };')]
    assert 'wasVisible' not in take, '候选池不按可见性变化筛'
    assert 'appeared.add(rec.target)' in take or 'appeared.add(node)' in take, \
        '新增节点和属性变化都要收进候选池'


def test_note_open_records_whatever_appeared_approved():
    """门后面不再架第二道能错杀的筛子：进门的判据准就够了。"""
    code = js_code()
    body = code[code.index('noteOpen(fieldHandle, panelHandle)'):]
    body = body[:body.index('\n    },')]
    assert 'contains(field)' not in body and 'field.contains(' not in body, \
        '不在记账时再按血缘淘汰：有的站把下拉渲染在控件内部，那样永远记不上账'
    assert 'return false' in body, '面板已经没了要明确返回 false，不能假装记上了'


def test_aim_widens_rather_than_narrows():
    """自定义控件的常规结构不该被当成故障：这里的改动方向是放宽，不是收紧。"""
    code = js_code()
    body = code[code.index('aim(handle)'):]
    body = body[:body.index('\n    },')]
    assert 'unit.contains(top)' in body, \
        '控件自己的皮肤盖在它上面不算遮挡（真正的 input 透明铺在底下是常规写法）'
    assert "if (!top) return { ok: false, why: 'offscreen'" in body, \
        'elementFromPoint 返回 null 是"不在视口"，报 covered 会把人带错方向'


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


# ---- 这条设计约束要写在仓库里，不能只活在一次对话里 ----

def test_the_positive_criterion_rule_is_written_down():
    """判据要肯定式这件事，是今天花了四轮才换来的结论，得留在 skill 里。"""
    doc = (HERE.parent / 'skills/apply-fill/references/on-site-principles.md').read_text(
        encoding='utf-8')
    assert '判据要肯定式' in doc, '这条约束要写进现场处理原则'
    assert '淘汰' in doc, '要说清淘汰式判据的代价'
    assert '排序' in doc, '要写明 class 清单只用于排序、不淘汰候选'


def test_class_hints_are_only_ever_used_for_ranking():
    """两张 class 清单都只能排序。它们是这个文件里仅存的站点特征，别让它们回到淘汰位置。"""
    code = js_code()
    for name in ('PANEL_HINT', 'OPTION_HINT'):
        for line in code.splitlines():
            if name in line and 'const ' + name not in line:
                assert 'filter(' not in line and 'querySelectorAll' not in line, \
                    name + ' 只能用于排序，不能拿去筛候选：' + line.strip()
