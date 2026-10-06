"""Catch label/identity disagreement using actual DOM, CDP, and the field executor."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('ca_browser_support', ROOT / 'evals/browser_test_support.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


@pytest.fixture(scope='module')
def browser(tmp_path_factory):
    with support.BrowserSession(tmp_path_factory.mktemp('label-behavior')) as session:
        yield session


def field_and_probe(browser, html, selector):
    browser.document(html)
    resolved = browser.call(f'window.__caFill.resolve({json.dumps(selector)},0)')
    fields = browser.call('window.__caFill.outline()')['fields']
    field = next(f for f in fields if f['handle'] == resolved['handle'])
    ident = browser.call(f"window.__caFill.identify({resolved['handle']})")
    probe = json.loads(browser.js((support.BROWSER / 'probe.js').read_text()))
    return field, ident, probe['controls'][0]


@pytest.mark.parametrize('html,label', [
    ('<div><span id=caption>获奖类别</span><input id=field aria-labelledby=caption placeholder=请选择></div>', '获奖类别'),
    ('<span id=a>获奖</span><span id=b>类别</span><input id=field aria-labelledby="a b" placeholder=请选择>', '获奖 类别'),
    ('<span id=a aria-labelledby=b>获奖类别</span><span id=b aria-labelledby=a></span><input id=field aria-labelledby=a placeholder=请选择>', '获奖类别'),
    ('<label for=field>家庭所在城市</label><input id=field aria-label=internal-component-name placeholder=请选择>', '家庭所在城市'),
    ('<label for=field>城市</label><input id=field aria-labelledby=missing placeholder=请选择>', '城市'),
])
def test_visible_label_is_consistent_with_identity_and_probe(browser, html, label):
    field, ident, probe = field_and_probe(browser, html, '#field')
    assert field['label'] == label
    assert ident['name'] == label
    assert probe['label'] == label


def test_correct_semantic_target_is_not_rejected_as_placeholder(browser):
    field, _, _ = field_and_probe(browser,
        '<div><span id=caption>获奖类别</span><input id=field aria-labelledby=caption placeholder=请选择></div>', '#field')
    plan = {k: field[k] for k in ('section','occurrence','label','nth')}
    plan.update(kind='text', value='虚构奖项', expect_label='获奖类别')
    ok, report = browser.cdp._fill_one(browser.tab, plan, {})
    assert ok, report
    assert browser.js("document.getElementById('field').value") == '虚构奖项'


def test_repeated_labels_keep_distinct_semantic_targets(browser):
    browser.document('<div><label for=a>年</label><input id=a></div><div><label for=b>年</label><input id=b></div>')
    fields = [f for f in browser.call('window.__caFill.outline()')['fields'] if f['tag'] == 'input']
    assert len(fields) == 2
    assert [f['label'] for f in fields] == ['年','年']
    for index, field in enumerate(fields):
        plan = {k: field[k] for k in ('section','occurrence','label','nth')}
        plan.update(kind='text', value=str(2024+index), expect_label='年')
        ok, report = browser.cdp._fill_one(browser.tab, plan, {})
        assert ok, report
    assert browser.js("[document.getElementById('a').value,document.getElementById('b').value]") == ['2024','2025']
