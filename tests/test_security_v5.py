from fastapi.testclient import TestClient
from meridian.api import create_app
from meridian.db import init_db
from meridian.security import add_user


def test_auth_protects_local_api_and_role_matrix(tmp_path):
    db=tmp_path/'secure.db';init_db(db)
    add_user(db,'adminlocal','this-is-a-test-password-1234','admin')
    add_user(db,'viewerlocal','this-is-another-test-password-1234','viewer')
    add_user(db,'operatorlocal','this-is-third-test-password-1234','operator')
    with TestClient(create_app(db,auth_required=True)) as c:
        assert c.get('/').status_code==200
        assert c.get('/api/security/status').json()['login_required']
        assert c.get('/api/items').status_code==401
        assert c.post('/api/security/login',json={'username':'adminlocal','password':'bad-password'}).status_code==401
        admin=c.post('/api/security/login',json={'username':'adminlocal','password':'this-is-a-test-password-1234'}).json()['access_token']
        viewer=c.post('/api/security/login',json={'username':'viewerlocal','password':'this-is-another-test-password-1234'}).json()['access_token']
        operator=c.post('/api/security/login',json={'username':'operatorlocal','password':'this-is-third-test-password-1234'}).json()['access_token']
        auth=lambda t:{'Authorization':'Bearer '+t}
        assert c.get('/api/items',headers=auth(viewer)).status_code==200
        assert c.post('/api/items',json={'sku':'DEMO-001','name':'Test'},headers=auth(viewer)).status_code==403
        assert c.post('/api/items',json={'sku':'DEMO-001','name':'Test'},headers=auth(operator)).status_code==201
        assert c.post('/api/finance/companies',json={'code':'COMP','name':'Demo'},headers=auth(operator)).status_code==403
        assert c.post('/api/finance/companies',json={'code':'COMP','name':'Demo'},headers=auth(admin)).status_code==201
        assert c.post('/api/security/logout',headers=auth(admin)).status_code==200
        assert c.get('/api/items',headers=auth(admin)).status_code==401
        assert c.get('/api/items',headers={'Authorization':'Bearer not-a-real-token'}).status_code==401


def test_legacy_mode_remains_compatible(tmp_path):
    with TestClient(create_app(tmp_path/'open.db',auth_required=False)) as c:
        assert c.get('/api/security/status').json()['login_required'] is False
        assert c.get('/api/items').status_code==200
