#!/usr/bin/env python3
"""把一次求职工作目录里适合反馈给 skill 作者的文件收成一个文件夹，自动打码，不压缩、不上传。只用标准库。

用法：python3 feedback_bundle.py --workspace <工作目录> [--out <输出文件夹>] [--name <姓名>]
  --out 默认桌面下 campus-apply-反馈_<日期>；--name 默认取 campus-apply.json 里 profile.name，用来把姓名打码。

收什么：log.txt；applications/ 下的 执行清单、待你决定.md、fill-log.md、fill-report.md、limits.json、岗位清单_*.md、
  岗位筛选_*.md/.json、改动清单_*.md；工作目录根的 *_岗位筛选_*.xlsx；site-notes/*.md。
不收什么：事实库、campus-apply.json、rules.json、resume.md、form.md、简历 docx/pdf、screens/、stages/、jobs/ 和其他一切。
打码（.md / .json / .txt）：11 位手机号、邮箱、18 位证件号、"出生"附近的日期、姓名、用户主目录路径。
最后生成 反馈摘要.md 骨架（环境和依赖检查由本脚本填，其余留给 agent 补），打印文件清单，提醒用户自己翻一遍再发。
只在用户明确要反馈包时运行。"""
import argparse, datetime, glob, json, os, platform, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'browser'))

try:
    sys.stdout.reconfigure(encoding='utf-8')  # Windows 终端默认不是 UTF-8，中文会乱码
except AttributeError:
    pass

APP_PATTERNS = ['*执行清单*.md', '待你决定.md', 'fill-log.md', 'fill-report.md', 'limits.json', '岗位清单_*.md', '岗位筛选_*.md', '岗位筛选_*.json', '改动清单_*.md']
TEXT_EXT = {'.md', '.json', '.txt'}
MASKS = [
    (re.compile(r'(?<!\d)1\d{10}(?!\d)'), '【手机】'),
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '【邮箱】'),
    (re.compile(r'(?<![\dXx])\d{17}[\dXx](?![\dXx])'), '【证件号】'),
    (re.compile(r'(出生[^\n]{0,12}?)(\d{4}\s*[-./年]\s*\d{1,2}(?:\s*[-./月]\s*\d{1,2}\s*日?)?)'), r'\1【出生日期】'),
    (re.compile(r'[A-Za-z]:\\Users\\[^\\\s/]+'), '<主目录>'),
    (re.compile(r'/(?:Users|home)/[^/\s]+'), '<主目录>'),
]


def collect(ws):
    """返回 (相对路径, 绝对路径) 列表。"""
    found = []
    for name in ['log.txt']:
        p = os.path.join(ws, name)
        if os.path.isfile(p):
            found.append((name, p))
    for pat in APP_PATTERNS:
        for p in glob.glob(os.path.join(ws, 'applications', '**', pat), recursive=True):
            found.append((os.path.relpath(p, ws), p))
    for p in glob.glob(os.path.join(ws, '*_岗位筛选_*.xlsx')):
        found.append((os.path.relpath(p, ws), p))
    for p in glob.glob(os.path.join(ws, 'site-notes', '*.md')):
        found.append((os.path.relpath(p, ws), p))
    seen, out = set(), []
    for rel, p in found:
        if rel not in seen:
            seen.add(rel); out.append((rel, p))
    return out


def mask_text(text, name=None):
    n = 0
    for rx, rep in MASKS:
        text, k = rx.subn(rep, text); n += k
    if name and len(name) >= 2:
        text, k = re.subn(re.escape(name), '【姓名】', text); n += k
    return text, n


def profile_name(ws):
    try:
        cfg = json.load(open(os.path.join(ws, 'campus-apply.json'), encoding='utf-8'))
        return (cfg.get('profile') or {}).get('name')
    except (OSError, ValueError):
        return None


def environment():
    lines = [f'- 操作系统：{platform.system()} {platform.release()} ({platform.version()[:40]})',
             f'- Python：{platform.python_version()}（{sys.executable}）']
    try:
        from chrome_cdp import find_browser
        lines.append(f'- 浏览器：{find_browser() or "未找到"}')
    except Exception:
        pass
    plugin = os.path.normpath(os.path.join(HERE, '..', '..', '..', '.claude-plugin', 'plugin.json'))
    try:
        lines.append(f"- campus-apply 版本：{json.load(open(plugin, encoding='utf-8')).get('version', '?')}")
    except (OSError, ValueError):
        lines.append('- campus-apply 版本：未知（请填 claude plugin details 或 SKILL 目录位置）')
    return '\n'.join(lines)


def doctor_output():
    try:
        import doctor
        return '\n'.join(r.line() for r in doctor.run_checks(doctor.Machine()))
    except Exception as e:
        return f'（doctor 未能运行：{e}）'


def summary(files):
    return f'''# campus-apply 反馈摘要（{datetime.date.today()}）

## 环境
{environment()}
- 用的 agent 工具及版本：（agent 补）

## doctor
```
{doctor_output()}
```

## 走到了哪一步
（agent 补：resume-facts / job-screen / resume-tailor / apply-fill 各做没做、做到哪）

## 未勾选的步骤
（agent 补：每份执行清单里未勾选的行）

## 停下来问了什么
（agent 补：一共停了几次，每次在哪一步、问什么、用户怎么答）

## 报错原文
（agent 补：本次会话所有报错逐条原样贴）

## 不顺的地方
（agent 补：绕弯、不确定是否按 skill 做的地方，如实写）

## 本包文件
{chr(10).join('- ' + f for f in files)}
'''


def main(argv=None):
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument('--workspace', required=True); ap.add_argument('--out'); ap.add_argument('--name')
    if not (argv if argv is not None else sys.argv[1:]):
        print(__doc__); return 2
    a = ap.parse_args(argv)
    ws = os.path.abspath(a.workspace)
    out = a.out or os.path.join(os.path.expanduser('~'), 'Desktop', f'campus-apply-反馈_{datetime.date.today()}')
    name = a.name or profile_name(ws)
    files, masked = [], 0
    for rel, src in collect(ws):
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.splitext(rel)[1] in TEXT_EXT:
            text, n = mask_text(open(src, encoding='utf-8', errors='replace').read(), name)
            masked += n
            with open(dst, 'w', encoding='utf-8') as f:
                f.write(text)
        else:
            shutil.copy2(src, dst)
        files.append(rel)
    text, n = mask_text(summary(files), name); masked += n
    with open(os.path.join(out, '反馈摘要.md'), 'w', encoding='utf-8') as f:
        f.write(text)
    files.append('反馈摘要.md')
    print(f'反馈包：{out}')
    for rel in files:
        print(f'  {os.path.getsize(os.path.join(out, rel)):>8} B  {rel}')
    print(f'打码 {masked} 处。没有压缩、没有发送；请自己翻一遍再压缩发给别人，不要把工作目录整个发出去。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
