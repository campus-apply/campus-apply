import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.join(HERE, '..', 'skills')
SCRIPTS = ['resume-tailor/scripts/docx_dump.py', 'resume-tailor/scripts/render_basic.py',
           'resume-tailor/scripts/render_inplace.py', 'job-screen/scripts/screen_render.py']


def test_scripts_print_usage_instead_of_traceback_when_run_without_arguments():
    for rel in SCRIPTS:
        r = subprocess.run([sys.executable, os.path.join(SK, rel)], capture_output=True, text=True)
        out = r.stdout + r.stderr
        assert r.returncode == 2 and '用法' in out and 'Traceback' not in out, (rel, out[:300])
