#!/usr/bin/env python3
"""Check that semantic addressing survives what global indexes do not.

A plan addressed by position breaks the moment the page grows a row: every index after the
insertion point shifts, and the model has to remap the whole table. Worse, a wrong index is
silently a different control — and the most sensitive fields sit at the very top of a form.

The page below has what makes that go wrong: two sections, repeated record groups, a pair of
controls sharing one label ("年"/"月"), a sensitive field at index 0, and a button that adds
another record group mid-session.

  python3 evals/semantic_plan_check.py --out /tmp/semantic-check [--headless]

Exit 0 = every case behaved as documented. No models, no recruitment sites.
"""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
BROWSER_DIR = HERE.parent / 'skills/campus-apply/scripts/browser'
CDP = BROWSER_DIR / 'chrome_cdp.py'

PAGE = '''<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>语义寻址</title>
<style>body{font:14px system-ui;margin:24px;width:900px}
h3{margin:18px 0 8px}.row{margin:8px 0}label{display:inline-block;width:92px}
input{padding:4px 8px;border:1px solid #bbb;border-radius:4px;width:180px}
.rec{border-left:3px solid #ddd;padding-left:10px;margin:10px 0}</style></head>
<body>
<h3>个人信息</h3>
<div class="rec">
  <!-- 敏感字段放在最前面：位置寻址写错一位，最先撞上的就是它 -->
  <div class="row"><label for="idcard">证件号码</label><input id="idcard" value=""></div>
  <div class="row"><label for="pname">姓名</label><input id="pname" value=""></div>
</div>

<h3>教育背景</h3>
<div id="edu">
  <div class="rec">
    <!-- 两个控件共用一个 label、都没有 placeholder：这时只给标签定位不到具体哪一个，
         必须靠"同一条记录里同名标签的第几个"区分。真实站点的"年/月""起/止"就是这样。 -->
    <div class="row"><label>入学</label><input data-f="y"><input data-f="m"></div>
    <div class="row"><label>学校名称</label><input data-f="school"></div>
  </div>
</div>
<button id="add">添加</button>

<h3>工作经历</h3>
<div class="rec">
  <div class="row"><label>公司名称</label><input data-f="company"></div>
  <!-- maxlength 写成 Infinity：真实站点见过这种写法，浏览器按"没有上限"对待，
       而把它直接 int() 会抛异常、让整条命令退出。 -->
  <div class="row"><label>工作描述</label><textarea data-f="duty" maxlength="Infinity"></textarea></div>
</div>

<script>
// 加一组教育经历：全局下标从这里往后全变，位置寻址的计划当场作废
document.getElementById('add').addEventListener('click', () => {
  const first = document.querySelector('#edu .rec');
  document.getElementById('edu').appendChild(first.cloneNode(true));
});
</script>
</body></html>
'''


