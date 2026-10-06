"""Display-node meaning belongs to the agent, not text length or class order."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('display_support',ROOT/'evals/browser_test_support.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)

@pytest.fixture(scope='module')
def browser(tmp_path_factory):
    with support.BrowserSession(tmp_path_factory.mktemp('display-observation')) as session:
        yield session

def test_multiple_visible_texts_are_evidence_not_longest_value(browser):
    browser.document('<div id=field><span id=hint>推荐选择北京</span><span id=actual>广州</span></div>')
    handle=browser.call("window.__caFill.resolve('#field',0)")['handle']
    result=browser.call(f'window.__caFill.readback({handle},null)')
    assert result['display'] is None
    assert result['display_unknown'] is True
    assert {c['text'] for c in result['display_candidates']}=={'推荐选择北京','广州'}

def test_explicit_display_selector_must_be_unique(browser):
    browser.document('<input id=field><span class=shown>北京</span><span class=shown>广州</span>')
    handle=browser.call("window.__caFill.resolve('#field',0)")['handle']
    result=browser.call(f'window.__caFill.readback({handle},".shown")')
    assert result['display'] is None and result['display_unknown'] is True

def test_agent_can_bind_display_outside_native_carrier(browser):
    browser.document('<input id=field readonly><span id=actual>广州</span>')
    handle=browser.call("window.__caFill.resolve('#field',0)")['handle']
    result=browser.call(f'window.__caFill.readback({handle},"#actual")')
    assert result['display']=='广州'
    assert result['display_source']=='agent-selector'

def test_native_empty_value_is_not_replaced_by_neighbor_display(browser):
    browser.document('<input id=field readonly><span class=selected-value>邻字段的广州</span>')
    handle=browser.call("window.__caFill.resolve('#field',0)")['handle']
    result=browser.call(f'window.__caFill.readback({handle},null)')
    assert result['dom']=='' and result['display']==''
    assert result['display_source']=='native-value'
