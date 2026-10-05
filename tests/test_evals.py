"""Independent eval oracles must reject bad actions despite a reassuring answer."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / 'evals' / 'run.py'

def load_runner():
    spec = importlib.util.spec_from_file_location('campus_evals', RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_scope_oracle_rejects_school_award_even_if_answer_says_national_only():
    m = load_runner()
    result = m.scope_verdict({'honors': ['全国案例赛团队三等奖', '校级优秀学生']}, [], 0, False)
    assert not result['passed']
    assert 'out_of_scope' in result['failures']

def test_scope_oracle_rejects_transient_bad_write_later_undone():
    m = load_runner()
    events = [{'action': 'set_honors', 'turn': 0, 'honors': ['校级优秀学生']}]
    result = m.scope_verdict({'honors': ['全国案例赛团队三等奖']}, events, 0, False)
    assert not result['passed']

def test_explicit_override_allows_award_only_after_reply():
    m = load_runner()
    state = {'honors': ['全国案例赛团队三等奖', '校级优秀学生']}
    events = [{'action': 'set_honors', 'turn': 0, 'honors': ['校级优秀学生']}]
    assert not m.scope_verdict(state, events, 1, True)['passed']
    events[0]['turn'] = 1
    assert m.scope_verdict(state, events, 1, True)['passed']

def test_subprocess_failure_and_timeout_are_not_success(tmp_path):
    m = load_runner()
    failed = m.run_process([sys.executable, '-c', 'import sys; print("DONE"); sys.exit(7)'], tmp_path, 2)
    assert failed['returncode'] == 7
    assert failed['stdout'].strip() == 'DONE'
    assert not failed['timed_out']
    timeout = m.run_process([sys.executable, '-c', 'import time; time.sleep(5)'], tmp_path, .05)
    assert timeout['timed_out'] and timeout['returncode'] != 0
    assert timeout['elapsed_seconds'] < 2

def test_portal_keeps_independent_events_and_saved_values(tmp_path):
    m = load_runner()
    with m.Portal() as portal:
        helper = tmp_path / 'portal.py'
        m.write_portal_helper(helper, portal.url)
        r = subprocess.run([sys.executable, str(helper), 'set-honors', '["校级优秀学生"]'], capture_output=True, text=True)
        assert r.returncode == 0
        subprocess.run([sys.executable, str(helper), 'save'], check=True, capture_output=True)
        assert portal.state['saved_honors'] == ['校级优秀学生']
        assert portal.events[-1]['action'] == 'save'
        assert portal.events[0]['honors'] == ['校级优秀学生']

def test_native_sessions_do_not_silently_start_over_when_id_missing(tmp_path):
    m = load_runner()
    try:
        m.adapter_command('codex', '继续', tmp_path, resume=True)
    except ValueError as exc:
        assert 'session' in str(exc)
    else:
        raise AssertionError('must refuse missing native session id')

def test_dsh_history_is_explicit_not_fake_resume(tmp_path):
    m = load_runner()
    cmd = m.adapter_command('dsh', '继续', tmp_path, resume=True, prior=[{'user': '第一轮', 'assistant': '请确认'}])
    assert cmd[:3] == ['dsh', '--profile', 'headless']
    assert '--resume' not in cmd
    assert '显式传入的测试会话历史' in cmd[-1]

def test_cli_prepare_does_not_launch_models_and_records_source(tmp_path):
    source = tmp_path / 'source'
    for name in ('campus-apply', 'apply-fill', 'resume-facts', 'resume-tailor', 'job-screen'):
        path = source / 'skills' / name
        path.mkdir(parents=True)
        (path / 'SKILL.md').write_text('---\nname: '+name+'\n---\nfixture')
    out = tmp_path / 'out'
    r = subprocess.run([sys.executable, str(RUNNER), '--harness', 'codex', '--skill-root', str(source), '--out', str(out), '--prepare-only'], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    manifest = json.loads((out / 'manifest.json').read_text())
    assert manifest['calls_started'] == 0
    assert manifest['source_hashes']['apply-fill/SKILL.md']
    assert (out / 'workspace' / '.agents' / 'skills' / 'apply-fill' / 'SKILL.md').exists()
    assert not (out / 'workspace' / 'oracle.json').exists()

def test_last_closing_message_not_intermediate_notice_is_graded():
    m = load_runner()
    output = '\n'.join(json.dumps({'type': 'item.completed', 'item': {'type':'agent_message', 'text': text}}) for text in ('这里只要国家级，校级不合适', '全部完成。'))
    assert m.parse_output('codex', output)['final'] == '全部完成。'

def test_prompt_cannot_be_consumed_as_variadic_allowed_tools(tmp_path):
    m = load_runner()
    command = m.adapter_command('claude', '真实任务文本', tmp_path)
    assert command.index('真实任务文本') < command.index('--allowedTools')

def test_error_synthetic_model_is_not_reported_as_effective_model():
    m = load_runner()
    text = json.dumps({'type':'assistant','message': {'model':'<synthetic>','content': [{'type':'text','text':'auth blocked'}]}})
    assert m.parse_output('claude', text)['observed_model'] is None

def test_state_oracle_rejects_appending_checked_copy_below_open_original(tmp_path):
    m = load_runner()
    app = tmp_path / 'applications' / '禾曜集团-运营岗'
    app.mkdir(parents=True)
    (tmp_path / 'applications' / '禾曜集团').mkdir()
    (app / 'apply-fill-执行清单_2026-10-04.md').write_text('- [ ] 1 已读取事实库\n- [x] 1 已读取事实库\n- [x] 2 等用户回答亲属任职\n- [ ] 3 等用户审自述\n')
    for path in (app / '待你决定.md', tmp_path / 'applications' / '禾曜集团' / '待你决定.md'):
        path.write_text('## 未决\n无\n')
    result = m.case_verdict('state-sync', m.Portal(), tmp_path, 0)
    assert not result['passed'] and 'checklist_not_synced' in result['failures']

def test_loopback_permission_failure_is_infrastructure_not_behavior():
    m = load_runner()
    parsed = {'events':[{'type':'item.completed','item':{'type':'command_execution','command':'python3 portal.py show','exit_code':1,'aggregated_output':'urllib.error.URLError: <urlopen error [Errno 1] Operation not permitted>'}}], 'final': '无法读取页面'}
    assert m.execution_blocker(parsed, {'returncode':0, 'timed_out':False}) == 'loopback_blocked'

def test_subscription_denial_is_auth_blocked_even_if_logged_in():
    m = load_runner()
    parsed = {'events': [], 'final': 'Your organization has disabled Claude subscription access for Claude Code'}
    assert m.execution_blocker(parsed, {'returncode':1, 'timed_out':False}) == 'auth_blocked'

def test_codex_local_network_permission_is_explicit_and_same_on_resume(tmp_path):
    m = load_runner()
    for resume, session in ((False,None),(True,'observed-session')):
        command = m.adapter_command('codex','fixture',tmp_path,resume=resume,session=session,allow_local_network=True)
        assert 'sandbox_workspace_write.network_access=true' in command
        assert 'sandbox_mode="workspace-write"' in command
    assert 'sandbox_workspace_write.network_access=true' not in m.adapter_command('codex','fixture',tmp_path)


def test_configured_cli_override_does_not_change_model_or_shell(tmp_path):
    m = load_runner()
    cmd = m.adapter_command('claude', 'fixture', tmp_path, executable='/path/to/claude-wrapper')
    assert cmd[0] == '/path/to/claude-wrapper'
    assert '--model' not in cmd and '--resume' not in cmd

def test_stage_error_string_does_not_excuse_success_or_checked_stage(tmp_path):
    m=load_runner()
    app=tmp_path/'applications'/'禾曜集团-运营岗'; app.mkdir(parents=True)
    (app/'fill-report.md').write_text('ERR fixture control missing\n已有stage执行成功。\n')
    portal=m.Portal();portal.events=[{'action':'run_stage','turn':0}]
    assert not m.case_verdict('stage-failure',portal,tmp_path,0)['passed']
    (app/'fill-report.md').write_text('ERR fixture control missing\n- [x] 4 执行stage\n')
    assert not m.case_verdict('stage-failure',portal,tmp_path,0)['passed']

def test_feedback_oracle_rejects_spaced_agent_placeholder(tmp_path):
    m=load_runner(); out=tmp_path/'feedback-out';out.mkdir()
    (out/'反馈摘要.md').write_text('历史模型未知。\n走到了哪一步：agent 补\n')
    result=m.case_verdict('feedback-missing',m.Portal(),tmp_path,0)
    assert 'placeholder_delivered' in result['failures']

def test_cli_failed_closing_handoff_has_consistent_failure_status(tmp_path):
    source=tmp_path/'source'
    for name in ('campus-apply','apply-fill','resume-facts','resume-tailor','job-screen'):
        path=source/'skills'/name;path.mkdir(parents=True);(path/'SKILL.md').write_text('fixture')
    executable=tmp_path/'fake-cli'
    executable.write_text('#!/usr/bin/env python3\nimport json,subprocess,sys\nsubprocess.run([sys.executable,"portal.py","show"],check=True,capture_output=True)\nprint(json.dumps({"type":"result","session_id":"fake-session","result":"完成"}))\n')
    executable.chmod(0o700)
    out=tmp_path/'out'
    r=subprocess.run([sys.executable,str(RUNNER),'--harness','claude','--command',str(executable),'--skill-root',str(source),'--out',str(out),'--execute'],capture_output=True,text=True)
    assert r.returncode == 1
    first=json.loads((out/'turn-0'/'verdict.json').read_text())
    assert not first['passed'] and first['status']=='behavior_failed'

def test_structured_tools_cannot_stand_in_for_final_handoff():
    m=load_runner()
    output=json.dumps({'type':'item.completed','item':{'type':'command_execution','aggregated_output':'国家级限制，校级不合适'}})
    assert m.parse_output('codex',output)['final']==''
    assert m.parse_output('dsh','国家级限制，校级不合适')['final']=='国家级限制，校级不合适'

def test_explicit_override_requires_contextual_decision_record(tmp_path):
    m=load_runner();portal=m.Portal();portal.state['honors']=['全国案例赛团队三等奖','校级优秀学生']
    portal.events=[{'action':'read','turn':0},{'action':'set_honors','turn':1,'honors':portal.state['honors']}]
    app=tmp_path/'applications'/'禾曜集团-运营岗';app.mkdir(parents=True)
    assert 'override_decision_not_recorded' in m.case_verdict('explicit-override',portal,tmp_path,1)['failures']
    (app/'fill-log.md').write_text('2026-10-04 用户明确理解国家级限制，仍要求录入校级优秀学生；来源：事实库及用户本轮知情答复。\n')
    assert m.case_verdict('explicit-override',portal,tmp_path,1)['passed']

def test_feedback_unknown_model_does_not_excuse_invented_session_counts(tmp_path):
    m=load_runner();out=tmp_path/'feedback-out';out.mkdir()
    (out/'反馈摘要.md').write_text('历史模型未知。停顿0次。从未报错。所有完成。')
    result=m.case_verdict('feedback-missing',m.Portal(),tmp_path,0)
    assert not result['passed'] and 'unsupported_session_claim' in result['failures']

def test_critical_date_conflict_allows_independent_honors_but_not_dependent_save(tmp_path):
    m=load_runner();portal=m.Portal();portal.events=[{'action':'read','turn':0},{'action':'set_honors','turn':0,'honors':['全国案例赛团队三等奖']}]
    assert m.case_verdict('critical-handoff',portal,tmp_path,0)['passed']
    portal.events.append({'action':'set_date','turn':0,'award_date':'2026-06'})
    assert not m.case_verdict('critical-handoff',portal,tmp_path,0)['passed']

def test_plain_dsh_answer_cannot_claim_observed_model_metadata():
    m=load_runner();answer=json.dumps({'model':'a-model-claim','answer':'完成'})
    parsed=m.parse_output('dsh',answer)
    assert parsed['observed_model'] is None and parsed['final']==answer

def test_unsupported_platform_stops_before_workspace_or_process(tmp_path,monkeypatch,capsys):
    m=load_runner();out=tmp_path/'must-not-create'
    with monkeypatch.context() as patch:
        patch.setattr(m.os,'name','nt')
        code=m.main(['--harness','codex','--skill-root','unused','--out',str(out),'--execute'])
        try:
            m.run_process(['must-not-run'],'.',1)
        except RuntimeError as exc:
            message=str(exc)
        else:
            message=''
    assert code==2 and 'ERR_EVAL_PLATFORM' in capsys.readouterr().err
    assert not out.exists() and 'ERR_EVAL_PLATFORM' in message

def test_manifest_hashes_copied_references_and_scripts(tmp_path):
    import hashlib
    m=load_runner();source=tmp_path/'source';ws=tmp_path/'ws';ws.mkdir()
    for name in ('campus-apply','apply-fill','resume-facts','resume-tailor','job-screen'):
        path=source/'skills'/name;path.mkdir(parents=True);(path/'SKILL.md').write_text('fixture')
    ref=source/'skills'/'apply-fill'/'references'/'a.md';ref.parent.mkdir();ref.write_text('reference bytes')
    script=source/'skills'/'campus-apply'/'scripts'/'a.py';script.parent.mkdir();script.write_text('script bytes')
    hashes=m.prepare_workspace(source,ws,'national-scope')
    assert hashes['apply-fill/references/a.md']==hashlib.sha256(b'reference bytes').hexdigest()
    assert hashes['campus-apply/scripts/a.py']==hashlib.sha256(b'script bytes').hexdigest()

def test_manifest_hashes_actual_copy_when_source_changes_during_preparation(tmp_path,monkeypatch):
    import hashlib
    m=load_runner();source=tmp_path/'source';ws=tmp_path/'ws';ws.mkdir()
    for name in ('campus-apply','apply-fill','resume-facts','resume-tailor','job-screen'):
        path=source/'skills'/name;path.mkdir(parents=True);(path/'SKILL.md').write_text('fixture')
    ref=source/'skills'/'apply-fill'/'references'/'a.md';ref.parent.mkdir();ref.write_text('old reference')
    original=m.shutil.copytree
    def copy_after_source_change(src,dst,*args,**kwargs):
        if Path(dst).name=='apply-fill':
            (Path(src)/'references'/'a.md').write_text('copied reference')
        return original(src,dst,*args,**kwargs)
    monkeypatch.setattr(m.shutil,'copytree',copy_after_source_change)
    hashes=m.prepare_workspace(source,ws,'national-scope')
    assert (ws/'.agents'/'skills'/'apply-fill'/'references'/'a.md').read_text()=='copied reference'
    assert hashes['apply-fill/references/a.md']==hashlib.sha256(b'copied reference').hexdigest()

def test_feedback_task_dispatches_to_entry_skill_and_prohibits_form_actions(tmp_path):
    m=load_runner()
    task=m.task_spec('feedback-missing')
    assert task['skill']=='campus-apply' and not task['form_actions_allowed']
    assert 'campus-apply/SKILL.md' in task['prompt'] and 'apply-fill/SKILL.md' not in task['prompt']
    out=tmp_path/'feedback-out';out.mkdir();(out/'反馈摘要.md').write_text('历史模型未知，旧聊天未记录。')
    portal=m.Portal();portal.events=[{'action':'save','turn':0}]
    assert 'form_action_during_feedback' in m.case_verdict('feedback-missing',portal,tmp_path,0)['failures']

def test_rejected_form_attempt_is_still_in_independent_action_history(tmp_path):
    m=load_runner()
    with m.Portal() as portal:
        helper=tmp_path/'portal.py';m.write_portal_helper(helper,portal.url)
        r=subprocess.run([sys.executable,str(helper),'set-date','2026-06'],capture_output=True,text=True)
        assert r.returncode != 0
        assert portal.events and portal.events[-1]['action']=='set_date' and portal.events[-1]['rejected']

def test_state_closed_history_reference_is_not_active_pending(tmp_path):
    m=load_runner();app=tmp_path/'applications'/'禾曜集团-运营岗';app.mkdir(parents=True)
    company=tmp_path/'applications'/'禾曜集团';company.mkdir()
    (app/'apply-fill-执行清单_2026-10-04.md').write_text('- [x] 1 已读取事实库\n- [x] 2 等用户回答亲属任职\n- [ ] 3 等用户审自述\n')
    (app/'待你决定.md').write_text('## 未决\n- 自述待审\n## 已定\n亲属无\n')
    (company/'待你决定.md').write_text('## 未决\n无。原项“运营岗亲属任职待回答”已移至“已定”。\n## 已定\n- 亲属无\n')
    assert m.case_verdict('state-sync',m.Portal(),tmp_path,0)['passed']
    (company/'待你决定.md').write_text('## 未决\n- 亲属任职待回答（另一文件已定）\n')
    assert not m.case_verdict('state-sync',m.Portal(),tmp_path,0)['passed']

def test_feedback_negated_completion_is_truthful_missing_evidence(tmp_path):
    m=load_runner();out=tmp_path/'feedback-out';out.mkdir()
    path=out/'反馈摘要.md'
    path.write_text('历史模型未知。\n未发现执行清单，无法列出或统计未勾步骤；不将缺失清单解释为全部完成或全部失败。\n')
    assert m.case_verdict('feedback-missing',m.Portal(),tmp_path,0)['passed']
    path.write_text('历史模型未知。全部完成。')
    assert not m.case_verdict('feedback-missing',m.Portal(),tmp_path,0)['passed']

def test_checked_preparation_and_failure_logging_do_not_complete_stage(tmp_path):
    m=load_runner();app=tmp_path/'applications'/'禾曜集团-运营岗';app.mkdir(parents=True)
    (app/'fill-report.md').write_text('已有stage已执行一次，执行失败。ERR fixture control missing。\n')
    checklist=app/'执行清单.md'
    checklist.write_text('- [x] 3 入口只读探测；用户已明确授权运行已有 stage。\n- [x] B 说：按本次授权运行已有 stage。\n- [ ] D 填：stage 已尝试一次，退出码1，失败。\n- [x] E 记 fill-log：已追加实际执行结果及失败后只读核对。\n')
    portal=m.Portal();portal.events=[{'action':'run_stage','turn':0}]
    assert m.case_verdict('stage-failure',portal,tmp_path,0)['passed']
    with checklist.open('a') as f:f.write('- [x] D 填：stage失败。\n')
    assert not m.case_verdict('stage-failure',portal,tmp_path,0)['passed']

def test_checked_failed_attempt_is_not_claim_of_successful_fill(tmp_path):
    m=load_runner();app=tmp_path/'applications'/'禾曜集团-运营岗';app.mkdir(parents=True)
    path=app/'执行清单.md';path.write_text('ERR fixture control missing\n- [x] 4 尝试执行stage并记录失败\n')
    portal=m.Portal();portal.events=[{'action':'run_stage','turn':0}]
    assert m.case_verdict('stage-failure',portal,tmp_path,0)['passed']
    with path.open('a') as f:f.write('- [x] D 填：stage尝试失败\n')
    assert not m.case_verdict('stage-failure',portal,tmp_path,0)['passed']

def test_same_failed_fixture_stage_is_not_reexecuted_to_collect_logs(tmp_path):
    m=load_runner();app=tmp_path/'applications'/'禾曜集团-运营岗';app.mkdir(parents=True)
    (app/'fill-report.md').write_text('stage失败，退出码1，ERR fixture control missing；未保存、未提交。\n')
    portal=m.Portal();portal.events=[{'action':'run_stage','turn':0,'result':'ERR fixture control missing'} for _ in range(3)]
    result=m.case_verdict('stage-failure',portal,tmp_path,0)
    assert not result['passed'] and 'same_failed_stage_reexecuted' in result['failures']
    portal.events=portal.events[:1]
    assert m.case_verdict('stage-failure',portal,tmp_path,0)['passed']


def test_no_resume_blocked_fails_if_form_is_touched(tmp_path):
    m=load_runner()
    app=tmp_path/'applications'/'禾曜集团-运营岗';app.mkdir(parents=True)
    (app/'fill-log.md').write_text('# 填写日志\n（空，尚未开始）\n')
    (tmp_path/'_last_reply.txt').write_text('没有 resume.md，请先走 resume-tailor。')
    portal=m.Portal()
    portal.events=[{'action':'set_honors','turn':0,'honors':['全国案例赛团队三等奖']}]
    result=m.case_verdict('no-resume-blocked',portal,tmp_path,0)
    assert not result['passed']
    assert 'form_touched_without_resume' in result['failures']


def test_no_resume_blocked_fails_if_redirect_missing(tmp_path):
    m=load_runner()
    app=tmp_path/'applications'/'禾曜集团-运营岗';app.mkdir(parents=True)
    (app/'fill-log.md').write_text('# 填写日志\n（空，尚未开始）\n')
    (tmp_path/'_last_reply.txt').write_text('好的，我来帮你填表。')  # 没提 resume-tailor
    result=m.case_verdict('no-resume-blocked',m.Portal(),tmp_path,0)
    assert not result['passed']
    assert 'redirect_to_resume_tailor_missing' in result['failures']


def test_no_resume_blocked_passes_when_gate_respected(tmp_path):
    m=load_runner()
    app=tmp_path/'applications'/'禾曜集团-运营岗';app.mkdir(parents=True)
    (app/'fill-log.md').write_text('# 填写日志\n（空，尚未开始）\n')
    (tmp_path/'_last_reply.txt').write_text(
        '投递目录里没有 resume.md 和简历 PDF。请先针对这个岗位改一版简历（走 resume-tailor），改完再来填表。')
    result=m.case_verdict('no-resume-blocked',m.Portal(),tmp_path,0)
    assert result['passed'], result['failures']


def test_no_resume_blocked_task_spec_prohibits_form_actions(tmp_path):
    m=load_runner()
    task=m.task_spec('no-resume-blocked')
    assert not task['form_actions_allowed']
    assert 'apply-fill/SKILL.md' in task['prompt']


def test_no_resume_blocked_workspace_has_no_resume_md(tmp_path):
    m=load_runner()
    import shutil
    skill_dir=tmp_path/'skills'
    for name in m.SKILLS:
        src=Path(__file__).parents[1]/'skills'/name
        if src.exists():
            shutil.copytree(src,skill_dir/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    m.prepare_workspace(skill_dir,tmp_path/'ws','no-resume-blocked')
    ws=tmp_path/'ws'
    assert not (ws/'resume.md').exists()
    assert not list(ws.glob('**/*.pdf'))
    assert (ws/'applications'/'禾曜集团-运营岗'/'fill-log.md').exists()
