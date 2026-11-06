"""Transactional procurement, quality, and configurability regression coverage."""
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from meridian.api import create_app
from meridian.db import connect

@pytest.fixture
def setup(tmp_path):
    path=tmp_path/'enterprise-v4.db'
    with TestClient(create_app(path)) as c:
        item=c.post('/api/items',json={'sku':'SCREW-A','name':'Machine Screw'}).json()
        location=c.post('/api/locations',json={'code':'MAIN','name':'Main Warehouse'}).json()
        yield c, path, item['id'], location['id']

def post(c,url,body,expected=201):
    r=c.post(url,json=body)
    assert r.status_code==expected,(url,r.status_code,r.text)
    return r.json()

def supplier(c):
    return post(c,'/api/suppliers',{'code':'SUP1','name':'Synthetic Supplier','email':'sample@example.com'})

def po(c, supplier_id, item_id,qty=10):
    return post(c,'/api/purchase-orders',{'number':'PO-TEST-0001','supplier_id':supplier_id,
        'lines':[{'item_id':item_id,'quantity':qty,'unit_price_cents':125}]})

def recv(item_id,loc_id,qty,cmd):
    return {'item_id':item_id,'location_id':loc_id,'quantity':qty,'command_id':cmd}

def test_purchase_order_receipt_atomic_and_idempotent(setup):
    c,path,item,loc=setup
    s=supplier(c);p=po(c,s['id'],item)
    assert p['status']=='draft' and p['total_cents']==1250
    r=c.post(f"/api/purchase-orders/{p['id']}/receive",json=recv(item,loc,1,'RECV-1'))
    assert r.status_code==409
    approved=post(c,f"/api/purchase-orders/{p['id']}/approve",{'actor':'demo.manager'},200)
    assert approved['status']=='approved'
    first=post(c,f"/api/purchase-orders/{p['id']}/receive",recv(item,loc,4,'RECV-1'))
    assert first['purchase_order']['status']=='partial' and first['on_hand']==4
    repeated=post(c,f"/api/purchase-orders/{p['id']}/receive",recv(item,loc,4,'RECV-1'))
    assert repeated['idempotent_replay'] and repeated['ledger_id']==first['ledger_id']
    bad=c.post(f"/api/purchase-orders/{p['id']}/receive",json=recv(item,loc,7,'RECV-2'))
    assert bad.status_code==409
    done=post(c,f"/api/purchase-orders/{p['id']}/receive",recv(item,loc,6,'RECV-2'))
    assert done['purchase_order']['status']=='received' and done['on_hand']==10
    replay=post(c,f"/api/purchase-orders/{p['id']}/receive",recv(item,loc,6,'RECV-2'))
    assert replay['idempotent_replay']
    assert c.post(f"/api/purchase-orders/{p['id']}/receive",json=recv(item,loc,1,'RECV-3')).status_code==409
    assert len(c.get('/api/ledger').json())==2

def test_supplier_po_validation_and_duplicate_lines(setup):
    c,path,item,loc=setup
    s=supplier(c)
    assert c.post('/api/suppliers',json={'code':'SUP1','name':'repeat'}).status_code==409
    assert c.post('/api/purchase-orders',json={'number':'PO-X','supplier_id':s['id'],
      'lines':[{'item_id':item,'quantity':2,'unit_price_cents':2},
      {'item_id':item,'quantity':1,'unit_price_cents':4}]}).status_code==422
    p=po(c,s['id'],item)
    assert c.post('/api/purchase-orders',json={'number':p['number'],'supplier_id':s['id'],
      'lines':[{'item_id':item,'quantity':3,'unit_price_cents':1}]}).status_code==409

def test_quality_lifecycle_with_audit(setup):
    c,path,item,loc=setup
    q=post(c,'/api/quality-cases',{'number':'NCR-001','summary':'Cracked sample screw',
        'source':'incoming','severity':'high','item_id':item})
    assert q['status']=='open'
    assert c.post('/api/quality-cases',json={'number':'NCR-001','summary':'again','source':'inventory'}).status_code==409
    status=post(c,f"/api/quality-cases/{q['id']}/status",{'status':'in_review'},200)
    assert status['status']=='in_review'
    assert c.post(f"/api/quality-cases/{q['id']}/status",json={'status':'resolved','resolution':''}).status_code==422
    resolved=post(c,f"/api/quality-cases/{q['id']}/status",{'status':'resolved','resolution':'Scrap recorded and supplier advised'},200)
    assert resolved['status']=='resolved'
    assert c.post(f"/api/quality-cases/{q['id']}/status",json={'status':'in_review'}).status_code==409
    assert c.get('/api/insights').json()['open_quality_cases']==0
    assert any(x['event_type']=='quality.status_changed' for x in c.get('/api/audit').json())

def test_typed_custom_fields_and_persistence(setup):
    c,path,item,loc=setup
    field=post(c,'/api/custom-fields',{'field_key':'cost_center','label':'Cost center','field_type':'text'})
    assert c.post('/api/custom-fields',json={'field_key':'cost_center','label':'Duplicate'}).status_code==409
    assert c.put(f"/api/items/{item}/custom-fields/{field['id']}",json={'value':5}).status_code==422
    r=c.put(f"/api/items/{item}/custom-fields/{field['id']}",json={'value':'Plant A'})
    assert r.status_code==200 and r.json()['value']=='Plant A'
    assert c.get(f'/api/items/{item}/custom-fields').json()['values']['cost_center']=='Plant A'
    numeric=post(c,'/api/custom-fields',{'field_key':'reorder_point','label':'Reorder point','field_type':'number'})
    assert c.put(f"/api/items/{item}/custom-fields/{numeric['id']}",json={'value':'5'}).status_code==422
    assert c.put(f"/api/items/{item}/custom-fields/{numeric['id']}",json={'value':5}).status_code==200
    yesno=post(c,'/api/custom-fields',{'field_key':'controlled','label':'Controlled','field_type':'boolean'})
    assert c.put(f"/api/items/{item}/custom-fields/{yesno['id']}",json={'value':True}).status_code==200
    values=c.get(f'/api/items/{item}/custom-fields').json()['values']
    assert values=={'cost_center':'Plant A','reorder_point':5,'controlled':True}

def test_existing_v03_migration_keeps_inventory(tmp_path):
    from meridian.db import init_db
    p=tmp_path/'existing.db'
    init_db(p)
    with connect(p) as db:
        db.execute("INSERT INTO items(sku,name) VALUES ('OLD-01','Existing part')")
        db.commit()
    with TestClient(create_app(p)) as client:
        assert client.get('/api/items').json()[0]['sku']=='OLD-01'
        assert client.get('/api/suppliers').json()==[]
        assert client.get('/api/quality-cases').json()==[]
        assert client.get('/api/custom-fields').json()==[]
