#!/usr/bin/env python3
"""Judge actual choice identities in isolated local Chrome, without calling a model."""
import argparse
import json
from pathlib import Path
import sys
import time

from browser_test_support import BrowserSession, ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True)
    parser.add_argument('--headless',action='store_true',help='this checker always isolates headless Chrome')
    args=parser.parse_args()
    out=Path(args.out).resolve()
    if out.is_relative_to(ROOT):
        parser.error('--out must be outside the repository')
    rows=[]
    with BrowserSession(out) as browser:
        for mode,choices,expected in [
            ('many',{},None),
            ('many',{'panel_selector':'#p4'},'p4o1'),
            ('duplicate',{},None),
            ('duplicate',{'option_selector':'#p0o1'},'p0o1'),
            ('inline',{},'p0o1'),
        ]:
            url=browser.url+'agent_choices.html?mode='+mode+'&run='+str(time.monotonic_ns())
            browser.tab.call('Page.navigate',url=url)
            deadline=time.monotonic()+10
            while not browser.js('document.readyState==="complete" && location.href==='+json.dumps(url)):
                if time.monotonic()>deadline: raise RuntimeError('fixture navigation timed out')
                time.sleep(.03)
            browser.js(browser.cdp._fill_lib())
            field=next(f for f in browser.call('window.__caFill.outline()')['fields'] if f['tag']=='input')
            item={k:field[k] for k in ('section','occurrence','label','nth')}
            item.update(kind='dropdown',value='同名项' if mode=='duplicate' else '硕士',**choices)
            ok,record=browser.cdp._fill_one(browser.tab,item,{'panel':.3,'option':.3})
            actual=browser.js('window.fixtureTruth()');audit=browser.js('window.fixtureAudit()')
            passed=(ok==(expected is not None) and actual['node']==expected
                    and audit['clicked']==([] if expected is None else [expected]) and audit['openPanels']==0)
            rows.append(dict(mode=mode,choices=choices,expected_node=expected,actual=actual,audit=audit,report=record,passed=passed))
            print(('PASS ' if passed else 'FAIL ')+mode+' '+str(choices))
    (out/'report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    return 0 if all(r['passed'] for r in rows) else 1


if __name__=='__main__':
    sys.exit(main())
