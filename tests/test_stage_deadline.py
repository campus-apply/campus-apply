"""Stage CLI regressions against the real HTTP/WebSocket driver, no live browser."""
import json
import re
import time
import pytest
from test_chrome_cdp import cdp, run, _js


def stage_tab(cdp, logs, *, delay=0, stale=False):
    tab = cdp.add('stage-tab', 'work', 'https://example.test/form')
    tab.mark = 'run1'
    state = {'polls': 0}

    def respond(expression):
        if "window.__caRun='" in expression:
            state['injection'] = expression
            state['run_id'] = expression.split("window.__caRun='", 1)[1].split("'", 1)[0]
            return None
        if 'window.__caRun===' in expression:
            time.sleep(delay)
            index = min(state['polls'], len(logs) - 1)
            state['polls'] += 1
            log = logs[index]
            if '__caStageSnapshot' in expression:
                return {'run_id': 'other' if stale else state['run_id'], 'log': log}
            return 'STALE:' + log if stale else log
        return NotImplemented
    tab.responder = respond
    return tab, state


def invoke(cdp, tmp_path, max_s='1', **kwargs):
    stage = _js(tmp_path, "(async () => { window.__ca.L('DONE') })()", 'stage.js')
    return run(cdp.port, 'stage', stage, '--max', max_s, env={'TAB_MARK': 'run1', **kwargs})


def test_stage_error_is_a_failure(cdp, tmp_path):
    stage_tab(cdp, ['step1\nERR cannot fill'])
    result = invoke(cdp, tmp_path)
    assert result.returncode == 1 and 'ERR cannot fill' in result.stdout


def test_stale_done_cannot_complete_current_run(cdp, tmp_path):
    stage_tab(cdp, ['DONE'], stale=True)
    result = invoke(cdp, tmp_path)
    assert result.returncode == 1 and 'ERR_STAGE_STALE' in result.stdout


def test_timeout_is_a_failure(cdp, tmp_path):
    stage_tab(cdp, ['still running'])
    result = invoke(cdp, tmp_path)
    assert result.returncode == 1 and 'timeout 1s' in result.stdout


def test_done_inside_field_text_is_not_terminal(cdp, tmp_path):
    stage_tab(cdp, ['field value: UNDONE; message ERR inside text'])
    result = invoke(cdp, tmp_path)
    assert result.returncode == 1 and 'timeout 1s' in result.stdout


def test_done_near_deadline_is_success(cdp, tmp_path):
    stage_tab(cdp, ['DONE'], delay=.65)
    started = time.monotonic()
    result = invoke(cdp, tmp_path)
    assert result.returncode == 0 and result.stdout.strip() == 'DONE'
    assert time.monotonic() - started < 1.6


def test_slow_poll_respects_total_deadline(cdp, tmp_path):
    stage_tab(cdp, ['still running'], delay=1.8)
    started = time.monotonic()
    result = invoke(cdp, tmp_path)
    assert result.returncode == 1 and 'timeout 1s' in result.stdout
    assert time.monotonic() - started < 1.6


def test_hung_target_locating_counts_toward_total_deadline(cdp, tmp_path):
    cdp.add('hung', 'blocked', 'https://example.test/hung').hang = True
    started = time.monotonic()
    result = invoke(cdp, tmp_path)
    assert result.returncode == 1 and 'timeout 1s' in result.stdout
    assert time.monotonic() - started < 1.6


@pytest.mark.parametrize('max_s', ['0', '-1', 'nan', 'inf', 'oops'])
def test_invalid_max_is_usage_failure(cdp, tmp_path, max_s):
    stage_tab(cdp, ['DONE'])
    result = invoke(cdp, tmp_path, max_s)
    assert result.returncode == 2 and 'ERR_USAGE stage' in result.stdout
    assert 'Traceback' not in result.stderr


def test_success_reuses_one_connection_and_locates_once(cdp, tmp_path):
    tab, state = stage_tab(cdp, ['work', 'DONE'])
    result = invoke(cdp, tmp_path, '4')
    assert result.returncode == 0 and result.stdout.strip() == 'DONE'
    assert tab.connections == 1
    assert sum("sessionStorage.getItem('__caClaim')" in expr for expr in tab.evaluated) == 1


