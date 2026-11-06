"""Manufacturing extension regression tests. All records are synthetic."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from meridian.api import create_app
from meridian.db import connect


@pytest.fixture
def system(tmp_path):
    path = tmp_path / 'v2.db'
    with TestClient(create_app(path)) as client:
        yield client, path


def post(c, url, data=None, status=200):
    r=c.post(url,json=data or {'actor':'demo.operator'})
    assert r.status_code==status, (url,r.status_code,r.text)
    return r.json()


def setup(c, qty=20):
    item=post(c,'/api/items',{'sku':'BOLT-001','name':'Fastener'},201)['id']
    loc=post(c,'/api/locations',{'code':'MAIN','name':'Main warehouse'},201)['id']
    post(c,'/api/stock/receive',{'item_id':item,'location_id':loc,'quantity':qty,
        'reference':'PO-1','command_id':'R-001'},201)
    return item,loc


def create_bom(c,item,rev='A',per=4):
    return post(c,'/api/boms',{'product_sku':'BOX-001','product_name':'Control Box','revision':rev,
          'components':[{'item_id':item,'per_unit':per}]},201)


def make_wo(c,item,number='WO-1',quantity=1,per=4):
    return post(c,'/api/work-orders',{'number':number,'product_name':'Control Box','quantity':quantity,
       'components':[{'item_id':item,'per_unit':per}]},201)


def issue(c,wo,item,loc,qty,cmd):
    return post(c,f'/api/work-orders/{wo}/issue',{
      'item_id':item,'location_id':loc,'quantity':qty,'reference':'PRODUCTION','command_id':cmd},201)


def test_active_bom_snapshot_and_superseding(system):
    c,_=system;item,loc=setup(c)
    b1=create_bom(c,item)
    assert b1['status']=='draft'
    assert c.post(f"/api/boms/{b1['id']}/work-orders",json={'number':'W-0','quantity':1}).status_code==409
    assert post(c,f"/api/boms/{b1['id']}/activate")['status']=='active'
    wo=post(c,f"/api/boms/{b1['id']}/work-orders",{'number':'W-1','quantity':2},201)
    assert wo['bom']['revision']=='A' and wo['components'][0]['required']==8
    b2=create_bom(c,item,rev='B',per=5)
    post(c,f"/api/boms/{b2['id']}/activate")
    assert c.get(f"/api/boms/{b1['id']}").json()['status']=='superseded'
    assert c.post(f"/api/boms/{b1['id']}/work-orders",json={'number':'W-2','quantity':1}).status_code==409
    assert c.get(f"/api/work-orders/{wo['id']}").json()['components'][0]['required']==8
    assert post(c,f"/api/boms/{b2['id']}/work-orders",{'number':'W-2','quantity':1},201)['components'][0]['required']==5


def test_activated_bom_lines_immutable(system):
    c,path=system;item,loc=setup(c)
    b=create_bom(c,item)
    post(c,f"/api/boms/{b['id']}/activate")
    db=connect(path)
    with pytest.raises(sqlite3.DatabaseError,match='immutable'):
        db.execute('UPDATE bom_lines SET per_unit=17 WHERE bom_id=?',(b['id'],))
    with pytest.raises(sqlite3.DatabaseError,match='immutable'):
        db.execute('DELETE FROM bom_lines WHERE bom_id=?',(b['id'],))
    db.close()


def test_reservation_protects_stock_from_another_order(system):
    c,_=system;item,loc=setup(c,qty=6)
    w1=make_wo(c,item,'WO-ONE',per=4)['id']
    w2=make_wo(c,item,'WO-TWO',per=4)['id']
    post(c,f'/api/work-orders/{w1}/release')
    post(c,f'/api/work-orders/{w1}/reserve')
    stock=c.get('/api/stock').json()[0]
    assert (stock['on_hand'],stock['reserved'],stock['available'])==(6,4,2)
    assert c.post(f'/api/work-orders/{w2}/release',json={'actor':'demo'}).status_code==409
    assert issue(c,w1,item,loc,4,'ISSUE-W1')['work_order']['status']=='materials_issued'
    stock=c.get('/api/stock').json()[0]
    assert (stock['on_hand'],stock['reserved'],stock['available'])==(2,0,2)


def test_reserved_stock_blocks_unreserved_issue(system):
    c,_=system;item,loc=setup(c,qty=10)
    w1=make_wo(c,item,'WO-ONE',per=7)['id'];w2=make_wo(c,item,'WO-TWO',per=6)['id']
    post(c,f'/api/work-orders/{w1}/release');post(c,f'/api/work-orders/{w2}/release')
    post(c,f'/api/work-orders/{w1}/reserve')
    bad=c.post(f'/api/work-orders/{w2}/issue',json={'item_id':item,'location_id':loc,'quantity':6,
       'reference':'DEMO','command_id':'I-W2'})
    assert bad.status_code==409 and 'unreserved' in bad.json()['detail']
    assert c.get('/api/stock').json()[0]['on_hand']==10


def test_failed_multicomponent_reservation_rolls_back(system):
    c,_=system;item,loc=setup(c,qty=10)
    extra=post(c,'/api/items',{'sku':'PANEL-1','name':'Panel'},201)['id']
    wo=post(c,'/api/work-orders',{'number':'WO-MULTI','product_name':'Box','quantity':1,
        'components':[{'item_id':item,'per_unit':3},{'item_id':extra,'per_unit':1}]},201)
    # Need sufficient stock to release; reserve after another order takes some.
    post(c,'/api/stock/receive',{'item_id':extra,'location_id':loc,'quantity':2,
       'reference':'PO-2','command_id':'R-002'},201)
    post(c,f"/api/work-orders/{wo['id']}/release")
    competitor=make_wo(c,extra,'WO-COMP',per=2)['id']
    post(c,f'/api/work-orders/{competitor}/release')
    post(c,f'/api/work-orders/{competitor}/reserve')
    assert c.post(f"/api/work-orders/{wo['id']}/reserve",json={'actor':'demo'}).status_code==409
    assert c.get(f'/api/work-orders/{wo["id"]}').json()['reservations']==[]
    assert c.get('/api/stock').json()[0]['reserved']==0  # no leaked BOLT allocations


def test_release_reserved_quantity_and_idempotency(system):
    c,_=system;item,loc=setup(c,qty=8)
    wo=make_wo(c,item,per=4)['id']
    post(c,f'/api/work-orders/{wo}/release')
    first=post(c,f'/api/work-orders/{wo}/reserve')
    second=post(c,f'/api/work-orders/{wo}/reserve')
    assert first['reservations'][0]['outstanding']==4 and second['reservations'][0]['outstanding']==4
    freed=post(c,f'/api/work-orders/{wo}/release-reservations')
    assert freed['released']==4 and c.get('/api/stock').json()[0]['available']==8
    assert post(c,f'/api/work-orders/{wo}/reserve')['reservations'][0]['outstanding']==4


def test_routing_blocks_out_of_order_start_and_job_completion(system):
    c,_=system;item,loc=setup(c,qty=10)
    wo=make_wo(c,item)['id']
    routing=post(c,f'/api/work-orders/{wo}/routing',{
      'operations':[{'sequence':20,'operation':'Wiring','work_center':'ELEC'},
                    {'sequence':10,'operation':'Assembly','work_center':'ASSY'}]},201)
    assert [x['sequence'] for x in routing['operations']]==[10,20]
    post(c,f'/api/work-orders/{wo}/release')
    issue(c,wo,item,loc,4,'I-1')
    assert c.post(f'/api/work-orders/{wo}/complete',json={'actor':'demo'}).status_code==409
    assert c.post(f'/api/work-orders/{wo}/operations/20/start',json={'actor':'demo'}).status_code==409
    post(c,f'/api/work-orders/{wo}/operations/10/start')
    assert c.post(f'/api/work-orders/{wo}/operations/20/start',json={'actor':'demo'}).status_code==409
    post(c,f'/api/work-orders/{wo}/operations/10/finish')
    post(c,f'/api/work-orders/{wo}/operations/20/start')
    post(c,f'/api/work-orders/{wo}/operations/20/finish')
    completed=post(c,f'/api/work-orders/{wo}/complete')
    assert completed['status']=='completed'
    assert all(x['status']=='done' for x in completed['operations'])


def test_routing_duplicate_sequence_and_status_guards(system):
    c,_=system;item,loc=setup(c)
    wo=make_wo(c,item)['id']
    bad=c.post(f'/api/work-orders/{wo}/routing',json={'operations':[
       {'sequence':10,'operation':'A','work_center':'A'},{'sequence':10,'operation':'B','work_center':'B'}]})
    assert bad.status_code==422
    post(c,f'/api/work-orders/{wo}/routing',{'operations':[{'sequence':10,'operation':'Assembly','work_center':'A'}]},201)
    assert c.post(f'/api/work-orders/{wo}/routing',json={'operations':[{'sequence':20,'operation':'QA','work_center':'Q'}]}).status_code==409
    assert c.post(f'/api/work-orders/{wo}/operations/10/start',json={'actor':'demo'}).status_code==409


def test_v1_database_migrates_without_deleting_ledger(system):
    c,path=system;item,loc=setup(c,qty=12)
    before=c.get('/api/ledger').json()
    from meridian.db import init_db
    init_db(path)
    assert c.get('/api/ledger').json()==before
    assert c.get('/api/boms').json()==[]


def test_upgrade_from_v1_database_retains_existing_transactions(tmp_path):
    from meridian.db import SCHEMA, connect, init_db
    path=tmp_path/'old-version.db'
    db=connect(path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO items(sku,name) VALUES ('OLD-1','Legacy sample')")
    db.execute("INSERT INTO locations(code,name) VALUES ('MAIN','Main warehouse')")
    db.execute("""INSERT INTO stock_ledger(item_id,location_id,quantity_delta,entry_type,reference,command_id,actor)
       VALUES (1,1,7,'receipt','OLD-RECEIPT','OLD-CMD','old.user')""")
    db.close()
    init_db(path)
    with TestClient(create_app(path)) as client:
        assert client.get('/api/stock').json()[0]['on_hand']==7
        assert client.get('/api/boms').json()==[]
        assert client.get('/api/ledger').json()[0]['command_id']=='OLD-CMD'


def test_concurrent_reservations_do_not_double_allocate(system):
    c,_=system;item,loc=setup(c,qty=8)
    wa=make_wo(c,item,'WO-A',per=6)['id']
    wb=make_wo(c,item,'WO-B',per=6)['id']
    for wo in [wa,wb]:post(c,f'/api/work-orders/{wo}/release')
    def reserve(wo):
        with TestClient(c.app) as other:
            return other.post(f'/api/work-orders/{wo}/reserve',json={'actor':'demo'}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses=list(executor.map(reserve,[wa,wb]))
    assert sorted(statuses)==[200,409]
    assert c.get('/api/stock').json()[0]['reserved']==6
    assert c.get('/api/stock').json()[0]['available']==2
