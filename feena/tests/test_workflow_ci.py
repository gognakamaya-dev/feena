from unittest.mock import patch
import httpx
import pytest
from click.testing import CliRunner
from feena.workflow_ci import run_reviewed, summary
from feena.cli import main

ID='a'*32
VERSION='b'*64

def test_ci_uses_same_run_and_links_results():
    seen=[]
    def handle(request):
        seen.append(request)
        return httpx.Response(200,json={'campaign_id':'c'*32,'status':'queued' if request.method=='POST' else 'completed','journey_id':ID,'version':VERSION,'results_url':'https://qa.example.com/workspace#run/'+('c'*32)})
    real=httpx.Client
    with patch('feena.workflow_ci.httpx.Client',side_effect=lambda **kw:real(transport=httpx.MockTransport(handle),**kw)),patch('feena.workflow_ci.time.sleep'):
        result=run_reviewed('https://qa.example.com/mcp','private-key',ID,VERSION,'ci-request')
    assert result['ci_status']=='completed'
    assert all(r.headers['Authorization']=='Bearer private-key' for r in seen)
    assert '/workspace#run/' in summary(result) and 'private-key' not in summary(result)

@pytest.mark.parametrize('endpoint',['http://qa.example.com','https://user:secret@qa.example.com','https://qa.example.com?key=secret'])
def test_reject_unsafe_endpoint(endpoint):
    with pytest.raises(ValueError):run_reviewed(endpoint,'key',ID,VERSION,'ci-request')

def test_report_only_and_blocking_modes(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    result={'ci_status':'failed','journey_id':ID,'version':VERSION,'results_url':'https://qa.example.com/workspace#run/test'}
    args=['workflow-ci','--endpoint','https://qa.example.com','--journey',ID,'--version',VERSION,'--request-id','ci-request']
    with patch('feena.workflow_ci.run_reviewed',return_value=result):
        assert CliRunner().invoke(main,args+['--report-only']).exit_code==0
        assert CliRunner().invoke(main,args).exit_code==1
    assert 'authenticated results' in (tmp_path/'.feena/report.md').read_text()
