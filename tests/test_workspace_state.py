import importlib.util
import json
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).parents[1] / 'skills/campus-apply/scripts/workspace_state.py'


def check(ws, *args):
    return subprocess.run([sys.executable, str(SCRIPT), '--workspace', str(ws), *args],
                          capture_output=True, text=True)


def write(ws, folder, name, text):
    p = ws / 'applications' / folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')
    return p


def test_reports_same_item_pending_and_decided_without_modifying_files(tmp_path):
    p = write(tmp_path, '示例公司', '待你决定.md',
              '## 未决\n- 4. 亲属回避：是否有本公司亲属？\n\n## 已定\n'
              '- 4. 亲属回避 → 2026-10-04 用户「无」\n')
    before = p.read_bytes()
    r = check(tmp_path)
    assert r.returncode == 1, r.stderr
    finding = json.loads(r.stdout)['findings'][0]
    assert finding['kind'] == 'pending_and_decided'
    assert finding['line'] == 2 and finding['related'][0]['line'] == 5
    assert p.read_bytes() == before


def test_reports_related_directory_answer_but_not_another_company(tmp_path):
    write(tmp_path, '示例公司', '待你决定.md', '## 未决\n- 1. 志愿上限：最多几个？\n')
    write(tmp_path, '示例公司-综合岗', '待你决定.md',
          '## 已定\n- 2. 志愿上限 → 用户确认1个\n')
    write(tmp_path, '别家公司', '待你决定.md', '## 未决\n- 1. 志愿上限：最多几个？\n')
    r = check(tmp_path)
    findings = json.loads(r.stdout)['findings']
    assert len(findings) == 1
    assert findings[0]['kind'] == 'related_decision'
    assert findings[0]['path'] == 'applications/示例公司/待你决定.md'


def test_duplicate_checklist_row_warns_without_inferring_completion(tmp_path):
    write(tmp_path, '示例公司', 'apply-fill-执行清单_2026-10-04.md',
          '- [ ] 1 探测\n- [x] 1 探测\n- [ ] 2 保存\n')
    write(tmp_path, '示例公司', 'fill-log.md', '已填写，尚未保存\n')
    r = check(tmp_path)
    findings = json.loads(r.stdout)['findings']
    assert len(findings) == 1 and findings[0]['kind'] == 'duplicate_checklist_state'
    assert findings[0]['line'] == 1


def test_different_topics_with_same_number_are_not_answers(tmp_path):
    write(tmp_path, '示例公司', '待你决定.md',
          '## 未决\n- 1. 是否继续子公司筛岗？\n## 已定\n- 1. 总部岗位：不投\n')
    r = check(tmp_path)
    assert r.returncode == 0 and json.loads(r.stdout)['findings'] == []


def test_pause_and_unchecked_steps_are_not_automatically_errors(tmp_path):
    write(tmp_path, '示例公司', '待你决定.md', '## 已定\n- 1. 剩余岗位 → 用户暂停\n')
    write(tmp_path, '示例公司', '执行清单.md', '- [ ] 1 填表\n')
    r = check(tmp_path)
    assert r.returncode == 0


def test_scope_filters_findings_and_rejects_path_escape(tmp_path):
    write(tmp_path, '示例公司', '待你决定.md',
          '## 未决\n- 1. 账号：有没有？\n## 已定\n- 1. 账号 → 已注册\n')
    write(tmp_path, '另一公司', '待你决定.md', '## 未决\n- 1. 账号：有没有？\n')
    r = check(tmp_path, '--scope', 'applications/另一公司')
    assert r.returncode == 0
    r = check(tmp_path, '--scope', '../outside')
    assert r.returncode == 2 and 'ERR' in r.stderr


def test_missing_workspace_is_input_error(tmp_path):
    r = check(tmp_path / 'missing')
    assert r.returncode == 2


def test_explicit_original_title_answer_does_not_require_number(tmp_path):
    write(tmp_path, '示例公司', '待你决定.md',
          '## 未决\n- 1. 亲属任职：待回答\n## 已定\n- 亲属任职 → 用户「无」\n')
    r = check(tmp_path)
    assert r.returncode == 1
    assert json.loads(r.stdout)['findings'][0]['kind'] == 'pending_and_decided'


def test_explicit_plain_title_answer_and_nested_candidate_are_distinct(tmp_path):
    write(tmp_path, '示例公司', '待你决定.md',
          '## 未决\n- 1. 亲属任职：待回答\n  - 候选：无\n'
          '## 已定\n亲属任职：无。用户明确回答。\n')
    r = check(tmp_path)
    findings = json.loads(r.stdout)['findings']
    assert r.returncode == 1 and len(findings) == 1
    assert findings[0]['line'] == 2 and findings[0]['related'][0]['line'] == 5
