"""Tests for the job-list prescreen.

The point of prescreening is to keep jobs out of the model's context — so the dangerous
failure is not "too many survive", it's "a real candidate got excluded". Most of these tests
are about refusing to exclude without citable evidence.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / 'skills/job-screen/scripts/prescreen.py'


def module():
    spec = importlib.util.spec_from_file_location('prescreen', SCRIPT)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=60)


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return path


PREFS = {'preferences': {'apply_types': ['校招正式批'],
                         'role_types_no': ['研究岗（声学、算法）', '纯销售型岗'],
                         'overseas_ok': False}}


def test_usage_without_arguments():
    r = run()
    assert r.returncode == 2
    assert '预筛' in r.stdout


def test_missing_file():
    r = run('/no/such/list.json')
    assert r.returncode == 2
    assert 'ERR_NO_FILE' in r.stdout


def test_rejects_unparseable_and_shapeless_input(tmp_path):
    bad = tmp_path / 'bad.json'
    bad.write_text('{not json', encoding='utf-8')
    assert run(str(bad)).returncode == 2
    assert 'ERR_LIST' in run(str(write(tmp_path, 'empty.json', []))).stdout
    assert 'ERR_LIST' in run(str(write(tmp_path, 'scalars.json', [1, 2]))).stdout


def test_accepts_bare_array_and_wrapped_shapes(tmp_path):
    job = {'title': '产品经理岗', 'jobDuty': '做产品', 'jobRequirement': '本科及以上'}
    for name, data in [('bare.json', [job]), ('jobs.json', {'jobs': [job]}),
                       ('list.json', {'list': [job]}), ('data.json', {'data': [job]})]:
        r = run(str(write(tmp_path, name, data)))
        assert r.returncode == 0, name
        assert 'ERR_LIST' not in r.stdout, name


def test_missing_body_is_never_treated_as_unqualified(tmp_path):
    """A job with no duty/requirement text must go to 读, not 排除. Silence is not evidence."""
    m = module()
    row = {'title': '产品经理岗', 'cat': '产品类', 'loc': '北京市', 'duty': '', 'req': '',
           'nature': '', 'url': '', 'jobId': '', 'org': '', 'date': ''}
    tier, rule, _ = m.judge(row, {'overseas': True}, facts_degree=3)
    assert tier == '读'
    assert '没有正文' in rule


def test_degree_gate_only_fires_when_the_text_says_so(tmp_path):
    m = module()
    base = dict(title='岗', cat='', loc='北京市', nature='', url='', jobId='', org='', date='')
    # 要求博士，用户是硕士 → 排除，且带原文
    tier, rule, evidence = m.judge(dict(base, duty='职责', req='博士学历'), {'overseas': True}, 3)
    assert tier == '排除' and '学历' in rule and '博士' in evidence
    # 要求本科及以上 → 硕士符合，不排除
    tier, _, _ = m.judge(dict(base, duty='职责', req='本科及以上学历'), {'overseas': True}, 3)
    assert tier == '读'
    # 没有事实库学历时，即使正文要求博士也不排除（没有依据就不判）
    tier, _, _ = m.judge(dict(base, duty='职责', req='博士学历'), {'overseas': True}, None)
    assert tier == '读'


def test_job_type_keywords_match_title_and_category_but_not_body():
    """实测美团 194 个岗位里 72 个正文含"研究"，全是动词用法（"深入代码研究"）。
    拿正文匹配会把一半岗位推进待定，等于没筛。"""
    m = module()
    prefs = {'exclude_keywords': ['研究'], 'overseas': True}
    base = dict(cat='', loc='北京市', nature='', url='', jobId='', org='', date='')
    tier, _, _ = m.judge(dict(base, title='用户研究岗', duty='', req='x'), prefs, None)
    assert tier == '排除', '标题命中要排除'
    tier, _, _ = m.judge(dict(base, title='产品经理', cat='研究类', duty='', req='x'), prefs, None)
    assert tier == '排除', '类别命中要排除'
    tier, _, _ = m.judge(dict(base, title='AI后端开发工程师',
                              duty='能深入代码研究，通过英文论文', req='本科'), prefs, 3)
    assert tier == '读', '正文里的"研究"是动词，不能据此排除'


def test_overseas_is_detected_by_shape_not_by_a_city_list():
    """海外城市名没法枚举（利雅得、迪拜、科威特城、圣保罗…）。反过来认：国内地点写作"××市"。"""
    m = module()
    prefs = {'overseas': False, 'exclude_keywords': []}
    base = dict(title='岗', cat='', nature='', url='', jobId='', org='', date='', duty='职责', req='本科')
    tier, rule, _ = m.judge(dict(base, loc='利雅得'), prefs, 3)
    assert tier == '排除' and '海外' in rule
    tier, rule, _ = m.judge(dict(base, loc='圣保罗、利雅得'), prefs, 3)
    assert tier == '排除'
    tier, _, _ = m.judge(dict(base, loc='北京市、上海市'), prefs, 3)
    assert tier == '读', '纯国内不该被当成海外'
    # 国内 + 海外混在一起：不替用户决定
    tier, rule, _ = m.judge(dict(base, loc='北京市、迪拜'), prefs, 3)
    assert tier == '待定' and '要你定' in rule


def test_overseas_rule_is_off_when_the_user_accepts_overseas():
    m = module()
    row = dict(title='岗', cat='', loc='迪拜', nature='', url='', jobId='', org='', date='',
               duty='职责', req='本科')
    tier, _, _ = module().judge(row, {'overseas': True, 'exclude_keywords': []}, 3)
    assert tier == '读'


def test_city_list_of_objects_is_flattened():
    """站点常把地点写成 [{"name": "北京市"}, …]，要能读成一串文本。"""
    m = module()
    row = m.normalise({'name': '岗', 'cityList': [{'name': '北京市'}, {'name': '迪拜'}]}, {})
    assert '北京市' in row['loc'] and '迪拜' in row['loc']


def test_estimate_reports_browser_time_and_reading_volume_separately(tmp_path):
    """上一轮的教训：把两种代价混成一个"大约几分钟"就会报出 6～10 分钟这种对不上的数。
    正文随清单返回时浏览器时间应当是 0。"""
    m = module()
    rows = [{'duty': '甲' * 100, 'req': '乙' * 50}]
    with_body = m.estimate(rows, has_body=True)
    assert with_body['browser_minutes'] == 0.0
    assert with_body['chars'] == 150
    without = m.estimate(rows, has_body=False)
    assert without['browser_minutes'] > 0


def test_keywords_are_split_out_of_whole_sentences():
    """preferences 里的条目是人话整句（"研究岗（声学、算法、香港研究类）"），要切成关键词。"""
    m = module()
    words = m.keywords_from(['研究岗（声学、算法、香港研究类）', '纯销售型岗'])
    assert '声学' in words and '算法' in words
    assert '研究' in words, '"研究岗"要能去掉"岗"后缀'
    assert '纯销售' in words
    assert all(len(w) >= 2 for w in words), '单字关键词太容易误伤'


def test_evidence_is_present_on_every_exclusion(tmp_path):
    """排除必须能引用原文。说不出依据的排除等于没依据。"""
    jobs = [{'name': '用户研究岗', 'jobFamily': '研究类', 'cityList': [{'name': '北京市'}],
             'jobDuty': '做研究', 'jobRequirement': '硕士'},
            {'name': '招商采购岗', 'cityList': [{'name': '利雅得'}],
             'jobDuty': '采购', 'jobRequirement': '本科'},
            {'name': '产品经理岗', 'cityList': [{'name': '上海市'}],
             'jobDuty': '做产品', 'jobRequirement': '本科及以上'}]
    listing = write(tmp_path, 'jobs.json', {'jobs': jobs})
    prefs = write(tmp_path, 'campus-apply.json', PREFS)
    out = tmp_path / 'pre.json'
    r = run(str(listing), '--prefs', str(prefs), '--json', str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    for job in data['jobs']:
        if job['_tier'] == '排除':
            assert job['_rule'], job['title']
            assert job['_evidence'], '排除没给依据原文：' + job['title']


def test_prescreen_does_not_decide_for_the_user(tmp_path):
    """三档里没有"投这个"。脚本只负责把读取量压下来，选岗仍是用户的事。"""
    text = SCRIPT.read_text(encoding='utf-8')
    assert '不替用户决定投哪个' in text
    for forbidden in ('建议投', '推荐投'):
        assert forbidden not in text, 'prescreen 不该给投递建议：' + forbidden
