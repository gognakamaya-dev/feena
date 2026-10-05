from unittest.mock import Mock, patch
import pytest
from click.testing import CliRunner
from pydantic import ValidationError
from feena.cli import main, _run_agents
from feena.config import Config, RunConfig, TargetConfig, load_config
from feena.journeys import JourneyProposal, save_proposal, approve_proposal
from feena.sandbox import SandboxError


def proposal():
    return JourneyProposal.model_validate({'setup': 'Reset disposable orders to zero.', 'scenario': {
        'name': 'checkout', 'goal': 'One order after checkout',
        'steps': [{'action': 'goto', 'target': '/checkout'}],
        'assertions': [{'kind': 'text', 'target': 'h1', 'expected': 'Checkout'},
                       {'kind': 'json', 'target': '/api/orders/count', 'expected': {'count': 1}}]}})


def test_export(tmp_path):
    source, destination = tmp_path/'proposal.json', tmp_path/'approved.yaml'
    digest = save_proposal(proposal(), source)
    approve_proposal(source, digest, destination)
    cfg = load_config(destination)
    assert cfg.run.agents == [] and cfg.scenarios[0].name == 'checkout'


def test_changed_proposal(tmp_path):
    source = tmp_path/'proposal.json'
    digest = save_proposal(proposal(), source)
    source.write_text(source.read_text() + ' ')
    with pytest.raises(ValueError, match='changed'):
        approve_proposal(source, digest, tmp_path/'approved.yaml')
    assert not (tmp_path/'approved.yaml').exists()


def test_no_overwrite(tmp_path):
    source, destination = tmp_path/'proposal.json', tmp_path/'approved.yaml'
    digest = save_proposal(proposal(), source)
    with pytest.raises(FileExistsError):
        save_proposal(proposal(), source)
    destination.write_text('existing')
    with pytest.raises(FileExistsError):
        approve_proposal(source, digest, destination)
    assert destination.read_text() == 'existing'


@pytest.mark.parametrize('kind', ['json', 'text'])
def test_both_assertions_required(kind):
    data = proposal().model_dump()
    data['scenario']['assertions'] = [a for a in data['scenario']['assertions'] if a['kind'] == kind]
    with pytest.raises(ValidationError):
        JourneyProposal.model_validate(data)


def test_no_self_approval():
    data = proposal().model_dump()
    data['approved'] = True
    with pytest.raises(ValidationError):
        JourneyProposal.model_validate(data)


def test_cli_never_starts_browser(tmp_path):
    observation = tmp_path/'observation.txt'
    observation.write_text('- button "Checkout"')
    with patch('feena.cli.LLM') as llm, patch('feena.cli.session') as browser:
        llm.return_value.propose.return_value = proposal()
        result = CliRunner().invoke(main, ['propose-journey', '--goal', 'Checkout once',
            '--observation', str(observation), '--out', str(tmp_path/'draft.json')])
        assert result.exit_code == 0, result.output
        browser.assert_not_called()
        assert 'No tests were run' in result.output


@pytest.mark.parametrize('path', ['https://other.example/reset', '//other/reset', '/reset#fragment'])
def test_reset_must_be_local(path):
    with pytest.raises(ValidationError):
        RunConfig(reset_path=path)


def test_failed_reset_stops_agent(tmp_path):
    cfg = Config(target=TargetConfig(compose='', service='', port=0), run=RunConfig(reset_path='/reset'))
    cfg.report.out_dir = str(tmp_path)
    with patch('httpx.post', return_value=Mock(status_code=302)) as reset, patch('feena.cli.session') as browser:
        with pytest.raises(SandboxError, match='reset failed'):
            _run_agents(cfg, Mock(base_url='http://localhost:5055'), ['regular'], Mock())
        browser.assert_not_called()
        assert reset.call_args.kwargs['follow_redirects'] is False


def test_goal_override():
    from feena.agents.base import AgentContext
    from feena.agents.regular import RegularAgent
    cfg = Config(target=TargetConfig(compose='', service='', port=0), run=RunConfig(goals={'regular': 'Save a draft'}))
    assert RegularAgent(AgentContext(cfg, Mock(), Mock())).goal == 'Save a draft'
