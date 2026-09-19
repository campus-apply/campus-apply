#!/usr/bin/env python3
"""初始化 campus-apply 工作目录：写标记文件 campus-apply.json；缺 rules.json 就从模板复制；没指定事实库就从模板新建一份。
用法：python3 init_workspace.py --dir <工作目录> [--facts a.md b.md] [--resume-docx x.docx] [--force]
不挪动、不覆盖用户已有文件；标记文件已存在且未加 --force 时只打印现状。退出码：0 成功，1 指定的文件不存在。"""
import argparse, json, os, shutil, sys

try:
    sys.stdout.reconfigure(encoding='utf-8')  # Windows 终端默认不是 UTF-8，中文会乱码
except AttributeError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(os.path.dirname(HERE), 'templates')
MARK = 'campus-apply.json'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='.')
    ap.add_argument('--facts', nargs='*', default=None, help='事实库文件（相对工作目录）')
    ap.add_argument('--resume-docx', default=None, help='用户现有简历 docx（相对工作目录）')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args(argv)
    d = os.path.abspath(a.dir)
    os.makedirs(d, exist_ok=True)
    mark = os.path.join(d, MARK)
    if os.path.exists(mark) and not a.force:
        print('已初始化：', mark)
        print(open(mark, encoding='utf-8').read())
        return 0
    facts = a.facts
    if not facts:
        fp = os.path.join(d, '个人经历事实库.md')
        if not os.path.exists(fp):
            shutil.copy(os.path.join(TPL, 'facts.template.md'), fp)
            print('新建事实库：', fp)
        facts = ['个人经历事实库.md']
    for f in facts:
        if not os.path.exists(os.path.join(d, f)):
            print('找不到事实库文件：', f, file=sys.stderr)
            return 1
    if a.resume_docx and not os.path.exists(os.path.join(d, a.resume_docx)):
        print('找不到简历文件：', a.resume_docx, file=sys.stderr)
        return 1
    gi = os.path.join(d, '.gitignore')
    if not os.path.exists(gi):
        with open(gi, 'w', encoding='utf-8') as fh:
            fh.write('# campus-apply 工作目录含个人数据，不要放进公开仓库；若必须用 git，至少忽略这些\n'
                     'campus-apply.json\nrules.json\napplications/\nsite-notes/\n*.docx\n*.pdf\n')
        print('新建 .gitignore（工作目录含个人数据，请勿放进公开仓库）：', gi)
    rules = os.path.join(d, 'rules.json')
    if not os.path.exists(rules):
        shutil.copy(os.path.join(TPL, 'rules.template.json'), rules)
        print('新建规则文件：', rules)
    cfg = {'version': 1, 'facts': facts, 'rules': 'rules.json', 'resume_docx': a.resume_docx,
           'applications_dir': 'applications', 'site_notes_dir': 'site-notes',
           # 求职偏好：由 resume-facts 的偏好访谈填写，job-screen 读它做粗筛，只问变化的部分
           'preferences': {'apply_types': [], 'role_types_ok': [], 'role_types_no': [], 'locations_ok': [],
                           'overseas_ok': None, 'english_working_ok': None, 'early_onboarding_ok': None, 'notes': ''},
           # 个人档案：网申各站都要的基本字段，初始化访谈填；证件号、密码永远不存
           'profile': {'gender': '', 'birth': '', 'city': '', 'politics': '', 'degree': '', 'graduation': '',
                       'expected_city': '', 'expected_salary_month_k': '', 'expected_salary_year_w': '', 'channel': '', 'referral': ''}}
    with open(mark, 'w', encoding='utf-8') as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    print('已写入：', mark)
    return 0


if __name__ == '__main__':
    sys.exit(main())
