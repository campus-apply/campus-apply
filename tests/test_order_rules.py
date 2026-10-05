"""Guard the pipeline order rules that only exist as prose.

Three rules came out of the 2026-10-04 Meituan POC, where the agent went from picking a job
straight to filling fields — no tailored resume, no attachment:

  1. apply-fill refuses to start without resume.md + a rendered PDF (no "this page doesn't
     need resume text" exception).
  2. The resume attachment goes up first, before any field is written.
  3. job-screen hands off to resume-tailor instead of to apply-fill.

Prose can drift, and tests are the only thing that notices. These assert the rules are stated
and, just as importantly, that no file still states the opposite.
"""
from pathlib import Path
import re

ROOT = Path(__file__).parents[1]
SKILLS = ROOT / 'skills'
APPLY_FILL = SKILLS / 'apply-fill/SKILL.md'
ROUTER = SKILLS / 'campus-apply/SKILL.md'
JOB_SCREEN = SKILLS / 'job-screen/SKILL.md'
UPLOAD_DOC = SKILLS / 'apply-fill/references/upload-and-parse.md'
# 正文瘦身后（见 test_skill_body_size），步骤细则搬进 references，正文只留不可逆的几条。
# 下面的断言跟着内容走：不可逆的查正文，流程细则查搬过去的那份。
PAGE_LOOP = SKILLS / 'apply-fill/references/page-loop.md'
JOB_SCREEN_STEPS = SKILLS / 'job-screen/references/steps.md'
JOB_SCREEN_CHECKLIST = SKILLS / 'job-screen/references/checklist.md'
ROUTING = SKILLS / 'campus-apply/references/routing.md'
RED_FLAGS = SKILLS / 'campus-apply/references/red-flags.md'
TALKING = SKILLS / 'campus-apply/references/talking-to-the-user.md'


def every_doc():
    return sorted(SKILLS.rglob('*.md')) + [ROOT / 'README.md']


def test_apply_fill_requires_a_tailored_resume_before_starting():
    """前提是不可逆的一条（没有简历就开填 = 投出去一份没改过的），所以留在正文里。"""
    text = APPLY_FILL.read_text(encoding='utf-8')
    head = text[text.index('## 前提'):text.index('## 不可逆的几条')]
    assert 'resume.md' in head and 'PDF' in head, 'the prerequisite must name both artifacts'
    assert '不开始' in head or '不开工' in head, 'it must say the skill does not start without them'
    assert 'resume-tailor' in head, 'it must point at the skill that produces them'


def test_the_no_resume_text_exception_is_gone_everywhere():
    """This exact backdoor is what let the POC skip resume-tailor: 志愿选择/账号信息 pages were
    allowed to proceed without resume.md. If any doc reintroduces it, the gate is useless."""
    for doc in every_doc():
        text = doc.read_text(encoding='utf-8')
        for phrase in ('不需要简历文本的页面可以先走', '这类不需要简历文本的页面可以'):
            assert phrase not in text, 'backdoor reintroduced in ' + doc.name


def test_upload_comes_before_filling_fields():
    loop = PAGE_LOOP.read_text(encoding='utf-8')
    assert '第一件事是传简历 PDF 附件' in loop, 'the entry step must put the upload first'
    upload = UPLOAD_DOC.read_text(encoding='utf-8')
    # 顺序不变（有上传位的页面上，附件先于字段），变的是判定时机：按页探，不按流程阶段定。
    assert '传附件永远排在填字段之前' in loop
    assert '先探一次有没有上传位' in upload
    assert '不要停下来问' in upload, '本页没有上传位时不该停下来问'
    assert '不要先填字段再传附件' in upload, 'the wrong order must be called out explicitly'


def test_upload_default_is_the_agent_and_no_doc_says_otherwise():
    upload = UPLOAD_DOC.read_text(encoding='utf-8')
    assert '默认由 agent 代传' in upload
    # The old rule, in every wording it appeared in across the repo.
    for doc in every_doc():
        text = doc.read_text(encoding='utf-8')
        for phrase in ('上传默认由用户做', '上传默认用户做', '文件上传默认由用户做',
                       '上传简历默认由你自己做', '不碰文件上传'):
            assert phrase not in text, 'stale upload default in ' + doc.name + ': ' + phrase


def test_other_attachments_still_come_from_the_user():
    """Only the resume PDF is sent by default. Transcripts, photos and portfolios need a file
    from the user, because we have no business guessing which file is meant."""
    text = APPLY_FILL.read_text(encoding='utf-8')
    section = text[text.index('## 不可逆的几条'):]
    assert '证件照' in section and '成绩单' in section


def test_job_screen_hands_off_to_resume_tailor():
    text = JOB_SCREEN.read_text(encoding='utf-8')
    assert 'resume-tailor' in text, 'job-screen must name the next skill'
    handoff = text[text.index('## 交接'):]
    assert 'resume-tailor' in handoff, '正文要留下交接对象'
    assert '填网申要等它跑完' in handoff, '并且说明填表排在它之后'
    steps = JOB_SCREEN_STEPS.read_text(encoding='utf-8')
    steps = steps[steps.index('## 步骤'):]
    assert re.search(r'10\..*resume-tailor', steps, re.S), 'the handoff must be a numbered step'
    checklist = JOB_SCREEN_CHECKLIST.read_text(encoding='utf-8')
    assert 'resume-tailor' in checklist, 'and a checklist line, so it cannot be skipped silently'


