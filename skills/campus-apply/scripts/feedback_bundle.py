#!/usr/bin/env python3
"""把一次求职工作目录里适合反馈给 skill 作者的文件收成一个文件夹，自动打码，不压缩、不上传。只用标准库。

用法：python3 feedback_bundle.py --workspace <工作目录> [--out <输出文件夹>] [--name <姓名>]
  --out 默认桌面下 campus-apply-反馈_<日期>；--name 默认取 campus-apply.json 里 profile.name，用来把姓名打码。

收什么：log.txt；applications/ 下的 执行清单、待你决定.md、fill-log.md、fill-report.md、limits.json、岗位清单_*.md、
  岗位筛选_*.md/.json、改动清单_*.md；工作目录根的 *_岗位筛选_*.xlsx；site-notes/*.md。
不收什么：事实库、campus-apply.json、rules.json、resume.md、form.md、简历 docx/pdf、screens/、stages/、jobs/ 和其他一切。
打码（.md / .json / .txt）：11 位手机号、邮箱、18 位证件号、"出生"附近的日期、姓名、用户主目录路径。
最后生成有来源的 反馈摘要.md（清单和包内错误自动汇总，缺会话信息明确未记录），打印文件清单，提醒用户自己翻一遍再发。
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
    version_file = os.path.join(HERE, '..', 'VERSION')
    try:
        with open(version_file, encoding='utf-8') as f:
            version = f.read().strip()
        if version:
            lines.append(f'- 当前打包工具 campus-apply 版本：{version}（来源：本skill的VERSION）')
            return '\n'.join(lines)
    except OSError:
        pass
    plugin = os.path.normpath(os.path.join(HERE, '..', '..', '..', '.claude-plugin', 'plugin.json'))
    try:
        with open(plugin, encoding='utf-8') as f:
            version = json.load(f).get('version', '?')
        lines.append(f'- 当前打包工具 campus-apply 版本：{version}（来源：仓库plugin.json）')
    except (OSError, ValueError):
        lines.append('- 当前打包工具 campus-apply 版本：未知（VERSION和仓库清单不可读取）')
    return '\n'.join(lines)


def doctor_output():
    try:
        import doctor
        return '\n'.join(r.line() for r in doctor.run_checks(doctor.Machine()))
    except Exception as e:
        return f'（doctor 未能运行：{e}）'


def bundle_evidence(files, bundle_dir):
    """只汇总已打码副本的明确行，不把文件存在或未勾推断为完成/失败。"""
    steps, unchecked, errors = [], [], []
    for rel in files:
        if os.path.splitext(rel)[1] not in TEXT_EXT:
            continue
        with open(os.path.join(bundle_dir, rel), encoding='utf-8') as f:
            lines = f.read().splitlines()
        if '执行清单' in os.path.basename(rel):
            done = sum(bool(re.match(r'^\s*[-*+]\s+\[[xX]\]', line)) for line in lines)
            todo = [(n, line) for n, line in enumerate(lines, 1)
                    if re.match(r'^\s*[-*+]\s+\[ \]', line)]
            steps.append(f'- {rel}：已勾{done}项、未勾{len(todo)}项（来源：该清单；完成状态需结合最新日志）')
            unchecked.extend(f'- {rel}:{n} — {line.strip()}' for n, line in todo)
        if os.path.basename(rel) in {'log.txt', 'fill-log.md', 'fill-report.md'}:
            for n, line in enumerate(lines, 1):
                if re.search(r'\bERR(?:_[A-Z][A-Z0-9_]*|[ :])', line):
                    errors.append(f'- {rel}:{n} — {line.strip()}')
    return steps, unchecked, errors


def summary(files, bundle_dir):
    steps, unchecked, errors = bundle_evidence(files, bundle_dir)
    step_text = '\n'.join(steps) or '未记录执行清单，无法从本包确认各阶段完成情况。'
    unchecked_text = '\n'.join(unchecked) or '所收清单未检出未勾行；没有清单或实际完成情况仍需结合原记录核对。'
    error_text = '\n'.join(errors) or '所收日志未检出明确ERR标记；没有完整工具轨迹，无法确认是否发生其他错误。'
    return f'''# campus-apply 反馈摘要（{datetime.date.today()}）

## 环境
{environment()}
- 历史执行实际载入的skill版本：未知（当前打包工具版本不能证明历史每次会话的版本）
- 历史harness、agent及模型版本：未记录（本脚本未读取聊天或全局配置，不能从现有材料确认）

## doctor
```
{doctor_output()}
```

## 走到了哪一步
{step_text}

## 未勾选的步骤
{unchecked_text}

## 停下来问了什么
未记录完整会话，无法确认停顿次数及每次问答。包内待你决定文件和填写日志可作为已记录事项的来源，不能据文件条数推算会话次数。

## 报错原文
以下为包内日志含ERR标记的原文位置；可能含历史记录或说明，需结合上下文核对。
{error_text}

## 不顺的地方
未记录完整会话及逐次计时，无法自动判断绕路、返工或规则跳步；仅能根据上述清单、日志和用户另行补充核查。

## 资料完整性
本摘要已汇总包内可识别证据；会话、实际载入版本、harness与模型、停顿及工具计时仍未确认。用户补充时注明来源，不覆盖原始记录。包只包含允许收集的工作记录，没有自动发送。

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
    if not os.path.isdir(ws):
        print('ERR_WORKSPACE: 工作目录不存在或不是目录', file=sys.stderr)
        return 2
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
    os.makedirs(out, exist_ok=True)
    text, n = mask_text(summary(files, out), name); masked += n
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
