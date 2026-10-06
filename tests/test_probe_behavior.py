"""A read-only option survey cannot choose a branch or keep executing stale nodes."""
import importlib.util
import json
from pathlib import Path
import time

import pytest

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('probe_support',ROOT/'evals/browser_test_support.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)


@pytest.fixture(scope='module')
def browser(tmp_path_factory):
    with support.BrowserSession(tmp_path_factory.mktemp('probe-behavior')) as session:
        yield session


def page(browser,query=''):
    url=browser.url+'dynamic_branches.html?run='+str(time.monotonic_ns())+'&'+query
    browser.tab.call('Page.navigate',url=url)
    deadline=time.monotonic()+10
    while not browser.js('document.readyState==="complete" && location.href==='+json.dumps(url)):
        assert time.monotonic()<deadline,'fixture did not finish loading'
        time.sleep(.03)
    browser.js(browser.cdp._fill_lib())


def item(browser,label,value,kind='text'):
    f=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['label']==label)
    result={k:f[k] for k in ('section','occurrence','label','nth')}
    result['key']=' / '.join(str(result[k]) for k in ('section','occurrence','label','nth') if result[k]!='')
    result.update(kind=kind,value=value)
    return result


def report_of(result):
    return json.loads(result.stdout[result.stdout.index('{'):result.stdout.rfind('}')+1])


def test_default_probe_does_not_click_native_carriers(browser):
    page(browser);path=browser.out/'default-probe.json'
    result=browser.command('probe-options',path)
    assert result.returncode==0,result.stdout
    assert browser.js('window.fixtureAudit().opened')==0
    assert browser.js('window.fixtureTruth().language')==''
    rows=json.loads(path.read_text())['fields']
    assert next(r for r in rows if r['label']=='语言类型')['kind']=='needs-agent'


def test_named_probe_reads_options_without_selecting_first(browser):
    page(browser);path=browser.out/'named-probe.json'
    result=browser.command('probe-options',path,'--only','语言类型')
    assert result.returncode==0,result.stdout
    row=json.loads(path.read_text())['fields'][0]
    assert row['options']==['中文','英语']
    assert row['branch_selected'] is False
    assert browser.js('window.fixtureAudit().selected')==[]
    assert browser.js('window.fixtureTruth().language')==''
    assert browser.js('window.fixtureAudit().openPanels')==0


def test_nonempty_field_options_can_be_read_without_trial_reset(browser):
    page(browser,'existing=1');path=browser.out/'existing-probe.json'
    result=browser.command('probe-options',path,'--only','语言类型')
    assert result.returncode==0,result.stdout
    assert json.loads(path.read_text())['fields'][0]['options']==['中文','英语']
    assert browser.js('window.fixtureTruth()')==dict(common='不应覆盖',language='中文',note='已有中文说明')
    assert browser.js('window.fixtureAudit().selected')==[]


@pytest.mark.parametrize('query',['','replacement_only=1'])
def test_real_branch_change_stops_old_plan_before_same_label_replacement(browser,query):
    page(browser,query)
    first=item(browser,'语言类型','英语','dropdown');first['options']=['中文','英语']
    old=item(browser,'说明','仅适用于旧中文分支')
    path=browser.out/'branch-plan.json';path.write_text(json.dumps(dict(fields=[first,old],pace=dict(min=0,max=0))))
    result=browser.command('fill',path)
    assert result.returncode==1,result.stdout
    report=report_of(result)
    assert report['fields'][0]['status']=='filled'
    assert report['fields'][1]['status']=='not-started'
    assert report['needs_observation'] is True
    assert browser.js('window.fixtureTruth().note')==''
    assert browser.js('window.fixtureTruth().common')=='不应覆盖'


def test_confirmed_choice_and_incremental_observation_reach_nested_fields(browser):
    page(browser)
    first=item(browser,'语言类型','英语','dropdown');first['options']=['中文','英语']
    path=browser.out/'language.json';path.write_text(json.dumps(dict(fields=[first],pace=dict(min=0,max=0))))
    result=browser.command('fill',path)
    assert report_of(result)['fields'][0]['status']=='filled'
    current=browser.call('window.__caFill.outline()')['fields']
    assert any(f['label']=='语言考试' for f in current)
    exam=item(browser,'语言考试','CET-6','dropdown');exam['options']=['CET-6','TEM-8']
    path=browser.out/'exam.json';path.write_text(json.dumps(dict(fields=[exam],pace=dict(min=0,max=0))))
    result=browser.command('fill',path)
    assert report_of(result)['fields'][0]['status']=='filled'
    current=browser.call('window.__caFill.outline()')['fields']
    assert any(f['label']=='考试分数' for f in current)
    score=item(browser,'考试分数','598')
    note=item(browser,'说明','英语考试成绩已核对')
    path=browser.out/'remaining.json';path.write_text(json.dumps(dict(fields=[score,note],pace=dict(min=0,max=0))))
    result=browser.command('fill',path)
    assert result.returncode==0,result.stdout
    assert browser.js('window.fixtureTruth()')==dict(common='不应覆盖',language='英语',note='英语考试成绩已核对',exam='CET-6',score='598')


def test_close_rebuilding_menu_reports_unknown_not_closed(browser):
    browser.document('<label for=field>学历</label><input id=field readonly style="position:absolute;left:30px;top:30px;width:180px;height:32px">')
    browser.js('''document.getElementById('field').onclick=()=>{
      const old=document.getElementById('rebuilt-menu');if(old)old.remove();
      const pane=document.createElement('div');pane.id='rebuilt-menu';
      pane.style='position:absolute;left:30px;top:100px;width:200px';
      pane.innerHTML='<span style="display:block;min-height:32px;cursor:pointer">本科</span><span style="display:block;min-height:32px;cursor:pointer">硕士</span>';
      document.body.append(pane);
    }''')
    path=browser.out/'rebuilt-probe.json'
    result=browser.command('probe-options',path,'--only','学历')
    row=json.loads(path.read_text())['fields'][0]
    assert row['closed'] is not True
    assert row['panel_status_unknown'] is True
    assert row['close_candidates']
    assert browser.js("document.querySelectorAll('#rebuilt-menu').length")==1
