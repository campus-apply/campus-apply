#!/usr/bin/env python3
"""按偏好和硬门槛把岗位清单机器预筛成三档，并算出读 JD 的两个代价。只用标准库。

为什么要它：清单读下来动辄一两百个岗位，把它们全部交给模型逐字读，既慢又占上下文，而其中
多数只看标题和一行要求就能排除。脚本先做能机器判的那部分，模型只逐字读真正的候选。

用法：
  python3 prescreen.py <清单.json> [--prefs campus-apply.json] [--facts 事实库.md …]
                       [--json 预筛_<日期>.json] [--md 预筛_<日期>.md] [--print]

清单 JSON 可以是数组，或 {"jobs": [...]} / {"list": [...]}。每条记录认下面这些键（都可缺）：
  标题       title / name / jobName / 岗位
  类别       cat / jobFamily / 类别
  地点       loc / city / cityList（支持 [{"name": …}] 这种结构）/ 地点
  职责正文   duty / jobDuty / 职责
  要求正文   req / jobRequirement / requirement / 要求
  性质       nature / recruitType / 性质
  链接       url / link
  站内编号   jobId / jobUnionId / id
键名在站点之间不一致，`--map 目标键=来源键` 可以手工接（可重复）。

三档的含义，和它们各自给谁看：
  读        机器判不出来、或判出来像候选 —— 交给模型逐字读 JD
  待定      命中了偏好里的排除词但正文里有反证，或地点等信息缺失 —— 列给用户圈
  排除      有明确可引用的硬证据 —— 每条都带规则名和命中的原文片段

规矩：脚本只做能引用原文的判断。学历、专业、语言这类要看 JD 正文的硬门槛，只有正文里确实
出现了对应说法才判；正文缺失一律进"读"，绝不当成不符合。任何一条排除都要能说出依据，
说不出就不排除。这份结果是给用户圈定用的建议，不替用户决定投哪个。
"""
import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

ALIASES = {
    'title': ('title', 'name', 'jobName', '岗位', '岗位名称'),
    'cat': ('cat', 'jobFamily', 'jobFamilyGroup', 'category', '类别'),
    'loc': ('loc', 'city', 'cityList', 'cities', 'location', '地点', '工作地点'),
    'duty': ('duty', 'jobDuty', 'responsibility', '职责', '岗位职责'),
    'req': ('req', 'jobRequirement', 'requirement', 'requirements', '要求', '岗位要求'),
    'nature': ('nature', 'recruitType', 'recruitTypeName', 'jobType', '性质'),
    'url': ('url', 'link', 'detailUrl'),
    'jobId': ('jobId', 'jobUnionId', 'id', '编号'),
    'org': ('org', 'department', 'departmentName', '部门', '单位'),
    'date': ('date', 'firstPostTime', 'refreshTime', 'publishTime', '发布日期'),
}

# 学历层级：数字越大要求越高
DEGREES = [('专科', 1), ('大专', 1), ('本科', 2), ('学士', 2), ('硕士', 3), ('研究生', 3),
           ('博士', 4), ('MBA', 3)]
DEGREE_NAMES = {1: '专科', 2: '本科', 3: '硕士', 4: '博士'}


