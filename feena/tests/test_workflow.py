import asyncio
from pathlib import Path
from unittest.mock import Mock
import pytest
from starlette.testclient import TestClient
from feena.campaigns import Campaigns
from feena.workflow import Workflow
from feena.mcp_server import CampaignRuns, create_server, http_app

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    c=Campaigns(Path('examples/resilient-checkout/feena.yaml'),['http://127.0.0.1:5056'],tmp_path,reset_path='/test/reset')
    async def resume():pass
    monkeypatch.setattr(c,'resume',resume)
    yield Workflow(c,'https://qa.example.com/mcp')
    asyncio.run(c.close())

def proposal():
    return {'setup':'Reset disposable orders','assumptions':['Verify count API'],'scenario':{'name':'checkout','goal':'Exactly one order','steps':[{'action':'goto','target':'/checkout'}],'assertions':[{'kind':'visible','target':'#success'},{'kind':'json','target':'/api/count','expected':{'orders':1}}]}}

def approved(w):
    d=w.submit(proposal());w.approve(d['journey_id'],d['version'],True);return d

def test_review_run_and_rerun(workspace):
    w=workspace;d=w.submit(proposal())
    with pytest.raises(ValueError):asyncio.run(w.start(d['journey_id'],d['version'],'first-request'))
    with pytest.raises(ValueError):w.approve(d['journey_id'],'wrong',True)
    with pytest.raises(ValueError):w.approve(d['journey_id'],d['version'],False)
    w.approve(d['journey_id'],d['version'],True)
    r=asyncio.run(w.start(d['journey_id'],d['version'],'first-request'))
    assert asyncio.run(w.start(d['journey_id'],d['version'],'first-request'))['campaign_id']==r['campaign_id']
    assert w.db.execute('SELECT count(*) FROM jobs').fetchone()[0]==1
    with pytest.raises(ValueError):asyncio.run(w.start(d['journey_id'],d['version'],'rerun-request',rerun_of=r['campaign_id']))
    w.campaigns._update(r['jobs'][0]['id'],'failed')
    again=asyncio.run(w.start(d['journey_id'],d['version'],'rerun-request',rerun_of=r['campaign_id']))
    assert again['rerun_of']==r['campaign_id'] and again['version']==r['version']
    snapshots=[x[0] for x in w.db.execute('SELECT snapshot FROM jobs')]
    assert snapshots[0]==snapshots[1]

def test_revision_and_request_scope(workspace):
    w=workspace;d=approved(w);asyncio.run(w.start(d['journey_id'],d['version'],'same-request'))
    p=proposal();p['scenario']['goal']='Revised goal'
    revision=w.submit(p,d['journey_id']);assert revision['status']=='draft'
    w.approve(revision['journey_id'],revision['version'],True)
    with pytest.raises(ValueError):asyncio.run(w.start(revision['journey_id'],revision['version'],'same-request'))

def test_export(workspace,tmp_path):
    from feena.config import load_config
    d=workspace.submit(proposal())
    with pytest.raises(ValueError):workspace.export(d['journey_id'])
    workspace.approve(d['journey_id'],d['version'],True)
    p=tmp_path/'approved.yaml';p.write_text(workspace.export(d['journey_id']))
    assert load_config(p).run.agents==[] and d['version'] in p.read_text()

def test_http_auth_and_flow(workspace,monkeypatch):
    monkeypatch.setenv('FEENA_MCP_PUBLIC_URL','https://qa.example.com/mcp')
    runs=CampaignRuns(workspace.campaigns)
    app=http_app(create_server(runs,['testserver'],workspace.campaigns,workspace),runs,'x'*40,workspace)
    h={'Authorization':'Bearer '+'x'*40};d=workspace.submit(proposal());i=d['journey_id']
    with TestClient(app) as client:
        assert client.get('/workspace').status_code==200
        assert client.get('/workflow-api/journeys').status_code==401
        assert client.post(f'/workflow-api/journeys/{i}/approve',json={'version':d['version'],'reviewed':True}).status_code==401
        assert client.get('/workflow-api/journeys',headers=h).headers['cache-control']=='no-store'
        assert client.post(f'/workflow-api/journeys/{i}/approve',headers=h,json={'version':d['version'],'reviewed':True}).json()['status']=='approved'
        r=client.post(f'/workflow-api/journeys/{i}/run',headers=h,json={'version':d['version'],'request_id':'http-request'}).json()
        assert r['status']=='queued'
        assert client.get('/workflow-api/runs/'+r['campaign_id'],headers=h).status_code==200
        assert client.get('/workflow-api/runs/missing',headers=h).status_code==400
        assert client.post(f'/workflow-api/journeys/{i}/approve',headers=h,content='x'*70000).status_code==413