def test_optional_timing_has_only_safe_metrics(cdp, tmp_path):
    stage_tab(cdp, ['DONE'])
    timing = tmp_path / 'timing.jsonl'
    result = invoke(cdp, tmp_path, CA_TIMING_FILE=str(timing))
    assert result.returncode == 0
    # 两行：stage 自己的分段计时，和每条命令都记的那一行（算命令之间的空置要用它）
    rows = [json.loads(line) for line in timing.read_text().splitlines() if line.strip()]
    assert len(rows) == 2
    staged = next(r for r in rows if 'status' in r)
    assert staged['command'] == 'stage' and staged['status'] == 'success'
    assert 0 <= staged['elapsed_seconds'] < 1.6
    assert set(staged) <= {'command', 'status', 'elapsed_seconds', 'locate_seconds',
                           'execute_seconds', 'wait_seconds'}
    outer = next(r for r in rows if 'started_at' in r)
    assert set(outer) == {'command', 'started_at', 'elapsed_seconds', 'exit_code'}
    assert outer['command'] == 'stage' and outer['exit_code'] == 0
    for row in rows:
        assert all(isinstance(v, (int, float)) and v >= 0
                   for k, v in row.items() if k.endswith('_seconds'))


def test_one_transient_disconnect_recovers_without_reinjecting(cdp, tmp_path):
    tab, state = stage_tab(cdp, ['DONE'])
    original = tab.responder
    dropped = []
    def respond(expression):
        if '__caStageSnapshot' in expression and not dropped:
            dropped.append(True)
            return ConnectionResetError('transient')
        return original(expression)
    tab.responder = respond
    result = invoke(cdp, tmp_path, '2')
    assert result.returncode == 0 and result.stdout.strip() == 'DONE'
    assert tab.connections == 2
    assert sum("window.__caRun='" in expr for expr in tab.evaluated) == 1


def test_repeated_disconnects_stop_before_full_deadline(cdp, tmp_path):
    tab, _ = stage_tab(cdp, ['DONE'])
    original = tab.responder
    tab.responder = lambda expr: ConnectionResetError('transient') if '__caStageSnapshot' in expr else original(expr)
    started = time.monotonic()
    result = invoke(cdp, tmp_path, '5')
    assert result.returncode == 1 and 'ERR_CDP' in result.stdout
    assert time.monotonic() - started < 2
    assert tab.connections == 3


def test_async_injection_catches_its_own_error_without_page_listener(cdp, tmp_path):
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('Node needed to execute the actual injected JavaScript')
    _, state = stage_tab(cdp, ['DONE'])
    stage = _js(tmp_path, "(async () => { await Promise.resolve(); throw new Error('synthetic-stage-error'); })()")
    result = run(cdp.port, 'stage', stage, '--max', '1', env={'TAB_MARK': 'run1'})
    assert result.returncode == 0
    script = "const window = {}; Promise.resolve(eval(" + json.dumps(state['injection']) + ")).then(() => console.log(window.__calog));"
    executed = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=5)
    assert executed.returncode == 0, executed.stderr
    assert 'ERR Error: synthetic-stage-error' in executed.stdout
    assert 'UnhandledPromiseRejection' not in executed.stderr


def test_async_error_cannot_overwrite_a_newer_run(cdp, tmp_path):
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('Node needed to execute the actual injected JavaScript')
    _, state = stage_tab(cdp, ['DONE'])
    stage = _js(tmp_path, "(async () => { window.__caRun='newer'; window.__calog='new log'; throw new Error('old error'); })()")
    result = run(cdp.port, 'stage', stage, '--max', '1', env={'TAB_MARK': 'run1'})
    assert result.returncode == 0
    script = "const window = {}; Promise.resolve(eval(" + json.dumps(state['injection']) + ")).then(() => console.log(window.__calog));"
    executed = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=5)
    assert executed.returncode == 0 and executed.stdout.strip() == 'new log'


def test_error_after_done_is_still_failure(cdp, tmp_path):
    stage_tab(cdp, ['DONE\nERR postcheck failed'])
    result = invoke(cdp, tmp_path)
    assert result.returncode == 1 and 'ERR postcheck failed' in result.stdout


def test_slow_injection_uses_the_same_deadline_as_polling(cdp, tmp_path):
    tab, _ = stage_tab(cdp, ['DONE'], delay=.4)
    original = tab.responder
    def respond(expression):
        if "window.__caRun='" in expression:
            time.sleep(.8)
        return original(expression)
    tab.responder = respond
    started = time.monotonic()
    result = invoke(cdp, tmp_path)
    assert result.returncode == 1 and 'timeout 1s' in result.stdout
    assert time.monotonic() - started < 1.6


def test_malformed_state_is_not_success(cdp, tmp_path):
    tab, _ = stage_tab(cdp, ['DONE'])
    original = tab.responder
    tab.responder = lambda expr: 'DONE' if '__caStageSnapshot' in expr else original(expr)
    result = invoke(cdp, tmp_path)
    assert result.returncode == 1 and 'ERR_STAGE_STATE' in result.stdout


