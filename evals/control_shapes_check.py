#!/usr/bin/env python3
"""Check `outline()` and `probe-options` against the control-shapes fixture.

Three assertions:
  A. outline() sees the two div dropdowns (shape 1) — they have labels in `above`
     and are non-native; the nav <li> items end up in `unlabeled`, not `fields`.
  B. probe-options explores the two dropdowns and finds options (optionCount ≥ 1),
     marks the upload shell as link?/kind:upload, and never clicks a nav item.
  C. fixtureAudit.navTriggered == 0 and filePickerOpened == 0 after the run.

Usage:
    python3 evals/control_shapes_check.py [--port 8799]

The test starts its own HTTP server on --port (default 8799) unless something is
already listening there, runs chrome_cdp.py subcommands against the browser at
port 9222, then stops the server.
"""
import argparse, json, os, signal, socket, subprocess, sys, tempfile, time

HERE   = os.path.dirname(os.path.abspath(__file__))
ROOT   = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, 'skills', 'campus-apply', 'scripts', 'browser', 'chrome_cdp.py')
FIX    = os.path.join(HERE, 'fixtures')

# ── helpers ──────────────────────────────────────────────────────────────────

def port_open(port):
    with socket.socket() as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def cdp(mark, *args, capture_stdout=True):
    cmd = [sys.executable, SCRIPT, '--mark', mark] + list(args)
    r = subprocess.run(cmd, capture_output=capture_stdout, text=True)
    return r

def assert_eq(label, got, want):
    if got != want:
        print(f'  FAIL  {label}: expected {want!r}, got {got!r}')
        return False
    print(f'  PASS  {label}')
    return True

def assert_ge(label, got, want):
    if got < want:
        print(f'  FAIL  {label}: expected ≥ {want}, got {got}')
        return False
    print(f'  PASS  {label} (= {got})')
    return True

