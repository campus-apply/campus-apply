#!/usr/bin/env python3
"""Measure proxy metrics for the survey → probe-options → plan-skeleton pipeline on a fixture page.

Wall-clock idle time (the real target) cannot be gated on a fixture because the fixture
has no model in the loop — the idle time is near zero by construction.  Instead this script
counts things the *model* would have to do that we want to push toward zero:

  driver_calls   — round-trips to the browser (commands issued by the three sub-commands)
  skeleton_nulls — fields whose value is still null in the skeleton (model must fill these)
  skeleton_bytes — bytes in the skeleton JSON the model must read and write

These are repeatable, model-free, and map directly to the bottlenecks measured on the real
Moka page (2026-10-05: 7.5 min to produce a 112-field plan because the model was hand-
maintaining selector+index tables).

Gates (based on the 112-field Moka session and scaled to the fixture's field count):
  driver_calls  ≤ GATE_CALLS   — each extra call is a browser round-trip the model waits for
  skeleton_nulls ≤ GATE_NULLS  — fields left for the model to fill (should be all of them,
                                  but the skeleton should *list* them all, not invent extras)
  skeleton_bytes ≤ GATE_BYTES  — bytes the model must read before it can fill the first field

Usage:
  python3 evals/proxy_metrics_check.py --out /private/proxy-check [--headless]

--out must be outside the repository.  The script creates it if absent.
"""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
BROWSER_DIR = HERE.parent / 'skills/campus-apply/scripts/browser'
CDP = BROWSER_DIR / 'chrome_cdp.py'

# Gates — calibrated against the 2026-10-05 Moka session at 112 fields.
# The fixture has ~10 visible interactive fields, so we scale proportionally and add headroom.
# driver_calls: Moka survey alone was ~8 driver calls; probe-options added ~14 (one per panel
#   field); plan-skeleton added ~3.  Total ~25 for 112 fields → ~3 per 10 fields.  Gate at 12
#   (generous — the point is to catch regressions where commands fan out into per-field loops).
# skeleton_nulls: every non-disabled field should appear with value:null.  The fixture has
#   roughly 10 fields, so we gate null-count in [1, 15] — at least one null means the skeleton
#   ran and populated fields; more than 15 means phantom fields were hallucinated.
# skeleton_bytes: the skeleton should be compact enough for the model to read in one pass.
#   Gate at 8 KiB; the 112-field Moka skeleton was ~6 KiB before the language fix.
GATE_CALLS = 20
GATE_NULL_MIN = 1
GATE_NULL_MAX = 20
GATE_BYTES = 8192


def browser_path():
    candidates = [
        os.environ.get('CA_BROWSER'),
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome'),
    ]
    return next((p for p in candidates if p and Path(p).is_file()), None)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class Runner:
    """Issues commands against an isolated browser and counts round-trips."""

    def __init__(self, port, out):
        self.env = dict(os.environ, CA_CDP_PORT=str(port))
        self.env.pop('TAB_MARK', None)
        self.env.pop('TAB_MATCH', None)
        self.out = out
        self.calls = []
        out.mkdir(parents=True, exist_ok=True)

    def run(self, phase, *args, check=True):
        before = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(CDP), *args],
            env=self.env, capture_output=True, text=True, timeout=120,
        )
        elapsed = round(time.monotonic() - before, 3)
        self.calls.append(dict(phase=phase, seconds=elapsed, exit_code=result.returncode))
        (self.out / (phase + '.out')).write_text(
            result.stdout + ('\n--- stderr ---\n' + result.stderr if result.stderr else ''),
            encoding='utf-8',
        )
        if check and result.returncode:
            raise RuntimeError(
                phase + ' exited ' + str(result.returncode) + ': '
                + (result.stdout + result.stderr).strip()[:600]
            )
        return result

    def marked(self, phase, *args, **kw):
        return self.run(phase, '--mark', 'proxy-check', *args, **kw)


def run_pipeline(runner, url, out):
    """Open the page then run survey → probe-options → plan-skeleton."""
    runner.marked('open', 'open', url, 'proxy-check')

    survey_out = out / 'survey.json'
    runner.marked('survey', 'survey', str(survey_out))

    probe_out = out / 'probe_options.json'
    runner.marked('probe-options', 'probe-options', str(probe_out))

    skeleton_out = out / 'skeleton.json'
    runner.marked('plan-skeleton', 'plan-skeleton', str(skeleton_out))

    return survey_out, probe_out, skeleton_out


