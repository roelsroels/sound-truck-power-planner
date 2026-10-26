import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path/'test.sqlite3'),admin_token='test-secret')) as c:
        yield c

def test_seed_and_example(client):
    data=client.get('/api/v1/catalog').json()
    assert client.get('/api/health').json()['status']=='ok'
    assert len(data)==4
    assert next(e for e in data if e['id']=='top-12ndl88-dcx464')['amplifier'].endswith('3004PFC4 × 1')
    assert len(client.get('/api/v1/example').json()['units'])==6

def test_public_catalog_is_read_only(client):
    item=client.get('/api/v1/catalog').json()[0]
    assert client.put('/api/v1/catalog/'+item['id'],json=item).status_code==403
    assert client.put('/api/v1/catalog/'+item['id'],json=item,headers={'X-Admin-Token':'wrong'}).status_code==403
    assert client.delete('/api/v1/catalog/'+item['id']).status_code==403

def test_admin_update_persists(client):
    item=client.get('/api/v1/catalog').json()[0]
    item['design_va']=7000
    h={'X-Admin-Token':'test-secret'}
    assert client.put('/api/v1/catalog/'+item['id'],json=item,headers=h).status_code==200
    assert next(e for e in client.get('/api/v1/catalog').json() if e['id']==item['id'])['design_va']==7000
    assert client.delete('/api/v1/catalog/'+item['id'],headers=h).status_code==200
    assert len(client.get('/api/v1/catalog').json())==3

def test_reject_bad_payload(client):
    item=client.get('/api/v1/catalog').json()[0]
    item['power_factor']=1.5
    assert client.put('/api/v1/catalog/'+item['id'],json=item,headers={'X-Admin-Token':'test-secret'}).status_code==422
    item['power_factor']=0.95
    assert client.put('/api/v1/catalog/different',json=item,headers={'X-Admin-Token':'test-secret'}).status_code==400

def test_pdf_report_export(client):
    project=client.get('/api/v1/example').json()
    equipment=client.get('/api/v1/catalog').json()
    response=client.post('/api/v1/reports/engineering.pdf',
                         json={'project':project,'equipment':equipment})
    assert response.status_code==200, response.text[:250] if response.status_code!=200 else ''
    assert response.headers['content-type']=='application/pdf'
    assert response.headers['cache-control']=='no-store'
    assert response.content.startswith(b'%PDF-')
    assert len(response.content)>3500
    assert b'/Type /Page' in response.content

def test_pdf_report_rejects_missing_or_excessive_equipment(client):
    project=client.get('/api/v1/example').json()
    assert client.post('/api/v1/reports/engineering.pdf',
                       json={'project':project,'equipment':[]}).status_code==422
    project['units']*=40
    equipment=client.get('/api/v1/catalog').json()
    assert client.post('/api/v1/reports/engineering.pdf',
                       json={'project':project,'equipment':equipment}).status_code==422
