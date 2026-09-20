import json, os, subprocess, sys
import pytest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fake_cdp import FakeCDP
SCRIPT = os.path.join(HERE, '..', 'skills', 'campus-apply', 'scripts', 'browser', 'chrome_cdp.py')


@pytest.fixture
def cdp():
    srv = FakeCDP().start()
    yield srv
    srv.stop()


def run(port, *args, env=None, cwd=None):
    e = dict(os.environ, CA_CDP_PORT=str(port))
    e.pop('TAB_MARK', None); e.pop('TAB_MATCH', None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=e, cwd=cwd, timeout=60)


def test_list_prints_only_page_targets_with_index_title_url_id(cdp):
    cdp.add('aaa111', '示例公司校招', 'https://jobs.example.com/campus#/home')
    cdp.add('bbb222', 'Omnibox', 'chrome://omnibox', ttype='browser_ui')
    cdp.add('ccc333', '新标签页', 'chrome://newtab')
    r = run(cdp.port, 'list')
    assert r.returncode == 0, r.stderr
    lines = r.stdout.rstrip('\n').split('\n')
    assert lines == ['1\t示例公司校招\thttps://jobs.example.com/campus#/home\taaa111',
                     '2\t新标签页\tchrome://newtab\tccc333']


def test_list_filters_by_keyword_in_title_or_url(cdp):
    cdp.add('aaa111', '示例公司校招', 'https://jobs.example.com/campus#/home')
    cdp.add('ccc333', '新标签页', 'chrome://newtab')
    r = run(cdp.port, 'list', 'example')
    assert r.stdout.rstrip('\n').split('\n') == ['1\t示例公司校招\thttps://jobs.example.com/campus#/home\taaa111']


def test_list_without_browser_reports_err_no_cdp():
    import socket
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    r = run(port, 'list')
    assert r.stdout.startswith('ERR_NO_CDP')
    assert str(port) in r.stdout and 'launch' in r.stdout
    assert r.returncode == 2


def _js(tmp_path, body, name='a.js'):
    p = tmp_path / name
    p.write_text(body, encoding='utf-8')
    return str(p)


def test_exec_runs_js_in_the_tab_carrying_tab_mark_and_prints_string_raw(cdp, tmp_path):
    other = cdp.add('aaa111', '用户自己的页', 'https://jobs.example.com/campus#/job/1')
    mine = cdp.add('bbb222', '工作页', 'https://jobs.example.com/campus#/job/2')
    mine.mark = 'run1'
    mine.answers['document.title'] = '工作页'
    r = run(cdp.port, 'exec', _js(tmp_path, 'document.title'), env={'TAB_MARK': 'run1'})
    assert r.returncode == 0, r.stderr
    assert r.stdout == '工作页\n'
    assert 'document.title' not in other.evaluated


def test_exec_dumps_non_string_results_as_json(cdp, tmp_path):
    t = cdp.add('bbb222', '工作页', 'https://x/'); t.mark = 'run1'
    t.answers['({a:1,b:[true,"中"]})'] = {'a': 1, 'b': [True, '中']}
    r = run(cdp.port, 'exec', _js(tmp_path, '({a:1,b:[true,"中"]})'), env={'TAB_MARK': 'run1'})
    assert json.loads(r.stdout) == {'a': 1, 'b': [True, '中']}


def test_exec_prints_err_js_on_exception(cdp, tmp_path):
    t = cdp.add('bbb222', '工作页', 'https://x/'); t.mark = 'run1'
    t.answers['boom()'] = ReferenceError('ReferenceError: boom is not defined')
    r = run(cdp.port, 'exec', _js(tmp_path, 'boom()'), env={'TAB_MARK': 'run1'})
    assert r.stdout.startswith('ERR_JS: ReferenceError: boom is not defined')
    assert r.returncode == 1