def count_nulls(skeleton_path):
    """Count fields with value: null in the skeleton."""
    try:
        data = json.loads(skeleton_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    fields = data if isinstance(data, list) else data.get('fields', [])
    return sum(1 for f in fields if isinstance(f, dict) and f.get('value') is None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', required=True, help='artifact directory, outside this repo')
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args(argv)

    browser = browser_path()
    if not browser:
        parser.error('Chrome/Edge not found; set CA_BROWSER')

    out = Path(args.out).resolve()
    if out.is_relative_to(HERE.parent):
        parser.error('--out must be outside the repository')
    out.mkdir(parents=True, exist_ok=True)

    handler = functools.partial(QuietHandler, directory=str(HERE / 'fixtures'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        cdp_port = sock.getsockname()[1]

    proc = None
    profile = tempfile.mkdtemp(prefix='campus-apply-proxy-check-')
    try:
        command = [
            browser,
            '--user-data-dir=' + profile,
            '--remote-debugging-port=' + str(cdp_port),
            '--no-first-run', '--no-default-browser-check',
            '--disable-background-timer-throttling',
            '--disable-renderer-backgrounding',
            '--disable-backgrounding-occluded-windows',
            '--window-size=1100,900', 'about:blank',
        ]
        if args.headless:
            command.insert(1, '--headless=new')

        with (out / 'browser.stderr').open('w') as stderr:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stderr)
            deadline = time.monotonic() + 20
            while True:
                try:
                    with urllib.request.urlopen(
                        'http://127.0.0.1:' + str(cdp_port) + '/json/version', timeout=1
                    ) as resp:
                        browser_version = json.load(resp)['Browser']
                    break
                except OSError:
                    if time.monotonic() >= deadline or proc.poll() is not None:
                        raise RuntimeError('isolated browser did not start')
                    time.sleep(0.2)

            print(browser_version, flush=True)
            url = ('http://127.0.0.1:' + str(server.server_address[1])
                   + '/apply_form.html?run=proxy-check')
            runner = Runner(cdp_port, out)

            error = None
            survey_out = probe_out = skeleton_out = None
            try:
                survey_out, probe_out, skeleton_out = run_pipeline(runner, url, out)
            except Exception as exc:
                error = str(exc)[:600]
                print('ERR ' + error, flush=True)
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        server.shutdown()
        server.server_close()
        shutil.rmtree(profile, ignore_errors=True)

    # --- measure ---
    driver_calls = len(runner.calls)
    skeleton_bytes = skeleton_out.stat().st_size if skeleton_out and skeleton_out.exists() else None
    skeleton_nulls = count_nulls(skeleton_out) if skeleton_out and skeleton_out.exists() else None

    # --- gate ---
    problems = []
    if error:
        problems.append('pipeline error: ' + error)
    if skeleton_bytes is None:
        problems.append('skeleton.json not written')
    if skeleton_nulls is None:
        problems.append('skeleton.json unreadable or has no fields array')
    if driver_calls > GATE_CALLS:
        problems.append(
            f'driver_calls {driver_calls} > gate {GATE_CALLS} '
            '(too many browser round-trips; model will wait longer)'
        )
    if skeleton_bytes is not None and skeleton_bytes > GATE_BYTES:
        problems.append(
            f'skeleton_bytes {skeleton_bytes} > gate {GATE_BYTES} '
            '(skeleton too large; model reads more before first keystroke)'
        )
    if skeleton_nulls is not None and skeleton_nulls < GATE_NULL_MIN:
        problems.append(
            f'skeleton_nulls {skeleton_nulls} < gate_min {GATE_NULL_MIN} '
            '(skeleton has no null fields — plan-skeleton may not have run)'
        )
    if skeleton_nulls is not None and skeleton_nulls > GATE_NULL_MAX:
        problems.append(
            f'skeleton_nulls {skeleton_nulls} > gate_max {GATE_NULL_MAX} '
            '(skeleton lists far more fields than the fixture has)'
        )

    report = dict(
        browser=browser_version,
        headless=args.headless,
        driver_calls=driver_calls,
        skeleton_bytes=skeleton_bytes,
        skeleton_nulls=skeleton_nulls,
        gates=dict(calls=GATE_CALLS, bytes=GATE_BYTES,
                   null_min=GATE_NULL_MIN, null_max=GATE_NULL_MAX),
        passed=not problems,
        problems=problems,
        calls=runner.calls,
    )
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                      encoding='utf-8')

    print(f'\ndriver_calls  {driver_calls:3d}   (gate ≤ {GATE_CALLS})', flush=True)
    if skeleton_bytes is not None:
        print(f'skeleton_bytes {skeleton_bytes:5d}   (gate ≤ {GATE_BYTES})', flush=True)
    if skeleton_nulls is not None:
        print(f'skeleton_nulls {skeleton_nulls:4d}   '
              f'(gate {GATE_NULL_MIN}–{GATE_NULL_MAX})', flush=True)

    if problems:
        print('\nFAIL', flush=True)
        for p in problems:
            print('  ' + p, flush=True)
    else:
        print('\nPASS', flush=True)

    print('明细：' + str(out / 'report.json'), flush=True)
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
