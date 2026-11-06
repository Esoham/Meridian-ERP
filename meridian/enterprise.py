"""Additional local ERP workflows: purchasing, quality, item extension fields.

This is a single-user demonstration, not an accounting or production security system.
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field, StringConstraints, model_validator

from .db import connect, db_write

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]

EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 email TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS purchase_orders (
 id INTEGER PRIMARY KEY, number TEXT NOT NULL UNIQUE,
 supplier_id INTEGER NOT NULL REFERENCES suppliers(id), status TEXT NOT NULL DEFAULT 'draft'
 CHECK(status IN ('draft','approved','partial','received')),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS purchase_order_lines (
 id INTEGER PRIMARY KEY, po_id INTEGER NOT NULL REFERENCES purchase_orders(id),
 item_id INTEGER NOT NULL REFERENCES items(id), ordered_qty INTEGER NOT NULL CHECK (ordered_qty > 0),
 received_qty INTEGER NOT NULL DEFAULT 0 CHECK(received_qty >= 0 AND received_qty <= ordered_qty),
 unit_price_cents INTEGER NOT NULL DEFAULT 0 CHECK(unit_price_cents >= 0),
 UNIQUE(po_id,item_id)
);
CREATE TABLE IF NOT EXISTS purchase_receipts (
 id INTEGER PRIMARY KEY, po_id INTEGER NOT NULL REFERENCES purchase_orders(id),
 po_line_id INTEGER NOT NULL REFERENCES purchase_order_lines(id),
 stock_ledger_id INTEGER NOT NULL UNIQUE REFERENCES stock_ledger(id),
 quantity INTEGER NOT NULL CHECK(quantity > 0)
);
CREATE TABLE IF NOT EXISTS quality_cases (
 id INTEGER PRIMARY KEY, number TEXT NOT NULL UNIQUE, summary TEXT NOT NULL,
 source TEXT NOT NULL CHECK(source IN ('incoming','production','inventory')),
 severity TEXT NOT NULL CHECK(severity IN ('low','medium','high')),
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','in_review','resolved')),
 item_id INTEGER REFERENCES items(id), work_order_id INTEGER REFERENCES work_orders(id),
 resolution TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS item_field_definitions (
 id INTEGER PRIMARY KEY, field_key TEXT NOT NULL UNIQUE, label TEXT NOT NULL,
 field_type TEXT NOT NULL CHECK(field_type IN ('text','number','boolean'))
);
CREATE TABLE IF NOT EXISTS item_field_values (
 item_id INTEGER NOT NULL REFERENCES items(id), field_id INTEGER NOT NULL REFERENCES item_field_definitions(id),
 value_json TEXT NOT NULL, PRIMARY KEY(item_id,field_id)
);
CREATE INDEX IF NOT EXISTS idx_po_supplier ON purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS idx_q_status ON quality_cases(status);
"""

class SupplierIn(BaseModel):
    code: Code
    name: Text
    email: str = Field(default='', max_length=180)

class POLine(BaseModel):
    item_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000000)
    unit_price_cents: int = Field(ge=0, le=100000000)

class POIn(BaseModel):
    number: Code
    supplier_id: int = Field(gt=0)
    lines: list[POLine] = Field(min_length=1, max_length=100)
    actor: Text = 'demo.purchasing'

    @model_validator(mode='after')
    def unique_lines(self):
        if len({x.item_id for x in self.lines}) != len(self.lines):
            raise ValueError('Each item can appear only once on this purchase order')
        return self

class Approval(BaseModel):
    actor: Text = 'demo.purchasing'

class POReceiptIn(BaseModel):
    item_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000000)
    command_id: Code
    actor: Text = 'demo.receiving'

class QualityIn(BaseModel):
    number: Code
    summary: Description
    source: Literal['incoming','production','inventory']
    severity: Literal['low','medium','high'] = 'medium'
    item_id: int | None = Field(default=None, gt=0)
    work_order_id: int | None = Field(default=None, gt=0)
    actor: Text = 'demo.quality'

class QualityStatus(BaseModel):
    status: Literal['in_review','resolved']
    resolution: str = Field(default='', max_length=2000)
    actor: Text = 'demo.quality'