def test_exec_no_tab_with_mark_prints_no_matching_tab(cdp, tmp_path):
    cdp.add('bbb222', '工作页', 'https://x/').mark = 'other'
    r = run(cdp.port, 'exec', _js(tmp_path, '1'), env={'TAB_MARK': 'run1'})
    assert r.stdout == 'NO_MATCHING_TAB\n' and r.returncode == 1


def test_exec_falls_back_to_tab_match_url_substring(cdp, tmp_path):
    cdp.add('aaa111', 'a', 'https://a.example/')
    t = cdp.add('bbb222', 'b', 'https://jobs.example.com/campus#/me/resume')
    t.answers['1+1'] = 2
    r = run(cdp.port, 'exec', _js(tmp_path, '1+1'), env={'TAB_MATCH': 'me/resume'})
    assert r.stdout == '2\n'


def test_exec_requires_mark_or_match_and_existing_file(cdp, tmp_path):
    r = run(cdp.port, 'exec', _js(tmp_path, '1'))
    assert r.stdout.startswith('ERR_NEED_TAB_MARK_OR_TAB_MATCH') and r.returncode == 2
    r = run(cdp.port, 'exec', str(tmp_path / 'nope.js'), env={'TAB_MARK': 'run1'})
    assert r.stdout.startswith('ERR_NO_FILE') and r.returncode == 2


def test_exec_skips_a_tab_that_never_answers(cdp, tmp_path):
    hung = cdp.add('aaa111', '卡住的页', 'https://x/1'); hung.hang = True
    t = cdp.add('bbb222', '工作页', 'https://x/2'); t.mark = 'run1'; t.answers['1'] = 1
    r = run(cdp.port, 'exec', _js(tmp_path, '1'), env={'TAB_MARK': 'run1', 'CA_CDP_TIMEOUT': '1'})
    assert r.stdout == '1\n'


def test_claim_by_index_writes_mark_and_prints_id_and_url(cdp):
    cdp.add('aaa111', 'a', 'https://a.example/')
    t = cdp.add('bbb222', 'b', 'https://jobs.example.com/campus#/home')
    r = run(cdp.port, 'claim', '2', 'run7')
    assert r.stdout == 'run7\thttps://jobs.example.com/campus#/home\n', r.stderr
    assert t.mark == 'run7'


def test_claim_generates_run_id_when_omitted(cdp):
    t = cdp.add('bbb222', 'b', 'https://x/')
    r = run(cdp.port, 'claim', '1')
    rid, url = r.stdout.rstrip('\n').split('\t')
    assert rid.startswith('ca') and len(rid) >= 6 and t.mark == rid and url == 'https://x/'


def test_claim_accepts_target_id(cdp):
    cdp.add('aaa111', 'a', 'https://a/')
    t = cdp.add('bbb222', 'b', 'https://b/')
    r = run(cdp.port, 'claim', 'bbb222', 'run8')
    assert t.mark == 'run8' and r.stdout.startswith('run8\t')


def test_claim_bad_index_reports_err_no_such_tab(cdp):
    cdp.add('aaa111', 'a', 'https://a/')
    r = run(cdp.port, 'claim', '9')
    assert r.stdout.startswith('ERR_NO_SUCH_TAB') and r.returncode == 1


def test_open_creates_tab_waits_for_load_and_claims_it(cdp):
    cdp.add('aaa111', 'a', 'https://a/')
    r = run(cdp.port, 'open', 'https://jobs.example.com/campus#/me/resume', 'run9')
    assert r.stdout == 'run9\thttps://jobs.example.com/campus#/me/resume\n', r.stderr
    assert cdp.new_calls == ['https://jobs.example.com/campus#/me/resume']
    new = cdp.tabs[-1]
    assert new.mark == 'run9'
    assert new.evaluated.index('document.readyState') < len(new.evaluated) - 1  # 先等加载完再写标记


def test_screenshot_brings_tab_to_front_and_writes_png(cdp, tmp_path):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    out = tmp_path / 'screens' / 's.png'
    r = run(cdp.port, 'screenshot', str(out), env={'TAB_MARK': 'run1'})
    assert r.returncode == 0, r.stderr
    assert out.read_bytes() == b'\x89PNG fake' and t.front == 1
    assert r.stdout.strip() == str(out)


