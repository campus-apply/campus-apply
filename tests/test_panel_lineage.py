"""面板要按"点击前后谁新出现了"找，不按 class 清单猜。

两个真实站点给出了两种相反的死法，都出在"全局列举 + 几何配对"这条路上：
一个站的真面板被同样命中选择器的祖先容器吞掉，另一个站的面板盖在输入框上、被
"必须紧贴 24 像素内"的配对规则扔掉。同一条路还让常驻的行内容器被数成"开着的面板"，
于是整页填完也必定报 ERR_PANELS。

按 DOM 血缘找就都没有了：点击前后比对，新出现的那个就是面板，不需要任何 class 清单。
几何只用来在多个候选里排序，不用来淘汰。

这里只验源码契约；真页面上的行为归 evals/panel_shape_check.py。
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
BROWSER = HERE.parent / 'skills/campus-apply/scripts/browser'
LIB = BROWSER / 'lib_fill.js'
CDP = BROWSER / 'chrome_cdp.py'
PRINCIPLES = HERE.parent / 'skills/apply-fill/references/on-site-principles.md'


def js_code():
    text = LIB.read_text(encoding='utf-8')
    return '\n'.join(l for l in text.splitlines() if not l.strip().startswith('//'))


def py_code():
    import re
    text = CDP.read_text(encoding='utf-8')
    text = re.sub(r'""".*?"""', '""""""', text, flags=re.DOTALL)
    return '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))


def test_panels_are_found_by_what_appeared_not_by_a_class_list():
    """点击前装观察器、点击后收新增节点 —— 这是站点无关的机制。"""
    code = js_code()
    assert 'MutationObserver' in code, '要观察点击前后的变化，而不是全局按 class 列举'
    assert 'watchStart' in code and 'watchTake' in code, \
        '要有"开始观察 / 取走这一轮新出现的节点"这一对动作'


def test_the_outermost_only_rule_is_gone():
    """"只留最外层"会让真面板被同样命中选择器的祖先容器吞掉。"""
    code = js_code()
    assert 'out.some(p => get(p.handle) && get(p.handle).contains(el))' not in code, \
        '按包含关系淘汰候选，正是真面板被祖先吞掉的原因'


def test_open_panel_count_is_what_we_opened_not_what_matches_a_selector():
    """常驻的行内容器不是"开着的面板"；只数自己点开过、现在仍可见的。"""
    code = js_code()
    assert 'openedByUs' in code, '面板计数要按 handle 记账'
    driver = py_code()
    assert "_fill_call(tab, 'window.__caFill.panels().length')" not in driver, \
        '收尾不能拿全局匹配数当失败判据'


def test_geometry_ranks_candidates_and_never_eliminates_them():
    """面板可能盖在输入框上，"必须紧贴 24 像素内"会把它扔掉。"""
    driver = py_code()
    assert 'gap > 24' not in driver, '几何不能用于淘汰，只能用于排序'


def test_closing_a_panel_learns_which_trick_works_on_this_page():
    """收面板的有效办法两个站正好相反，写死顺序必然在其中一个站上全错。"""
    driver = py_code()
    assert 'learned' in driver or 'remember' in driver, \
        '哪一招奏效要记下来，本页后续字段优先用它'


def test_readback_is_bounded_by_the_control_own_container():
    """多个控件共用一个字段容器时，往上找会抓到隔壁字段的显示值。"""
    code = js_code()
    assert 'ownBox' in code, '回读要先定界到控件自己的最小容器'
    assert 'sameRow' in code or 'overlap' in code, \
        '上溯取到的显示值要校验与本控件的几何位置对得上'


def test_the_rule_is_written_down_for_the_model_too():
    text = PRINCIPLES.read_text(encoding='utf-8')
    assert '点击前后' in text, 'on-site-principles 要写明面板按点击前后的变化找'
    assert '现场试' in text, '收面板不写死顺序，改成现场试并记下哪招有效'
