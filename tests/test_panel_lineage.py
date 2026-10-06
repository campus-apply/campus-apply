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




def test_close_panels_waits_for_delayed_animation_not_instant_query():
    """收面板动作发出后应等条件满足，不能瞬时查一次就定论。

    真实站点的组件有过渡动画，瞬时查会把"正在收"读成"没收掉"，从而一招接一招全部失败。
    修复方法是用带 budget 的条件等待，而不是固定延时。
    """
    code = py_code()
    assert '_panel_closed_within' in code, \
        '_close_panels 里收面板后的判定要用带 budget 的条件等待，不能用瞬时查询'
    assert '_panel_still_open' in code and '_panel_closed_within' in code, \
        '两个函数都要存在：入口用瞬时查（面板还没开，不存在动画），收后用条件等'


def test_panel_closed_within_uses_wait_for_not_sleep():
    """_panel_closed_within 要按"条件满足"返回，而不是睡固定秒。"""
    import re
    text = CDP.read_text(encoding='utf-8')
    # 取 _panel_closed_within 函数体
    m = re.search(r'def _panel_closed_within\(.*?(?=\ndef )', text, re.DOTALL)
    assert m, '_panel_closed_within 函数应存在'
    body = m.group(0)
    assert '_wait_for' in body, \
        '_panel_closed_within 应用 _wait_for 按条件等，不应用 time.sleep 固定等'
    assert 'time.sleep' not in body, \
        '用 _wait_for 就不需要 sleep：sleep 是固定等，_wait_for 是条件等，只要面板消失就立刻返回'


def test_per_trick_budget_is_bounded_reasonably():
    """每招的等待预算要有上下界：太短仍然卡，太长每招失败要等太久。"""
    import re
    text = CDP.read_text(encoding='utf-8')
    m = re.search(r'per_trick\s*=\s*max\(([^,]+),\s*min\(([^,]+),', text)
    assert m, 'per_trick 应用 max(lower, min(upper, ...)) 形式限制范围'
    lower = float(m.group(1).strip())
    upper = float(m.group(2).strip())
    assert 0.1 <= lower <= 0.5, f'下界 {lower} 太小会仍然卡（< 0.1）或太大（> 0.5）'
    assert 0.4 <= upper <= 1.5, f'上界 {upper} 过小时每招失败要等太久或等不够（应在 0.4–1.5 之间）'
