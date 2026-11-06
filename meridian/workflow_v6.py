"""Opt-in manufacturing-to-finance workflow for fictional single-company demo data.

IMPORTANT: NOT a general ledger or real multi-tenant financial integration.
This module posts *illustrative standard-cost* entries only after the operator
explicitly configures one local finance company and mapped chart accounts.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI
from pydantic import BaseModel, Field, StringConstraints, model_validator
from .db import connect, db_write

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60, pattern=r'^[A-Za-z0-9._-]+$')]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

WORKFLOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS operational_accounting_config (
 id INTEGER PRIMARY KEY CHECK(id=1),
 company_id INTEGER NOT NULL REFERENCES erp_companies(id),
 raw_account_id INTEGER NOT NULL,
 grni_account_id INTEGER NOT NULL,
 wip_account_id INTEGER NOT NULL,
 finished_account_id INTEGER NOT NULL,
 FOREIGN KEY(company_id,raw_account_id) REFERENCES gl_accounts(company_id,id),
 FOREIGN KEY(company_id,grni_account_id) REFERENCES gl_accounts(company_id,id),
 FOREIGN KEY(company_id,wip_account_id) REFERENCES gl_accounts(company_id,id),
 FOREIGN KEY(company_id,finished_account_id) REFERENCES gl_accounts(company_id,id),
 CHECK(raw_account_id<>grni_account_id AND raw_account_id<>wip_account_id
   AND raw_account_id<>finished_account_id AND grni_account_id<>wip_account_id
   AND grni_account_id<>finished_account_id AND wip_account_id<>finished_account_id)
);
CREATE TABLE IF NOT EXISTS operational_finance_events (
 id INTEGER PRIMARY KEY,
 source_kind TEXT NOT NULL CHECK(source_kind IN ('po_receipt','material_issue','finished_receipt')),
 stock_ledger_id INTEGER NOT NULL UNIQUE REFERENCES stock_ledger(id),
 company_id INTEGER NOT NULL REFERENCES erp_companies(id),
 journal_id INTEGER NOT NULL UNIQUE REFERENCES journal_entries(id),
 value_cents INTEGER NOT NULL CHECK(value_cents>0),
 UNIQUE(source_kind,stock_ledger_id)
);
CREATE TABLE IF NOT EXISTS finished_good_receipts (
 id INTEGER PRIMARY KEY,
 work_order_id INTEGER NOT NULL UNIQUE REFERENCES work_orders(id),
 item_id INTEGER NOT NULL REFERENCES items(id),
 location_id INTEGER NOT NULL REFERENCES locations(id),
 stock_ledger_id INTEGER NOT NULL UNIQUE REFERENCES stock_ledger(id),
 command_id TEXT NOT NULL UNIQUE,
 quantity INTEGER NOT NULL CHECK(quantity>0),
 actor TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TRIGGER IF NOT EXISTS operational_events_no_update BEFORE UPDATE ON operational_finance_events
 BEGIN SELECT RAISE(ABORT,'operational finance events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS operational_events_no_delete BEFORE DELETE ON operational_finance_events
 BEGIN SELECT RAISE(ABORT,'operational finance events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS finished_receipts_no_update BEFORE UPDATE ON finished_good_receipts
 BEGIN SELECT RAISE(ABORT,'finished receipts are append-only'); END;
CREATE TRIGGER IF NOT EXISTS finished_receipts_no_delete BEFORE DELETE ON finished_good_receipts
 BEGIN SELECT RAISE(ABORT,'finished receipts are append-only'); END;
"""

class PostingConfig(BaseModel):
    company_id: int = Field(gt=0)
    raw_account_id: int = Field(gt=0)
    grni_account_id: int = Field(gt=0)
    wip_account_id: int = Field(gt=0)
    finished_account_id: int = Field(gt=0)

    @model_validator(mode='after')
    def distinct_accounts(self):
        values=[self.raw_account_id,self.grni_account_id,self.wip_account_id,self.finished_account_id]
        if len(set(values))!=4:raise ValueError('Four distinct accounts required')
        return self

class FinishedReceipt(BaseModel):
    item_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    command_id: Code
    actor: Name = 'demo.production'


def config(db: sqlite3.Connection):
    row=db.execute('SELECT * FROM operational_accounting_config WHERE id=1').fetchone()
    return dict(row) if row else None


def unit_cost(db: sqlite3.Connection, company: int, item: int) -> int:
    row=db.execute('SELECT cost_cents FROM item_standard_costs WHERE company_id=? AND item_id=?',
                   (company,item)).fetchone()
    if not row or row['cost_cents']<=0:
        from fastapi import HTTPException
        raise HTTPException(409,'Set a positive standard cost for this item before posting an integrated transaction')
    return row['cost_cents']