def test_old_stage_can_use_injected_library_local_bindings(cdp, tmp_path):
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('Node needed to execute actual injected JavaScript')
    _, state = stage_tab(cdp, ['DONE'])
    lib = _js(tmp_path, 'const LIB_VALUE = 7', 'lib.js')
    stage = _js(tmp_path, '(async () => { window.__calog = "DONE " + LIB_VALUE })();', 'stage.js')
    result = run(cdp.port, 'stage', stage, '--libs', lib, '--max', '1', env={'TAB_MARK': 'run1'})
    assert result.returncode == 0
    script = 'const window={}; Promise.resolve(eval(' + json.dumps(state['injection']) + ')).then(() => console.log(window.__calog));'
    executed = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=5)
    assert executed.returncode == 0 and executed.stdout.strip() == 'DONE 7'


def test_legacy_top_level_statements_execute_once_with_real_javascript(cdp, tmp_path):
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('Node needed to execute actual injected JavaScript')
    tab = cdp.add('legacy', 'work', 'https://example.test/form')
    tab.mark = 'run1'
    state = {'attempts': [], 'window': {}}
    def compile_only(expression):
        parsed = subprocess.run([node, '-e', "new (require('node:vm').Script)(" + json.dumps(expression) + ')'], capture_output=True, text=True, timeout=5)
        return parsed.stderr if parsed.returncode else None
    tab.compile_responder = compile_only
    def respond(expression):
        if "window.__caRun='" in expression:
            state['attempts'].append(expression)
            script = 'const window={}; Promise.resolve(eval(' + json.dumps(expression) + ')).then(() => console.log(JSON.stringify(window)));'
            evaluated = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=5)
            if evaluated.returncode:
                return SyntaxError('SyntaxError: ' + evaluated.stderr)
            state['window'] = json.loads(evaluated.stdout)
            return None
        if '__caStageSnapshot' in expression:
            return {'run_id': state['window'].get('__caRun'), 'log': state['window'].get('__calog')}
        return NotImplemented
    tab.responder = respond
    stage = _js(tmp_path, "const VALUE = 7; window.sideeffects = (window.sideeffects || 0) + 1; (async () => { window.__calog = 'DONE ' + VALUE; })();")
    result = run(cdp.port, 'stage', stage, '--max', '3', env={'TAB_MARK': 'run1'})
    assert result.returncode == 0 and result.stdout.strip() == 'DONE 7', result.stdout + result.stderr
    assert state['window']['sideeffects'] == 1
    assert len(state['attempts']) == 1
    assert len(tab.compiled) == 2


def test_runtime_syntax_error_never_replays_side_effects(cdp, tmp_path):
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('Node needed to execute actual injected JavaScript')
    tab = cdp.add('runtime-error', 'work', 'https://example.test/form')
    tab.mark = 'run1'
    state = {'window': {}, 'attempts': 0}
    def respond(expression):
        if "window.__caRun='" in expression:
            state['attempts'] += 1
            script = 'const window={}; Promise.resolve(eval(' + json.dumps(expression) + ')).then(() => console.log(JSON.stringify(window)));'
            executed = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=5)
            assert executed.returncode == 0, executed.stderr
            state['window'] = json.loads(executed.stdout)
            return None
        if '__caStageSnapshot' in expression:
            return {'run_id': state['window'].get('__caRun'), 'log': state['window'].get('__calog')}
        return NotImplemented
    tab.responder = respond
    stage = _js(tmp_path, "(async () => { window.sideeffects = (window.sideeffects || 0) + 1; throw new SyntaxError('runtime failure'); })()")
    result = run(cdp.port, 'stage', stage, '--max', '3', env={'TAB_MARK': 'run1'})
    assert result.returncode == 1 and 'ERR SyntaxError: runtime failure' in result.stdout
    assert state['window']['sideeffects'] == 1 and state['attempts'] == 1
    assert len(tab.compiled) == 1


def test_stage_enables_runtime_before_compiling(cdp, tmp_path):
    tab, _ = stage_tab(cdp, ['DONE'])
    result = invoke(cdp, tmp_path)
    assert result.returncode == 0 and result.stdout.strip() == 'DONE', result.stdout
    assert tab.runtime_enabled and len(tab.compiled) == 1


def test_close_frame_cannot_exceed_remaining_deadline_under_backpressure():
    import importlib.util
    import socket
    from test_chrome_cdp import SCRIPT
    spec = importlib.util.spec_from_file_location('stage_cdp_close', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sender, peer = socket.socketpair()
    try:
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
        sender.setblocking(False)
        try:
            while True:
                sender.send(b'x' * 65536)
        except BlockingIOError:
            pass
        sender.settimeout(.8)  # 上一次CDP调用的较大预算，现只剩0.12秒
        tab = module.Tab.__new__(module.Tab)
        tab.sock = sender
        tab.deadline = time.monotonic() + .12
        started = time.monotonic()
        tab.close()
        assert time.monotonic() - started < .5
        assert sender.fileno() == -1
    finally:
        sender.close()
        peer.close()
