import os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
SKILLS = sorted(os.listdir(os.path.join(ROOT, 'skills')))


def run(tmp_home, *args):
    """在一个空的假主目录里跑 install.sh --dry-run，返回每一行输出。"""
    r = subprocess.run(['bash', os.path.join(ROOT, 'install.sh'), *args, '--dry-run'],
                       capture_output=True, text=True, env={**os.environ, 'HOME': str(tmp_home)})
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines()


def would_link_into(lines, dest):
    return sorted(l.split(' -> ')[1].rsplit('/', 1)[1] for l in lines
                  if l.startswith('would link ') and l.split(' -> ')[1].startswith(dest + '/'))


def test_each_target_maps_to_its_harness_skills_dir(tmp_path):
    for target, rel in [('claude', '.claude/skills'), ('codex', '.codex/skills'),
                        ('agents', '.agents/skills'), ('codebuddy', '.codebuddy/skills')]:
        dest = tmp_path / rel
        dest.mkdir(parents=True)
        assert would_link_into(run(tmp_path, target), str(dest)) == SKILLS, target


def test_all_installs_into_every_existing_harness_dir_including_codebuddy(tmp_path):
    for rel in ['.claude/skills', '.codebuddy/skills']:
        (tmp_path / rel).mkdir(parents=True)
    lines = run(tmp_path, 'all')
    assert would_link_into(lines, str(tmp_path / '.claude/skills')) == SKILLS
    assert would_link_into(lines, str(tmp_path / '.codebuddy/skills')) == SKILLS
    assert any(l.startswith('skip (no such dir): ') and l.endswith('.codex/skills') for l in lines)
