"""Guard the panel-shape fixture's contract without launching a browser.

The real check needs Chrome (evals/panel_shape_check.py). These tests only hold the line on
what silently rots: each of the three real-site shapes keeps the DOM structure that makes it
fail, the measured geometry stays the measured geometry, the two opposite close-panel tempers
stay opposite, and the checker still refuses to write into the repository.
"""
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / 'evals/fixtures/panel_shapes.html'
CHECKER = ROOT / 'evals/panel_shape_check.py'


def module():
    spec = importlib.util.spec_from_file_location('panel_shape_check', CHECKER)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def html():
    return FIXTURE.read_text(encoding='utf-8')


def test_fixture_says_it_is_fictional_and_names_no_site():
    text = html()
    assert '虚构' in text, 'the fixture must state that its data is made up'
    for host in ('mokahr', 'zhaopin', 'jd.com', 'moka', '韶音', '京东'):
        assert host not in text.lower() if host.isascii() else host not in text, \
            'no real recruitment site in a public fixture: ' + host


@pytest.mark.parametrize('shape, needle', [
    # 形状 A：真面板必须是常驻容器的**后代**，容器和面板都带 Dropdown 字样（同命中一套 class 词）。
    ('A 真面板挂在常驻容器里，不是挂 body 下', "container.appendChild(panel)"),
    ('A 常驻容器是行内的，不是弹层', '.sd-Dropdown-container-1CigZ{position:relative'),
    ('A 容器和真面板的 class 都带 Dropdown', 'sd-Dropdown-dropdown-1CigZ'),
    # 形状 B：几何是证据，偏移量和尺寸都不能动。
    ('B 面板左边比输入框右 39px（实测）', "box.left + scrollX + 39"),
    ('B 面板上边比输入框高 3px（实测）', "box.top + scrollY - 3"),
    ('B 面板实测 280×341', 'width:280px;height:341px'),
    ('B 输入框实测 131×32', '.ps-date{width:131px;height:32px}'),
    ('B 边框算进尺寸里，量出来才等于实测值', 'box-sizing:border-box'),
    ('B 日期面板只听 mousedown', "input.addEventListener('mousedown'"),
    # 形状 C：常驻假容器默认 77 个，且点了不开任何面板。
    ('C 假容器默认 77 个', "params.get('fillers') || 77"),
    ('C 假容器是真的建出来的', "container.className = 'sd-Dropdown-container-1CigZ'"),
    # 收面板脾气：两种必须真的相反。
    ('收面板 甲站脾气：再点一次输入框就收', "if (temper === 'close-reclick') closePanel(open)"),
    ('收面板 乙站脾气：只认点板块标题', 'ps-section-title'),
    ('收面板 点字段标题只记一笔、什么都不做', "bump(input.dataset.psInput, 'click-field-label')"),
    ('收面板 两个控件的面板都紧贴输入框下方 2px（配得上，考的只是收面板）',
     "box.bottom + scrollY + 2"),
])
def test_fixture_still_contains_each_shape(shape, needle):
    assert needle in html(), 'shape went missing: ' + shape


def test_fixture_exposes_the_readonly_test_hooks():
    text = html()
    for hook in ('window.fixtureTruth', 'window.fixtureAudit'):
        assert hook + ' =' in text, hook + ' must stay available to the checker'
    # 收面板那条规矩的验收点：试过哪几招、各几次，必须看得见。
    assert 'closeTries' in text, 'the audit must record which close tricks were tried'
    assert 'fakeContainers' in text, 'the audit must expose how many inline containers exist'


def test_each_case_judges_the_desired_behaviour_not_todays():
    """判据是"应该怎样"：面板找得到、字段填成、面板收干净。迁就现状就失去意义了。"""
    source = CHECKER.read_text(encoding='utf-8')
    assert "result.returncode != 0" in source, 'a passing case must require exit 0'
    assert "row.get('status') != 'filled'" in source, 'a passing case must require filled fields'
    assert 'expect_keys' in source and 'regression' in source


def test_checker_keeps_the_real_site_failure_signatures():
    """红的时候要能分清"复现了已知的坑"和"出现了新的死法"，所以签名原文不能丢。"""
    module_source = CHECKER.read_text(encoding='utf-8')
    for signature in ('没出现面板', 'ERR_PANELS', '收不起来'):
        assert signature in module_source, 'lost the real-site signature: ' + signature


def test_checker_measures_geometry_without_the_executor_api():
    """几何证据只能用 DOM 量：被测的那套接口正要改，证据跟着它变就对不了账。"""
    source = CHECKER.read_text(encoding='utf-8')
    diagnose = source[source.index('DIAGNOSE_JS'):source.index('# 每个 case：')]
    assert '__caFill' not in diagnose, 'the evidence probe must not call the executor API'
    for field in ('swallowedBy', 'keptItself', 'gap', 'panelCoversAnchorCentre', 'fakeContainers'):
        assert field in diagnose, 'missing evidence field: ' + field


def test_checker_refuses_to_write_inside_the_repository():
    with pytest.raises(SystemExit) as caught:
        module().main(['--out', str(ROOT / 'evals/tmp-artifacts')])
    assert caught.value.code == 2, 'argparse errors exit 2'


def test_checker_requires_an_output_directory():
    with pytest.raises(SystemExit) as caught:
        module().main([])
    assert caught.value.code == 2
