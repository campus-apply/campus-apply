import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.join(HERE, '..', 'skills')
SCRIPTS = ['resume-tailor/scripts/docx_dump.py', 'resume-tailor/scripts/render_basic.py', 'resume-tailor/scripts/render_inplace.py',
           'resume-tailor/scripts/check_content.py', 'resume-facts/scripts/init_workspace.py', 'job-screen/scripts/screen_render.py',
           'campus-apply/scripts/doctor.py', 'campus-apply/scripts/feedback_bundle.py', 'campus-apply/scripts/browser/chrome_cdp.py']


def test_help_flag_prints_usage_and_never_a_traceback():
    for rel in SCRIPTS:
        r = subprocess.run([sys.executable, os.path.join(SK, rel), '--help'], capture_output=True, text=True)
        out = r.stdout + r.stderr
        assert 'Traceback' not in out and 'ERR_UNKNOWN_COMMAND' not in out and ('用法' in out or 'usage' in out.lower()), (rel, out[:200])
        assert r.returncode == 0, (rel, r.returncode)
