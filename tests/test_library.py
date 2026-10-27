import copy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app import library


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / 'test.sqlite3'), admin_token='test-secret-for-local-tests-only-123456')) as c:
        yield c


def example_pack():
    return json.loads(Path('web/library-template.json').read_text())


def test_bundled_variants_and_passive_consumption(client):
    data = client.get('/api/v3/library').json()
    assert {m['id'] for m in data['manufacturers']} == {'bc-speakers', 'powersoft'}
    assert len(data['products']) >= 500
    variants = [p for p in data['products'] if p['model'] == 'DCX464']
    assert {p['variant'] for p in variants} >= {'8 Ω','16 Ω'}
    assert len({p['id'] for p in data['products']}) == len(data['products'])
    for p in data['products']:
        assert 'specs' not in p  # Manifest stays small; load details on selection.
    driver = client.get('/api/v3/library/products/' + variants[0]['id']).json()
    assert driver['electrical'] is None and driver['specs']
    assert driver['source_url'].startswith('https://www.bcspeakers.com/')
    amp = client.get('/api/v3/library/products/powersoft-digimod-3004pfc2').json()
    assert amp['electrical']['reference_va'] == 600
    assert amp['electrical']['design_va'] is None
    assert amp['electrical']['power_factor'] is None
    assert '1/8' in amp['electrical']['basis']
    assert client.get('/api/v3/library/products/missing').status_code == 404
    assert client.get('/api/v3/library/schema').json()['properties']['schema_version']
    assert client.get('/api/v3/library/products/powersoft-k20').json()['status'] == 'archived'


def test_future_manufacturer_validation_is_read_only_and_import_is_admin_only(client):
    pack = example_pack()
    count = len(client.get('/api/v3/library').json()['products'])
    assert client.post('/api/v3/library/validate', json=pack).status_code == 200
    assert len(client.get('/api/v3/library').json()['products']) == count
    assert client.post('/api/v3/library/import', json=pack).status_code == 403
    response = client.post('/api/v3/library/import', json=pack, headers={'X-Admin-Token':'test-secret-for-local-tests-only-123456'})
    assert response.status_code == 200
    assert response.json()['products'] == 1
    assert len(client.get('/api/v3/library').json()['products']) == count + 1
    assert client.get('/api/v3/library/products/example-audio-passive-cabinet-8').json()['kind'] == 'passive_cabinet'
    assert len(client.get('/api/v1/catalog').json()) == 4
    # Upsert updates, rather than duplicating the product.
    pack['products'][0]['model'] = 'Updated model'
    client.post('/api/v3/library/import', json=pack, headers={'X-Admin-Token':'test-secret-for-local-tests-only-123456'})
    assert len(client.get('/api/v3/library').json()['products']) == count + 1
    assert client.get('/api/v3/library/products/example-audio-passive-cabinet-8').json()['model'] == 'Updated model'


@pytest.mark.parametrize('mutation', ['duplicate','missing-brand','unsafe-url','credentials','passive-mains','invalid-namespace','nonfinite','unknown-field'])
def test_invalid_pack_rejected_before_write(client, mutation):
    pack = example_pack(); p = pack['products'][0]
    if mutation == 'duplicate': pack['products'].append(copy.deepcopy(p))
    elif mutation == 'missing-brand': p['manufacturer_id'] = 'missing-brand'
    elif mutation == 'unsafe-url': p['source_url'] = 'javascript:alert(1)'
    elif mutation == 'credentials': p['source_url'] = 'https://secret:password@example.com/spec'
    elif mutation == 'passive-mains': p['electrical'] = {'reference_va':1000, 'basis':'speaker watts'}
    elif mutation == 'invalid-namespace': p['id'] = 'another-brand-model'
    elif mutation == 'nonfinite':
        p.update(kind='amplifier',power_input='ac',electrical={'reference_va':'NaN','basis':'invalid'})
    elif mutation == 'unknown-field': p['invented_power'] = 500
    assert client.post('/api/v3/library/import', json=pack, headers={'X-Admin-Token':'test-secret-for-local-tests-only-123456'}).status_code == 422
    assert client.get('/api/v3/library/products/example-audio-passive-cabinet-8').status_code == 404


def test_import_survives_restart_and_bundle_does_not_overwrite_it(tmp_path):
    path = str(tmp_path / 'test.sqlite3')
    with TestClient(create_app(path, admin_token='test-secret-for-local-tests-only-123456')) as client:
        pack = example_pack()
        assert client.post('/api/v3/library/import', json=pack, headers={'X-Admin-Token':'test-secret-for-local-tests-only-123456'}).status_code == 200
    with TestClient(create_app(path)) as client:
        assert client.get('/api/v3/library/products/example-audio-passive-cabinet-8').status_code == 200
        assert len(client.get('/api/v1/catalog').json()) == 4


def test_every_bundled_pack_is_valid_and_technical_data_is_sourced():
    manufacturers, products = library.bundled()
    for p in products.values():
        assert p['specs'] and p['checked_at']
        assert p['source_url'].startswith(manufacturers[p['manufacturer_id']]['website'])
        if p['kind'] not in ('amplifier','active_cabinet') or p['power_input'] == 'dc':
            assert p['electrical'] is None


def test_library_profile_survives_report_validation(client):
    project = json.loads(Path('app/example.json').read_text())
    equipment = json.loads(Path('app/seed.json').read_text())
    custom = copy.deepcopy(equipment[0])
    custom.update(id='user-library',name='Library test assembly',library_components=[{
        'product_id':'powersoft-m-drive','manufacturer':'Powersoft','model':'M-Drive',
        'variant':'','quantity':1,'source_url':'https://www.powersoft.com/en/products/amp-modules/m-drive'}])
    project['custom_equipment'] = [custom]
    project['units'].append({'equipment_id':'user-library','phase':'L1'})
    response = client.post('/api/v1/reports/engineering.pdf',json={'project':project,'equipment':equipment+[custom]})
    assert response.status_code == 200
    assert response.content.startswith(b'%PDF')


def test_bad_second_product_cannot_partially_import(client):
    pack = example_pack()
    second = copy.deepcopy(pack['products'][0]);second['id'] = 'example-audio-second'
    second['kind'] = 'incorrect-type';pack['products'].append(second)
    assert client.post('/api/v3/library/import',json=pack,headers={'X-Admin-Token':'test-secret-for-local-tests-only-123456'}).status_code == 422
    assert client.get('/api/v3/library/products/example-audio-passive-cabinet-8').status_code == 404
