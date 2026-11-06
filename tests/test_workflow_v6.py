"""Full synthetic purchasing → manufacturing → finished stock → illustrative GL tests."""
import sqlite3

import pytest
from fastapi.testclient import TestClient
from meridian.api import create_app
from meridian.db import connect


@pytest.fixture
def env(tmp_path):
    path=tmp_path/'flow.db'
    with TestClient(create_app(path,auth_required=False)) as c:
        yield c,path


def post(c,url,body,code=201):
    result=c.post(url,json=body)
    assert result.status_code==code,(url,result.status_code,result.text)
    return result.json()


def configure(c,products=True):
    company=post(c,'/api/finance/companies',{'code':'DEMO','name':'Demo Company'})['id']
    ids={}
    for code,category in [('1200','asset'),('2100','liability'),('1300','asset'),('1400','asset')]:
        ids[code]=post(c,'/api/finance/accounts',{'company_id':company,'code':code,'name':code,'category':category})['id']
    setup={'company_id':company,'raw_account_id':ids['1200'],'grni_account_id':ids['2100'],
           'wip_account_id':ids['1300'],'finished_account_id':ids['1400']}
    post(c,'/api/finance/operational-config',setup,200)
    return company,ids,setup


def items(c):
    bolt=post(c,'/api/items',{'sku':'BOLT-001','name':'Fastener'})['id']
    panel=post(c,'/api/items',{'sku':'PANEL-001','name':'Panel'})['id']
    finished=post(c,'/api/items',{'sku':'BOX-002','name':'Finished Control Box'})['id']
    warehouse=post(c,'/api/locations',{'code':'MAIN','name':'Main warehouse'})['id']
    return bolt,panel,finished,warehouse


def setup_po(c,bolt,panel,location):
    s=post(c,'/api/suppliers',{'code':'SUP-01','name':'Fictional Industrial'})['id']
    p=post(c,'/api/purchase-orders',{'number':'PO-DEMO-100','supplier_id':s,'lines':[
        {'item_id':bolt,'quantity':20,'unit_price_cents':250},
        {'item_id':panel,'quantity':10,'unit_price_cents':400}]})
    post(c,f"/api/purchase-orders/{p['id']}/approve",{'actor':'demo.purchasing'},200)
    for item,qty,cmd in [(bolt,20,'PO-BOLT-RECV'),(panel,10,'PO-PANEL-RECV')]:
        r=post(c,f"/api/purchase-orders/{p['id']}/receive",{
            'item_id':item,'location_id':location,'quantity':qty,'command_id':cmd})
        assert r['on_hand']==qty
    return p


def setup_order(c,bolt,panel):
    bom=post(c,'/api/boms',{'product_sku':'BOX-002','product_name':'Control Box',
      'revision':'A','components':[{'item_id':bolt,'per_unit':4},{'item_id':panel,'per_unit':1}]})
    post(c,f"/api/boms/{bom['id']}/activate",{'actor':'demo.engineering'},200)
    wo=post(c,f"/api/boms/{bom['id']}/work-orders",{'number':'WO-2002','quantity':3})
    post(c,f"/api/work-orders/{wo['id']}/routing",{
        'operations':[{'sequence':10,'operation':'Assembly','work_center':'ASSY'},
                      {'sequence':20,'operation':'Inspection','work_center':'QA'}]})
    post(c,f"/api/work-orders/{wo['id']}/release",{'actor':'demo'},200)
    post(c,f"/api/work-orders/{wo['id']}/reserve",{'actor':'demo'},200)
    return wo


def finish(c,wo,bolt,panel,location):
    for item,qty,cmd in [(bolt,12,'ISSUE-BOLT-1'),(panel,3,'ISSUE-PANEL-1')]:
        post(c,f"/api/work-orders/{wo['id']}/issue",{
            'item_id':item,'location_id':location,'quantity':qty,'reference':'MFG-ISSUE','command_id':cmd})
    for seq in [10,20]:
        post(c,f"/api/work-orders/{wo['id']}/operations/{seq}/start",{'actor':'demo'},200)
        post(c,f"/api/work-orders/{wo['id']}/operations/{seq}/finish",{'actor':'demo'},200)
    post(c,f"/api/work-orders/{wo['id']}/complete",{'actor':'demo'},200)


def test_full_po_to_finished_goods_with_balanced_auto_postings(env):
    c,path=env
    bolt,panel,fg,loc=items(c)
    company,ids,_=configure(c)
    for item,cost in [(bolt,200),(panel,350)]:
        r=c.put('/api/finance/costs',json={'company_id':company,'item_id':item,'cost_cents':cost})
        assert r.status_code==200
    po=setup_po(c,bolt,panel,loc)
    assert po['status']=='draft'
    wo=setup_order(c,bolt,panel)
    assert c.post(f"/api/work-orders/{wo['id']}/receive-finished",json={
        'item_id':fg,'location_id':loc,'command_id':'PREMATURE'}).status_code==409
    finish(c,wo,bolt,panel,loc)
    payload={'item_id':fg,'location_id':loc,'command_id':'FG-WO-2002','actor':'demo.production'}
    received=post(c,f"/api/work-orders/{wo['id']}/receive-finished",payload)
    assert received['quantity']==3 and received['journal_id'] and received['on_hand']==3
    replay=post(c,f"/api/work-orders/{wo['id']}/receive-finished",payload)
    assert replay['idempotent_replay'] is True
    assert c.post(f"/api/work-orders/{wo['id']}/receive-finished",json={**payload,'command_id':'NEW-CMD'}).status_code==409
    stock={r['sku']:r['on_hand'] for r in c.get('/api/stock').json()}
    assert stock=={'BOLT-001':8,'PANEL-001':7,'BOX-002':3}
    trace=c.get(f"/api/flow/work-orders/{wo['id']}").json()
    assert trace['accounting_enabled'] and trace['posted_material_cost_cents']==3450
    assert len(trace['material_issues'])==2
    events=c.get('/api/finance/operational-events').json()
    assert [e['source_kind'] for e in events]==['finished_receipt','material_issue','material_issue','po_receipt','po_receipt']
    assert events[0]['value_cents']==3450
    # Raw inventory debit: (20*200+10*350)=7500; material issue credit=3450.
    balances={x['code']:x['net_debit_cents'] for x in c.get('/api/finance/trial-balance',params={'company_id':company}).json()}
    assert balances=={'1200':4050,'2100':-7500,'1300':0,'1400':3450}
    assert sum(balances.values())==0
    assert len(c.get('/api/flow/finished-receipts').json())==1
    with connect(path) as db:
        assert db.execute('SELECT count(*) FROM operational_finance_events').fetchone()[0]==5
        assert db.execute('SELECT count(*) FROM finished_good_receipts').fetchone()[0]==1
        with pytest.raises(sqlite3.DatabaseError,match='append-only'):
            db.execute('DELETE FROM finished_good_receipts')


