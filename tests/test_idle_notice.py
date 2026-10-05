# -*- coding: utf-8 -*-
"""工具要把"距上次操作过了多久"打出来，让空置看得见。

模型没有时钟概念，感知不到自己想了多久，所以"浏览器空置超过两分钟就该说句话"这种规矩
只写在文档里等于没写。把时间感知交给唯一知道时间的一方：工具每次运行都能读系统时钟。

顺带也给用户可见性——看终端就知道上一条命令和这一条之间隔了多久。
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CDP = HERE.parent / 'skills/campus-apply/scripts/browser/chrome_cdp.py'


def run(*args, env=None):
    e = dict(os.environ)
    e.pop('TAB_MARK', None)
    e.pop('TAB_MATCH', None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(CDP), *args],
                          capture_output=True, text=True, env=e, timeout=60)


def code():
    text = CDP.read_text(encoding='utf-8')
    text = re.sub(r'""".*?"""', '""""""', text, flags=re.DOTALL)
    return '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))


def test_a_long_gap_between_commands_is_printed(tmp_path):
    """上一条命令结束到这一条开始隔得久了，要在输出里说一声。"""
    timing = tmp_path / 'timing.jsonl'
    # 伪造一条"两分半钟前跑完"的记录
    timing.write_text(json.dumps({
        'command': 'survey', 'started_at': time.time() - 160,
        'elapsed_seconds': 1.0, 'exit_code': 0,
    }) + '\n', encoding='utf-8')
    r = run('list', env={'CA_TIMING_FILE': str(timing)})
    assert '距上次操作' in r.stdout + r.stderr, \
        '隔了两分多钟没动浏览器，要提示一句：' + (r.stdout + r.stderr)[-300:]


def test_a_short_gap_stays_quiet(tmp_path):
    """隔得短就不要啰嗦——每条命令都报一次等于没报。"""
    timing = tmp_path / 'timing.jsonl'
    timing.write_text(json.dumps({
        'command': 'survey', 'started_at': time.time() - 3,
        'elapsed_seconds': 1.0, 'exit_code': 0,
    }) + '\n', encoding='utf-8')
    r = run('list', env={'CA_TIMING_FILE': str(timing)})
    assert '距上次操作' not in r.stdout + r.stderr, '隔了几秒不该提示'


def test_the_gap_notice_goes_to_stderr_not_into_data_output(tmp_path):
    """提示不能混进 stdout——那里是给调用方解析的数据。"""
    timing = tmp_path / 'timing.jsonl'
    timing.write_text(json.dumps({
        'command': 'survey', 'started_at': time.time() - 300,
        'elapsed_seconds': 1.0, 'exit_code': 0,
    }) + '\n', encoding='utf-8')
    r = run('list', env={'CA_TIMING_FILE': str(timing)})
    assert '距上次操作' in r.stderr and '距上次操作' not in r.stdout


def test_no_timing_file_means_no_notice(tmp_path):
    """没开计时就什么都不做，不要凭空多出一行。"""
    r = run('list')
    assert '距上次操作' not in r.stdout + r.stderr


def test_waiting_for_a_parse_has_an_upper_bound():
    """等解析要有上限，否则"等不到"这个条件永远不成立。"""
    doc = (HERE.parent / 'skills/apply-fill/references/upload-and-parse.md'
           ).read_text(encoding='utf-8')
    assert '最多' in doc and '秒' in doc, 'upload-and-parse 要给"等解析"一个秒数上限'
