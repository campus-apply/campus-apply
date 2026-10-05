# -*- coding: utf-8 -*-
"""预筛结果和出表工具之间要能直接对接，不要每次现写一个转换脚本。

`prescreen.py` 出的是 `{"jobs": [...]}`，每项带 `_tier` / `_rule` / `_evidence`；
`screen_render.py` 吃的是扁平列表，每项带 `tier`。两个格式差一层，于是每跑一次筛岗，
模型就现写一个转换加拼装的脚本——而现写脚本正是这套工具要消灭的事。

这里要的是一条命令：读预筛结果，出一份"精读骨架"，模型只往里填精读结论，填完直接给
screen_render 出表。
"""
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / 'skills/job-screen/scripts'
SKELETON = SCRIPTS / 'screen_skeleton.py'
RENDER = SCRIPTS / 'screen_render.py'


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, timeout=60)


def sample(tmp_path):
    """一份 prescreen 形状的输入：三档各一条。"""
    path = tmp_path / 'prescreen.json'
    path.write_text(json.dumps({
        'title': '某公司校招',
        'notes': ['偏好来自 campus-apply.json'],
        'counts': {'读': 1, '待定': 1, '排除': 1},
        'jobs': [
            {'title': '产品经理', 'cat': '产品', 'loc': '北京市', 'org': '某部门',
             'url': 'https://example.com/1', 'jobId': '1',
             'duty': '做需求', 'req': '本科以上',
             '_tier': '读', '_rule': '机器判不出硬门槛，像候选', '_evidence': ''},
            {'title': '某新区岗', 'cat': '运营', 'loc': '某新区', 'org': '',
             'url': 'https://example.com/2', 'jobId': '2',
             'duty': '', 'req': '',
             '_tier': '待定', '_rule': '认不出是国内还是海外', '_evidence': '某新区'},
            {'title': '法务岗', 'cat': '法务', 'loc': '上海市', 'org': '',
             'url': 'https://example.com/3', 'jobId': '3',
             'duty': '', 'req': '法学专业',
             '_tier': '排除', '_rule': '专业不符', '_evidence': '法学专业'},
        ],
    }, ensure_ascii=False), encoding='utf-8')
    return path


def test_skeleton_script_exists():
    assert SKELETON.is_file(), '要有一条命令把预筛结果转成精读骨架'


def test_skeleton_carries_the_tier_render_expects(tmp_path):
    """出来的每项要带 screen_render 认的 tier，不是 prescreen 的 _tier。"""
    out = tmp_path / 'skeleton.json'
    r = run(SKELETON, str(sample(tmp_path)), str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    rows = json.loads(out.read_text(encoding='utf-8'))
    assert isinstance(rows, list), 'screen_render 吃的是列表'
    assert all('tier' in row for row in rows), '每项都要有 tier'


def test_skeleton_leaves_the_reading_conclusions_empty(tmp_path):
    """骨架是给模型填的：精读结论留空，不要替它编。"""
    out = tmp_path / 'skeleton.json'
    run(SKELETON, str(sample(tmp_path)), str(out))
    rows = json.loads(out.read_text(encoding='utf-8'))
    need_read = [r for r in rows if r['tier'] == '读']
    assert need_read, '至少有一条要模型读的'
    for row in need_read:
        assert row.get('major_match') == '', '精读结论要留空'
        assert row.get('why') == '', '精读结论要留空'


def test_excluded_rows_keep_their_evidence(tmp_path):
    """排除档的依据原文是机器判出来的，要带过去，不能让模型重写一遍。"""
    out = tmp_path / 'skeleton.json'
    run(SKELETON, str(sample(tmp_path)), str(out))
    rows = json.loads(out.read_text(encoding='utf-8'))
    dropped = next(r for r in rows if r['tier'] == '排除')
    assert dropped.get('why'), '排除档要带上机器给的理由'
    assert dropped.get('gap'), '排除档要带上依据原文或剔除原因'


def test_the_skeleton_feeds_render_without_a_hand_written_script(tmp_path):
    """端到端：预筛 → 骨架 → 出表，中间不许再写脚本。"""
    out = tmp_path / 'skeleton.json'
    run(SKELETON, str(sample(tmp_path)), str(out))
    md = tmp_path / 'screen.md'
    r = run(RENDER, str(out), '--md', str(md), '--title', '某公司校招')
    assert r.returncode == 0, r.stdout + r.stderr
    text = md.read_text(encoding='utf-8')
    assert '产品经理' in text and '法务岗' in text