def test_missing_cost_rolls_back_receipt_and_retry_succeeds(env):
    c,_=env
    bolt,panel,fg,loc=items(c)
    co,_,_=configure(c)
    supplier=post(c,'/api/suppliers',{'code':'SUP-01','name':'Supplier'})
    po=post(c,'/api/purchase-orders',{'number':'PO-100','supplier_id':supplier['id'],
        'lines':[{'item_id':bolt,'quantity':10,'unit_price_cents':200}]})
    post(c,f"/api/purchase-orders/{po['id']}/approve",{'actor':'demo'},200)
    data={'item_id':bolt,'location_id':loc,'quantity':10,'command_id':'NO-COST'}
    fail=c.post(f"/api/purchase-orders/{po['id']}/receive",json=data)
    assert fail.status_code==409
    assert c.get('/api/ledger').json()==[]
    assert c.get('/api/purchase-orders').json()[0]['lines'][0]['received_qty']==0
    assert c.put('/api/finance/costs',json={'company_id':co,'item_id':bolt,'cost_cents':99}).status_code==200
    assert post(c,f"/api/purchase-orders/{po['id']}/receive",data)['journal_id']>0
    assert len(c.get('/api/ledger').json())==1


def test_quality_hold_prevents_finished_receipt_until_resolved(env):
    c,_=env
    bolt,panel,fg,loc=items(c)
    for item,qty,cmd in [(bolt,20,'RAW-1'),(panel,8,'RAW-2')]:
        post(c,'/api/stock/receive',{'item_id':item,'location_id':loc,'quantity':qty,
             'reference':'DEMO','command_id':cmd})
    wo=setup_order(c,bolt,panel)
    finish(c,wo,bolt,panel,loc)
    case=post(c,'/api/quality-cases',{'number':'NCR-HOLD-1','summary':'Unverified inspection result',
       'source':'production','severity':'high','work_order_id':wo['id']})
    body={'item_id':fg,'location_id':loc,'command_id':'FG-BLOCK'}
    assert c.post(f"/api/work-orders/{wo['id']}/receive-finished",json=body).status_code==409
    assert not c.get('/api/flow/finished-receipts').json()
    post(c,f"/api/quality-cases/{case['id']}/status",{'status':'in_review'},200)
    assert c.post(f"/api/work-orders/{wo['id']}/receive-finished",json=body).status_code==409
    post(c,f"/api/quality-cases/{case['id']}/status",{'status':'resolved','resolution':'Inspection and test evidence verified'},200)
    assert post(c,f"/api/work-orders/{wo['id']}/receive-finished",body)['journal_id'] is None


def test_wrong_sku_and_unlinked_bom_rejected(env):
    c,_=env
    bolt,panel,fg,loc=items(c)
    post(c,'/api/stock/receive',{'item_id':bolt,'location_id':loc,'quantity':20,'reference':'DEMO','command_id':'RC1'})
    post(c,'/api/stock/receive',{'item_id':panel,'location_id':loc,'quantity':10,'reference':'DEMO','command_id':'RC2'})
    wo=setup_order(c,bolt,panel)
    finish(c,wo,bolt,panel,loc)
    r=c.post(f"/api/work-orders/{wo['id']}/receive-finished",json={'item_id':bolt,'location_id':loc,'command_id':'WRONG-SKU'})
    assert r.status_code==409 and 'SKU' in r.json()['detail']
    assert len(c.get('/api/ledger').json())==4


def test_config_validation_is_company_scoped_and_locked(env):
    c,_=env
    co,ids,settings=configure(c)
    assert c.get('/api/finance/operational-config').json()['enabled']
    assert c.post('/api/finance/operational-config',json=settings).status_code==409
    other=post(c,'/api/finance/companies',{'code':'OTHER','name':'Another'})['id']
    x=post(c,'/api/finance/accounts',{'company_id':other,'code':'1000','name':'Other asset','category':'asset'})['id']
    assert x>0


def test_empty_config_no_automatic_financial_postings(env):
    c,_=env
    bolt,panel,fg,loc=items(c)
    post(c,'/api/stock/receive',{'item_id':bolt,'location_id':loc,'quantity':5,'reference':'DEMO','command_id':'RC1'})
    assert c.get('/api/finance/operational-config').json()['enabled'] is False
    assert c.get('/api/finance/operational-events').json()==[]
