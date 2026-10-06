"""Unresolved observations are evidence, not confirmed open panels."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('panel_observation_support',ROOT/'evals/browser_test_support.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)

@pytest.fixture(scope='module')
def browser(tmp_path_factory):
    with support.BrowserSession(tmp_path_factory.mktemp('panel-observation')) as session:
        yield session

def observe(browser):
    browser.document('<label for=field>城市</label><input id=field><div id=noise style="cursor:pointer;width:200px;height:40px">普通表单容器</div>')
    field=browser.call("window.__caFill.resolve('#field',0)")['handle']
    candidate=browser.call("window.__caFill.resolve('#noise',0)")['handle']
    browser.call(f'window.__caFill.noteCandidates({field},[{candidate}])')
    return field,candidate

def test_candidate_identity_is_not_a_confirmed_panel(browser):
    field,candidate=observe(browser)
    rows=browser.call('window.__caFill.stillOpen()')
    assert len(rows)==1 and rows[0]['handle']==candidate
    assert rows[0].get('identity')=='candidate'
    browser.call(f'window.__caFill.noteOpen({field},{candidate})')
    rows=browser.call('window.__caFill.stillOpen()')
    assert len(rows)==1 and rows[0]['identity']=='confirmed-panel'
    browser.call(f'window.__caFill.noteClosed({field})')
    assert browser.call('window.__caFill.stillOpen()')==[]

def test_fill_reports_unresolved_evidence_without_claiming_open_panels(browser):
    observe(browser)
    field=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f.get('tag')=='input')
    item={k:field[k] for k in ('section','occurrence','label','nth')}
    item.update(kind='text',value='广州')
    path=browser.out/'candidate-plan.json';path.write_text(json.dumps(dict(fields=[item],pace=dict(min=0,max=0))))
    result=browser.command('fill',path)
    payload=result.stdout.split('---\n',1)[1]
    report=json.JSONDecoder().raw_decode(payload.lstrip())[0]
    assert report['filled']==1
    assert report['open_panels']==0
    assert report['unresolved_panel_candidates'][0]['identity']=='candidate'
    assert result.returncode==1 and 'ERR_PANEL_CANDIDATES' in result.stdout
    assert browser.js('document.querySelector("#field").value')=='广州'

def test_live_explicit_panel_choice_confirms_previously_unresolved_identity(browser):
    field,candidate=observe(browser)
    chosen=browser.cdp._panel_for(browser.tab,field,.05,selector='#noise')
    assert chosen['reason']=='ok' and chosen['panel']['handle']==candidate
    rows=browser.call('window.__caFill.stillOpen()')
    assert len(rows)==1 and rows[0]['identity']=='confirmed-panel'
