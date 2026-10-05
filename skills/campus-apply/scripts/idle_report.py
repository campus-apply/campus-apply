#!/usr/bin/env python3
"""Turn a CA_TIMING_FILE into one number: how long the browser sat doing nothing.

Total elapsed time hides the thing worth fixing. The browser is only busy while a command is
running; the rest of the session it is loaded, logged in, and idle — waiting for the model to
finish writing a plan, a log entry, or a field-index table. On a real page that gap was twice
the time spent working.

  python3 idle_report.py <timing.jsonl> [--json]

Prints a line per command kind, then the split: commands versus idle. Exit 0 always unless
the file cannot be read — this is a report, not a gate.
"""
import argparse
import json
import sys


def load(path):
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get('started_at') is not None and row.get('elapsed_seconds') is not None:
                rows.append(row)
    return rows


def summarise(rows):
    """排序在这里做，不在读取那里：几个进程并行写同一个文件时，行序不等于时序。"""
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r['started_at'])
    busy = sum(r['elapsed_seconds'] for r in rows)
    span = (rows[-1]['started_at'] + rows[-1]['elapsed_seconds']) - rows[0]['started_at']
    gaps = []
    for before, after in zip(rows, rows[1:]):
        gap = after['started_at'] - (before['started_at'] + before['elapsed_seconds'])
        if gap > 0:
            gaps.append(dict(after=before.get('command'), before=after.get('command'),
                             seconds=round(gap, 2)))
    by_command = {}
    for r in rows:
        name = r.get('command') or '?'
        slot = by_command.setdefault(name, dict(count=0, seconds=0.0, failures=0))
        slot['count'] += 1
        slot['seconds'] += r['elapsed_seconds']
        slot['failures'] += 1 if r.get('exit_code') else 0
    return dict(commands=len(rows), span_seconds=round(span, 2),
                busy_seconds=round(busy, 2), idle_seconds=round(max(0.0, span - busy), 2),
                idle_share=round(max(0.0, span - busy) / span, 3) if span > 0 else 0.0,
                by_command={k: dict(count=v['count'], seconds=round(v['seconds'], 2),
                                    failures=v['failures'])
                            for k, v in sorted(by_command.items(),
                                               key=lambda kv: -kv[1]['seconds'])},
                longest_gaps=sorted(gaps, key=lambda g: -g['seconds'])[:5])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('timing', help='CA_TIMING_FILE 写出来的 JSONL')
    parser.add_argument('--json', action='store_true', help='只打 JSON，给脚本用')
    args = parser.parse_args(argv)
    try:
        rows = load(args.timing)
    except OSError as e:
        print(f'ERR_NO_FILE {args.timing}：{e}')
        return 2
    report = summarise(rows)
    if report is None:
        print('这个文件里没有带墙钟时间戳的记录，算不出命令之间的空当')
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    for name, slot in report['by_command'].items():
        print(f'{name}\t{slot["count"]} 次\t{slot["seconds"]:.1f} 秒'
              + (f'\t{slot["failures"]} 次非零退出' if slot['failures'] else ''))
    print('---')
    print(f'全程 {report["span_seconds"]:.1f} 秒；命令占用 {report["busy_seconds"]:.1f} 秒；'
          f'浏览器空置 {report["idle_seconds"]:.1f} 秒（{report["idle_share"] * 100:.0f}%）')
    if report['longest_gaps']:
        print('最长的几段空置：')
        for gap in report['longest_gaps']:
            print(f'  {gap["seconds"]:.1f} 秒\t在 {gap["after"]} 之后、{gap["before"]} 之前')
    print('空置是浏览器已经就绪、却没有命令在跑的时间。压它比压命令本身更有用。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
