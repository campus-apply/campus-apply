#!/usr/bin/env python3
"""只读检查执行清单和待决记录中的明确矛盾，不推断完成、不修改文件。

用法：workspace_state.py --workspace DIR [--scope applications/公司或岗位]
输出JSON（文件相对路径、行号、关联位置）；0无发现，1有待核项，2输入/读取错误。
识别同标题事项同时未决和已定、同编号同标题清单重复勾选状态；未勾本身不是错误。
"""
import argparse
import json
from pathlib import Path
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

ITEM = re.compile(r'^\s*(?:[-*+]\s+)?(?:\[([ xX])\]\s*)?(\d+)[.、．)]?\s+(.+?)\s*$')
CHECK = re.compile(r'^\s*[-*+]\s+\[([ xX])\]\s*(.+?)\s*$')


def topic(text):
    """只按明示标题匹配，不凭相近措辞认定已回答。"""
    head = re.split(r'[:：→]|\s+[—–]{1,2}\s*', text, maxsplit=1)[0]
    return re.sub(r'\s+', '', head).strip()


def records(ws):
    decisions, checks, count = [], [], 0
    apps = ws / 'applications'
    if not apps.exists():
        return decisions, checks, count
    for path in sorted(apps.rglob('*.md')):
        if path.name != '待你决定.md' and '执行清单' not in path.name:
            continue
        if not path.resolve().is_relative_to(ws):
            raise ValueError('记录文件位于工作目录外')
        count += 1
        rel = path.relative_to(ws).as_posix()
        group = path.relative_to(apps).parts[0].split('-', 1)[0]
        section = None
        for line, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            heading = re.match(r'^\s*#{1,6}\s+(.+)', raw)
            if heading:
                title = heading[1].strip()
                section = ('pending' if title.startswith(('未决', '待决定', '待你决定')) else
                           'decided' if title.startswith(('已定', '已决定', '已回答')) else None)
                continue
            if path.name == '待你决定.md' and section:
                if raw[:1].isspace():
                    continue  # 嵌套候选、说明和代码不是原标题事项。
                match = ITEM.match(raw)
                text = match[3] if match else None
                if text is None:
                    named = re.match(r'^(?:[-*+]\s+)?([^\n]+?[:：→].+)$', raw)
                    text = named[1] if named else None
                if text and topic(text):
                    decisions.append(dict(path=rel, line=line, group=group, state=section,
                                          key=topic(text)))
            elif '执行清单' in path.name:
                match = CHECK.match(raw)
                if match:
                    item = ITEM.match(match[2])
                    if item:
                        checks.append(dict(path=rel, line=line, state=match[1].lower() == 'x',
                                           key=(item[2], topic(item[3]))))
    return decisions, checks, count


def inspect(workspace, scope=None):
    ws = Path(workspace).resolve()
    if not ws.is_dir():
        raise ValueError('工作目录不存在或不是目录')
    selected = None
    if scope:
        selected = (ws / scope).resolve()
        if Path(scope).is_absolute() or not selected.is_relative_to(ws / 'applications') or not selected.is_dir():
            raise ValueError('--scope 必须是工作目录内存在的 applications 相对目录')
    decisions, checks, count = records(ws)
    findings = []

    def add(item, kind, matches, message):
        if selected and not (ws / item['path']).is_relative_to(selected):
            return
        findings.append(dict(path=item['path'], line=item['line'], kind=kind, message=message,
                             related=[dict(path=m['path'], line=m['line']) for m in matches]))

    for item in decisions:
        if item['state'] != 'pending':
            continue
        same = [d for d in decisions if d['state'] == 'decided' and d['path'] == item['path'] and d['key'] == item['key']]
        related = [d for d in decisions if d['state'] == 'decided' and d['path'] != item['path']
                   and d['group'] == item['group'] and d['key'] == item['key']]
        if same:
            add(item, 'pending_and_decided', same, '同一标题事项同时列为未决和已定，请依据明确答复更新原项。')
        elif related:
            add(item, 'related_decision', related, '相关投递目录有同标题已定项，请核对是否适用后同步；不会自动关闭。')
    for item in checks:
        if not item['state']:
            same = [c for c in checks if c['state'] and c['path'] == item['path'] and c['key'] == item['key']]
            if same:
                add(item, 'duplicate_checklist_state', same, '同编号同标题步骤另起已勾行，请核对完成依据并回改原行。')
    return dict(findings=findings, checked_files=count,
                limitations=['只识别明确编号/标题和章节；无法证明实际执行完成，或自然语言答复的适用性。'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--scope')
    args = parser.parse_args(argv)
    try:
        result = inspect(args.workspace, args.scope)
    except (OSError, ValueError, UnicodeError) as exc:
        print('ERR_STATE: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result['findings'] else 0


if __name__ == '__main__':
    sys.exit(main())