def assert_true(label, val):
    if not val:
        print(f'  FAIL  {label}')
        return False
    print(f'  PASS  {label}')
    return True

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8799)
    args = parser.parse_args()

    server_proc = None
    if not port_open(args.port):
        server_proc = subprocess.Popen(
            [sys.executable, '-m', 'http.server', str(args.port)],
            cwd=FIX, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 8
        while not port_open(args.port):
            if time.monotonic() > deadline:
                print('ERR server failed to start')
                sys.exit(1)
            time.sleep(0.1)

    base  = f'http://127.0.0.1:{args.port}/control_shapes.html'
    mark  = 'csc-check'
    fails = 0

    try:
        # ── open fixture ──────────────────────────────────────────────────────
        r = cdp(mark, 'open', base, mark)
        if r.returncode != 0:
            print('ERR open failed:', r.stderr[:200])
            sys.exit(1)

        # ── run outline() via survey ──────────────────────────────────────────
        print('\n=== A: outline() sees div dropdowns, nav goes to unlabeled ===')
        tf_survey = tempfile.mktemp(suffix='.json')
        r = cdp(mark, 'survey', tf_survey)
        survey = json.load(open(tf_survey))
        fields = survey.get('fields', [])
        unlab  = survey.get('unlabeled', [])

        # shape-1 div dropdowns should be in fields with a real above label
        degree_f = [f for f in fields if (f.get('labels') or {}).get('above') == '最高学历']
        country_f= [f for f in fields if (f.get('labels') or {}).get('above') == '国籍地区']
        fails   += 0 if assert_true('degree div-dropdown in fields', degree_f) else 1
        fails   += 0 if assert_true('country div-dropdown in fields', country_f) else 1
        fails   += 0 if assert_true('degree is non-native', degree_f and not degree_f[0].get('native')) else 1

        # nav <li> items should NOT be in fields (they have no label above)
        nav_in_fields = [f for f in fields if (f.get('labels') or {}).get('innerText','') in
                         ('首页','社会招聘','校园招聘','了解公司','个人中心')]
        fails += 0 if assert_eq('nav items not in fields', len(nav_in_fields), 0) else 1

        # nav items should be in unlabeled instead
        nav_in_unlab = [u for u in unlab if u.get('innerText','') in
                        ('首页','社会招聘','校园招聘','了解公司','个人中心')]
        fails += 0 if assert_ge('nav items in unlabeled', len(nav_in_unlab), 3) else 1

        # native text input is still there
        name_f = [f for f in fields if f.get('native') and f.get('tag') == 'input']
        fails += 0 if assert_true('native text input in fields', name_f) else 1

        # ── run probe-options ─────────────────────────────────────────────────
        print('\n=== B: probe-options leaves non-native controls to the agent ===')
        tf_probe = tempfile.mktemp(suffix='.json')
        r = cdp(mark, 'probe-options', tf_probe)
        probe = json.load(open(tf_probe))
        pfields = probe.get('fields', [])

        # Without --only, the div dropdowns must be reported as needs-agent and NOT clicked.
        # That is the whole point of the split: the code lists them with evidence,
        # the agent decides. Auto-clicking anything non-native is what navigated the
        # real page away and popped the file picker on 2026-10-06.
        deg_p = [f for f in pfields if f.get('label') == '最高学历']
        cty_p = [f for f in pfields if f.get('label') == '国籍地区']
        fails += 0 if assert_true('degree listed', deg_p) else 1
        fails += 0 if assert_true('country listed', cty_p) else 1
        if deg_p:
            fails += 0 if assert_eq('degree kind', deg_p[0].get('kind'), 'needs-agent') else 1
            fails += 0 if assert_true('degree carries evidence',
                                      (deg_p[0].get('evidence') or {}).get('labels')) else 1
        if cty_p:
            fails += 0 if assert_eq('country kind', cty_p[0].get('kind'), 'needs-agent') else 1

        # Upload shell: irreversible, must be refused with a reason.
        up_p = [f for f in pfields if f.get('label') == '附件简历']
        if up_p:
            fails += 0 if assert_eq('upload kind', up_p[0].get('kind'), 'irreversible') else 1
            fails += 0 if assert_true('upload flagged opensFilePicker',
                                      up_p[0].get('opensFilePicker')) else 1

        # ── agent names the field: --only must actually explore it ────────────
        print('\n=== B2: --only explores the named control (agent点名才探) ===')
        tf_only = tempfile.mktemp(suffix='.json')
        r = cdp(mark, 'probe-options', tf_only, '--only', '最高学历')
        only = json.load(open(tf_only))
        ofields = only.get('fields', [])
        deg_o = [f for f in ofields if f.get('label') == '最高学历']
        fails += 0 if assert_true('degree explored under --only', deg_o) else 1
        if deg_o:
            fails += 0 if assert_ge('degree optionCount under --only',
                                    deg_o[0].get('count') or deg_o[0].get('optionCount') or 0, 1) else 1

        # ── audit: nav and file-picker must not have been triggered ───────────
        print('\n=== C: audit — nav and file-picker untouched ===')
        audit_js = 'JSON.stringify(window.fixtureAudit())'
        r2 = cdp(mark, 'exec', '/dev/stdin')   # exec reads stdin — use tmpfile instead
        tf_js = tempfile.mktemp(suffix='.js')
        open(tf_js, 'w').write(audit_js + '\n')
        r2 = cdp(mark, 'exec', tf_js)
        try:
            audit = json.loads(r2.stdout.strip())
        except Exception:
            print(f'  FAIL  audit parse: {r2.stdout[:120]}')
            fails += 1
            audit = {}
        fails += 0 if assert_eq('navTriggered == 0', audit.get('navTriggered'), 0) else 1
        fails += 0 if assert_eq('filePickerOpened == 0', audit.get('filePickerOpened'), 0) else 1

    finally:
        if server_proc:
            server_proc.send_signal(signal.SIGTERM)

    print()
    if fails:
        print(f'FAIL  {fails} assertion(s) failed')
        sys.exit(1)
    else:
        print('PASS  all assertions')

if __name__ == '__main__':
    main()
