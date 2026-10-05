import json
from unittest.mock import Mock
import pytest
from feena.agents.base import AgentContext, BaseAgent
from feena.agents.regular import RegularAgent
from feena.config import Config, TargetConfig
from feena.llm import Decision
from feena.cli import _exploration_report, _exploration_incomplete


def agent(tmp_path, decisions, cls=BaseAgent):
    cfg = Config(target=TargetConfig(compose='', service='', port=0))
    cfg.run.max_steps = 3
    cfg.report.out_dir = str(tmp_path)
    session = Mock(out_dir=tmp_path)
    session.snapshot.return_value = 'Page'
    session.screenshot.return_value = tmp_path/'screen.png'
    session.page.url = 'http://localhost/'
    session.page.inner_text.return_value = 'Normal page'
    session.perform.return_value = {'status': 'ok'}
    llm = Mock(available=True)
    llm.decide.side_effect = decisions
    return cls(AgentContext(cfg, session, llm))


@pytest.mark.parametrize('decision,status', [(Decision('done'), 'completed_unverified'),
    (Decision('error', reason='invalid model output'), 'model_error'), (RuntimeError(), 'model_error')])
def test_stops(tmp_path, decision, status):
    a = agent(tmp_path, [decision]); a.run()
    result = json.loads((tmp_path/'run-summary.json').read_text())
    assert result['status'] == status and result['goal_verified'] is False


def test_budget(tmp_path):
    a = agent(tmp_path, [Decision('click', '#go')]*3); a.run()
    assert a.summary['status'] == 'budget_exhausted'


def test_no_model(tmp_path):
    a = agent(tmp_path, []); a.ctx.llm.available = False; a.run()
    assert a.summary['status'] == 'model_unavailable'
    a.ctx.session.goto.assert_not_called()


def test_candidate(tmp_path):
    a = agent(tmp_path, [Decision('click', '#buy'), Decision('note_finding', reason='Order disappeared'), Decision('done')])
    findings = a.run()
    assert len(findings) == 1 and findings[0].detail == 'Order disappeared'
    assert findings[0].steps[0].target == '#buy' and not findings[0].confirmed
    assert findings[0].evidence['observation'].endswith('observation-0001.txt')


def test_uncertain_action(tmp_path):
    a = agent(tmp_path, [Decision('click', '#buy'), Decision('done')])
    a.ctx.session.perform.return_value = {'status': 'error'}; a.run()
    assert a.summary['status'] == 'inconclusive' and a.summary['action_errors'] == 1


def test_500_copy(tmp_path):
    a = agent(tmp_path, [Decision('click', '#products'), Decision('done')], RegularAgent)
    a.ctx.session.page.inner_text.return_value = 'Choose from 500 products'
    assert a.run() == []


def test_report(tmp_path):
    a = agent(tmp_path, [RuntimeError()]); a.run()
    (tmp_path/'exploration.json').write_text(json.dumps([{**a.summary, 'evidence_dir': str(tmp_path)}]))
    (tmp_path/'candidates.json').write_text(json.dumps([{'title':'Lost order','verification_status':'inconclusive', 'verification_reason':'Missing replay input'}]))
    assert _exploration_incomplete(a.ctx.cfg)
    text = _exploration_report(a.ctx.cfg)
    assert 'model_error' in text and 'Lost order' in text and 'not confirmed bugs' in text


def test_browser_start_failure_is_reported(tmp_path):
    from unittest.mock import patch
    from feena.cli import _run_agents
    a = agent(tmp_path, [])
    with patch('feena.cli.session', side_effect=RuntimeError('browser unavailable')):
        assert _run_agents(a.ctx.cfg, Mock(base_url='http://localhost'), ['regular'], Mock(available=True)) == []
    assert json.loads((tmp_path/'exploration.json').read_text())[0]['status'] == 'blocked'


def test_unverified_candidate_is_preserved_by_scan(tmp_path):
    from unittest.mock import patch
    from feena.cli import _scan
    from feena.findings import Finding, Kind, Severity
    a = agent(tmp_path, [])
    f = Finding(Kind.BROKEN_FLOW, Severity.MEDIUM, 'Lost order', 'Order absent after checkout', 'regular')
    with patch('feena.cli._run_agents', return_value=[f]):
        confirmed, dropped = _scan(a.ctx.cfg, Mock(), [])
    saved = json.loads((tmp_path/'candidates.json').read_text())
    assert confirmed == [] and dropped == 1
    assert saved[0]['detail'] == 'Order absent after checkout'
    assert saved[0]['verification_status'] == 'inconclusive'


def test_incomplete_run_exits_nonzero_and_writes_report(tmp_path):
    from feena.cli import _emit
    a = agent(tmp_path, [RuntimeError()]); a.run()
    (tmp_path/'exploration.json').write_text(json.dumps([{**a.summary, 'evidence_dir': str(tmp_path)}]))
    with pytest.raises(SystemExit) as error:
        _emit(a.ctx.cfg, [], 0, ['regular'])
    assert error.value.code == 1
    assert 'model_error' in (tmp_path/'report.md').read_text()
