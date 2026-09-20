import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, '..', 'skills', 'campus-apply', 'scripts')
sys.path.insert(0, SCRIPTS)
import doctor


def env(**kw):
    """一台假机器：默认什么都齐全，按需拿掉。"""
    base = dict(platform='darwin', version=(3, 11, 4), modules={'docx', 'openpyxl', 'pypdf', 'docx2pdf'},
                which={'git', 'pdfinfo'}, browser='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                paths={'/Applications/Microsoft Word.app'}, python='/usr/bin/python3', free_gb=50, latest=None)
    base.update(kw)
    return doctor.Machine(**base)


def by_name(results):
    return {r.name: r for r in results}


def test_all_good_machine_has_no_missing_required_items():
    rs = doctor.run_checks(env())
    assert all(r.ok for r in rs if r.required), [r for r in rs if r.required and not r.ok]
    assert doctor.exit_code(rs) == 0


def test_missing_pip_packages_get_one_install_command_with_this_python():
    rs = by_name(doctor.run_checks(env(modules={'openpyxl'})))
    assert not rs['python-docx'].ok and rs['python-docx'].required
    assert rs['python-docx'].fix == '/usr/bin/python3 -m pip install python-docx'
    m = env(modules={'openpyxl'}, which={'git'})
    assert doctor.pip_command(doctor.run_checks(m), m) == '/usr/bin/python3 -m pip install python-docx pypdf'


def test_pypdf_not_required_when_pdftotext_present_and_docx2pdf_only_on_windows():
    rs = by_name(doctor.run_checks(env(modules={'docx', 'openpyxl'}, which={'git', 'pdftotext'})))
    assert rs['pypdf'].ok and 'pdftotext' in rs['pypdf'].detail
    assert 'docx2pdf' not in rs
    rs = by_name(doctor.run_checks(env(platform='win32', modules={'docx', 'openpyxl', 'pypdf'}, which={'git'})))
    assert not rs['docx2pdf'].ok and not rs['docx2pdf'].required


def test_pdfinfo_alone_does_not_replace_pypdf_because_facts_need_pdf_text():
    m = env(modules={'docx', 'openpyxl'}, which={'git', 'pdfinfo'})
    rs = by_name(doctor.run_checks(m))
    assert not rs['pypdf'].ok and rs['pypdf'].required
    assert rs['pypdf'].fix == '/usr/bin/python3 -m pip install pypdf'
    assert '正文' in rs['pypdf'].detail


def test_install_rechecks_in_a_fresh_process(monkeypatch, capsys):
    """刚 pip 装的包在同一个进程里探测不到（导入缓存、启动时不存在的 site 目录），所以装完必须换个进程再查。"""
    m = env(modules={'openpyxl'})
    calls = []
    monkeypatch.setattr(doctor, 'Machine', lambda: m)
    monkeypatch.setattr(doctor, 'install_missing', lambda rs, mm: calls.append(('install', [r.name for r in doctor.pip_missing(rs, mm)])) or [])
    monkeypatch.setattr(doctor, 'recheck_in_fresh_process', lambda python: calls.append(('recheck', python)) or 0)
    assert doctor.main(['--install']) == 0
    assert calls == [('install', ['python-docx', 'pypdf']), ('recheck', '/usr/bin/python3')]
    assert '缺' not in capsys.readouterr().out


def test_old_python_is_flagged_with_platform_specific_fix():
    rs = by_name(doctor.run_checks(env(version=(3, 8, 10))))
    assert not rs['python'].ok and 'brew' in rs['python'].fix
    rs = by_name(doctor.run_checks(env(platform='win32', version=(3, 8, 10))))
    assert 'winget' in rs['python'].fix


def test_missing_browser_and_git_give_platform_commands():
    rs = by_name(doctor.run_checks(env(browser=None, which=set())))
    assert not rs['browser'].ok and rs['browser'].required and 'google-chrome' in rs['browser'].fix
    assert not rs['git'].ok and not rs['git'].required and 'git' in rs['git'].fix
    rs = by_name(doctor.run_checks(env(platform='win32', browser=None, which=set())))
    assert 'winget' in rs['browser'].fix and 'winget' in rs['git'].fix


def test_word_is_optional_and_reports_skip_page_count():
    rs = by_name(doctor.run_checks(env(paths=set())))
    assert not rs['word'].ok and not rs['word'].required and '核页数' in rs['word'].fix
    assert doctor.exit_code(doctor.run_checks(env(paths=set()))) == 0


def test_cli_prints_tab_separated_lines_and_exit_code():
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'doctor.py')], capture_output=True, text=True)
    lines = [ln for ln in r.stdout.splitlines() if ln and not ln.startswith('#')]
    assert lines and all(len(ln.split('\t')) == 4 for ln in lines), r.stdout
    assert lines[0].split('\t')[1] == 'python'
    assert r.returncode in (0, 1)


def test_cli_install_flag_runs_pip_for_missing_packages_only(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(doctor.subprocess, 'run', lambda cmd, **kw: calls.append(cmd) or type('R', (), {'returncode': 0})())
    m = env(modules={'openpyxl', 'pypdf'})
    doctor.install_missing(doctor.run_checks(m), m)
    assert calls == [['/usr/bin/python3', '-m', 'pip', 'install', 'python-docx']]
    calls.clear()
    doctor.install_missing(doctor.run_checks(env()), env())
    assert calls == []


def test_pdftoppm_is_optional_with_platform_hint():
    rs = by_name(doctor.run_checks(env(which={'git'})))
    assert 'pdftoppm' in rs and not rs['pdftoppm'].ok and not rs['pdftoppm'].required and 'poppler' in rs['pdftoppm'].fix
    rs = by_name(doctor.run_checks(env(platform='win32', which={'git'})))
    assert 'winget' in rs['pdftoppm'].fix or 'poppler' in rs['pdftoppm'].fix
    assert by_name(doctor.run_checks(env(which={'git', 'pdfinfo', 'pdftoppm'})))['pdftoppm'].ok


def test_pdftoppm_hint_offers_pymupdf_as_pip_alternative():
    rs = by_name(doctor.run_checks(env(which={'git'})))
    assert 'pymupdf' in rs['pdftoppm'].fix


def test_low_disk_space_is_an_optional_warning_not_a_failure():
    rs = by_name(doctor.run_checks(env(free_gb=0.2)))
    assert 'disk' in rs and not rs['disk'].ok and not rs['disk'].required and '1 GB' in rs['disk'].fix
    assert doctor.exit_code(doctor.run_checks(env(free_gb=0.2))) == 0
    assert by_name(doctor.run_checks(env(free_gb=50)))['disk'].ok


def test_version_line_reports_local_version_and_update_hint_only_when_newer_exists():
    rs = by_name(doctor.run_checks(env(latest='9.9.9')))
    assert rs['version'].ok and '有新版 9.9.9' in rs['version'].detail and '/plugin marketplace update' in rs['version'].fix and 'codex plugin marketplace upgrade' in rs['version'].fix
    rs = by_name(doctor.run_checks(env(latest=None)))          # 没网、超时、被墙：静默，只报本地版本
    assert rs['version'].ok and '新版' not in rs['version'].detail and rs['version'].fix == ''
    local = doctor.local_version()
    rs = by_name(doctor.run_checks(env(latest=local)))
    assert rs['version'].ok and '新版' not in rs['version'].detail
