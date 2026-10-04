import importlib.util
import json
from pathlib import Path
import pytest

FILE = Path(__file__).parents[1] / 'evals/browser_benchmark.py'


def module():
    spec = importlib.util.spec_from_file_location('browser_benchmark', FILE)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_oracle_checks_full_values_all_layers_not_just_lengths():
    m = module()
    snapshot = {key: m.EXPECTED for key in ['dom', 'model', 'display', 'saved']}
    m.verify_snapshot(snapshot, require_saved=True)
    changed = json.loads(json.dumps(snapshot))
    changed['model'][0]['description'] = '错误但同长的文本'.ljust(len(m.EXPECTED[0]['description']), '字')
    with pytest.raises(AssertionError):
        m.verify_snapshot(changed, require_saved=True)


def test_saved_state_is_required_after_refresh():
    m = module()
    snapshot = {key: m.EXPECTED for key in ['dom', 'model', 'display']}
    snapshot['saved'] = []
    m.verify_snapshot(snapshot, require_saved=False)
    with pytest.raises(AssertionError):
        m.verify_snapshot(snapshot, require_saved=True)
