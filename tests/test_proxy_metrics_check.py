"""Guard the proxy_metrics_check script's contract without launching a browser.

The real check needs Chrome (evals/proxy_metrics_check.py --out /private/…).
These tests hold the line on things that silently rot: the script exists, the
gate constants are in the expected range, and helper functions behave correctly.
"""
import importlib.util
import json
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / 'evals/proxy_metrics_check.py'


def module():
    spec = importlib.util.spec_from_file_location('proxy_metrics_check', SCRIPT)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_script_exists():
    assert SCRIPT.exists(), 'evals/proxy_metrics_check.py must exist'


def test_gates_are_positive_and_ordered():
    m = module()
    assert m.GATE_CALLS > 0
    assert m.GATE_NULL_MIN >= 1
    assert m.GATE_NULL_MAX > m.GATE_NULL_MIN
    assert m.GATE_BYTES > 0


def test_gates_are_not_absurdly_loose():
    """Prevent accidental multi-thousand values that would never catch a regression."""
    m = module()
    assert m.GATE_CALLS <= 100, 'GATE_CALLS should be a tight round-trip budget'
    assert m.GATE_NULL_MAX <= 200, 'GATE_NULL_MAX should reflect realistic field counts'
    assert m.GATE_BYTES <= 64 * 1024, 'GATE_BYTES should fit in a single model context read'


def test_count_nulls_flat_list():
    m = module()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump([
            {'key': 'a', 'value': None},
            {'key': 'b', 'value': '已填'},
            {'key': 'c', 'value': None},
        ], f, ensure_ascii=False)
        path = Path(f.name)
    assert m.count_nulls(path) == 2
    path.unlink()


def test_count_nulls_nested_fields_key():
    m = module()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({'fields': [
            {'key': 'x', 'value': None},
            {'key': 'y', 'value': None},
            {'key': 'z', 'value': '已有'},
        ]}, f, ensure_ascii=False)
        path = Path(f.name)
    assert m.count_nulls(path) == 2
    path.unlink()


def test_count_nulls_empty_list():
    m = module()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump([], f)
        path = Path(f.name)
    assert m.count_nulls(path) == 0
    path.unlink()


def test_count_nulls_missing_file():
    m = module()
    assert m.count_nulls(Path('/nonexistent/nowhere.json')) is None


def test_count_nulls_bad_json():
    m = module()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('not json at all {{{')
        path = Path(f.name)
    assert m.count_nulls(path) is None
    path.unlink()


def test_out_must_be_outside_repo(tmp_path, monkeypatch):
    """--out inside the repo must be rejected without touching a browser."""
    m = module()
    # Patch browser_path so the test never tries to find Chrome.
    monkeypatch.setattr(m, 'browser_path', lambda: '/fake/chrome')
    with pytest.raises(SystemExit) as exc:
        m.main(['--out', str(ROOT / 'evals' / 'tmp-test-out')])
    assert exc.value.code != 0


def test_no_browser_exits_nonzero(monkeypatch):
    m = module()
    monkeypatch.setattr(m, 'browser_path', lambda: None)
    with pytest.raises(SystemExit) as exc:
        m.main(['--out', '/tmp/proxy-check-test-no-browser'])
    assert exc.value.code != 0