BROWSER_DIR = os.path.join(HERE, '..', 'skills', 'campus-apply', 'scripts', 'browser')


def test_stage_injects_libs_then_stage_and_polls_log_until_done(cdp, tmp_path):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    seen = {}

    def responder(expr):
        if "window.__caRun='" in expr and 'LIB_ONE' in expr:
            seen['run'] = expr.split("window.__caRun='", 1)[1].split("'", 1)[0]
            seen['script'] = expr
            return None
        if seen.get('run') and f"window.__caRun==='{seen['run']}'" in expr:
            seen['polls'] = seen.get('polls', 0) + 1
            return 'step1\nDONE' if seen['polls'] >= 2 else 'step1'
        return NotImplemented
    t.responder = responder
    lib = _js(tmp_path, 'const LIB_ONE = 1', 'lib.js')            # 故意不带分号
    stage = _js(tmp_path, "(async () => { window.__ca.L('DONE') })()", 'stage.js')
    r = run(cdp.port, 'stage', stage, '--libs', lib, '--max', '10', env={'TAB_MARK': 'run1'})
    assert r.returncode == 0, r.stderr
    assert r.stdout.rstrip('\n').endswith('step1\nDONE')
    body = seen['script']
    assert body.index("window.__calog=''") < body.index('LIB_ONE') < body.index('(async')
    assert 'const LIB_ONE = 1\n;' in body or 'const LIB_ONE = 1;' in body


def test_stage_reports_timeout_with_last_log(cdp, tmp_path):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    t.responder = lambda expr: 'still running' if 'window.__caRun===' in expr else None
    stage = _js(tmp_path, "(async () => {})()", 'stage.js')
    r = run(cdp.port, 'stage', stage, '--max', '2', env={'TAB_MARK': 'run1'})
    assert 'still running' in r.stdout and 'timeout 2s' in r.stdout


def _read_urls_tab(cdp, texts, captcha_at=None):
    """模拟一个可导航的标签页：location.href 赋值改 url；read_page.js 返回 texts[url]；guard.js 第 captcha_at 次起报验证码。"""
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    state = {'guards': 0}

    def responder(expr):
        if expr.startswith("location.href='"):
            t.url = expr.split("'", 2)[1]
            return 'nav'
        if 'read_page.js' in expr:
            return json.dumps({'url': t.url, 'title': 'p', 'text': texts.get(t.url, ''), 'links': []})
        if 'guard.js' in expr:
            state['guards'] += 1
            hit = captcha_at is not None and state['guards'] >= captcha_at
            return json.dumps({'url': t.url, 'captcha': hit, 'loginRedirect': False})
        return NotImplemented
    t.responder = responder
    return t, state


def test_read_urls_saves_each_page_and_reports_done_count(cdp, tmp_path):
    long = '岗位描述' * 100
    t, _ = _read_urls_tab(cdp, {'https://x/job/j1': long, 'https://x/job/j2': long})
    lst = tmp_path / 'list.tsv'
    lst.write_text('j1\thttps://x/job/j1\nj2\thttps://x/job/j2\n', encoding='utf-8')
    out = tmp_path / 'out'
    r = run(cdp.port, 'read-urls', str(lst), str(out), env={'TAB_MARK': 'run1', 'PACE_MIN': '0', 'PACE_MAX': '0'})
    assert r.returncode == 0, r.stderr
    assert json.load(open(out / 'j1.json', encoding='utf-8'))['text'] == long
    assert (out / 'j2.json').exists()
    assert r.stdout.rstrip('\n').split('\n')[-1] == 'done 2/2'


