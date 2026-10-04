"""Guard the apply-form fixture's contract without launching a browser.

The full trap check needs real Chrome (evals/fixture_check.py). These tests only assert
the things that silently rot: the fixture still contains each documented trap, and the
checker refuses to write artifacts into the repository.
"""
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / 'evals/fixtures/apply_form.html'
CHECKER = ROOT / 'evals/fixture_check.py'
WIZARD = ROOT / 'evals/fixtures/wizard_form.html'


def module():
    spec = importlib.util.spec_from_file_location('fixture_check', CHECKER)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def html():
    return FIXTURE.read_text(encoding='utf-8')


def test_fixture_exists_and_says_it_is_fictional():
    text = html()
    assert '虚构' in text, 'the fixture must state that its data is made up'
    assert 'zhaopin' not in text and 'mokahr' not in text, 'no real recruitment host in the fixture'


@pytest.mark.parametrize('trap, needle', [
    # Each needle is the mechanism, not just a comment, so deleting the trap fails the test.
    ('必填星号走 CSS 伪元素，probe 读不到', ".fx-form-item--must>label::before{content:'*'"),
    ('模态遮罩是 position:fixed（guard 的 offsetParent 判法看不见它）', '.fx-mask{position:fixed'),
    ('长文本 maxlength 属性是 2000', 'maxlength="2000"'),
    ('长文本页面明文写 200-1000 字', '请填写 200-1000 字'),
    ('长文本真正生效的校验是 500 字，且在失焦时才报', "el.value.length > 500"),
    ('React fiber 双缓冲：挂载时挂上去的引用之后不再更新', "el[FIBER_KEY] = a;"),
    ('从 root.current 才能找到活动 fiber', '__reactContainer$'),
    ('只读日期框只听 mousedown，页面脚本的 click 打不开', "getElementById('birth').addEventListener('mousedown'"),
    ('有一类面板选完不自动收起，只认点字段标签', 'data-sticky="1"'),
    ('可搜索下拉：选中后搜索框清空，值只在显示元素上', "input.value = '';"),
    ('级联第二级点过第一级才出现', 'fx-cascader-col'),
    ('有后果的开关页面默认已勾选', 'id="transfer" checked'),
    ('账号级字段 disabled 写不进', 'id="phone" value="13800000000" disabled'),
    ('上传区支持拖拽，限 10M 以下 doc/docx/pdf', '支持 doc、docx、pdf 格式（10M 以下）'),
    ('自动解析只填空字段，且质量很差', "apply('email', 'ZHANG.MOU@EXAMPLE.COM')"),
    ('投递按钮只记一笔，永远不真的提交', "audit.submitClicked++"),
])
def test_fixture_still_contains_each_trap(trap, needle):
    assert needle in html(), 'trap went missing: ' + trap


def test_fixture_exposes_the_three_readonly_test_hooks():
    text = html()
    for hook in ('window.fixtureTruth', 'window.fixtureSnapshot', 'window.fixtureAudit'):
        assert hook + ' =' in text, hook + ' must stay available to the checker'


def test_checker_refuses_to_write_inside_the_repository():
    with pytest.raises(SystemExit) as caught:
        module().main(['--out', str(ROOT / 'evals/tmp-artifacts')])
    assert caught.value.code == 2, 'argparse errors exit 2'


def test_checker_requires_an_output_directory():
    with pytest.raises(SystemExit) as caught:
        module().main([])
    assert caught.value.code == 2


def test_wizard_fixture_covers_both_rendering_strategies():
    """分步表单有两种渲染法，fill 在两者下行为完全不同，所以两种都要有。"""
    text = WIZARD.read_text(encoding='utf-8')
    assert 'keep' in text, 'must support the ?keep= switch'
    assert 'step2.innerHTML = \'\'' in text, 'keep=0 must leave step 2 unmounted'
    assert '.step.off{display:none}' in text or 'display:none' in text, \
        'keep=1 must leave step 2 in the DOM but hidden'
    for hook in ('window.wizardTruth', 'window.wizardAudit'):
        assert hook + ' =' in text, hook + ' must stay available'
    assert 'nextClicked' in text, 'the audit must record whether 下一步 was pressed'


def test_fill_refuses_invisible_controls():
    """最关键的一条：在 DOM 里但不可见的控件写得进去、回读还会通过，报成功就是假的。"""
    source = (ROOT / 'skills/campus-apply/scripts/browser/chrome_cdp.py').read_text(encoding='utf-8')
    section = source[source.index('FILL_KINDS = '):source.index('def cmd_screenshot')]
    assert "if not info.get('visible')" in section, 'the visibility gate must stay'
    assert '不可见' in section


def test_fill_prints_the_report_even_if_the_page_navigated_away():
    """收尾的只读检查不能把逐字段账本烧掉。"""
    source = (ROOT / 'skills/campus-apply/scripts/browser/chrome_cdp.py').read_text(encoding='utf-8')
    section = source[source.index('FILL_KINDS = '):source.index('def cmd_screenshot')]
    assert 'ERR_CONTEXT' in section
    assert 'context_lost' in section
