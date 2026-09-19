import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'skills', 'campus-apply', 'scripts', 'feedback_bundle.py')


def make_workspace(ws):
    (ws / 'applications' / '示例公司-岗位').mkdir(parents=True)
    (ws / 'applications' / '示例公司').mkdir()
    (ws / 'site-notes').mkdir()
    (ws / 'campus-apply.json').write_text(json.dumps({'facts': ['事实库.md'], 'profile': {'name': '张三'}}, ensure_ascii=False), encoding='utf-8')
    (ws / 'rules.json').write_text('{}', encoding='utf-8')
    (ws / '事实库.md').write_text('秘密经历', encoding='utf-8')
    (ws / 'log.txt').write_text('2026-01-01 张三 开始；联系 13800138000\n', encoding='utf-8')
    a = ws / 'applications' / '示例公司-岗位'
    (a / 'apply-fill-执行清单_2026-01-01.md').write_text('- [x] 1\n- [ ] 2 等用户回复\n', encoding='utf-8')
    (a / 'fill-log.md').write_text('姓名 张三 邮箱 zs@example.com 证件 41010119900101001X 出生日期 1990-01-01 路径 C:\\Users\\alice\\x /Users/alice/y\n', encoding='utf-8')
    (a / 'fill-report.md').write_text('| 已填 | 手机 | 13800138000 |\n', encoding='utf-8')
    (a / 'limits.json').write_text('{"自我评价": {"max": 1000}}', encoding='utf-8')
    (a / 'resume.md').write_text('不该带走', encoding='utf-8')
    (a / 'form.md').write_text('不该带走', encoding='utf-8')
    (a / '待你决定.md').write_text('## 未决\n（无）\n', encoding='utf-8')
    (a / 'screens').mkdir(); (a / 'screens' / 's.png').write_bytes(b'x')
    c = ws / 'applications' / '示例公司'
    (c / '岗位清单_2026-01-01.md').write_text('| 1 | 岗 |\n', encoding='utf-8')
    (c / '岗位筛选_2026-01-01.json').write_text('[{"tier":"建议投","title":"岗"}]', encoding='utf-8')
    (c / '岗位筛选_2026-01-01.md').write_text('| 建议投 | 岗 |\n', encoding='utf-8')
    (c / 'jobs').mkdir(); (c / 'jobs' / 'x.md').write_text('JD 原文', encoding='utf-8')
    (ws / '示例公司_岗位筛选_2026-01-01.xlsx').write_bytes(b'PK')
    (ws / '简历_张三.docx').write_bytes(b'PK')
    (ws / 'site-notes' / 'jobs.example.com.md').write_text('控件写法', encoding='utf-8')


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


def test_collects_allowed_files_and_skips_personal_ones(tmp_path):
    ws = tmp_path / 'ws'; make_workspace(ws)
    out = tmp_path / 'out'
    r = run('--workspace', str(ws), '--out', str(out))
    assert r.returncode == 0, r.stderr
    got = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
    assert 'log.txt' in got and 'site-notes/jobs.example.com.md' in got and '示例公司_岗位筛选_2026-01-01.xlsx' in got
    assert 'applications/示例公司-岗位/fill-log.md' in got and 'applications/示例公司-岗位/limits.json' in got
    assert 'applications/示例公司/岗位筛选_2026-01-01.json' in got and 'applications/示例公司/岗位清单_2026-01-01.md' in got
    assert not any(x in got for x in ['campus-apply.json', 'rules.json', '事实库.md', '简历_张三.docx', 'applications/示例公司-岗位/resume.md',
                                        'applications/示例公司-岗位/form.md', 'applications/示例公司-岗位/screens/s.png', 'applications/示例公司/jobs/x.md'])
    assert '反馈摘要.md' in got


def test_masks_phone_email_id_birthdate_name_and_home_paths(tmp_path):
    ws = tmp_path / 'ws'; make_workspace(ws)
    out = tmp_path / 'out'
    r = run('--workspace', str(ws), '--out', str(out))
    fl = (out / 'applications' / '示例公司-岗位' / 'fill-log.md').read_text(encoding='utf-8')
    for secret in ['张三', 'zs@example.com', '41010119900101001X', '1990-01-01', 'C:\\Users\\alice', '/Users/alice']:
        assert secret not in fl, secret
    assert '【姓名】' in fl and '【邮箱】' in fl and '【证件号】' in fl and '【出生日期】' in fl and '<主目录>' in fl
    log = (out / 'log.txt').read_text(encoding='utf-8')
    assert '13800138000' not in log and '【手机】' in log and '张三' not in log
    assert '打码' in r.stdout


def test_summary_skeleton_has_environment_and_agent_sections_and_lists_files(tmp_path):
    ws = tmp_path / 'ws'; make_workspace(ws)
    out = tmp_path / 'out'
    r = run('--workspace', str(ws), '--out', str(out))
    summary = (out / '反馈摘要.md').read_text(encoding='utf-8')
    for sec in ['## 环境', '## doctor', '## 走到了哪一步', '## 未勾选的步骤', '## 停下来问了什么', '## 报错原文', '## 不顺的地方']:
        assert sec in summary, sec
    assert 'Python' in summary
    assert 'log.txt' in r.stdout and '不要' in r.stdout   # 列出文件并提醒不要直接发
    assert not list(out.parent.glob('*.zip'))


def test_refuses_to_run_without_workspace_argument():
    r = run()
    assert r.returncode == 2 and '--workspace' in (r.stdout + r.stderr)
