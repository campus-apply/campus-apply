import importlib.util, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..', 'skills', 'resume-tailor', 'scripts', 'check_content.py')
spec = importlib.util.spec_from_file_location('check_content', P); cc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)

RULES = {"banned_words": ["赋能"], "banned_chars": ["→"], "sensitive_terms": ["万联易达"], "forbidden_claims": ["主导上线"],
         "max_numbers_per_bullet": 2, "number_source_check": True}
FACTS = "调用量 15 个月约 519 万次，成功率 92%–95.6%。2026-05 入职。"


def levels(res, sec=None):
    return [(l, m) for l, s, m in res if sec is None or s == sec]


def test_banned_word_and_char_are_err():
    res = cc.check("## 实习\n- 为客户赋能→提升", RULES, FACTS)
    msgs = [m for l, m in levels(res) if l == 'ERR']
    assert any('赋能' in m for m in msgs) and any('→' in m for m in msgs)


def test_sensitive_term_is_err_and_claim_is_warn():
    res = cc.check("## 实习\n- 支撑万联易达项目，主导上线", RULES, FACTS)
    assert ('ERR', '实习') in [(l, s) for l, s, m in res if '万联易达' in m]
    assert ('WARN', '实习') in [(l, s) for l, s, m in res if '主导上线' in m]


def test_number_without_source_is_warn_but_sourced_number_passes():
    res = cc.check("## 实习\n- 分析519万次调用，成功率95.6%\n- 峰值1285路", RULES, FACTS)
    warns = [m for l, m in levels(res) if l == 'WARN']
    assert any('1285' in m for m in warns)
    assert not any('519' in m or '95.6' in m for m in warns)


def test_years_and_single_digits_are_ignored():
    res = cc.check("## 教育\n- 2020年入学，3个项目", RULES, "")
    assert not [m for l, m in levels(res) if l == 'WARN' and '找不到' in m]


def test_too_many_numbers_per_line_is_warn():
    res = cc.check("## 实习\n- 15个月519万次跌50%三项", RULES, FACTS)
    assert any('3个数字' in m for l, m in levels(res) if l == 'WARN')


def test_section_limit_is_err_and_exit_code(tmp_path):
    res = cc.check("## 工作描述\n" + "字" * 30, RULES, FACTS, limits={"工作描述": 20})
    assert any(l == 'ERR' and '超长' in m for l, m in levels(res))
    t = tmp_path / 't.md'; t.write_text("## 工作描述\n" + "字" * 30, encoding='utf-8')
    r = tmp_path / 'r.json'; r.write_text(json.dumps(RULES), encoding='utf-8')
    f = tmp_path / 'f.md'; f.write_text(FACTS, encoding='utf-8')
    lim = tmp_path / 'l.json'; lim.write_text('{"工作描述": 20}', encoding='utf-8')
    assert cc.main([str(t), '--rules', str(r), '--facts', str(f), '--limits', str(lim)]) == 1
    t.write_text("## 工作描述\n没有问题的文字", encoding='utf-8')
    assert cc.main([str(t), '--rules', str(r), '--facts', str(f)]) == 0


def test_model_numbers_like_cet6_are_not_counted():
    res = cc.check("## 技能\n- 英语CET-6（598/710）", RULES, "598/710")
    assert not [m for l, m in levels(res) if l == 'WARN']