def test_read_urls_marks_miss_when_text_too_short_or_url_mismatch(cdp, tmp_path):
    t, _ = _read_urls_tab(cdp, {'https://x/job/j1': '太短', 'https://x/job/j2': '岗位描述' * 100})
    lst = tmp_path / 'list.tsv'
    lst.write_text('j1\thttps://x/job/j1\nj2\thttps://x/job/j2\n', encoding='utf-8')
    r = run(cdp.port, 'read-urls', str(lst), str(tmp_path / 'out'), env={'TAB_MARK': 'run1', 'PACE_MIN': '0', 'PACE_MAX': '0'})
    assert 'MISS j1' in r.stdout and 'MISS j2' not in r.stdout and r.stdout.rstrip('\n').endswith('done 1/2')


def test_read_urls_stops_when_guard_sees_captcha(cdp, tmp_path):
    texts = {f'https://x/job/j{i}': '岗位描述' * 100 for i in range(1, 7)}
    t, state = _read_urls_tab(cdp, texts, captcha_at=1)
    lst = tmp_path / 'list.tsv'
    lst.write_text(''.join(f'j{i}\thttps://x/job/j{i}\n' for i in range(1, 7)), encoding='utf-8')
    r = run(cdp.port, 'read-urls', str(lst), str(tmp_path / 'out'), env={'TAB_MARK': 'run1', 'PACE_MIN': '0', 'PACE_MAX': '0', 'GUARD_EVERY': '2'})
    assert 'STOP guard' in r.stdout and state['guards'] == 1
    assert not (tmp_path / 'out' / 'j3.json').exists()


def test_read_urls_honours_line_range(cdp, tmp_path):
    texts = {f'https://x/job/j{i}': '岗位描述' * 100 for i in range(1, 4)}
    _read_urls_tab(cdp, texts)
    lst = tmp_path / 'list.tsv'
    lst.write_text(''.join(f'j{i}\thttps://x/job/j{i}\n' for i in range(1, 4)), encoding='utf-8')
    r = run(cdp.port, 'read-urls', str(lst), str(tmp_path / 'out'), '2', '3', env={'TAB_MARK': 'run1', 'PACE_MIN': '0', 'PACE_MAX': '0'})
    assert not (tmp_path / 'out' / 'j1.json').exists() and (tmp_path / 'out' / 'j3.json').exists()
    assert r.stdout.rstrip('\n').endswith('done 2/2')


def test_launch_reports_browser_already_on_port_without_starting(cdp):
    r = run(cdp.port, 'launch', env={'CA_BROWSER': '/nonexistent/chrome'})
    assert r.returncode == 0 and 'Chrome/999.0' in r.stdout and str(cdp.port) in r.stdout


def test_launch_without_browser_binary_reports_err_no_browser(tmp_path):
    import socket
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    r = run(port, 'launch', env={'CA_BROWSER': str(tmp_path / 'nope.exe')})
    assert r.stdout.startswith('ERR_NO_BROWSER') and r.returncode == 2


def test_launch_args_include_port_profile_and_url():
    sys.path.insert(0, BROWSER_DIR)
    import chrome_cdp
    args = chrome_cdp.launch_args('/x/chrome', 9222, '/home/u/campus-apply-chrome', 'https://a/')
    assert args[0] == '/x/chrome'
    assert '--remote-debugging-port=9222' in args and '--user-data-dir=/home/u/campus-apply-chrome' in args
    assert '--no-first-run' in args and args[-1] == 'https://a/'
    assert '--disable-background-timer-throttling' in args and '--disable-renderer-backgrounding' in args   # 后台标签页不减速


def test_click_waits_until_the_element_stops_moving(cdp):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    calls = {'n': 0}

    def responder(expr):
        if 'getBoundingClientRect' in expr:
            calls['n'] += 1
            y = 300 if calls['n'] >= 3 else 100 * calls['n']     # 前两次还在滚动，第三次起稳定
            return '{"x":50,"y":%d,"tag":"DIV"}' % y
        return NotImplemented
    t.responder = responder
    r = run(cdp.port, '--mark', 'run1', 'click', '.btn')
    assert r.stdout == 'clicked DIV 50,300\n', r.stdout
    assert all(m['y'] == 300 for m in t.mouse)


