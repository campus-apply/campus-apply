"""Prevent implicit choices; exercise explicit choices against live, rebuilt DOM."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('choice_support', ROOT / 'evals/browser_test_support.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


@pytest.fixture(scope='module')
def browser(tmp_path_factory):
    with support.BrowserSession(tmp_path_factory.mktemp('agent-choice-behavior')) as session:
        yield session


def panels(browser, count=2, duplicate=False, inline=False):
    browser.document('<style>input {width:180px;height:32px} .pick {display:block;width:180px;height:28px;cursor:pointer}</style><label for=field>学历</label><input id=field readonly>')
    browser.js('''(() => {
      window.choiceAudit=[]; window.choiceTruth=null;
      const field=document.getElementById('field');
      field.onclick=() => {
        const old=[...document.querySelectorAll('[data-test-panel]')];
        if(old.length) { old.forEach(e=>e.remove()); return; }
        for(let i=0;i<COUNT;i++) {
          const panel=document.createElement('div');
          panel.id='p'+i; panel.dataset.testPanel='1';
          panel.className=i===0?'panel':'plain';
          panel.style=INLINE?'width:200px;min-height:70px':
            'position:absolute;left:'+(20+i*210)+'px;top:95px;width:200px;height:70px';
          for(let j=0;j<2;j++) {
            const item=document.createElement('span');
            item.className='pick'+(j===0?' option':'');
            item.id='p'+i+'o'+j; item.textContent=DUPLICATE?'同名项':(j===0?'本科':'硕士');
            item.onclick=e=>{
              e.stopPropagation();window.choiceAudit.push(item.id);window.choiceTruth=item.id;
              field.value=item.textContent;document.querySelectorAll('[data-test-panel]').forEach(p=>p.remove());
            };
            panel.append(item);
          }
          document.body.append(panel);
        }
      };
    })()'''.replace('COUNT', str(count)).replace('DUPLICATE', str(duplicate).lower()).replace('INLINE', str(inline).lower()))
    f = next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['tag']=='input')
    plan = {k:f[k] for k in ('section','occurrence','label','nth')}
    plan.update(kind='dropdown',value='同名项' if duplicate else '硕士',expect_label='学历')
    return f, plan


def test_two_eligible_panels_remain_ambiguous_despite_score_gap(browser):
    rows=[{'handle':1,'score':14,'optionCount':2,'floating':True},
          {'handle':2,'score':4,'optionCount':2,'floating':True}]
    selected, reason, candidates=browser.cdp._pick_panel(rows)
    assert selected is None
    assert reason=='ambiguous'
    assert len(candidates)==2


def test_inline_panel_is_not_excluded_by_floating(browser):
    row={'handle':1,'score':4,'optionCount':2,'floating':False}
    selected, reason, _=browser.cdp._pick_panel([row])
    assert selected==row
    assert reason=='ok'


def test_ambiguous_fill_reports_all_six_panels_and_does_not_pick(browser):
    _, plan=panels(browser,count=6)
    ok, report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert not ok
    assert report['reason']=='ambiguous-panel'
    assert len(report['candidates'])==6
    assert browser.js('window.choiceAudit')==[]
    assert report['panel_left_open'] is False


def test_agent_can_choose_the_fifth_panel(browser):
    _,plan=panels(browser,count=6)
    plan['panel_selector']='#p4'
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert ok,report
    assert browser.js('window.choiceTruth')=='p4o1'


def test_duplicate_text_does_not_implicitly_pick_hint_first(browser):
    _,plan=panels(browser,count=1,duplicate=True)
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert not ok
    assert report['reason']=='ambiguous-option'
    assert len(report['candidates'])==2
    assert browser.js('window.choiceAudit')==[]


def test_agent_can_choose_second_duplicate_by_live_selector(browser):
    _,plan=panels(browser,count=1,duplicate=True)
    plan['option_selector']='#p0o1'
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert ok,report
    assert browser.js('window.choiceTruth')=='p0o1'


@pytest.mark.parametrize('selector',['.pick','#missing','#field'])
def test_invalid_option_choice_never_falls_back_to_first(browser,selector):
    _,plan=panels(browser,count=1)
    plan['option_selector']=selector
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert not ok
    assert report['reason']=='invalid-option-choice'
    assert browser.js('window.choiceAudit')==[]


@pytest.mark.parametrize('selector',['[data-test-panel]','#missing','#field'])
def test_invalid_panel_choice_never_falls_back_to_scored_first(browser,selector):
    _,plan=panels(browser,count=2)
    plan['panel_selector']=selector
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert not ok
    assert report['reason']=='invalid-panel-choice'
    assert browser.js('window.choiceAudit')==[]


def test_probe_handle_is_not_needed_when_panel_is_rebuilt(browser):
    field,plan=panels(browser,count=1)
    browser.cdp._real_click(browser.tab,field['handle'])
    prior=browser.call("window.__caFill.resolve('#p0',0)")['handle']
    browser.cdp._real_click(browser.tab,field['handle'])
    plan['panel_selector']='#p0'
    plan['option_selector']='#p0o1'
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert ok,report
    assert browser.js('window.choiceTruth')=='p0o1'
    assert browser.call(f'window.__caFill.identify({prior})')['error']=='gone'


def test_unique_inline_panel_still_fills_without_explicit_choice(browser):
    _,plan=panels(browser,count=1,inline=True)
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert ok,report
    assert browser.js('window.choiceTruth')=='p0o1'


def test_probe_keeps_all_candidates_and_closes_actual_portal_nodes(browser):
    panels(browser,count=6)
    path=browser.out/'probe-six.json'
    result=browser.command('probe-options',path,'--only','学历')
    assert result.returncode==0,result.stdout+result.stderr
    row=json.loads(path.read_text())['fields'][0]
    assert row['kind']=='unsure'
    assert len(row['candidates'])==6
    assert all(c['options'] and c['option_nodes'] for c in row['candidates'])
    assert browser.js("document.querySelectorAll('[data-test-panel]').length")==0


def test_skeleton_preserves_equal_text_tables_as_distinct_candidates(browser):
    field,_=panels(browser,count=2)
    key=' / '.join(str(field[k]) for k in ('section','occurrence','label','nth') if field[k]!='')
    source=browser.out/'equal-tables.json';target=browser.out/'skeleton.json'
    candidates=[dict(handle=100,options=['本科','硕士']),dict(handle=101,options=['本科','硕士'])]
    source.write_text(json.dumps(dict(url=browser.url,fields=[dict(key=key,kind='unsure',candidates=candidates)])))
    result=browser.command('plan-skeleton',target,'--from-options',source)
    assert result.returncode==0,result.stdout+result.stderr
    row=next(f for f in json.loads(target.read_text())['fields'] if f['label']=='学历')
    assert row['candidates']==candidates
    assert row['agent_decision_required'] is True
    assert not row.get('options')


@pytest.mark.parametrize('choices',[
    {'panel_selector':'#p0','panel_selectors':['#p0',None]},
    {'option_selectors':['#p0o0']},
    {'option_selectors':['',None]},
    {'panel_selectors':[3,None]},
])
def test_invalid_choice_arrays_reject_plan_before_any_actions(browser,choices):
    _,plan=panels(browser,count=1)
    plan.update(kind='cascader',value=['本科','硕士'],options=['本科','硕士'],**choices)
    path=browser.out/'bad-arrays.json'
    path.write_text(json.dumps({'fields':[plan]}))
    result=browser.command('fill',path)
    assert result.returncode==2,result.stdout
    assert 'ERR_PLAN' in result.stdout
    assert browser.js('window.choiceAudit')==[]


def cascade(browser, split=False, ambiguous=False):
    browser.document('<style>.pick{display:block;width:180px;height:28px;cursor:pointer}</style><label for=field>入学日期</label><input id=field readonly style="width:180px;height:30px">')
    browser.js('''(() => {
      window.choiceAudit=[];
      const field=document.getElementById('field');
      const item=(panel,id,text,action)=>{
        const node=document.createElement('span');node.id=id;node.className='pick';node.textContent=text;
        node.onclick=e=>{e.stopPropagation();window.choiceAudit.push(id);action(node)};panel.append(node);
      };
      const month=(id)=>{
        const panel=document.createElement('div');panel.id=id;panel.dataset.testPanel='1';
        panel.style='position:absolute;left:'+(id==='month'?240:460)+'px;top:80px;width:200px;height:70px';
        item(panel,id+'9','9月',()=>{field.value='2024-09';document.querySelectorAll('[data-test-panel]').forEach(p=>p.remove())});
        item(panel,id+'10','10月',()=>{field.value='2024-10';document.querySelectorAll('[data-test-panel]').forEach(p=>p.remove())});
        return panel;
      };
      field.onclick=()=>{
        const old=[...document.querySelectorAll('[data-test-panel]')];
        if(old.length){old.forEach(p=>p.remove());return;}
        const panel=document.createElement('div');panel.id='years';panel.dataset.testPanel='1';
        panel.style='position:absolute;left:20px;top:80px;width:200px;height:140px';
        item(panel,'y2024','2024',node=>{
          field.value='2024';node.classList.add('chosen');
          if(SPLIT){document.body.append(month('month'));if(AMBIGUOUS)document.body.append(month('other'));}
        });
        item(panel,'y2025','2025',()=>{field.value='2025'});
        if(!SPLIT){item(panel,'m9','9月',()=>{field.value='2024-09';panel.remove()});
                    item(panel,'m10','10月',()=>{field.value='2024-10';panel.remove()});}
        document.body.append(panel);
      };
    })()'''.replace('SPLIT',str(split).lower()).replace('AMBIGUOUS',str(ambiguous).lower()))
    f=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['tag']=='input')
    plan={k:f[k] for k in ('section','occurrence','label','nth')}
    plan.update(kind='cascader',value=['2024','9月'],display='2024-09')
    return plan


def test_second_level_ambiguity_keeps_first_step_and_readback(browser):
    plan=cascade(browser,split=True,ambiguous=True)
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert not ok and report['reason']=='ambiguous-panel',report
    assert [a['action'] for a in report['performed_steps']]==['opened-control','clicked-option']
    assert browser.js('window.choiceAudit')==['y2024']
    assert report['readback']['display']=='2024'
    assert report['panel_left_open'] is False


def test_explicit_choices_work_on_each_cascade_level(browser):
    plan=cascade(browser,split=True,ambiguous=True)
    plan.update(panel_selectors=['#years','#month'],option_selectors=['#y2024','#month9'])
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert ok,report
    assert browser.js('window.choiceAudit')==['y2024','month9']
    assert browser.js("document.getElementById('field').value")=='2024-09'


def test_null_second_choice_can_stay_in_same_cascade_panel(browser):
    plan=cascade(browser)
    plan['panel_selectors']=['#years',None]
    plan['option_selectors']=['#y2024',None]
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert ok,report
    assert browser.js('window.choiceAudit')==['y2024','m9']


def test_search_ambiguity_reports_typed_term_without_claiming_selection(browser):
    _,plan=panels(browser,count=2)
    browser.js("document.getElementById('field').readOnly=false")
    plan['kind']='search'
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert not ok and report['reason']=='ambiguous-panel',report
    assert any(a['action']=='typed-term' for a in report['performed_steps'])
    assert report['readback']['display']=='硕士'
    assert browser.js('window.choiceAudit')==[]


def test_custom_attribute_visibility_change_is_observed_without_site_names(browser):
    browser.document('<style>#p[data-open="no"]{display:none}.pick{display:block;width:180px;height:28px;cursor:pointer}</style><label for=field>学历</label><input id=field readonly><div id=p data-open=no><span class=pick id=a>本科</span><span class=pick id=b>硕士</span></div>')
    browser.js("document.getElementById('field').onclick=()=>document.getElementById('p').setAttribute('data-open','yes');document.getElementById('b').onclick=()=>{document.getElementById('field').value='硕士';document.getElementById('p').setAttribute('data-open','no')}")
    f=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['tag']=='input')
    item={k:f[k] for k in ('section','occurrence','label','nth')}
    item.update(kind='dropdown',value='硕士')
    ok,report=browser.cdp._fill_one(browser.tab,item,{'panel':.1,'option':.1})
    assert ok,report
    assert browser.js("document.getElementById('field').value")=='硕士'


def test_open_panel_stops_remaining_plan_even_if_later_field_is_uncovered(browser):
    _,item=panels(browser,count=1)
    browser.js('''(() => {
      const f=document.getElementById('field'),open=f.onclick;
      f.onclick=()=>{
        if(document.querySelector('[data-test-panel]'))return;
        open();document.getElementById('p0o1').onclick=e=>{
          e.stopPropagation();f.value='硕士';window.choiceAudit.push('p0o1');
        };
      };
      document.body.insertAdjacentHTML('beforeend','<div style="margin-top:250px"><label for=later>备注</label><input id=later></div>');
    })()''')
    f=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['label']=='备注')
    second={k:f[k] for k in ('section','occurrence','label','nth')};second.update(kind='text',value='不应执行')
    item['options']=['本科','硕士']
    path=browser.out/'stuck-panel.json';path.write_text(json.dumps(dict(fields=[item,second],pace=dict(min=0,max=0),panel_wait=.2)))
    result=browser.command('fill',path)
    assert result.returncode==1,result.stdout
    assert browser.js("document.getElementById('field').value")=='硕士'
    assert browser.js("document.getElementById('later').value")==''


def test_missing_observer_evidence_does_not_claim_the_panel_is_closed(browser):
    browser.document('<style>#p{display:none;position:absolute;top:80px}#field:focus+#p{display:block}.pick{display:block;width:180px;height:28px;cursor:pointer}</style><label for=field>学历</label><input id=field readonly><div id=p><span class=pick>本科</span><span class=pick>硕士</span></div>')
    f=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['tag']=='input')
    item={k:f[k] for k in ('section','occurrence','label','nth')};item.update(kind='dropdown',value='硕士')
    ok,report=browser.cdp._fill_one(browser.tab,item,{'panel':.1,'option':.1})
    assert not ok
    assert report['reason']=='no-panel'
    assert report['panel_status_unknown'] is True
    assert report['panel_left_open'] is None


def test_search_write_failure_reports_unconfirmed_panel_state(browser):
    _,plan=panels(browser,count=1)
    plan['kind']='search'  # readonly carrier: input attempt fails after opening
    ok,report=browser.cdp._fill_one(browser.tab,plan,{'panel':.1,'option':.1})
    assert not ok
    assert report['panel_status_unknown'] is True
    assert [s['action'] for s in report['performed_steps']]==['opened-control']


def test_long_option_text_can_prove_zero_height_portal_closed(browser):
    value='一个完整显示在下拉菜单中的虚构学校名称，长度超过旧版短文本假设'
    browser.document('<label for=field>学校名称</label><input id=field readonly>')
    browser.js('''(() => {
      const f=document.getElementById('field');
      f.onclick=()=>{
        if(document.getElementById('wrap'))return;
        const root=document.createElement('div');root.id='wrap';root.style='height:0';
        const pane=document.createElement('div');pane.style='position:absolute;left:30px;top:80px;width:360px';
        const item=document.createElement('span');item.style='display:block;cursor:pointer;min-height:36px';
        item.textContent=VALUE;item.onclick=e=>{e.stopPropagation();f.value=VALUE;pane.style.display='none'};
        pane.append(item);root.append(pane);document.body.append(root);
      };
    })()'''.replace('VALUE',json.dumps(value)))
    f=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['tag']=='input')
    item={k:f[k] for k in ('section','occurrence','label','nth')}
    item.update(kind='dropdown',value=value,panel_selector='#wrap')
    ok,report=browser.cdp._fill_one(browser.tab,item,{'panel':.1,'option':.1})
    assert ok,report
    assert report['panel_left_open'] is False


def native_select(browser, duplicate=True):
    browser.document('<label for=field>学历</label><select id=field><option value="">请选择</option><option id=first value=native-a>本科</option>'
                     + ('<option id=second value=native-b>本科</option>' if duplicate else '')+'</select>')
    f=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['tag']=='select')
    item={k:f[k] for k in ('section','occurrence','label','nth')};item.update(kind='native-select',value='本科')
    return item


def test_duplicate_native_labels_do_not_select_first(browser):
    item=native_select(browser)
    ok,report=browser.cdp._fill_one(browser.tab,item,{})
    assert not ok
    assert browser.js("document.getElementById('field').selectedIndex")==0
    assert report['reason']=='ambiguous-option'


def test_agent_can_select_second_native_duplicate(browser):
    item=native_select(browser);item['option_selector']='#second'
    ok,report=browser.cdp._fill_one(browser.tab,item,{})
    assert ok,report
    assert browser.js("document.getElementById('field').value")=='native-b'
    assert browser.js("document.getElementById('field').selectedIndex")==2


def test_native_label_and_encoded_value_can_be_verified(browser):
    item=native_select(browser,duplicate=False)
    ok,report=browser.cdp._fill_one(browser.tab,item,{})
    assert ok,report
    assert browser.js("document.getElementById('field').value")=='native-a'


def test_missing_target_never_overwrites_existing_text(browser):
    browser.document('<label for=field>备注</label><input id=field value="已有内容">')
    f=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['tag']=='input')
    item={k:f[k] for k in ('section','occurrence','label','nth')};item.update(kind='text',value=None)
    ok,report=browser.cdp._fill_one(browser.tab,item,{})
    assert not ok
    assert browser.js("document.getElementById('field').value")=='已有内容'
    assert report['reason']=='missing-value'


def test_empty_cascade_has_no_actions_to_execute(browser):
    item=cascade(browser);item['value']=[]
    ok,report=browser.cdp._fill_one(browser.tab,item,{'panel':.1,'option':.1})
    assert not ok and report['reason']=='missing-value'
    assert browser.js('window.choiceAudit')==[]


def test_invalid_second_level_choice_closes_new_panel_after_first_is_removed(browser):
    item=cascade(browser,split=True)
    browser.js('''(() => {
      const f=document.getElementById('field'),open=f.onclick;
      f.onclick=()=>{open();const y=document.getElementById('y2024');if(y){const select=y.onclick;
        y.onclick=e=>{select(e);document.getElementById('years').remove()};}};
    })()''')
    item['panel_selectors']=['#years','#missing']
    ok,report=browser.cdp._fill_one(browser.tab,item,{'panel':.1,'option':.1})
    assert not ok and report['reason']=='invalid-panel-choice',report
    assert browser.js("document.querySelectorAll('[data-test-panel]').length")==0