def post_event(db: sqlite3.Connection, *, kind: str, ledger_id: int, amount: int,
               debit_id: int, credit_id: int, actor: str, reference: str, memo: str, audit):
    if amount<=0:raise ValueError('Integrated journals require a positive amount')
    cfg=config(db)
    if cfg is None:return None
    # Source reference has a unique journal reference for idempotence; stock_ledger_id is unique too.
    ref=f'FLOW-{kind.upper()}-{ledger_id}'
    cur=db.execute('INSERT INTO journal_entries(company_id,reference,memo,actor) VALUES (?,?,?,?)',
                   (cfg['company_id'],ref,memo,actor))
    for account,debit,credit in ((debit_id,amount,0),(credit_id,0,amount)):
        db.execute('''INSERT INTO journal_lines(company_id,journal_id,account_id,debit_cents,credit_cents)
            VALUES (?,?,?,?,?)''',(cfg['company_id'],cur.lastrowid,account,debit,credit))
    db.execute('''INSERT INTO operational_finance_events(source_kind,stock_ledger_id,company_id,journal_id,value_cents)
         VALUES (?,?,?,?,?)''',(kind,ledger_id,cfg['company_id'],cur.lastrowid,amount))
    audit(db,'flow.journal_posted','journal_entry',cur.lastrowid,actor,
          {'source_kind':kind,'ledger_id':ledger_id,'amount_cents':amount,'reference':reference})
    return cur.lastrowid


def accounting_po_receipt(db, *, ledger_id: int, item_id: int, qty: int, actor: str, reference: str, audit):
    cfg=config(db)
    if cfg is None:return None
    amount=qty*unit_cost(db,cfg['company_id'],item_id)
    return post_event(db,kind='po_receipt',ledger_id=ledger_id,amount=amount,
                      debit_id=cfg['raw_account_id'],credit_id=cfg['grni_account_id'],
                      actor=actor,reference=reference,memo='Demo PO receipt at standard cost (no price variance)',audit=audit)


def accounting_material_issue(db, *, ledger_id: int, item_id: int, qty: int, actor: str, reference: str, audit):
    cfg=config(db)
    if cfg is None:return None
    amount=qty*unit_cost(db,cfg['company_id'],item_id)
    return post_event(db,kind='material_issue',ledger_id=ledger_id,amount=amount,
                      debit_id=cfg['wip_account_id'],credit_id=cfg['raw_account_id'],
                      actor=actor,reference=reference,memo='Demo materials issued to work in process',audit=audit)


