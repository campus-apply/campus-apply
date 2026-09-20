#!/usr/bin/env python3
"""内容检查：禁用词、禁用符号、敏感词、不可证明的表述、每条数字个数、数字出处、分节字数上限。
用法：python3 check_content.py <文本.md> --rules rules.json --facts 事实库.md [更多.md] [--limits limits.json]
文本按 "## 节名" 分节；limits.json 每项是上限数字，或 {"min": 200, "max": 1000, "unit": "字"|"字节"}。输出 [ERR]/[WARN]/[OK]；有 ERR 退出码 1。"""
import argparse, json, re, sys

try:
    sys.stdout.reconfigure(encoding='utf-8')  # Windows 终端默认不是 UTF-8，中文会乱码
except AttributeError:
    pass

NUM = re.compile(r'\d[\d,，.]*%?')
YEAR = re.compile(r'(19|20)\d\d')
LIST_PREFIX = re.compile(r'^\s*(?:[-*•·]\s*)?\d{1,2}[.、)]\s*')   # 行首的列表序号："3." "2、" "1)"
YM = re.compile(r'((?:19|20)\d\d)\s*[-./年]\s*(\d{1,2})\s*月?')     # 2019.12 / 2019-12 / 2019 年 12 月
QUOTED = re.compile(r'《[^》]*》|「[^」]*」|"[^"]*"')
COMMENT = re.compile(r'<!--.*?-->', re.S)                                  # 文件里的说明注释不是正文
LENGTH_NOTE = re.compile(r'[（(]\s*(?:约|不超过|≤)?\s*\d+\s*字\s*[)）]')   # "（约 300 字）"这类字数标注


def split_sections(text):
    secs, name, buf = [], '(全文)', []
    for line in text.splitlines():
        if line.startswith('## '):
            if buf: secs.append((name, '\n'.join(buf)))
            name, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if buf: secs.append((name, '\n'.join(buf)))
    return secs


def norm(s):
    return s.replace(',', '').replace('，', '').rstrip('.')


def norm_ym(s):
    """把各种写法的年月统一成 2019-12，便于和事实库互相匹配。"""
    return YM.sub(lambda m: f'{m.group(1)}-{int(m.group(2)):02d}', s)


def numbers_in(s):
    """抽出数字，跳过型号里的数字（CET-6、GPT-4 这类"字母-数字"）。"""
    out = []
    for m in NUM.finditer(s):
        i = m.start()
        if i >= 2 and s[i - 1] == '-' and s[i - 2].isalpha(): continue
        out.append(m.group())
    return out


def check(text, rules, facts_text, limits=None):
    out = []
    facts_norm = norm(norm_ym(facts_text))
    for name, body in split_sections(text):
        body = LENGTH_NOTE.sub('', COMMENT.sub('', body))
        body_for_words = QUOTED.sub('', body) if rules.get('banned_words_exempt_in_quotes') else body  # 书名号、引号里的标题名可豁免
        for w in rules.get('banned_words', []):
            if w in body_for_words: out.append(('ERR', name, f'禁用词「{w}」'))
        for ch in rules.get('banned_chars', []):
            if ch in body: out.append(('ERR', name, f'禁用符号「{ch}」'))
        for w in rules.get('sensitive_terms', []):
            if w in body: out.append(('ERR', name, f'敏感词「{w}」'))
        for w in rules.get('forbidden_claims', []):
            if w in body: out.append(('WARN', name, f'不可证明的表述「{w}」'))
        maxn = rules.get('max_numbers_per_bullet')
        if maxn:
            for ln in body.splitlines():
                if ln.strip() and not ln.startswith('#'):
                    nums = [m for m in numbers_in(LIST_PREFIX.sub('', ln)) if not YEAR.fullmatch(norm(m))]
                    if len(nums) > maxn:
                        out.append(('WARN', name, f'一条里有{len(nums)}个数字（上限{maxn}）：{ln.strip()[:40]}'))
        if rules.get('number_source_check'):
            seen = set()
            for m in numbers_in(norm_ym(body)):
                v = norm(m)
                if len(v.rstrip('%')) < 2 or YEAR.fullmatch(v) or v in seen: continue
                seen.add(v)
                if v not in facts_norm and v.rstrip('%') not in facts_norm:
                    out.append(('WARN', name, f'数字「{m}」在事实库里找不到'))
        if limits and name in limits:
            lim = limits[name] if isinstance(limits[name], dict) else {'max': limits[name]}
            unit = lim.get('unit', '字')
            n = len(body.strip().encode('utf-8')) if unit == '字节' else len(body.strip())
            if lim.get('max') is not None and n > lim['max']:
                out.append(('ERR', name, f'超长：{n} {unit} > 上限 {lim["max"]}'))
            if lim.get('min') is not None and n < lim['min']:
                out.append(('ERR', name, f'低于下限：{n} {unit} < 下限 {lim["min"]}'))
        out.append(('OK', name, f'{len(body.strip())} 字'))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('text'); ap.add_argument('--rules', required=True)
    ap.add_argument('--facts', nargs='+', required=True); ap.add_argument('--limits')
    a = ap.parse_args(argv)
    rules = json.load(open(a.rules, encoding='utf-8'))
    facts = '\n'.join(open(f, encoding='utf-8').read() for f in a.facts)
    limits = json.load(open(a.limits, encoding='utf-8')) if a.limits else None
    res = check(open(a.text, encoding='utf-8').read(), rules, facts, limits)
    for lvl, sec, msg in res: print(f'[{lvl}] {sec}: {msg}')
    return 1 if any(l == 'ERR' for l, _, _ in res) else 0


if __name__ == '__main__':
    sys.exit(main())