def flatten(value):
    """地点这类字段各站写法不一：字符串、数组、[{"name": …}] 都要能读成一串文本。"""
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ('name', 'label', 'text', 'value'):
            if isinstance(value.get(key), str):
                return value[key]
        return ' '.join(flatten(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return '、'.join(part for part in (flatten(v) for v in value) if part)
    return str(value)


def pick(record, field, extra_map):
    if field in extra_map:
        source = extra_map[field]
        if source in record:
            return flatten(record[source])
    for key in ALIASES.get(field, (field,)):
        if key in record and record[key] not in (None, ''):
            return flatten(record[key])
    return ''


def normalise(record, extra_map):
    out = {field: pick(record, field, extra_map) for field in ALIASES}
    out['_raw_keys'] = sorted(record)
    return out


def quote(text, pattern, width=46):
    """把命中的位置连上下文摘出来，作为"依据原文"。排除必须能引用原文，不能只给结论。"""
    hit = re.search(pattern, text)
    if not hit:
        return ''
    start = max(0, hit.start() - width // 3)
    end = min(len(text), hit.end() + width)
    return ('…' if start else '') + text[start:end].replace('\n', ' ') + ('…' if end < len(text) else '')


def required_degree(text):
    """JD 正文里要求的最低学历。'本科及以上'取本科；'硕士'且没有'及以上'也取硕士。"""
    best = None
    for name, level in DEGREES:
        for hit in re.finditer(re.escape(name), text):
            tail = text[hit.end():hit.end() + 6]
            # "硕士及以上" / "本科以上" → 门槛就是这一级；"硕士、博士" → 取较低的那个
            level_here = level
            if best is None or level_here < best[0]:
                best = (level_here, name, quote(text, re.escape(name) + r'(?:及?以上)?'))
            if '及以上' in tail or '以上' in tail:
                continue
    return best


def excluded_by_keyword(row, words):
    """偏好里"坚决不投"的词，只看标题和类别——这两处的词是岗位的名字。

    正文不参与匹配：实测美团 194 个岗位，72 个的职责/要求里出现"研究"，全是动词用法
    （"能深入代码研究""利用 LLM 辅助行业研究"），和"研究岗"没关系。拿正文匹配会把一半
    岗位推进待定，等于把判断又推回给人，白做。
    """
    title, cat = row['title'], row['cat']
    for word in words:
        if not word:
            continue
        if word in title:
            return 'title', word, quote(title, re.escape(word))
        if word in cat:
            return 'cat', word, quote(cat, re.escape(word))
    return None, None, None


def judge(row, prefs, facts_degree):
    """返回 (档, 规则名, 依据原文)。只在能引用原文时排除。"""
    body = row['duty'] + '\n' + row['req']
    title = row['title']

    # 1. 偏好里整体不投的岗位性质（实习、社招）：按性质字段和标题判
    for word in prefs.get('skip_nature', []):
        field = row['nature'] + ' ' + title
        if word and word in field:
            return '排除', '偏好：不投这类招聘', quote(field, re.escape(word))

    # 2. 坚决不投的岗位类型
    where, word, evidence = excluded_by_keyword(row, prefs.get('exclude_keywords', []))
    if where == 'title':
        return '排除', f'偏好：不投「{word}」类岗位（标题命中）', evidence
    if where == 'cat':
        return '排除', f'偏好：不投「{word}」类岗位（类别命中）', evidence

    # 3. 海外地点。
    # 不枚举城市名：实测美团的海外地点是利雅得、迪拜、科威特城、圣保罗这些，任何写死的清单都会漏。
    # 改成反过来判——国内地级市在招聘站上几乎一律写成"××市"（或直辖市、自治区、特别行政区），
    # 列出来的地点里只要有一个不符合这个形状，就当成海外候选。
    if not prefs.get('overseas', True) and row['loc']:
        places = [p.strip() for p in re.split(r'[、,，/；;]+', row['loc']) if p.strip()]
        odd = [p for p in places if not DOMESTIC_PLACE.search(p)]
        if odd:
            inland = [p for p in places if DOMESTIC_PLACE.search(p)]
            if inland:
                # 既有国内也有海外：岗位可能两地都招，不替用户决定
                return '待定', f'地点里有国内也有境外（{"、".join(odd)}），要你定投不投', row['loc']
            return '排除', f'偏好：不投海外（地点 {"、".join(odd)}）', row['loc']
    if not prefs.get('overseas', True) and not row['loc']:
        for word in ('海外', 'Overseas', '国际化业务'):
            if word in title:
                return '待定', f'标题里有「{word}」但地点字段是空的，要你看一眼', quote(title, re.escape(word))

    # 4. 学历硬门槛：只有正文明确写了才判
    if facts_degree and body.strip():
        need = required_degree(body)
        if need and need[0] > facts_degree:
            return '排除', f'学历硬门槛：要求{need[1]}，你是{DEGREE_NAMES.get(facts_degree, "?")}', need[2]

    # 5. 语言硬门槛
    for word in prefs.get('exclude_languages', []):
        if word and word in body:
            return '待定', f'正文提到「{word}」，是不是硬要求要读一下', quote(body, re.escape(word))

    # 6. 正文缺失：判不了，交给模型读
    if not body.strip():
        return '读', '清单里没有正文，要打开详情才知道', ''
    return '读', '机器判不出硬门槛，像候选', ''


def estimate(to_read, has_body):
    """读 JD 的两个代价，分开报。把它们混成一个"大约几分钟"是上一轮踩过的坑：
    正文随清单返回时浏览器时间是 0，真正的成本在模型读取量上。"""
    chars = sum(len(r['duty']) + len(r['req']) for r in to_read)
    if has_body:
        browser = 0.0
        note = '正文已随清单拿到，不用再开网页'
    else:
        browser = len(to_read) * 4 / 60
        note = f'要逐个打开详情页，按每个约 4 秒估'
    return dict(count=len(to_read), chars=chars, browser_minutes=round(browser, 1), note=note)


# resume-facts 写进 campus-apply.json 的键名（见 resume-facts 第 5 步的求职偏好访谈）。
# `role_types_no` 之类的条目是整句人话（"研究岗（声学、算法、香港研究类）"），不能整句去标题里匹配，
# 要先切成关键词：括号内外分开、顿号逗号斜杠分段、去掉"岗""型"这类后缀。
SPLIT = re.compile(r'[（）()、，,/；;]+')
TAIL = re.compile(r'(岗位|岗|类|型|的)+$')   # "纯销售型岗" 要一路剥到 "纯销售"
# 国内地点在招聘站上的写法：地级市带"市"，少数写成省/自治区/特别行政区或直辖市简称。
# 用它反过来认海外，比枚举海外城市名可靠（见 judge 里第 3 条的说明）。
DOMESTIC_PLACE = re.compile(r'(市|省|自治区|特别行政区|不限|全国|国内|远程|北京|上海|广州|深圳|天津|重庆)')


def keywords_from(entries):
    out = []
    for entry in entries or []:
        if not isinstance(entry, str):
            continue
        for part in SPLIT.split(entry):
            part = TAIL.sub('', part.strip())
            if len(part) >= 2 and part not in out:
                out.append(part)
    return out


def load_prefs(path):
    """从 campus-apply.json 的 preferences 读偏好。读不到就用空偏好——没有依据就不排除，不猜。"""
    prefs = {'exclude_keywords': [], 'skip_nature': [], 'exclude_languages': [], 'overseas': True}
    if not path or not os.path.isfile(path):
        return prefs, '没给 campus-apply.json，只做正文缺失和学历判断'
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return prefs, f'读不出 campus-apply.json（{e}），按空偏好处理'
    p = data.get('preferences') or {}
    prefs['exclude_keywords'] = keywords_from(p.get('role_types_no'))
    # apply_types 是"要投什么"，其他招聘类型就是不投的；性质字段里出现它们才排除
    wanted = ' '.join(p.get('apply_types') or [])
    if wanted and '实习' not in wanted:
        prefs['skip_nature'].append('实习')
    if wanted and '社招' not in wanted and '社会招聘' not in wanted:
        prefs['skip_nature'] += ['社会招聘', '社招']
    prefs['overseas'] = bool(p.get('overseas_ok', True))
    if 'overseas_words' in p:
        prefs['overseas_words'] = p['overseas_words']
    bits = []
    if prefs['exclude_keywords']:
        bits.append('不投的岗位类型关键词：' + '、'.join(prefs['exclude_keywords']))
    else:
        bits.append('preferences 里没有 role_types_no，不按岗位类型排除')
    bits.append('不接受海外' if not prefs['overseas'] else '海外可投')
    return prefs, '偏好来自 campus-apply.json（' + '；'.join(bits) + '）'


def read_degree(paths):
    """事实库里的最高学历。找不到返回 None——没有依据就不按学历排除。"""
    best, evidence = None, ''
    for path in paths or []:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding='utf-8') as f:
                text = f.read()
        except OSError:
            continue
        for name, level in DEGREES:
            if re.search(r'(学历|学位|在读|毕业|硕士|本科|博士)', text) and name in text:
                if best is None or level > best:
                    best, evidence = level, os.path.basename(path)
    return best, evidence


def render_md(groups, est, notes, title):
    lines = [f'# {title}', '']
    lines += ['机器预筛：只做能引用原文的判断。正文缺失、依据不足一律进"读"或"待定"，不当成不符合。', '']
    for note in notes:
        lines.append(f'- {note}')
    lines += ['', f"- 要模型逐字读的：**{est['count']} 个**，合计约 {est['chars']} 字",
              f"- 浏览器时间：**{est['browser_minutes']} 分钟**（{est['note']}）", '']
    for tier, label in (('读', '交给模型逐字读'), ('待定', '要你圈一下'), ('排除', '已排除（每条带依据）')):
        rows = groups.get(tier, [])
        lines += [f'## {label}（{len(rows)} 个）', '']
        if not rows:
            lines += ['（无）', '']
            continue
        lines.append('| 岗位 | 类别 | 地点 | 判断依据 | 依据原文 |')
        lines.append('|---|---|---|---|---|')
        for r in rows:
            evidence = (r['_evidence'] or '').replace('|', '｜')
            lines.append(f"| {r['title']} | {r['cat']} | {r['loc']} | {r['_rule']} | {evidence} |")
        lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('listing', nargs='?', help='岗位清单 JSON')
    parser.add_argument('--prefs', help='campus-apply.json 路径')
    parser.add_argument('--facts', nargs='*', default=[], help='事实库 md，用来读最高学历')
    parser.add_argument('--map', action='append', default=[], metavar='目标键=来源键')
    parser.add_argument('--json', dest='json_out')
    parser.add_argument('--md', dest='md_out')
    parser.add_argument('--print', dest='do_print', action='store_true')
    parser.add_argument('--title', default='岗位预筛')
    args = parser.parse_args(argv)
    if not args.listing:
        print(__doc__)
        return 2
    if not os.path.isfile(args.listing):
        print(f'ERR_NO_FILE {args.listing}')
        return 2
    try:
        with open(args.listing, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f'ERR_LIST: 读不出清单 JSON：{e}')
        return 2
    records = data
    if isinstance(data, dict):
        for key in ('jobs', 'list', 'data', 'records', 'items'):
            if isinstance(data.get(key), list):
                records = data[key]
                break
    if not isinstance(records, list) or not records:
        print('ERR_LIST: 清单里没有岗位数组（认 jobs / list / data / records / items，或直接是数组）')
        return 2
    if not all(isinstance(r, dict) for r in records):
        print('ERR_LIST: 清单里每一项都要是对象')
        return 2

    extra_map = {}
    for item in args.map:
        target, _, source = item.partition('=')
        if not target or not source:
            print(f'ERR_USAGE prescreen: --map 要写成 目标键=来源键，收到 {item!r}')
            return 2
        extra_map[target.strip()] = source.strip()

    prefs, prefs_note = load_prefs(args.prefs)
    degree, degree_from = read_degree(args.facts)
    notes = [prefs_note]
    notes.append(f'学历口径：{DEGREE_NAMES.get(degree, "未取到")}'
                 + (f'（来自 {degree_from}）' if degree_from else '，所以不按学历排除'))

    rows = [normalise(r, extra_map) for r in records]
    groups = {}
    for row in rows:
        tier, rule, evidence = judge(row, prefs, degree)
        row['_tier'], row['_rule'], row['_evidence'] = tier, rule, evidence
        groups.setdefault(tier, []).append(row)
    has_body = any((r['duty'] + r['req']).strip() for r in rows)
    est = estimate(groups.get('读', []), has_body)

    if args.json_out:
        payload = dict(title=args.title, notes=notes, estimate=est,
                       counts={k: len(v) for k, v in groups.items()},
                       jobs=[{k: v for k, v in r.items() if k != '_raw_keys'} for r in rows])
        try:
            with open(args.json_out, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
        except OSError as e:
            print(f'ERR_WRITE: {args.json_out}：{e.strerror or e}')
            return 1
        print(args.json_out)
    text = render_md(groups, est, notes, args.title)
    if args.md_out:
        try:
            with open(args.md_out, 'w', encoding='utf-8') as f:
                f.write(text + '\n')
        except OSError as e:
            print(f'ERR_WRITE: {args.md_out}：{e.strerror or e}')
            return 1
        print(args.md_out)
    if args.do_print or not (args.json_out or args.md_out):
        print(text)
    print(f"预筛 {len(rows)} 个：读 {len(groups.get('读', []))}、待定 {len(groups.get('待定', []))}、"
          f"排除 {len(groups.get('排除', []))}；"
          f"模型读取量 {est['chars']} 字，浏览器 {est['browser_minutes']} 分钟", file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
