# -*- coding: utf-8 -*-
"""SKILL.md 的正文只留"违反了会造成不可逆后果"的规矩。

正文每次都载入，细则是按需才读。把操作细节堆在正文里，模型一边干活一边回头查，
而浏览器就在旁边干等——实测一次真实投递里，这类纯阅读占掉了一大段时间。

判据定成"不可逆后果"而不是"重不重要"，因为后者每条都能论证成重要，所以会一轮轮长回来。
不可逆是可判定的：违反了会不会造成用户无法撤销的损失，能回答是或否。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / 'skills'
LIMIT = 900          # 正文字数上限（中文按字、英文按词）


def body_of(path):
    return re.sub(r'^---\n.*?\n---\n', '', path.read_text(encoding='utf-8'), flags=re.S)


def words(text):
    return len(re.findall(r'[一-鿿]|[A-Za-z]+', text))


def test_every_skill_body_is_short_enough_to_load_every_time():
    oversize = {}
    for skill in sorted(SKILLS.iterdir()):
        md = skill / 'SKILL.md'
        if not md.is_file():
            continue
        n = words(body_of(md))
        if n > LIMIT:
            oversize[skill.name] = n
    assert not oversize, (
        '正文超过 %d 字的 skill：%s。细则挪进 references，正文只留会造成不可逆后果的规矩'
        % (LIMIT, oversize))


def test_the_irreversible_rules_stay_in_the_body():
    """瘦身不能把真正要紧的几条也挪走——它们必须每次都在场。"""
    must = {
        'apply-fill': ['提交', '证件号'],
        'campus-apply': ['证件号'],
        'job-screen': ['不批量投递'],
        'resume-tailor': ['事实'],
        'resume-facts': ['来源'],
    }
    for name, needles in must.items():
        text = body_of(SKILLS / name / 'SKILL.md')
        for needle in needles:
            assert needle in text, '%s 的正文里不能缺「%s」这条' % (name, needle)


def test_bodies_point_at_references_instead_of_inlining_them():
    """正文要能指路：每个 skill 都得有指向 references 的链接。"""
    for skill in sorted(SKILLS.iterdir()):
        md = skill / 'SKILL.md'
        if not md.is_file() or not (skill / 'references').is_dir():
            continue
        assert 'references/' in body_of(md), '%s 的正文没有指向任何 reference' % skill.name
