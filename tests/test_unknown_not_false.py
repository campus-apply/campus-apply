"""一条规则，四个落点：读不出就报"读不出"，不报"不成立"。

同一个毛病在四处分别造成了不同的后果：上传成功被报成失败（诱发重传，而重传在某些站点
会二次弹出破坏性确认框）；一个弹窗被数成两个（"是不是又弹了一个"就判不了）；筛岗的
参数写错了静默失效（整批岗位的地点全空）；判不出是不是国内就当成海外（直接排除掉）。

把"我判断不出 X"当成"X 不成立"，是这套工具能造成实际损失的主要方式。
"""
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CDP = ROOT / 'skills/campus-apply/scripts/browser/chrome_cdp.py'
GUARD = ROOT / 'skills/campus-apply/scripts/browser/guard.js'
PRESCREEN = ROOT / 'skills/job-screen/scripts/prescreen.py'
UPLOAD_DOC = ROOT / 'skills/apply-fill/references/upload-and-parse.md'


def py_code(path):
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'""".*?"""', '""""""', text, flags=re.DOTALL)
    return '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))


def js_code(path):
    text = path.read_text(encoding='utf-8')
    return '\n'.join(l for l in text.splitlines() if not l.strip().startswith('//'))


def test_upload_does_not_call_a_cleared_input_a_failure():
    """站点在 change 回调里取走文件后清空 input 是常规做法——越规范的站点越会这么干。
    回读为空只说明"读不出"，不说明没传成。"""
    code = py_code(CDP)
    assert 'return 0 if names else 1' not in code, \
        '回读 input.files 为空就报失败，会把成功的上传报成失败'
    assert 'setFileInputFiles' in code


def test_upload_reports_corroborating_signals():
    """成败要多信号：CDP 调用本身没报错、页面上有没有出现文件名或确认框。"""
    code = py_code(CDP)
    assert 'UPLOAD_EVIDENCE' in code or 'evidence' in code, \
        '要带回页面侧的佐证，不能只看 input.files'


def test_upload_doc_warns_about_the_cleared_input():
    text = UPLOAD_DOC.read_text(encoding='utf-8')
    assert '清空' in text, 'upload-and-parse 要写明站点可能清空控件，这不是失败'


def test_a_mask_and_its_dialog_are_one_modal_not_two():
    """遮罩和弹窗体常常是兄弟节点、互不包含，按 contains 去重去不掉。"""
    code = js_code(GUARD)
    assert 'maskLike' in code or 'hasText' in code, \
        '要把没有文本的纯遮罩排除出计数，否则一个弹窗数成两个'


def test_prescreen_rejects_an_unknown_map_target_instead_of_ignoring_it():
    """--map 的目标键写错了不报错，整批岗位的那一列会全空，而且静默。"""
    code = py_code(PRESCREEN)
    assert 'ERR_USAGE prescreen' in code, '不认识的目标键要报错退出，不能静默忽略'


def test_prescreen_accepts_the_chinese_field_names_it_documents():
    """--help 的字段表列的是中文名，那就得真的认中文名。"""
    code = py_code(PRESCREEN)
    assert 'FIELD_ALIASES' in code or 'field_key' in code, \
        '要能把中文显示名映射回内部键'


def test_an_unrecognised_place_is_not_called_overseas():
    """判不出是不是国内，就不能当成海外排除——按形状反判会漏，方向只是反了。"""
    code = py_code(PRESCREEN)
    assert 'DOMESTIC_PLACE' not in code or 'unknown' in code.lower(), \
        '地点判不出要走 unknown 分支，不能直接归成海外'