def register_routes(app: FastAPI, path:Path, *, fail, audit, view_wo, stock_at, exists):
    @app.get('/api/finance/operational-config')
    def get_config():
        with connect(path) as db:
            cfg=config(db)
            return {'enabled':bool(cfg),'config':cfg,'warning':'Optional demo-only standard-cost postings. Global inventory is NOT company isolated.'}

    @app.post('/api/finance/operational-config')
    def enable_config(body:PostingConfig):
        with db_write(path) as db:
            if config(db):fail('Posting configuration already exists and is locked. Restore a clean demo to change it.',409)
            existing=db.execute('SELECT COUNT(*) AS n FROM operational_finance_events').fetchone()['n']
            if existing:fail('Cannot configure after operational postings',409)
            required={'raw_account_id':'asset','grni_account_id':'liability','wip_account_id':'asset','finished_account_id':'asset'}
            for field,category in required.items():
                row=db.execute('SELECT category FROM gl_accounts WHERE id=? AND company_id=?',
                               (getattr(body,field),body.company_id)).fetchone()
                if row is None or row['category']!=category:
                    fail(f'{field} must belong to the selected company and have category {category}',409)
            db.execute('''INSERT INTO operational_accounting_config
              (id,company_id,raw_account_id,grni_account_id,wip_account_id,finished_account_id)
              VALUES (1,?,?,?,?,?)''',(body.company_id,body.raw_account_id,body.grni_account_id,body.wip_account_id,body.finished_account_id))
            audit(db,'flow.accounting_enabled','erp_company',body.company_id,'demo.finance',body.model_dump())
            return {'enabled':True,'config':config(db)}

    @app.get('/api/finance/operational-events')
    def list_events(limit:int=100):
        with connect(path) as db:
            return [dict(x) for x in db.execute('''SELECT e.id,e.source_kind,e.stock_ledger_id,e.company_id,
                  e.journal_id,j.reference AS journal_reference,e.value_cents,j.created_at
                  FROM operational_finance_events e JOIN journal_entries j ON e.journal_id=j.id
                  ORDER BY e.id DESC LIMIT ?''',(min(200,max(1,limit)),))]

    @app.get('/api/flow/finished-receipts')
    def list_finished_receipts():
        with connect(path) as db:
            return [dict(x) for x in db.execute('''SELECT fg.*,w.number AS work_order,i.sku AS finished_sku,l.code AS location
                   FROM finished_good_receipts fg JOIN work_orders w ON w.id=fg.work_order_id
                   JOIN items i ON i.id=fg.item_id JOIN locations l ON l.id=fg.location_id
                   ORDER BY fg.id DESC''')]

    @app.get('/api/flow/work-orders/{wo_id}')
    def financial_trace(wo_id:int):
        with connect(path) as db:
            wo=view_wo(db,wo_id)
            issues=[dict(x) for x in db.execute('''SELECT s.id,s.item_id,s.quantity_delta,s.command_id,
                 f.journal_id,f.value_cents FROM stock_ledger s
                 LEFT JOIN operational_finance_events f ON f.stock_ledger_id=s.id
                 WHERE s.work_order_id=? AND s.entry_type='issue' ORDER BY s.id''',(wo_id,))]
            fg=db.execute('SELECT * FROM finished_good_receipts WHERE work_order_id=?',(wo_id,)).fetchone()
            return {'work_order':wo,'material_issues':issues,'finished_receipt':dict(fg) if fg else None,
                    'accounting_enabled':bool(config(db)),
                    'posted_material_cost_cents':sum(x['value_cents'] or 0 for x in issues)}

    @app.post('/api/work-orders/{wo_id}/receive-finished',status_code=201)
    def receive_finished(wo_id:int,body:FinishedReceipt):
        with db_write(path) as db:
            prior=db.execute('SELECT * FROM finished_good_receipts WHERE work_order_id=?',(wo_id,)).fetchone()
            if prior:
                if all((prior['item_id']==body.item_id,prior['location_id']==body.location_id,
                        prior['command_id']==body.command_id,prior['actor']==body.actor)):
                    return {'receipt_id':prior['id'],'ledger_id':prior['stock_ledger_id'],
                            'idempotent_replay':True,'quantity':prior['quantity']}
                fail('Finished goods already received for this work order',409)
            if db.execute('SELECT 1 FROM stock_ledger WHERE command_id=?',(body.command_id,)).fetchone():
                fail('Command ID already used for a different transaction',409)
            wo=view_wo(db,wo_id)
            if wo['status']!='completed':fail('Finish all materials and operations before receiving finished goods',409)
            linked=db.execute('''SELECT b.product_sku FROM work_order_boms wb JOIN boms b ON b.id=wb.bom_id
                                  WHERE wb.work_order_id=?''',(wo_id,)).fetchone()
            if not linked:fail('Finished goods receipt requires a work order created from an approved BOM',409)
            sku=db.execute('SELECT sku FROM items WHERE id=?',(body.item_id,)).fetchone()
            if not sku or sku['sku']!=linked['product_sku']:
                fail('Finished item SKU must match the approved BOM product SKU',409)
            if not exists(db,'locations',body.location_id):fail('Warehouse not found',404)
            blocked=db.execute('''SELECT COUNT(*) AS n FROM quality_cases WHERE work_order_id=?
                                 AND severity='high' AND status<>'resolved' ''',(wo_id,)).fetchone()['n']
            if blocked:fail('Open high-severity quality cases must be resolved before finished goods receipt',409)
            cfg=config(db)
            material_amount=None
            if cfg:
                issues=db.execute('''SELECT s.id,f.value_cents FROM stock_ledger s LEFT JOIN operational_finance_events f
                    ON f.stock_ledger_id=s.id AND f.source_kind='material_issue'
                    WHERE s.work_order_id=? AND s.entry_type='issue' ''',(wo_id,)).fetchall()
                if not issues or any(x['value_cents'] is None for x in issues):
                    fail('Cannot post finished goods with uncosted or legacy unposted material issues',409)
                material_amount=sum(x['value_cents'] for x in issues)
            ledger=db.execute('''INSERT INTO stock_ledger(item_id,location_id,quantity_delta,entry_type,reference,command_id,actor)
                                VALUES (?,?,?,'receipt',?,?,?)''',
                                (body.item_id,body.location_id,wo['quantity'],wo['number'],body.command_id,body.actor))
            new=db.execute('''INSERT INTO finished_good_receipts(work_order_id,item_id,location_id,stock_ledger_id,
                              command_id,quantity,actor) VALUES (?,?,?,?,?,?,?)''',
                              (wo_id,body.item_id,body.location_id,ledger.lastrowid,body.command_id,wo['quantity'],body.actor))
            posted=None
            if cfg:
                posted=post_event(db,kind='finished_receipt',ledger_id=ledger.lastrowid,amount=material_amount,
                                  debit_id=cfg['finished_account_id'],credit_id=cfg['wip_account_id'],
                                  actor=body.actor,reference=wo['number'],memo='Demo FG closeout: material costs only',audit=audit)
            audit(db,'finished_goods.received','work_order',wo_id,body.actor,
                  {'sku':sku['sku'],'quantity':wo['quantity'],'ledger_id':ledger.lastrowid,'journal_id':posted})
            return {'receipt_id':new.lastrowid,'ledger_id':ledger.lastrowid,'quantity':wo['quantity'],
                    'finished_sku':sku['sku'],'journal_id':posted,'idempotent_replay':False,
                    'on_hand':stock_at(db,body.item_id,body.location_id)}