class FieldIn(BaseModel):
    field_key: Code
    label: Text
    field_type: Literal['text','number','boolean'] = 'text'

class ValueIn(BaseModel):
    value: str | int | float | bool
    actor: Text = 'demo.admin'


def register_routes(app: FastAPI, path: Path, *, audit, fail, exists, stock_at):
    def po_view(db: sqlite3.Connection, po_id: int):
        p = db.execute('''SELECT po.*,s.code AS supplier_code,s.name AS supplier_name
          FROM purchase_orders po JOIN suppliers s ON po.supplier_id=s.id WHERE po.id=?''',(po_id,)).fetchone()
        if not p: fail('Purchase order not found',404)
        lines = [dict(x) for x in db.execute('''SELECT pl.id,pl.item_id,i.sku,i.name,pl.ordered_qty,pl.received_qty,
          (pl.ordered_qty-pl.received_qty) AS remaining,pl.unit_price_cents
          FROM purchase_order_lines pl JOIN items i ON pl.item_id=i.id WHERE po_id=? ORDER BY pl.id''',(po_id,))]
        return {**dict(p),'lines':lines,'total_cents':sum(x['ordered_qty']*x['unit_price_cents'] for x in lines)}

    @app.get('/api/suppliers')
    def list_suppliers():
        with connect(path) as db:
            return [dict(x) for x in db.execute('SELECT * FROM suppliers ORDER BY code')]

    @app.post('/api/suppliers',status_code=201)
    def add_supplier(body:SupplierIn):
        with db_write(path) as db:
            if db.execute('SELECT 1 FROM suppliers WHERE code=?',(body.code.upper(),)).fetchone():fail('Supplier code already exists',409)
            cur=db.execute('INSERT INTO suppliers(code,name,email) VALUES (?,?,?)',(body.code.upper(),body.name,body.email))
            audit(db,'supplier.created','supplier',cur.lastrowid,'demo.purchasing',{'code':body.code.upper()})
            return {'id':cur.lastrowid,'code':body.code.upper(),'name':body.name,'email':body.email}

    @app.get('/api/purchase-orders')
    def list_pos():
        with connect(path) as db:
            return [po_view(db,r['id']) for r in db.execute('SELECT id FROM purchase_orders ORDER BY id DESC').fetchall()]

    @app.post('/api/purchase-orders',status_code=201)
    def add_po(body:POIn):
        with db_write(path) as db:
            if not exists(db,'suppliers',body.supplier_id):fail('Supplier not found',404)
            if db.execute('SELECT 1 FROM purchase_orders WHERE number=?',(body.number.upper(),)).fetchone():fail('Purchase order number exists',409)
            for line in body.lines:
                if not exists(db,'items',line.item_id):fail(f'Item {line.item_id} not found',404)
            cur=db.execute('INSERT INTO purchase_orders(number,supplier_id) VALUES (?,?)',(body.number.upper(),body.supplier_id))
            for line in body.lines:
                db.execute('INSERT INTO purchase_order_lines(po_id,item_id,ordered_qty,unit_price_cents) VALUES (?,?,?,?)',
                    (cur.lastrowid,line.item_id,line.quantity,line.unit_price_cents))
            audit(db,'po.created','purchase_order',cur.lastrowid,body.actor,{'number':body.number.upper(),'lines':len(body.lines)})
            return po_view(db,cur.lastrowid)

    @app.post('/api/purchase-orders/{po_id}/approve')
    def approve_po(po_id:int,body:Approval):
        with db_write(path) as db:
            po=po_view(db,po_id)
            if po['status']!='draft':fail('Only draft purchase orders can be approved',409)
            db.execute("UPDATE purchase_orders SET status='approved' WHERE id=?",(po_id,))
            audit(db,'po.approved','purchase_order',po_id,body.actor,{'number':po['number']})
            return po_view(db,po_id)

    @app.post('/api/purchase-orders/{po_id}/receive',status_code=201)
    def receive_po(po_id:int,body:POReceiptIn):
        with db_write(path) as db:
            # Check replay before status check: receiving the final quantity closes the PO.
            prior=db.execute('''SELECT s.*,pr.po_id FROM stock_ledger s JOIN purchase_receipts pr
                 ON pr.stock_ledger_id=s.id WHERE s.command_id=?''',(body.command_id,)).fetchone()
            if prior:
                if all((prior['po_id']==po_id,prior['item_id']==body.item_id,
                    prior['location_id']==body.location_id,prior['quantity_delta']==body.quantity,
                    prior['actor']==body.actor)):
                    return {'ledger_id':prior['id'],'idempotent_replay':True,'purchase_order':po_view(db,po_id)}
                fail('Command ID already used for a different receipt',409)
            if db.execute('SELECT 1 FROM stock_ledger WHERE command_id=?',(body.command_id,)).fetchone():
                fail('Command ID already used',409)
            po=po_view(db,po_id)
            if po['status'] not in ('approved','partial'):fail('Purchase order must be approved and open',409)
            if not exists(db,'locations',body.location_id):fail('Location not found',404)
            line=next((x for x in po['lines'] if x['item_id']==body.item_id),None)
            if line is None:fail('Item does not belong to the purchase order',409)
            if body.quantity>line['remaining']:fail('Receipt exceeds outstanding PO quantity',409)
            cur=db.execute('''INSERT INTO stock_ledger(item_id,location_id,quantity_delta,entry_type,reference,command_id,actor)
                VALUES (?,?,?,'receipt',?,?,?)''',(body.item_id,body.location_id,body.quantity,po['number'],body.command_id,body.actor))
            db.execute('INSERT INTO purchase_receipts(po_id,po_line_id,stock_ledger_id,quantity) VALUES (?,?,?,?)',
                (po_id,line['id'],cur.lastrowid,body.quantity))
            db.execute('UPDATE purchase_order_lines SET received_qty=received_qty+? WHERE id=?',(body.quantity,line['id']))
            remaining=db.execute('SELECT COUNT(*) AS n FROM purchase_order_lines WHERE po_id=? AND received_qty<ordered_qty',(po_id,)).fetchone()['n']
            db.execute('UPDATE purchase_orders SET status=? WHERE id=?',('partial' if remaining else 'received',po_id))
            from .workflow_v6 import accounting_po_receipt
            journal_id=accounting_po_receipt(db,ledger_id=cur.lastrowid,item_id=body.item_id,qty=body.quantity,actor=body.actor,reference=po['number'],audit=audit)
            audit(db,'po.received','purchase_order',po_id,body.actor,{'sku':line['sku'],'quantity':body.quantity,'stock_ledger_id':cur.lastrowid})
            return {'ledger_id':cur.lastrowid,'idempotent_replay':False,'journal_id':journal_id,'on_hand':stock_at(db,body.item_id,body.location_id),'purchase_order':po_view(db,po_id)}

    @app.get('/api/quality-cases')
    def list_quality():
        with connect(path) as db:
            return [dict(x) for x in db.execute('''SELECT q.*,i.sku AS item_sku,w.number AS work_order_number FROM quality_cases q
                LEFT JOIN items i ON i.id=q.item_id LEFT JOIN work_orders w ON w.id=q.work_order_id ORDER BY q.id DESC''')]

    @app.post('/api/quality-cases',status_code=201)
    def create_quality(body:QualityIn):
        with db_write(path) as db:
            if body.item_id and not exists(db,'items',body.item_id):fail('Item not found',404)
            if body.work_order_id and not exists(db,'work_orders',body.work_order_id):fail('Work order not found',404)
            if db.execute('SELECT 1 FROM quality_cases WHERE number=?',(body.number.upper(),)).fetchone():fail('Quality case number exists',409)
            cur=db.execute('''INSERT INTO quality_cases(number,summary,source,severity,item_id,work_order_id)
                VALUES (?,?,?,?,?,?)''',(body.number.upper(),body.summary,body.source,body.severity,body.item_id,body.work_order_id))
            audit(db,'quality.created','quality_case',cur.lastrowid,body.actor,{'number':body.number.upper(),'severity':body.severity})
            return dict(db.execute('SELECT * FROM quality_cases WHERE id=?',(cur.lastrowid,)).fetchone())

    @app.post('/api/quality-cases/{case_id}/status')
    def quality_status(case_id:int,body:QualityStatus):
        with db_write(path) as db:
            old=db.execute('SELECT * FROM quality_cases WHERE id=?',(case_id,)).fetchone()
            if old is None:fail('Quality case not found',404)
            if old['status']=='resolved':fail('Resolved cases are closed; reopen is not implemented',409)
            if body.status=='resolved' and len(body.resolution.strip())<5:fail('Resolution explanation required',422)
            if body.status==old['status']:fail('Status unchanged',409)
            db.execute('UPDATE quality_cases SET status=?,resolution=? WHERE id=?',
                (body.status,body.resolution.strip(),case_id))
            audit(db,'quality.status_changed','quality_case',case_id,body.actor,
                {'from':old['status'],'to':body.status,'resolution':body.resolution.strip()})
            return dict(db.execute('SELECT * FROM quality_cases WHERE id=?',(case_id,)).fetchone())

    @app.get('/api/custom-fields')
    def custom_fields():
        with connect(path) as db:
            return [dict(x) for x in db.execute('SELECT * FROM item_field_definitions ORDER BY id')]

    @app.post('/api/custom-fields',status_code=201)
    def new_field(body:FieldIn):
        with db_write(path) as db:
            key=body.field_key.lower()
            if db.execute('SELECT 1 FROM item_field_definitions WHERE field_key=?',(key,)).fetchone():fail('Custom field key already exists',409)
            cur=db.execute('INSERT INTO item_field_definitions(field_key,label,field_type) VALUES (?,?,?)',
                (key,body.label,body.field_type))
            audit(db,'field.created','item_field_definition',cur.lastrowid,'demo.admin',{'key':key,'type':body.field_type})
            return {'id':cur.lastrowid,'field_key':key,'label':body.label,'field_type':body.field_type}

    @app.get('/api/items/{item_id}/custom-fields')
    def item_custom_fields(item_id:int):
        with connect(path) as db:
            if not exists(db,'items',item_id):fail('Item not found',404)
            values={x['field_key']:json.loads(x['value_json']) for x in db.execute('''SELECT d.field_key,v.value_json
               FROM item_field_values v JOIN item_field_definitions d ON d.id=v.field_id WHERE v.item_id=?''',(item_id,))}
            return {'item_id':item_id,'values':values}

    @app.put('/api/items/{item_id}/custom-fields/{field_id}')
    def set_field_value(item_id:int,field_id:int,body:ValueIn):
        with db_write(path) as db:
            if not exists(db,'items',item_id):fail('Item not found',404)
            row=db.execute('SELECT * FROM item_field_definitions WHERE id=?',(field_id,)).fetchone()
            if row is None:fail('Custom field not found',404)
            val=body.value
            correct=(row['field_type']=='boolean' and isinstance(val,bool)) or (
                row['field_type']=='number' and type(val) in (int,float) and math.isfinite(val)) or (
                row['field_type']=='text' and isinstance(val,str) and len(val)<=500)
            if not correct:fail('Incorrect value type for this custom field',422)
            db.execute('''INSERT INTO item_field_values(item_id,field_id,value_json) VALUES (?,?,?)
                ON CONFLICT(item_id,field_id) DO UPDATE SET value_json=excluded.value_json''',
                (item_id,field_id,json.dumps(val,ensure_ascii=False)))
            audit(db,'field.value_set','item',item_id,body.actor,{'field_key':row['field_key'],'value':val})
            return {'item_id':item_id,'field_key':row['field_key'],'value':val}

    @app.get('/api/insights')
    def insights():
        with connect(path) as db:
            open_po=db.execute("SELECT COUNT(*) n FROM purchase_orders WHERE status IN ('approved','partial')").fetchone()['n']
            draft_po=db.execute("SELECT COUNT(*) n FROM purchase_orders WHERE status='draft'").fetchone()['n']
            open_quality=db.execute("SELECT COUNT(*) n FROM quality_cases WHERE status!='resolved'").fetchone()['n']
            recent=[dict(x) for x in db.execute('''SELECT event_type,entity_type,actor,created_at FROM audit_log
                ORDER BY id DESC LIMIT 10''')]
            return {'open_purchase_orders':open_po,'draft_purchase_orders':draft_po,
                    'open_quality_cases':open_quality,'recent_events':recent}
