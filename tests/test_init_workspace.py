import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'skills', 'resume-facts', 'scripts', 'init_workspace.py')


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


def test_creates_marker_rules_and_facts_from_template(tmp_path):
    r = run('--dir', str(tmp_path))
    assert r.returncode == 0, r.stderr
    cfg = json.load(open(tmp_path / 'campus-apply.json', encoding='utf-8'))
    assert cfg['facts'] == ['个人经历事实库.md']
    assert set(cfg['preferences']) >= {'apply_types', 'role_types_no', 'locations_ok', 'early_onboarding_ok'}
    assert (tmp_path / 'rules.json').exists()
    assert 'applications/' in (tmp_path / '.gitignore').read_text(encoding='utf-8')
    assert '【来源' in (tmp_path / '个人经历事实库.md').read_text(encoding='utf-8')


def test_uses_existing_facts_and_docx_without_moving(tmp_path):
    (tmp_path / 'a.md').write_text('# 事实', encoding='utf-8')
    (tmp_path / 'b.md').write_text('# 更多', encoding='utf-8')
    (tmp_path / 'cv.docx').write_bytes(b'x')
    r = run('--dir', str(tmp_path), '--facts', 'a.md', 'b.md', '--resume-docx', 'cv.docx')
    assert r.returncode == 0, r.stderr
    cfg = json.load(open(tmp_path / 'campus-apply.json', encoding='utf-8'))
    assert cfg['facts'] == ['a.md', 'b.md'] and cfg['resume_docx'] == 'cv.docx'
    assert (tmp_path / 'a.md').exists() and not (tmp_path / '个人经历事实库.md').exists()


def test_missing_facts_file_fails(tmp_path):
    r = run('--dir', str(tmp_path), '--facts', 'nope.md')
    assert r.returncode == 1 and 'nope.md' in r.stderr


def test_second_run_does_not_overwrite(tmp_path):
    run('--dir', str(tmp_path))
    (tmp_path / 'rules.json').write_text('{"banned_words":["自定义"]}', encoding='utf-8')
    r = run('--dir', str(tmp_path))
    assert r.returncode == 0 and '已初始化' in r.stdout
    assert json.load(open(tmp_path / 'rules.json', encoding='utf-8'))['banned_words'] == ['自定义']


def test_without_dir_prints_usage_and_creates_nothing(tmp_path):
    r = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 2 and '--dir' in (r.stdout + r.stderr)
    assert not (tmp_path / 'campus-apply.json').exists() and not (tmp_path / 'rules.json').exists()
