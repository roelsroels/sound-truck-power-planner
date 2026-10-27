import asyncio
import json
import multiprocessing
import time
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import create_app
from app.security import SecurityMiddleware, Policy, Buckets, PDF, VALIDATE, valid_token
from app.workers import Worker

TOKEN='test-secret-for-local-tests-only-123456'


async def invoke(guard,path='/',method='GET',body=b'',extra=(),chunks=None,peer='127.0.0.1'):
    messages=[];reads=0
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':'http','server':('testserver',80),
           'path':path,'raw_path':path.encode(),'method':method,'query_string':b'','client':(peer,123),
           'headers':[(b'host',b'testserver')]+list(extra)}
    parts=iter(chunks or [{'type':'http.request','body':body,'more_body':False}])
    async def receive():
        nonlocal reads
        reads+=1
        return next(parts,{'type':'http.disconnect'})
    async def send(message):messages.append(message)
    await guard(scope,receive,send)
    return messages,reads


async def ok(scope,receive,send):
    await receive()
    await send({'type':'http.response.start','status':200,'headers':[]})
    await send({'type':'http.response.body','body':b'ok'})


def guard(policy=None,inner=ok):
    return SecurityMiddleware(inner,token=TOKEN,asset_prefix='/assets/test',policy=policy)


def status(result):return result[0][0]['status']


def test_admin_auth_and_declared_limits_run_before_body_read():
    for path,method in [('/api/v1/catalog/test','PUT'),('/api/v1/catalog/test','DELETE'),('/api/v3/library/import','POST')]:
        result=asyncio.run(invoke(guard(),path,method,extra=[(b'content-length',b'999999999')]))
        assert status(result)==403 and result[1]==0
    result=asyncio.run(invoke(guard(),PDF,'POST',extra=[(b'content-length',b'2000001')]))
    assert status(result)==413 and result[1]==0


def test_stream_limit_does_not_trust_content_length():
    chunks=[{'type':'http.request','body':b'x'*10,'more_body':True}, {'type':'http.request','body':b'x'*10,'more_body':False}]
    for extra in ([],[(b'content-length',b'3')]):
        result=asyncio.run(invoke(guard(Policy(report_body=16)),PDF,'POST',extra=[(b'content-type',b'application/json')]+extra,chunks=chunks))
        assert status(result)==413
    result=asyncio.run(invoke(guard(),PDF,'POST',body=b'{}',extra=[(b'content-type',b'application/json'),(b'content-length',b'3')]))
    assert status(result)==400


def test_body_deadline():
    async def check():
        sent=[]
        async def receive():await asyncio.sleep(.1);return {'type':'http.request','body':b''}
        async def send(message):sent.append(message)
        scope={'type':'http','path':PDF,'method':'POST','headers':[(b'host',b'testserver'),(b'content-type',b'application/json')],'client':('127.0.0.1',1)}
        await guard(Policy(body_timeout=.01))(scope,receive,send)
        assert sent[0]['status']==408
    asyncio.run(check())


def test_rate_limit_and_bounded_bucket_storage():
    now=[0.0];b=Buckets(capacity=4,clock=lambda:now[0])
    assert b.allow('one',6,1) and not b.allow('one',6,1)
    now[0]=10;assert b.allow('one',6,1)
    for n in range(20):b.allow(n,6,1)
    assert len(b.items)==4
    g=guard()
    codes=[status(asyncio.run(invoke(g,PDF,'POST',extra=[(b'content-type',b'application/json')]))) for _ in range(4)]
    assert codes[-1]==429


def test_busy_expensive_operation_does_not_block_health():
    async def check():
        waiting=asyncio.Event();release=asyncio.Event()
        async def inner(scope,receive,send):
            if scope['path']==PDF:waiting.set();await release.wait()
            await ok(scope,receive,send)
        g=guard(inner=inner)
        first=asyncio.create_task(invoke(g,PDF,'POST',extra=[(b'content-type',b'application/json')]))
        await waiting.wait()
        assert status(await invoke(g,VALIDATE,'POST',extra=[(b'content-type',b'application/json')]))==503
        assert status(await invoke(g,'/api/health'))==200
        release.set();assert status(await first)==200
        assert g.active==0 and g.heavy==0
    asyncio.run(check())


