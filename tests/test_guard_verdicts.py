"""guard 的四个判断要么是结论，要么是证据，不能混着用。

误报的代价是停下来等用户处理一件并不存在的事；漏报的代价是在被挡住的页面上继续填。
两头都踩过，样本记在待处理 #16：

- 一个已登录的在线简历页，账号设置菜单里有"安全验证"四个字，guard 报 captcha:true
  而 captchaHits 是空的——纯粹是正文有那几个字。
- agent 自己点了登录按钮跳到登录页，再看见 loginRedirect 为真就当成"站点要求登录"。
- guard 早就输出了 blocked（浏览器错误页、上网认证跳转），而 read-urls 压根不看它，
  于是在认证页上照读几百条，读回来全是垃圾。

所以：captcha / requiresLogin / blocked / visibleModals 是结论，调用方只认这四个；
loginRedirect / captchaWords / identityHits 是证据，留给人看和留底，不当停的依据。
"""
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
BROWSER = HERE.parent / 'skills/campus-apply/scripts/browser'
GUARD = BROWSER / 'guard.js'
CDP = BROWSER / 'chrome_cdp.py'
FIXTURE = HERE.parent / 'evals/fixtures/guard_shapes.html'
CHECK = HERE.parent / 'evals/guard_shapes_check.py'


def guard_code():
    text = GUARD.read_text(encoding='utf-8')
    return '\n'.join(l for l in text.splitlines() if not l.strip().startswith('//'))


def py_code():
    text = CDP.read_text(encoding='utf-8')
    text = re.sub(r'""".*?"""', '""""""', text, flags=re.DOTALL)
    return '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))


# ---- captcha：命中控件才算，词只是旁证 ----

def test_words_alone_do_not_make_a_captcha():
    code = guard_code()
    assert 'const captcha = ' in code, 'captcha 要有一个单独的判据，不在 return 里现算'
    verdict = code[code.index('const captcha = '):]
    verdict = verdict[:verdict.index('\n')]
    assert 'hits.length > 0' in verdict, '命中控件就算'
    assert 'words.length > 0 &&' in verdict, '词不能单独成立，要和别的条件并起来'


def test_words_still_count_when_something_is_actually_on_top():
    """不许为了治误报而制造漏报：验证码整层在 iframe 里时，词是唯一的线索。"""
    code = guard_code()
    assert 'somethingOnTop' in code, '要有"页上真的压着一层东西"这个条件'
    cond = code[code.index('const somethingOnTop'):]
    cond = cond[:cond.index('\n')]
    assert 'visibleModals' in cond and 'maskOnly' in cond, \
        '弹窗和纯遮罩都算"压着一层东西"'


def test_the_word_only_case_is_reported_as_its_own_fact():
    """只有词命中时要能看出来，否则下次又会在"为什么没报"上卡住。"""
    code = guard_code()
    assert 'captchaWordsOnly' in code


# ---- 要不要登录：身份证据比入口硬 ----

def test_requires_login_is_a_field_not_something_callers_derive():
    code = guard_code()
    assert 'const requiresLogin' in code, '结论要由 guard 算好，不留给每个调用方各自推'
    verdict = code[code.index('const requiresLogin'):]
    verdict = verdict[:verdict.index('\n')]
    assert 'loginRedirect' in verdict and '!loggedIn' in verdict, \
        '有身份就说明不用再登录一次'


def test_login_redirect_stays_in_the_report_as_evidence():
    """它仍然有用——说明"这页是登录页或有登录入口"，只是不能当停的依据。"""
    code = guard_code()
    ret = code[code.index('return {'):]
    assert 'loginRedirect' in ret and 'requiresLogin' in ret, '两个都要留在报告里'


# ---- 调用方：四个结论都要消费 ----

def test_read_urls_consumes_blocked_too():
    code = py_code()
    loop = code[code.index('def cmd_read_urls'):]
    loop = loop[:loop.index('\ndef ')]
    assert "gd.get('blocked')" in loop, 'guard 早就报了 blocked，调用方要看它'
    assert "gd.get('requiresLogin')" in loop, '要消费结论字段，不是 loginRedirect'
    assert "gd.get('loginRedirect')" not in loop, \
        'loginRedirect 是证据，已登录的页面上也为真，拿它当停的依据就是在误停'


def test_read_urls_says_why_it_stopped():
    code = py_code()
    loop = code[code.index('def cmd_read_urls'):]
    loop = loop[:loop.index('\ndef ')]
    assert 'reasons' in loop, '停的理由要说出来，不能只丢一整串 JSON'


# ---- fixture 与评测脚本的契约 ----

def test_fixture_covers_both_the_false_alarm_and_the_miss():
    html = FIXTURE.read_text(encoding='utf-8')
    assert 'mentions-verify' in html, '误报那一面：正文提到验证字样但页上没有控件'
    assert 'iframe-captcha' in html, '漏报那一面：验证码在 iframe 里、容器 class 不含验证字样'
    assert 'third-party-layer' in html, 'iframe 容器的 class 不能含验证字样'
    for word in ('captcha', 'verify', 'slider'):
        assert word not in 'third-party-layer', 'iframe 容器名不该命中控件选择器'


def test_fixture_covers_resident_login_and_real_login():
    html = FIXTURE.read_text(encoding='utf-8')
    assert 'resident-login' in html and 'real-login' in html
    assert 'login-panel' in html, '常驻入口那一条：登录面板在 DOM 里但不可见'


def test_fixture_modal_has_mask_and_body_as_siblings():
    html = FIXTURE.read_text(encoding='utf-8')
    mask = html.index('id="mask"')
    modal = html.index('id="modal"')
    between = html[mask:modal]
    assert '</div>' in between, '遮罩和弹窗体要是兄弟节点，不是嵌套'


def test_check_script_runs_without_models_or_recruitment_sites():
    code = CHECK.read_text(encoding='utf-8')
    assert '127.0.0.1' in code and 'tempfile.mkdtemp' in code
    assert 'outside the repository' in code, '产物不许落在仓库里'
    for banned in ('talent.baidu', 'zhaopin.', 'moka', 'Moka'):
        assert banned not in code, '评测脚本里不许出现真实站点：' + banned


def test_check_script_compares_against_the_fixtures_own_truth():
    code = CHECK.read_text(encoding='utf-8')
    assert 'fixtureTruth' in code, '要和 fixture 自己记的真值对账，免得 fixture 和期望一起写错'
