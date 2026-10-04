"""空置时长要能算出来，否则"浏览器别干等着"就只是一句口号。

命令自己跑了多久不是重点——实测里命令占用远小于命令**之间**的空当：页面加载好了、
登录着、什么也没发生，模型在写计划或者记日志。所以每条命令都要记墙钟起点，
相邻两条相减才看得见那段。
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / 'skills/campus-apply/scripts/idle_report.py'
CDP = HERE.parent / 'skills/campus-apply/scripts/browser/chrome_cdp.py'


def load():
    spec = importlib.util.spec_from_file_location('idle_report', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_idle_is_the_gap_between_commands_not_their_duration():
    m = load()
    rows = [dict(command='survey', started_at=100.0, elapsed_seconds=2.0, exit_code=0),
            dict(command='fill', started_at=140.0, elapsed_seconds=8.0, exit_code=0)]
    got = m.summarise(rows)
    assert got['busy_seconds'] == 10.0
    assert got['idle_seconds'] == 38.0, '100→148 共 48 秒，命令占 10 秒，空置 38 秒'
    assert got['span_seconds'] == 48.0


def test_the_longest_gap_says_what_it_sat_between():
    m = load()
    rows = [dict(command='probe', started_at=0.0, elapsed_seconds=1.0, exit_code=0),
            dict(command='fill', started_at=61.0, elapsed_seconds=1.0, exit_code=0),
            dict(command='exec', started_at=63.0, elapsed_seconds=1.0, exit_code=0)]
    got = m.summarise(rows)
    worst = got['longest_gaps'][0]
    assert worst['seconds'] == 60.0
    assert worst['after'] == 'probe' and worst['before'] == 'fill'


def test_out_of_order_lines_are_sorted_before_counting():
    m = load()
    rows = [dict(command='b', started_at=50.0, elapsed_seconds=1.0, exit_code=0),
            dict(command='a', started_at=10.0, elapsed_seconds=1.0, exit_code=0)]
    got = m.summarise(rows)
    assert got['idle_seconds'] == 39.0


def test_every_command_records_a_wall_clock_start(tmp_path):
    """不只是 stage：任何一条子命令都要记，否则算不出它前后的空当。"""
    timing = tmp_path / 'timing.jsonl'
    env = dict(**{k: v for k, v in __import__('os').environ.items()},
               CA_TIMING_FILE=str(timing))
    env.pop('TAB_MARK', None)
    env.pop('TAB_MATCH', None)
    subprocess.run([sys.executable, str(CDP), 'list'], env=env,
                   capture_output=True, text=True, timeout=60)
    assert timing.exists(), 'list 也要写计时'
    row = json.loads(timing.read_text(encoding='utf-8').strip().splitlines()[0])
    assert row['command'] == 'list'
    assert row['started_at'] > 0, '要有墙钟时间戳，不然算不出命令之间的空当'
    assert 'elapsed_seconds' in row and 'exit_code' in row


def test_timing_never_records_field_values(tmp_path):
    """计时文件可能被打进反馈包，只能有命令名、时间和退出码。"""
    m = load()
    rows = [dict(command='fill', started_at=1.0, elapsed_seconds=1.0, exit_code=0)]
    blob = json.dumps(m.summarise(rows), ensure_ascii=False)
    assert 'value' not in blob and 'secret' not in blob
