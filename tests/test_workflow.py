import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meridian.api import create_app
from meridian.db import connect

@pytest.fixture
def env(tmp_path):
    path = tmp_path / "test.db"
    with TestClient(create_app(path)) as client:
        yield client, path


def post(client, path, data, status=201):
    r = client.post(path, json=data)
    assert r.status_code == status, r.text
    return r.json()


def setup_env(client):
    item = post(client, "/api/items", {"sku":"BOLT-100","name":"Fastener"})
    loc = post(client, "/api/locations", {"code":"MAIN","name":"Warehouse"})
    return item["id"], loc["id"]


def receipt(item_id, loc_id, qty, cmd='cmd-00001'):
    return {"item_id":item_id,"location_id":loc_id,"quantity":qty,"reference":"PO-DEMO-1","command_id":cmd}


def issue(item_id,loc_id,qty,cmd='cmd-issue-1'):
    return {"item_id":item_id,"location_id":loc_id,"quantity":qty,"reference":"JOB-ISSUE","command_id":cmd}


def make_order(client, item, qty=2, per=3, number='WO-1001'):
    return post(client, "/api/work-orders", {"number":number,"product_name":"Frame","quantity":qty,
        "components":[{"item_id":item,"per_unit":per}]})


def stock(client):
    return client.get('/api/stock').json()[0]['on_hand']


def test_complete_receipt_to_workorder(env):
    client,_ = env
    item,loc=setup_env(client)
    received=post(client,'/api/stock/receive',receipt(item,loc,15))
    assert received['on_hand']==15
    wo=make_order(client,item)
    assert wo['status']=='planned' and wo['components'][0]['required']==6
    released=post(client,f"/api/work-orders/{wo['id']}/release",{'actor':'demo.supervisor'},200)
    assert released['status']=='released'
    first=post(client,f"/api/work-orders/{wo['id']}/issue",issue(item,loc,2),201)
    assert first['on_hand']==13
    second=post(client,f"/api/work-orders/{wo['id']}/issue",issue(item,loc,4,'cmd-issue-2'))
    assert second['work_order']['status']=='materials_issued'
    complete=post(client,f"/api/work-orders/{wo['id']}/complete",{'actor':'demo.supervisor'},200)
    assert complete['status']=='completed' and stock(client)==9
    ledger=client.get('/api/ledger').json()
    assert [x['quantity_delta'] for x in ledger]==[-4,-2,15]
    logs=client.get('/api/audit').json()
    assert any(x['event_type']=='work_order.completed' for x in logs)
    assert any(x['event_type']=='stock.issued' for x in logs)


def test_shortage_blocks_release_without_side_effect(env):
    client,_=env
    item,loc=setup_env(client)
    wo=make_order(client,item,qty=2,per=5)
    r=client.post(f"/api/work-orders/{wo['id']}/release",json={"actor":"demo"})
    assert r.status_code==409 and 'shortage' in r.json()['detail']
    assert client.get(f"/api/work-orders/{wo['id']}").json()['status']=='planned'
    assert stock(client)==0


def test_out_of_stock_at_selected_location_is_rejected(env):
    client,_=env
    item,loc=setup_env(client)
    second=post(client,'/api/locations',{"code":"SECOND","name":"Other"})['id']
    post(client,'/api/stock/receive',receipt(item,loc,8))
    wo=make_order(client,item)
    post(client,f"/api/work-orders/{wo['id']}/release",{'actor':'demo'},200)
    r=client.post(f"/api/work-orders/{wo['id']}/issue",json=issue(item,second,2))
    assert r.status_code==409
    assert client.get(f"/api/work-orders/{wo['id']}").json()['components'][0]['issued']==0
    assert stock(client)==8


def test_over_issue_rejected_and_atomic(env):
    client,_=env
    item,loc=setup_env(client)
    post(client,'/api/stock/receive',receipt(item,loc,12))
    wo=make_order(client,item,per=2)
    post(client,f"/api/work-orders/{wo['id']}/release",{'actor':'demo'},200)
    r=client.post(f"/api/work-orders/{wo['id']}/issue",json=issue(item,loc,5))
    assert r.status_code==409
    assert stock(client)==12
    assert client.get(f"/api/work-orders/{wo['id']}").json()['components'][0]['issued']==0