def test_stage_keeps_polling_while_tab_is_temporarily_unreachable(cdp, tmp_path):
    import threading
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'

    def responder(expr):
        if "window.__caRun='" in expr:
            t.mark = None                                   # 注入后页面“导航中”，探测不到标记
            threading.Timer(3, lambda: setattr(t, 'mark', 'run1')).start()
            return None
        if 'window.__caRun===' in expr:
            return 'DONE'
        return NotImplemented
    t.responder = responder
    stage = _js(tmp_path, "(async () => {})()", 'stage.js')
    r = run(cdp.port, 'stage', stage, '--max', '20', env={'TAB_MARK': 'run1'})
    assert r.stdout.rstrip('\n') == 'DONE', r.stdout


def test_list_reports_browser_identity_on_stderr(cdp):
    cdp.add('aaa111', 'a', 'https://a/')
    r = run(cdp.port, 'list')
    assert r.stdout == '1\ta\thttps://a/\taaa111\n'
    assert 'Chrome/999.0' in r.stderr and str(cdp.port) in r.stderr


def test_list_warns_on_stderr_when_browser_is_headless(cdp):
    cdp.ua = 'Mozilla/5.0 HeadlessChrome/999.0 Safari/537.36'
    cdp.add('aaa111', 'a', 'https://a/')
    r = run(cdp.port, 'list')
    assert r.returncode == 0 and r.stdout.startswith('1\t')
    assert 'Headless' in r.stderr and 'CA_CDP_PORT' in r.stderr


def test_launch_refuses_port_held_by_headless_browser(cdp):
    cdp.ua = 'Mozilla/5.0 HeadlessChrome/999.0 Safari/537.36'
    r = run(cdp.port, 'launch', env={'CA_BROWSER': '/nonexistent/chrome'})
    assert r.returncode == 1 and r.stdout.startswith('ERR_PORT_IN_USE') and 'Headless' in r.stdout


def test_mark_flag_selects_tab_without_env(cdp, tmp_path):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'; t.answers['1+1'] = 2
    r = run(cdp.port, '--mark', 'run1', 'exec', _js(tmp_path, '1+1'))
    assert r.stdout == '2\n', r.stdout


def test_match_and_port_flags_without_env(cdp, tmp_path):
    t = cdp.add('bbb222', 'b', 'https://jobs.example.com/campus#/me/resume'); t.answers['1+1'] = 2
    e = dict(os.environ); e.pop('CA_CDP_PORT', None); e.pop('TAB_MARK', None); e.pop('TAB_MATCH', None)
    r = subprocess.run([sys.executable, SCRIPT, '--port', str(cdp.port), '--match', 'me/resume', 'exec', _js(tmp_path, '1+1')],
                       capture_output=True, text=True, env=e, timeout=60)
    assert r.stdout == '2\n', r.stdout


def test_flags_also_work_after_the_subcommand(cdp, tmp_path):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    out = tmp_path / 's.png'
    r = run(cdp.port, 'screenshot', str(out), '--mark', 'run1')
    assert r.returncode == 0 and out.exists()


def test_read_urls_pace_and_guard_every_flags(cdp, tmp_path):
    texts = {f'https://x/job/j{i}': '岗位描述' * 100 for i in range(1, 5)}
    t, state = _read_urls_tab(cdp, texts, captcha_at=1)
    lst = tmp_path / 'list.tsv'
    lst.write_text(''.join(f'j{i}\thttps://x/job/j{i}\n' for i in range(1, 5)), encoding='utf-8')
    r = run(cdp.port, '--mark', 'run1', 'read-urls', str(lst), str(tmp_path / 'out'), '--pace', '0-0', '--guard-every', '2')
    assert 'STOP guard' in r.stdout and state['guards'] == 1 and (tmp_path / 'out' / 'j2.json').exists()