def test_artifact_boundaries(workspace,tmp_path):
    w=workspace;d=approved(w);r=asyncio.run(w.start(d['journey_id'],d['version'],'artifact-request'))
    job=r['jobs'][0]['id'];folder=w.campaigns.out/job/'evidence'/'normal';folder.mkdir(parents=True)
    (folder/'final.png').write_bytes(b'png');outside=tmp_path/'secret';outside.write_text('secret')
    (folder/'trace.zip').symlink_to(outside)
    a=w.run(r['campaign_id'])['jobs'][0]['evidence'];assert len(a)==1
    assert w.artifact(r['campaign_id'],job,a[0]['artifact_id']).read_bytes()==b'png'
    with pytest.raises(ValueError):w.artifact(r['campaign_id'],job,'../../secret')
    with pytest.raises(ValueError):w.artifact(r['campaign_id'],'other-job',a[0]['artifact_id'])

def test_requires_reset():
    with pytest.raises(ValueError):Workflow(Mock(reset_path=None))

def test_readiness_does_not_mutate(workspace,monkeypatch):
    import httpx
    async def get(self,url):return httpx.Response(200)
    async def forbidden(*args,**kwargs):raise AssertionError('must not reset')
    monkeypatch.setattr(httpx.AsyncClient,'get',get);monkeypatch.setattr(httpx.AsyncClient,'post',forbidden)
    r=asyncio.run(workspace.readiness());assert r['reset_executed'] is False
    assert r['targets']==[{'slot':1,'reachable':True}]

def test_mcp_submit_review_and_run(workspace,monkeypatch):
    import json
    monkeypatch.setenv('FEENA_MCP_PUBLIC_URL','https://qa.example.com/mcp')
    runs=CampaignRuns(workspace.campaigns)
    app=http_app(create_server(runs,['testserver'],workspace.campaigns,workspace),runs,'x'*40,workspace)
    h={'Authorization':'Bearer '+'x'*40,'Accept':'application/json, text/event-stream'}
    with TestClient(app) as client:
        def call(name,args):
            result=client.post('/mcp',headers=h,json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}}).json()['result']
            assert not result.get('isError'),result
            return json.loads(result['content'][0]['text'])
        d=call('submit_journey_proposal',{'proposal':proposal()})
        assert d['status']=='draft' and '/workspace#journey/' in d['review_url']
        assert call('get_journey',{'journey_id':d['journey_id']})['status']=='draft'
        result=client.post('/mcp',headers=h,json={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'run_journey','arguments':{'journey_id':d['journey_id'],'version':d['version'],'request_id':'blocked-request'}}}).json()['result']
        assert result['isError']
        client.post('/workflow-api/journeys/'+d['journey_id']+'/approve',headers=h,json={'version':d['version'],'reviewed':True}).raise_for_status()
        r=call('run_journey',{'journey_id':d['journey_id'],'version':d['version'],'request_id':'mcp-request'})
        assert call('get_journey_run',{'run_id':r['campaign_id']})['version']==d['version']


def test_approval_survives_restart(tmp_path,monkeypatch):
    config=Path('examples/resilient-checkout/feena.yaml')
    c=Campaigns(config,['http://127.0.0.1:5056'],tmp_path,reset_path='/test/reset')
    w=Workflow(c);d=approved(w);asyncio.run(c.close())
    c2=Campaigns(config,['http://127.0.0.1:5056'],tmp_path,reset_path='/test/reset')
    try:
        assert Workflow(c2).get(d['journey_id'])['status']=='approved'
    finally:asyncio.run(c2.close())


def test_no_evidence_directory_symlink(workspace,tmp_path):
    w=workspace;d=approved(w);r=asyncio.run(w.start(d['journey_id'],d['version'],'symlink-request'))
    job=r['jobs'][0]['id'];root=w.campaigns.out/job;root.mkdir()
    outside=tmp_path/'other';outside.mkdir();(outside/'final.png').write_text('private')
    (root/'evidence').symlink_to(outside,target_is_directory=True)
    assert w.run(r['campaign_id'])['jobs'][0]['evidence']==[]

def test_checkout_pilot_definition_and_reset(monkeypatch):
    import importlib.util,json
    from feena.journeys import JourneyProposal
    p=JourneyProposal.model_validate_json(Path('examples/workflow/checkout-proposal.json').read_text())
    assert any(a.kind=='json' for a in p.scenario.assertions)
    spec=importlib.util.spec_from_file_location('workflow_checkout','examples/resilient-checkout/app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client=module.app.test_client()
    monkeypatch.delenv('FEENA_DEMO_RESET',raising=False)
    assert client.post('/test/reset').status_code==404
    module.ORDERS['test']['order']={'status':'paid'}
    monkeypatch.setenv('FEENA_DEMO_RESET','1')
    assert client.post('/test/reset').status_code==200
    assert not module.ORDERS
