import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from feena.browser import Session
from feena.llm import Decision, _parse
from feena.agents.base import AgentContext, BaseAgent


def session(tmp_path):
    result = Session('http://localhost:5055', tmp_path)
    result.page = Mock(url='http://localhost:5055/form')
    return result


def test_observation_uses_aria_snapshot_and_includes_context(tmp_path):
    s = session(tmp_path)
    s.page.locator.return_value.aria_snapshot.return_value = '- button "Save"'
    s.errors.append('Request failed')
    text = s.snapshot()
    assert 'button "Save"' in text and 'http://localhost:5055/form' in text
    assert 'Request failed' in text


def test_observation_fallback_and_size_limit(tmp_path):
    s = session(tmp_path)
    s.page.locator.return_value.aria_snapshot.side_effect = RuntimeError()
    s.page.locator.return_value.inner_text.return_value = 'x' * 50000
    assert len(s.snapshot()) < 17000
    s.page.locator.return_value.inner_text.side_effect = RuntimeError()
    assert 'Do not infer' in s.snapshot()


@pytest.mark.parametrize('action', ['click', 'dblclick', 'fill', 'press'])
def test_semantic_actions_are_exact_and_record_outcomes(tmp_path, action):
    s = session(tmp_path)
    result = s.perform(Decision(action, role='button', name='Save', value='private-value'))
    s.page.get_by_role.assert_called_once_with('button', name='Save', exact=True)
    assert getattr(s.page.get_by_role.return_value, action).call_count == 1
    assert result['status'] == 'ok'
    record = (tmp_path / 'agent-actions.jsonl').read_text()
    assert 'private-value' not in record
    assert json.loads(record)['screenshot'].endswith('action-0001.png')


def test_failed_click_is_not_retried(tmp_path):
    s = session(tmp_path)
    s.page.locator.return_value.click.side_effect = TimeoutError('secret input')
    result = s.perform(Decision('click', '#submit'))
    assert result['status'] == 'error'
    assert s.page.locator.return_value.click.call_count == 1
    assert 'secret input' not in json.dumps(result)
    assert 'side effects' in result['reason']


@pytest.mark.parametrize('target', ['https://outside.example', '//outside.example', 'javascript:alert(1)'])
def test_explicit_navigation_stays_on_configured_origin(tmp_path, target):
    s = session(tmp_path)
    assert s.perform(Decision('goto', target))['status'] == 'error'
    s.page.goto.assert_not_called()


@pytest.mark.parametrize('value', ['[]', 'null', '{"action":"shell"}', '{"action":"click","target":{}}'])
def test_invalid_model_output_stops_safely(value):
    assert _parse(value).action == 'error'


def test_agent_receives_action_outcome_before_next_decision(tmp_path):
    s = session(tmp_path)
    s.page.locator.return_value.aria_snapshot.return_value = '- button "Save"'
    s.page.locator.return_value.click.side_effect = TimeoutError()
    llm = Mock()
    histories = []
    def decide(system, goal, observation, history, screenshot=None):
        histories.append(list(history))
        return Decision('click', '#save') if len(histories) == 1 else Decision('done')
    llm.decide.side_effect = decide
    cfg = SimpleNamespace(run=SimpleNamespace(budget_seconds=10, max_steps=2))
    BaseAgent(AgentContext(cfg, s, llm)).run()
    assert any('Action outcome:' in line and '"status": "error"' in line for line in histories[1])


def test_llm_receives_screenshot_with_text(tmp_path):
    from feena.llm import LLM
    image = tmp_path / 'screen.png'
    image.write_bytes(b'example-image')
    llm = LLM()
    llm._client = Mock()
    llm._client.messages.create.return_value.content = [SimpleNamespace(type='text', text='{"action":"done"}')]
    assert llm.decide('system', 'goal', 'page', [], screenshot=image).action == 'done'
    content = llm._client.messages.create.call_args.kwargs['messages'][0]['content']
    assert content[0]['type'] == 'text'
    assert content[1]['source']['media_type'] == 'image/png'