def test_idempotent_receipt_and_conflicting_reuse(env):
    client,_=env
    item,loc=setup_env(client)
    base=receipt(item,loc,9)
    a=post(client,'/api/stock/receive',base)
    b=post(client,'/api/stock/receive',base)
    assert a['idempotent_replay'] is False and b['idempotent_replay'] is True
    assert a['ledger_id']==b['ledger_id'] and stock(client)==9
    altered=dict(base,quantity=10)
    assert client.post('/api/stock/receive',json=altered).status_code==409
    assert stock(client)==9


def test_idempotent_issue_does_not_double_count(env):
    client,_=env
    item,loc=setup_env(client)
    post(client,'/api/stock/receive',receipt(item,loc,6))
    wo=make_order(client,item,per=3,qty=1)
    post(client,f"/api/work-orders/{wo['id']}/release",{'actor':'demo'},200)
    body=issue(item,loc,3)
    first=post(client,f"/api/work-orders/{wo['id']}/issue",body)
    repeat=post(client,f"/api/work-orders/{wo['id']}/issue",body)
    assert repeat['idempotent_replay'] is True and repeat['ledger_id']==first['ledger_id']
    assert stock(client)==3
    assert client.get(f"/api/work-orders/{wo['id']}").json()['components'][0]['issued']==3


def test_invalid_requests_and_fk_checks(env):
    client,_=env
    item,loc=setup_env(client)
    assert client.post('/api/items',json={'sku':'BOLT-100','name':'Duplicate'}).status_code==409
    assert client.post('/api/stock/receive',json=receipt(999,loc,4)).status_code==404
    assert client.post('/api/stock/receive',json=receipt(item,loc,-2)).status_code==422
    assert client.post('/api/work-orders',json={'number':'WO-A','product_name':'A','quantity':1,'components':[{'item_id':item,'per_unit':1},{'item_id':item,'per_unit':2}]}).status_code==422
    assert stock(client)==0


def test_append_only_triggers(env):
    client,path=env
    item,loc=setup_env(client)
    posted=post(client,'/api/stock/receive',receipt(item,loc,5))
    conn=connect(path)
    with pytest.raises(sqlite3.DatabaseError,match='append-only'):
        conn.execute('UPDATE stock_ledger SET quantity_delta=100 WHERE id=?',(posted['ledger_id'],))
    with pytest.raises(sqlite3.DatabaseError,match='append-only'):
        conn.execute('DELETE FROM stock_ledger WHERE id=?',(posted['ledger_id'],))
    with pytest.raises(sqlite3.DatabaseError,match='append-only'):
        conn.execute('DELETE FROM audit_log')
    conn.close()
    assert stock(client)==5


def test_concurrent_issues_do_not_spend_same_stock(env):
    client,_=env
    item,loc=setup_env(client)
    post(client,'/api/stock/receive',receipt(item,loc,5))
    w1=make_order(client,item,qty=1,per=4,number='WO-ONE')
    w2=make_order(client,item,qty=1,per=4,number='WO-TWO')
    for wo in (w1,w2):
        post(client,f"/api/work-orders/{wo['id']}/release",{'actor':'demo'},200)
    def do_issue(wo,cmd):
        with TestClient(client.app) as c:
            r=c.post(f"/api/work-orders/{wo['id']}/issue",json=issue(item,loc,4,cmd))
            return r.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(lambda x:do_issue(*x),[(w1,'cmd-con-1'),(w2,'cmd-con-2')]))
    assert sorted(codes)==[201,409]
    assert stock(client)==1


def test_server_health_and_html(env):
    client,_=env
    assert client.get('/api/health').json()['production_ready'] is False
    assert client.get('/').status_code==200
    assert 'MERIDIAN ERP' in client.get('/').text