def test_router_sends_an_untailored_job_to_resume_tailor_first():
    text = ROUTING.read_text(encoding='utf-8')
    order = text[text.index('## 判断顺序'):text.index('## 四步有先后')]
    assert 'resume-tailor' in order
    assert '简历 PDF' in order or 'PDF' in order, 'the router should check for the PDF too'


def test_router_states_the_four_steps_are_ordered():
    """四步的先后是不可逆的一条（没改简历就投 = 名额用掉了），所以留在正文里。"""
    assert '改简历没做完不开始填表' in ROUTER.read_text(encoding='utf-8')


def test_red_flags_cover_filling_before_tailoring():
    text = RED_FLAGS.read_text(encoding='utf-8')
    flags = text[text.index('# 红旗'):]
    assert '简历一会儿再改' in flags
    assert '附件等填完字段再传' in flags


def test_resume_tailor_does_not_wait_on_apply_fill_to_finish():
    """form.md needs the live page, so it is produced after apply-fill probes — but the resume
    itself must not depend on apply-fill, or the two skills deadlock."""
    text = (SKILLS / 'resume-tailor/SKILL.md').read_text(encoding='utf-8')
    assert '不在这里做' in text, 'step 7 must defer form.md explicitly'
    assert '第 6 步出了 PDF 就可以交给 apply-fill' in text, 'the handoff point must be the PDF'


# --- 第二批：停顿分级、依据的定义、弹窗与登录状态、清单去重 ---

def test_pauses_are_tiered_not_uniform():
    """停顿要花在真有选择的地方。2026-10-04 为不同意就没法投的隐私政策单独停了一次，
    却漏掉了页面默认已勾上的"接受其他职位调剂"。"""
    text = (SKILLS / 'apply-fill/references/collect-table.md').read_text(encoding='utf-8')
    assert '必须同意才能继续' in text, '不构成选择的条款要单列一类'
    assert '不为它单独停' in text
    assert '整页批成一次停顿' in text, '真有选择的要批量问'
    assert '页面默认已经勾上的也要列出来' in text, '默认勾选也是替用户做的选择'


def test_evidence_is_defined_and_excludes_our_own_rules():
    """两条规矩原本能读出矛盾：一边不许说文件路径，一边要求写明"依据"。"""
    text = TALKING.read_text(encoding='utf-8')
    assert '技能规定不是依据' in text
    assert '页面原文' in text and '站点笔记' in text and '不知道' in text
    assert '这是 xx 技能第几步要求的' in text, '要给出反例，光写禁令不够'
    flags = RED_FLAGS.read_text(encoding='utf-8')
    assert '技能要求的' in flags


def test_guard_sees_fixed_modals_and_reports_login_state():
    """offsetParent 对 position:fixed 恒为假，而真实弹窗几乎都是 fixed（pending 105）。
    另外 loginRedirect 只说明"这个页面是登录页"，loggedIn 才说明到底登没登。"""
    guard = (SKILLS / 'campus-apply/scripts/browser/guard.js').read_text(encoding='utf-8')
    code = '\n'.join(l for l in guard.splitlines() if not l.strip().startswith('//'))
    assert 'offsetParent' not in code, 'offsetParent 判法不能回来'
    assert 'checkVisibility' in code
    assert 'loggedIn' in code and 'identityHits' in code
    assert 'modalShape' in code, '光靠 class 含 modal 会把按钮和说明文字也算成弹窗'


def test_visibility_fix_applied_to_every_script():
    for name in ('guard.js', 'probe.js', 'lib_antd3.js', 'lib_fill.js'):
        text = (SKILLS / 'campus-apply/scripts/browser' / name).read_text(encoding='utf-8')
        code = '\n'.join(l for l in text.splitlines() if not l.strip().startswith('//'))
        assert 'offsetParent' not in code, name + ' 还在用 offsetParent 判可见'
    driver = (SKILLS / 'campus-apply/scripts/browser/chrome_cdp.py').read_text(encoding='utf-8')
    import re as _re
    # strip triple-quoted docstrings and single-line # comments before checking
    stripped = _re.sub(r'""".*?"""', '""""""', driver, flags=_re.DOTALL)
    stripped = _re.sub(r"'''.*?'''", "''''''", stripped, flags=_re.DOTALL)
    code_only = '\n'.join(l for l in stripped.splitlines() if not l.lstrip().startswith('#'))
    assert 'offsetParent' not in code_only, 'chrome_cdp.py 里内嵌的可执行 JS 也要改（docstring 和注释里的提及不算）'


def test_listing_collection_recovers_from_duplicates_in_the_library():
    """194 条响应只有 192 个唯一 ID 时不该停下来让人核对——去重、重拉、补不回来才报。"""
    text = (SKILLS / 'campus-apply/scripts/browser/lib_net.js').read_text(encoding='utf-8')
    assert 'async function collect' in text, '收集逻辑要在库里，不要每站现写'
    assert 'missingPages' in text and 'duplicates' in text
    assert '不再重试' in text, '确定性重复要尽早停，不能无限重试'


def test_no_matching_tab_tells_the_agent_what_to_do_next():
    driver = (SKILLS / 'campus-apply/scripts/browser/chrome_cdp.py').read_text(encoding='utf-8')
    assert 'def no_tab_report' in driver
    for marker in ('BROWSER_GONE', 'NO_PAGES', 'OTHER_TABS'):
        assert marker in driver, '三种情况要分开：' + marker
    assert '不要反复重试同一条命令' in driver