def test_malformed_hosts_tokens_and_validation_errors(tmp_path):
    with TestClient(create_app(str(tmp_path/'db'),admin_token=TOKEN)) as client:
        for host in ['testserver/ignored?x=','testserver#fragment','bad host','testserver:99999']:
            assert client.get('/api/health',headers={'host':host}).status_code==400
        assert client.delete('/api/v1/catalog/test',headers={'X-Admin-Token':b'\xff'}).status_code==403
        item=client.get('/api/v1/catalog').json()[0];item['bad']='secret-canary'*100
        response=client.put('/api/v1/catalog/'+item['id'],json=item,headers={'X-Admin-Token':TOKEN})
        assert response.status_code==422 and 'secret-canary' not in response.text and len(response.content)<200
        assert client.get('/docs').status_code==404
        assert client.get('/api/health').headers['cache-control']=='no-store'
        assert "object-src 'none'" in response.headers['content-security-policy']
    assert not valid_token(TOKEN,b'\xff')
    with pytest.raises(ValueError):create_app(str(tmp_path/'bad'),admin_token='short')


def test_strict_report_schema_and_successful_export(tmp_path):
    from app.workers import execute
    project=json.loads(Path('app/example.json').read_text());equipment=json.loads(Path('app/seed.json').read_text())
    raw=lambda:json.dumps({'project':project,'equipment':equipment}).encode()
    code,pdf,media=execute('pdf',raw(),None)
    assert code==200 and media=='application/pdf' and pdf.startswith(b'%PDF')
    project['arbitrary']={'deep':{'value':'canary'}}
    code,body,_=execute('pdf',raw(),None)
    assert code==422 and b'canary' not in body
    project.pop('arbitrary');project['name']='x'*121
    assert execute('pdf',raw(),None)[0]==422


def slow_child(send,*args):
    time.sleep(10)


def test_process_timeout_reaps_child_and_releases_capacity(monkeypatch):
    import app.workers as workers
    before={p.pid for p in multiprocessing.active_children()}
    monkeypatch.setattr(workers,'child',slow_child)
    worker=Worker(timeout=.05)
    async def check():
        with pytest.raises(HTTPException) as exc:await worker.run('validate',b'{}')
        assert exc.value.status_code==503
        assert not worker.lock.locked()
    asyncio.run(check())
    assert not [p for p in multiprocessing.active_children() if p.pid not in before]


def test_dns_connection_is_pinned_and_tls_keeps_original_hostname(monkeypatch):
    from app.spec_lookup import PinnedHTTPSConnection, public_addresses
    import app.spec_lookup as lookup
    class Context:
        def wrap_socket(self,raw,server_hostname):
            assert server_hostname=='www.powersoft.com';return raw
    with patch.object(lookup.ssl,'create_default_context',return_value=Context()),patch.object(lookup.socket,'create_connection',return_value=object()) as connect:
        connection=PinnedHTTPSConnection('www.powersoft.com',['93.184.216.34'],timeout=6)
        connection.connect();connect.assert_called_once_with(('93.184.216.34',443),6)
    monkeypatch.setattr(lookup.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('10.0.0.1',443))])
    with pytest.raises(ValueError):public_addresses('www.powersoft.com')


def test_rejected_client_cannot_spend_other_clients_global_budget():
    async def check():
        g=guard()
        for _ in range(200):await invoke(g,peer='192.0.2.1')
        assert status(await invoke(g,peer='192.0.2.2'))==200
    asyncio.run(check())


def test_worker_reply_is_bounded_data_not_pickle():
    from app.workers import packet,decode_result
    assert decode_result(packet(200,b'%PDF-test','application/pdf'))==(200,b'%PDF-test','application/pdf')
    for value in (b'',b'pickle-data',b'999Jtest',b'200Xtest'):
        with pytest.raises(ValueError):decode_result(value)


def test_cancelled_request_keeps_capacity_reserved_until_cleanup(monkeypatch):
    from threading import Event
    worker=Worker();started=Event();release=Event()
    def work(*args):started.set();release.wait(1);return (200,b'{}','application/json')
    monkeypatch.setattr(worker,'_run',work)
    async def check():
        task=asyncio.create_task(worker.run('validate',b'{}'))
        while not started.is_set():await asyncio.sleep(.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert worker.lock.locked()
        with pytest.raises(HTTPException):await worker.run('validate',b'{}')
        release.set()
        for _ in range(100):
            if not worker.lock.locked():break
            await asyncio.sleep(.001)
        assert not worker.lock.locked()
    asyncio.run(check())
