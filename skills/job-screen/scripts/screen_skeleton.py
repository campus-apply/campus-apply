#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把预筛结果转成精读骨架：机器判出来的结论带过去，要模型读的那几格留空。

用法：
  python3 screen_skeleton.py <prescreen 的 --json 输出> <骨架.json> [--only 档1,档2]

为什么要这一步：`prescreen.py` 出的是 `{"jobs": [...]}`，每项带 `_tier` / `_rule` /
`_evidence`；`screen_render.py` 吃的是扁平列表，每项带 `tier` 和一组固定列名。两个格式差一层，
于是每跑一次筛岗，模型就现写一个转换加拼装的脚本——而现写脚本是这套工具要消灭的事，
它占掉的时间比浏览器动的时间长得多。

骨架出来之后，模型只做一件事：给"读"档那几条填上专业匹配、优先项、理由、缺口。
填完直接交给 `screen_render.py` 出 md 和 xlsx，中间不需要再写任何脚本。

排除档和待定档的理由与依据原文是机器判出来的，原样带过去——那些话模型重写一遍只会更模糊，
而且"排除要能说出依据"这条规矩本来就要求引用原文。
"""
import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# 要模型精读才能填的几格：骨架里留空，不替它编
TO_READ = ('major', 'major_match', 'lang', 'pri', 'why', 'gap')
# 从预筛结果直接搬过来的几格
CARRY = ('title', 'cat', 'org', 'loc', 'nature', 'date', 'edu', 'url', 'jobId')


def build(payload, only=None):
    rows = []
    for job in payload.get('jobs') or []:
        tier = job.get('_tier') or '读'
        if only and tier not in only:
            continue
        row = {'tier': tier}
        for key in CARRY:
            value = job.get(key)
            if value:
                row[key] = value
        for key in TO_READ:
            row[key] = ''
        # 工作内容一句话：清单里带正文的话给个开头，模型改写成一句；没有就留空
        body = (job.get('duty') or '').strip()
        row['duty'] = body[:60] if body else ''
        if tier != '读':
            # 机器已经判明的，理由和依据原样带过去
            row['why'] = job.get('_rule') or ''
            row['gap'] = job.get('_evidence') or job.get('_rule') or ''
        rows.append(row)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('src', help='prescreen.py --json 写出来的文件')
    parser.add_argument('out', help='骨架写到哪')
    parser.add_argument('--only', help='只要这几档，逗号分隔，如 读,待定')
    args = parser.parse_args(argv)

    if not os.path.isfile(args.src):
        print('ERR_NO_FILE ' + args.src)
        return 2
    try:
        with open(args.src, encoding='utf-8') as f:
            payload = json.load(f)
    except (OSError, ValueError) as e:
        print('ERR_INPUT: 读不出预筛结果：%s' % e)
        return 2
    if not isinstance(payload, dict) or 'jobs' not in payload:
        print('ERR_INPUT: 要的是 prescreen.py --json 的输出（含 jobs 数组）')
        return 2

    only = [t.strip() for t in (args.only or '').split(',') if t.strip()] or None
    rows = build(payload, only)
    if not rows:
        print('ERR_INPUT: 没有符合条件的岗位')
        return 1
    try:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print('ERR_WRITE %s：%s' % (args.out, e.strerror or e))
        return 1

    by_tier = {}
    for row in rows:
        by_tier[row['tier']] = by_tier.get(row['tier'], 0) + 1
    for tier, n in by_tier.items():
        print('%s\t%d 个' % (tier, n))
    print('---')
    need = by_tier.get('读', 0)
    print('SKELETON %d 行 → %s' % (len(rows), args.out))
    if need:
        print('"读"档那 %d 行的专业匹配 / 优先项 / 理由 / 缺口留空了，逐份读 JD 填上；'
              '其余档的理由和依据已经带过来，不用重写' % need)
    print('填完交给 screen_render.py 出 md 和 xlsx，不要再写转换脚本')
    return 0


if __name__ == '__main__':
    sys.exit(main())
