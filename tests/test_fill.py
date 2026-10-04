"""Unit tests for the `fill` subcommand's argument and plan handling.

Behaviour against a real page is covered by evals/fill_benchmark.py (same end state, fewer
calls) and evals/fill_failure_check.py (each failure path fails and says why). These tests
cover what those cannot: bad input, and the promise that a plan never becomes executable code.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / 'skills/campus-apply/scripts/browser/chrome_cdp.py'
LIB = HERE.parent / 'skills/campus-apply/scripts/browser/lib_fill.js'


def run(*args, env=None):
    e = dict(os.environ)
    e.pop('TAB_MARK', None)
    e.pop('TAB_MATCH', None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, env=e, timeout=60)


def test_fill_without_arguments_prints_usage():
    r = run('fill')
    assert r.returncode == 2
    assert 'ERR_USAGE fill' in r.stdout


def test_fill_reports_a_missing_plan_file():
    r = run('fill', '/no/such/plan.json')
    assert r.returncode == 2
    assert 'ERR_NO_FILE' in r.stdout


def test_fill_rejects_unparseable_plan(tmp_path):
    plan = tmp_path / 'plan.json'
    plan.write_text('{not json', encoding='utf-8')
    r = run('fill', str(plan))
    assert r.returncode == 2
    assert 'ERR_PLAN' in r.stdout


def test_fill_rejects_a_plan_without_fields(tmp_path):
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'pace': {'min': 1}}), encoding='utf-8')
    r = run('fill', str(plan))
    assert r.returncode == 2
    assert 'ERR_PLAN' in r.stdout


def test_fill_rejects_an_empty_field_list(tmp_path):
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'fields': []}), encoding='utf-8')
    r = run('fill', str(plan))
    assert r.returncode == 2


def test_fill_accepts_a_bare_array_as_the_plan(tmp_path):
    """A list is shorthand for {"fields": [...]}; it must get past plan parsing."""
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps([{'key': 'a', 'selector': '#a', 'value': 'x'}]), encoding='utf-8')
    r = run('fill', str(plan))
    assert 'ERR_PLAN' not in r.stdout
    assert 'ERR_NEED_TAB_MARK_OR_TAB_MATCH' in r.stdout


def test_fill_requires_a_claimed_tab(tmp_path):
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'fields': [{'key': 'a', 'selector': '#a', 'value': 'x'}]}),
                    encoding='utf-8')
    r = run('fill', str(plan))
    assert r.returncode == 2
    assert 'ERR_NEED_TAB_MARK_OR_TAB_MATCH' in r.stdout


def test_fill_rejects_a_nonpositive_or_infinite_max(tmp_path):
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'fields': [{'key': 'a', 'selector': '#a', 'value': 'x'}]}),
                    encoding='utf-8')
    for bad in ('0', '-5', 'inf', 'nan', 'soon'):
        r = run('fill', str(plan), '--max', bad)
        assert r.returncode == 2, bad
        assert 'ERR_USAGE fill' in r.stdout, bad


def test_fill_reports_a_missing_max_value(tmp_path):
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'fields': [{'key': 'a', 'selector': '#a', 'value': 'x'}]}),
                    encoding='utf-8')
    r = run('fill', str(plan), '--max')
    assert r.returncode == 2
    assert '--max 缺少秒数' in r.stdout


def test_fill_is_listed_in_the_help_text():
    r = run('--help')
    assert r.returncode == 0
    assert 'fill <计划.json>' in r.stdout


def test_plan_values_are_passed_as_json_data_never_as_code():
    """The plan must reach the page as JSON arguments. If any value were interpolated into a
    script, a value like `");alert(1)//` would change what runs. Assert the call sites use
    json.dumps on every plan-derived string."""
    source = (HERE.parent / 'skills/campus-apply/scripts/browser/chrome_cdp.py').read_text(encoding='utf-8')
    fill_section = source[source.index('FILL_KINDS = '):source.index('def cmd_screenshot')]
    for forbidden in ("+ want +", "+ selector +", "+ text +", "{want}", "{selector}"):
        assert forbidden not in fill_section, 'plan value interpolated into JS: ' + forbidden
    for required in ('json.dumps(want)', 'json.dumps(selector)', 'json.dumps(step)'):
        assert required in fill_section, 'expected ' + required


def code_lines(path):
    """Source lines with // comments stripped, so prose about a pattern is not mistaken for it."""
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if stripped.startswith('//'):
            continue
        out.append(line.split('//')[0] if '//' in line and '://' not in line else line)
    return '\n'.join(out)


def test_in_page_library_never_evaluates_strings():
    text = code_lines(LIB)
    for forbidden in ('eval(', 'new Function', 'setTimeout("', 'innerHTML'):
        assert forbidden not in text, 'lib_fill.js must not evaluate strings: ' + forbidden


def test_in_page_library_does_not_use_offsetparent_for_visibility():
    """offsetParent is always null for position:fixed elements, which is how real modals and
    dropdown panels are positioned (pending 105). lib_fill.js must not reintroduce it."""
    assert 'offsetParent' not in code_lines(LIB)


def test_in_page_library_reads_the_active_react_fiber_not_the_attached_one():
    text = LIB.read_text(encoding='utf-8')
    assert '__reactContainer$' in text, 'must locate the root to find the active fiber'
    assert 'react-active' in text and 'react-attached' in text, 'must distinguish the two reads'


def test_in_page_library_forbids_body_click_and_key_events():
    text = LIB.read_text(encoding='utf-8')
    assert 'document.body.click' not in text
    assert 'KeyboardEvent' not in text and 'dispatchKeyEvent' not in text


def test_fill_never_presses_submit():
    """The executor only writes fields; pressing 投递/提交 stays the user's action."""
    source = (HERE.parent / 'skills/campus-apply/scripts/browser/chrome_cdp.py').read_text(encoding='utf-8')
    fill_section = source[source.index('FILL_KINDS = '):source.index('def cmd_screenshot')]
    code = '\n'.join(l.split('#')[0] for l in fill_section.splitlines())
    assert 'submit' not in code.lower(), 'fill must not touch submit controls'