def test_click_selector_sends_trusted_mouse_events_at_element_center(cdp):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    t.responder = lambda expr: '{"x":120.5,"y":300,"tag":"INPUT"}' if 'getBoundingClientRect' in expr and 'input.dob' in expr else NotImplemented
    r = run(cdp.port, '--mark', 'run1', 'click', 'input.dob')
    assert r.returncode == 0 and r.stdout == 'clicked INPUT 120.5,300\n', r.stdout
    types = [m['type'] for m in t.mouse]
    assert types == ['mouseMoved', 'mousePressed', 'mouseReleased']
    assert all(m['x'] == 120.5 and m['y'] == 300 for m in t.mouse)
    assert t.mouse[1]['button'] == 'left' and t.mouse[1]['clickCount'] == 1


def test_click_reports_no_element_when_selector_matches_nothing(cdp):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    t.responder = lambda expr: None if 'getBoundingClientRect' in expr else NotImplemented
    r = run(cdp.port, '--mark', 'run1', 'click', '.nope')
    assert r.stdout == 'NO_ELEMENT .nope\n' and r.returncode == 1 and t.mouse == []


def test_click_accepts_coordinates_and_js_expression(cdp):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    r = run(cdp.port, '--mark', 'run1', 'click', '40,50')
    assert r.stdout == 'clicked 40,50\n' and [m['type'] for m in t.mouse] == ['mouseMoved', 'mousePressed', 'mouseReleased']
    t.mouse.clear()
    t.responder = lambda expr: '{"x":1,"y":2,"tag":"DIV"}' if 'getBoundingClientRect' in expr and "innerText.trim()==='广东'" in expr else NotImplemented
    r = run(cdp.port, '--mark', 'run1', 'click', "js:[...document.querySelectorAll('li')].find(e=>e.innerText.trim()==='广东')")
    assert r.stdout == 'clicked DIV 1,2\n' and len(t.mouse) == 3


def test_stage_injection_does_not_wait_for_the_async_script_to_finish(cdp, tmp_path):
    """stage 脚本是 (async () => {...})()，注入只等注入本身，不等它跑完；否则长脚本必超时。"""
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'; t.slow_promise = True
    t.responder = lambda expr: 'DONE' if 'window.__caRun===' in expr else None
    stage = _js(tmp_path, "(async () => { await new Promise(r => setTimeout(r, 60000)); })()", 'stage.js')
    r = run(cdp.port, '--mark', 'run1', 'stage', stage, '--max', '10', env={'CA_CDP_TIMEOUT': '1'})
    assert 'ERR_CDP' not in r.stdout and r.stdout.rstrip('\n') == 'DONE', r.stdout
    inject = next(i for i, e in enumerate(t.evaluated) if '(async' in e)
    assert t.await_flags[inject] is False


def test_known_subcommand_with_wrong_arguments_prints_its_usage_not_unknown_command(cdp):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    r = run(cdp.port, '--mark', 'run1', 'click', 'js:[...document.querySelectorAll("a")].find(e', '=>', 'e.innerText)')
    assert 'ERR_UNKNOWN_COMMAND' not in r.stdout
    assert r.stdout.startswith('ERR_USAGE click') and '引号' in r.stdout and r.returncode == 2


def test_claim_on_page_that_denies_storage_gives_a_clear_message(cdp):
    t = cdp.add('bbb222', '隐私设置错误', 'chrome-error://chromewebdata/'); t.deny_storage = True
    r = run(cdp.port, 'claim', '1', 'run1')
    assert r.stdout.startswith('ERR_CLAIM') and '存储' in r.stdout and r.returncode == 1


def test_screenshot_reports_write_failure_without_traceback(cdp, tmp_path):
    t = cdp.add('bbb222', 'b', 'https://x/'); t.mark = 'run1'
    out = tmp_path / 'nodir.png'
    out.parent.chmod(0o500)
    try:
        r = run(cdp.port, '--mark', 'run1', 'screenshot', str(out / 'x' / 'y.png'))
    finally:
        out.parent.chmod(0o700)
    assert 'Traceback' not in r.stderr and r.stdout.startswith('ERR_WRITE') and r.returncode == 1
