"""Standard password semantics protect values even with a misleading ordinary label."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('private_support',ROOT/'evals/browser_test_support.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
DUMMY='test-only-secret'


@pytest.fixture(scope='module')
def browser(tmp_path_factory):
    with support.BrowserSession(tmp_path_factory.mktemp('private-controls')) as session:
        yield session


def password(browser):
    browser.document('<label for=field>昵称</label><input id=field type=password value="'+DUMMY+'">')
    browser.js("document.getElementById('field').__vueParentComponent={props:{modelValue:"+json.dumps(DUMMY)+'}}')
    return browser.call("window.__caFill.resolve('#field',0)")['handle']


def test_password_type_is_protected_independently_of_label(browser):
    handle=password(browser)
    ident=browser.call(f'window.__caFill.identify({handle})')
    assert ident['sensitive'] is True
    assert ident['hard_sensitive'] is True


def test_label_evidence_does_not_copy_input_values(browser):
    password(browser)
    result=browser.call("window.__caFill.describeLabel(document.getElementById('field'))")
    assert DUMMY not in json.dumps(result)


def test_probe_reports_only_password_presence_or_length(browser):
    password(browser)
    result=json.loads(browser.js((support.BROWSER/'probe.js').read_text()))
    assert DUMMY not in json.dumps(result)
    assert result['controls'][0]['valueLen']==len(DUMMY)


def test_readback_and_model_never_return_password_value(browser):
    handle=password(browser)
    result=browser.call(f'window.__caFill.readback({handle},null)')
    model=browser.call(f'window.__caFill.modelValue({handle})')
    assert DUMMY not in json.dumps([result,model])
    assert result['value_len']==len(DUMMY)


@pytest.mark.parametrize('override',[False,True])
def test_fill_cannot_override_password_type(browser,override):
    password(browser)
    ok,report=browser.cdp._fill_one(browser.tab,dict(selector='#field',kind='text',
        value='test-only-replacement',sensitive_ok=override),{})
    assert not ok,report
    assert browser.js("document.getElementById('field').value")==DUMMY


def test_page_write_primitive_also_rejects_password_type(browser):
    handle=password(browser)
    result=browser.call(f'window.__caFill.write({handle},"test-only-replacement")')
    assert result['ok'] is False
    assert browser.js("document.getElementById('field').value")==DUMMY


@pytest.mark.parametrize('kind,value',[('tel','13800000000'),('email','fixture@example.invalid')])
def test_contact_fill_verifies_without_returning_raw_value(browser,kind,value):
    browser.document('<label for=field>联系方式</label><input id=field type='+kind+'>')
    f=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['tag']=='input')
    item={k:f[k] for k in ('section','occurrence','label','nth')};item.update(kind='text',value=value)
    ok,report=browser.cdp._fill_one(browser.tab,item,{})
    assert ok,report
    assert report['readback']['masked'] is True
    assert value not in json.dumps(report)
    assert report['readback']['dom_len']==len(value)
