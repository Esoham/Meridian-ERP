"""Company-specific journal, balanced entries, preview-only imports and backup tests."""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meridian.api import create_app
from meridian.db import connect
from scripts.backup_db import backup_database,restore_database,valid_sqlite

@pytest.fixture
def env(tmp_path):
    db=tmp_path/'meridian.db'
    with TestClient(create_app(db,auth_required=False)) as c:yield c,db

def company(c,code):
    r=c.post('/api/finance/companies',json={'code':code,'name':'Company '+code});assert r.status_code==201,r.text;return r.json()['id']

def account(c,co,code,category='asset'):
    r=c.post('/api/finance/accounts',json={'company_id':co,'code':code,'name':code+' account','category':category});assert r.status_code==201,r.text;return r.json()['id']

def test_balanced_journal_posting_and_trial_balance(env):
    c,db=env;co=company(c,'CO-1');cash=account(c,co,'1000');eq=account(c,co,'3000','equity')
    r=c.post('/api/finance/journals',json={'company_id':co,'reference':'JE-001','memo':'Opening demonstration',
        'lines':[{'account_id':cash,'debit_cents':12000},{'account_id':eq,'credit_cents':12000}]})
    assert r.status_code==201,r.text
    assert r.json()['total_debit_cents']==12000
    bal=c.get('/api/finance/trial-balance',params={'company_id':co}).json()
    assert {x['code']:x['net_debit_cents'] for x in bal}=={'1000':12000,'3000':-12000}
    assert len(c.get('/api/finance/journals',params={'company_id':co}).json())==1
    with connect(db) as sql:
        with pytest.raises(sqlite3.DatabaseError,match='immutable'):sql.execute('DELETE FROM journal_lines')

def test_unbalanced_and_duplicate_journals_rejected(env):
    c,_=env;co=company(c,'CO-1');a=account(c,co,'1000');b=account(c,co,'2000','liability')
    body={'company_id':co,'reference':'JE-001','memo':'Demo',
        'lines':[{'account_id':a,'debit_cents':1000},{'account_id':b,'credit_cents':900}]}
    assert c.post('/api/finance/journals',json=body).status_code==422
    body['lines'][1]['credit_cents']=1000
    assert c.post('/api/finance/journals',json=body).status_code==201
    assert c.post('/api/finance/journals',json=body).status_code==409
    assert c.post('/api/finance/journals',json={**body,'reference':'JE-002','lines':[{'account_id':a,'debit_cents':1000,'credit_cents':1000},body['lines'][1]]}).status_code==422

def test_company_account_scope_enforced(env):
    c,_=env;co1=company(c,'CO-1');co2=company(c,'CO-2');a=account(c,co1,'1000');b=account(c,co2,'2000')
    r=c.post('/api/finance/journals',json={'company_id':co1,'reference':'JE-001','memo':'Mixed company not allowed',
        'lines':[{'account_id':a,'debit_cents':500},{'account_id':b,'credit_cents':500}]})
    assert r.status_code==409
    assert c.get('/api/finance/journals',params={'company_id':co1}).json()==[]
    assert c.get('/api/finance/journals',params={'company_id':co2}).json()==[]
    assert c.get('/api/finance/accounts',params={'company_id':co2}).json()[0]['code']=='2000'

def test_informational_stock_costing(env):
    c,_=env;co=company(c,'CO-1')
    item=c.post('/api/items',json={'sku':'BOLT-200','name':'Fastener'}).json()['id']
    loc=c.post('/api/locations',json={'code':'MAIN','name':'Warehouse'}).json()['id']
    r=c.post('/api/stock/receive',json={'item_id':item,'location_id':loc,'quantity':12,'reference':'DEMO','command_id':'RCPT-1'})
    assert r.status_code==201
    r=c.put('/api/finance/costs',json={'company_id':co,'item_id':item,'cost_cents':225})
    assert r.status_code==200,r.text
    v=c.get('/api/finance/valuation',params={'company_id':co}).json()
    assert v['informational_only'] and v['total_cents']==2700
    assert 'not segregated' in v['warning']

def test_stock_csv_preview_is_read_only(env):
    c,_=env
    c.post('/api/items',json={'sku':'BOLT-200','name':'Fastener'})
    c.post('/api/locations',json={'code':'MAIN','name':'Warehouse'})
    csv='sku,location,quantity,reference\nBOLT-200,MAIN,5,SAMPLE\nMISSING,MAIN,2,SAMPLE2'
    result=c.post('/api/integrations/stock-import/preview',json={'csv_text':csv})
    assert result.status_code==200,result.text
    assert result.json()['valid_count']==1 and result.json()['posted']==0
    assert len(c.get('/api/ledger').json())==0
    bad=c.post('/api/integrations/stock-import/preview',json={'csv_text':'sku,location,quantity,reference\nBOLT-200,MAIN,-5,BAD'})
    assert bad.status_code==422
    bad=c.post('/api/integrations/stock-import/preview',json={'csv_text':'sku,location,quantity,reference\nBOLT-200,MAIN,5,OK,EXTRA'})
    assert bad.status_code==422

def test_backup_and_guarded_restore(env,tmp_path):
    c,db=env
    c.post('/api/items',json={'sku':'BOLT-200','name':'Fastener'})
    backup=backup_database(db,tmp_path/'backups')
    assert backup.is_file() and valid_sqlite(backup)
    assert json.loads(backup.with_suffix('.sha256.json').read_text())['sha256']
    dest=tmp_path/'restored.db'
    with pytest.raises(ValueError,match='confirm'):restore_database(backup,dest)
    with pytest.raises(ValueError,match='exists'):restore_database(backup,db,confirm=True)
    restore_database(backup,dest,confirm=True)
    with sqlite3.connect(dest) as sql:assert sql.execute('SELECT count(*) FROM items').fetchone()[0]==1
    with pytest.raises(ValueError,match='exists'):restore_database(backup,dest,confirm=True)
    backup.with_suffix('.sha256.json').write_text('{"sha256":"wrong","type":"MeridianLocalSQLiteBackup"}')
    with pytest.raises(ValueError,match='checksum'):restore_database(backup,tmp_path/'other.db',confirm=True)