def browser_path():
    candidates = [os.environ.get('CA_BROWSER'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                  shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome')]
    return next((p for p in candidates if p and Path(p).is_file()), None)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class Driver:
    def __init__(self, port, out, mark):
        self.env = dict(os.environ, CA_CDP_PORT=str(port))
        self.env.pop('TAB_MARK', None)
        self.env.pop('TAB_MATCH', None)
        self.out, self.mark = out, mark

    def run(self, phase, *args, check=True):
        r = subprocess.run([sys.executable, str(CDP), *args], env=self.env,
                           capture_output=True, text=True, timeout=90)
        (self.out / (phase + '.out')).write_text(
            r.stdout + ('\n--- stderr ---\n' + r.stderr if r.stderr else ''), encoding='utf-8')
        if check and r.returncode:
            raise RuntimeError(phase + ' exited ' + str(r.returncode) + ': '
                               + (r.stdout + r.stderr).strip()[:400])
        return r

    def marked(self, phase, *args, check=True):
        return self.run(phase, '--mark', self.mark, *args, check=check)


def check_cases(driver, url, out, rows):
    def case(name, ok, detail=''):
        rows.append((name, bool(ok), str(detail)[:300]))

    driver.run('open', 'open', url + '/semantic.html', driver.mark)

    # --- 骨架生成 ---
    skeleton = out / 'plan.json'
    driver.marked('skeleton', 'plan-skeleton', str(skeleton))
    plan = json.loads(skeleton.read_text(encoding='utf-8'))
    fields = plan['fields']
    by_key = {f['key']: f for f in fields}

    case('骨架把字段按板块分开',
         len({f['section'] for f in fields}) >= 3,
         '板块：' + str(sorted({f['section'] for f in fields})))
    case('骨架里每个字段的 value 都是空的，等模型填',
         all(f['value'] is None for f in fields),
         str(sum(1 for f in fields if f['value'] is not None)) + ' 个不是 null')
    case('共用标签的两个控件靠 nth 区分',
         len([f for f in fields if f['label'] == '入学']) == 2
         and sorted(f['nth'] for f in fields if f['label'] == '入学') == [1, 2],
         str([(f['label'], f['nth']) for f in fields if f['label'] == '入学']))
    junk = [f for f in fields if f['label'] == '工作描述']
    case('maxlength 是非数字时不崩，且不写 max',
         len(junk) == 1 and 'max' not in junk[0],
         '取到的字段：' + str(junk))
    sensitive = [f for f in fields if '敏感' in (f.get('note') or '')]
    case('证件号被标成敏感字段', any('证件' in f['label'] for f in sensitive),
         '标注的有：' + str([f['label'] for f in sensitive]))

    # --- 加一组条目之后，语义坐标仍然指向原来那个字段 ---
    before = [f for f in fields if f['section'] == '教育背景' and f['label'] == '学校名称']
    driver.marked('add_row', 'click', '#add')
    time.sleep(.4)
    after_path = out / 'plan2.json'
    driver.marked('skeleton2', 'plan-skeleton', str(after_path))
    after = json.loads(after_path.read_text(encoding='utf-8'))['fields']
    schools = [f for f in after if f['section'] == '教育背景' and f['label'] == '学校名称']
    case('加一组条目后，原字段的语义坐标没变',
         len(before) == 1 and len(schools) == 2
         and schools[0]['occurrence'] == before[0]['occurrence'],
         '加组前 occurrence=' + str(before[0]['occurrence'] if before else None)
         + '，加组后 ' + str([f['occurrence'] for f in schools]))

    # --- 按语义坐标写入 ---
    target = next(f for f in after
                  if f['section'] == '教育背景' and f['label'] == '学校名称'
                  and f['occurrence'] == 2)
    plan_write = out / 'write.json'
    plan_write.write_text(json.dumps({'fields': [
        dict(key='school2', title='第二条学校', label='学校名称', section=target['section'],
             occurrence=2, nth=target['nth'], kind='text', value='某某大学'),
    ]}, ensure_ascii=False), encoding='utf-8')
    r = driver.marked('fill_semantic', 'fill', str(plan_write), check=False)
    case('按语义坐标能写进第二条记录', r.returncode == 0 and 'DONE' in r.stdout,
         r.stdout.strip().splitlines()[0] if r.stdout.strip() else '')
    written = json.loads(driver.marked('read_back', 'exec', str(_js(
        out, 'JSON.stringify([...document.querySelectorAll(\'#edu .rec\')]'
             '.map(rec => rec.querySelector(\'[data-f=school]\').value))'))).stdout)
    case('写进去的是第二条，不是第一条', written == ['', '某某大学'], str(written))

    # --- 敏感字段默认拒绝 ---
    plan_secret = out / 'secret.json'
    plan_secret.write_text(json.dumps({'fields': [
        dict(key='idcard', label='证件号码', section='个人信息', occurrence=1, nth=1,
             kind='text', value='110101200001011234'),
    ]}, ensure_ascii=False), encoding='utf-8')
    r = driver.marked('fill_secret', 'fill', str(plan_secret), check=False)
    idval = driver.marked('read_id', 'exec', str(_js(
        out, "document.getElementById('idcard').value"))).stdout.strip()
    case('敏感字段默认不写入，并说明原因',
         '敏感字段' in r.stdout and idval == '',
         '控件现值=' + repr(idval) + '；输出首行=' + (r.stdout.strip().splitlines() or [''])[0])

    # --- 身份校验拦住寻址错误 ---
    plan_wrong = out / 'wrong.json'
    plan_wrong.write_text(json.dumps({'fields': [
        dict(key='x', title='寻址写错了的字段', label='公司名称',
             section='工作经历', occurrence=1, nth=1,
             kind='text', value='甲', expect_label='学校名称'),
    ]}, ensure_ascii=False), encoding='utf-8')
    r = driver.marked('fill_expect', 'fill', str(plan_wrong), check=False)
    company = driver.marked('read_company', 'exec', str(_js(
        out, "document.querySelector('[data-f=company]').value"))).stdout.strip()
    case('控件身份对不上就不动它', '身份校验不通过' in r.stdout and company == '',
         '控件现值=' + repr(company))

    # --- 旧格式（selector + index）显式开关后仍然能用 ---
    plan_old = out / 'old.json'
    plan_old.write_text(json.dumps({'addressing': 'selector', 'fields': [
        dict(key='name', label='姓名', selector='#pname', kind='text', value='张某某'),
    ]}, ensure_ascii=False), encoding='utf-8')
    r = driver.marked('fill_old', 'fill', str(plan_old), check=False)
    case('selector + index 的老计划加 addressing:selector 后仍然能跑',
         r.returncode == 0 and 'DONE' in r.stdout,
         (r.stdout.strip().splitlines() or [''])[0])

    # --- survey 只读摸清整页 ---
    survey_out = out / 'survey.json'
    r = driver.marked('survey', 'survey', str(survey_out))
    survey = json.loads(survey_out.read_text(encoding='utf-8'))
    case('survey 一次报出板块、字段、上传位三件事',
         len(survey['sections']) >= 3 and survey['upload']['directFileInputs'] == 0
         and 'SURVEY' in r.stdout,
         (r.stdout.strip().splitlines() or [''])[0])

    # --- 只补没填成的 ---
    report = out / 'prior.json'
    report.write_text(json.dumps({'fields': [
        {'key': k, 'status': 'filled'} for k in list(by_key)[:2]
    ]}, ensure_ascii=False), encoding='utf-8')
    thin = out / 'plan3.json'
    driver.marked('skeleton3', 'plan-skeleton', str(thin), '--skip-ok', str(report))
    left = json.loads(thin.read_text(encoding='utf-8'))['fields']
    case('--skip-ok 跳过上轮已填成的字段',
         all(f['key'] not in list(by_key)[:2] for f in left),
         '上轮两个已成的键还在不在：'
         + str([f['key'] for f in left if f['key'] in list(by_key)[:2]]))
    return dict(skeleton=plan, after_add=after, survey=survey)


def _js(out, expression):
    """把一个表达式写成临时 js 文件给 exec 用。exec 对字符串原样输出，所以这里不额外包装。"""
    path = out / ('expr_' + str(abs(hash(expression)) % 10**8) + '.js')
    path.write_text(expression, encoding='utf-8')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', required=True)
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args(argv)
    browser = browser_path()
    if not browser:
        parser.error('Chrome/Edge not found; set CA_BROWSER')
    out = Path(args.out).resolve()
    if out.is_relative_to(HERE.parent):
        parser.error('--out must be outside the repository')
    out.mkdir(parents=True, exist_ok=True)

    pages = Path(tempfile.mkdtemp(prefix='campus-apply-semantic-'))
    (pages / 'semantic.html').write_text(PAGE, encoding='utf-8')
    handler = functools.partial(QuietHandler, directory=str(pages))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    rows, proc, detail = [], None, None
    profile = tempfile.mkdtemp(prefix='campus-apply-semantic-profile-')
    try:
        command = [browser, '--user-data-dir=' + profile,
                   '--remote-debugging-port=' + str(port), '--no-first-run',
                   '--no-default-browser-check', '--disable-background-timer-throttling',
                   '--disable-renderer-backgrounding',
                   '--disable-backgrounding-occluded-windows',
                   '--window-size=1100,900', 'about:blank']
        if args.headless:
            command.insert(1, '--headless=new')
        with (out / 'browser.stderr').open('w') as stderr:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stderr)
            deadline = time.monotonic() + 20
            while True:
                try:
                    with urllib.request.urlopen(
                            'http://127.0.0.1:' + str(port) + '/json/version', timeout=1) as resp:
                        version = json.load(resp)['Browser']
                    break
                except OSError:
                    if time.monotonic() >= deadline or proc.poll() is not None:
                        raise RuntimeError('isolated browser did not start')
                    time.sleep(.2)
            print(version, flush=True)
            driver = Driver(port, out, 'semantic-check')
            try:
                detail = check_cases(driver, 'http://127.0.0.1:'
                                     + str(server.server_address[1]), out, rows)
            except Exception as error:
                rows.append(('检查跑完（没有中途异常）', False, repr(error)))
            (out / 'report.json').write_text(json.dumps(
                dict(browser=version, detail=detail,
                     cases=[dict(name=n, passed=p, detail=d) for n, p, d in rows]),
                ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        server.shutdown()
        server.server_close()
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(pages, ignore_errors=True)

    for name, passed, det in rows:
        print(('  ok   ' if passed else '  FAIL ') + name + (('  — ' + det) if det else ''),
              flush=True)
    failed = [r for r in rows if not r[1]]
    print('\n' + str(len(rows) - len(failed)) + '/' + str(len(rows))
          + ' 项按预期。明细：' + str(out / 'report.json'), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
