"""Versioned BOMs, allocations and shop-floor operations for the local demo.

This module only handles fictional single-node inventory; there is no user auth,
financial accounting, or production-grade data integrity beyond SQLite transactions.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field, StringConstraints, model_validator
from typing import Annotated
from .db import connect, db_write

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60, pattern=r'^[A-Za-z0-9._-]+$')]
Revision = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20, pattern=r'^[A-Za-z0-9._-]+$')]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS boms (
 id INTEGER PRIMARY KEY, product_sku TEXT NOT NULL, product_name TEXT NOT NULL,
 revision TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft'
 CHECK(status IN ('draft','active','superseded')),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(product_sku,revision)
);
CREATE TABLE IF NOT EXISTS bom_lines (
 id INTEGER PRIMARY KEY, bom_id INTEGER NOT NULL REFERENCES boms(id),
 item_id INTEGER NOT NULL REFERENCES items(id), per_unit INTEGER NOT NULL CHECK(per_unit > 0),
 UNIQUE(bom_id,item_id)
);
CREATE TABLE IF NOT EXISTS work_order_boms (
 work_order_id INTEGER PRIMARY KEY REFERENCES work_orders(id),
 bom_id INTEGER NOT NULL REFERENCES boms(id)
);
CREATE TABLE IF NOT EXISTS stock_reservations (
 id INTEGER PRIMARY KEY, work_order_id INTEGER NOT NULL REFERENCES work_orders(id),
 item_id INTEGER NOT NULL REFERENCES items(id), location_id INTEGER NOT NULL REFERENCES locations(id),
 reserved_qty INTEGER NOT NULL CHECK(reserved_qty > 0),
 consumed_qty INTEGER NOT NULL DEFAULT 0 CHECK(consumed_qty >= 0),
 released_qty INTEGER NOT NULL DEFAULT 0 CHECK(released_qty >= 0),
 CHECK(consumed_qty + released_qty <= reserved_qty),
 UNIQUE(work_order_id,item_id,location_id)
);
CREATE INDEX IF NOT EXISTS idx_reservation_item_location ON stock_reservations(item_id,location_id);
CREATE TABLE IF NOT EXISTS work_order_operations (
 id INTEGER PRIMARY KEY, work_order_id INTEGER NOT NULL REFERENCES work_orders(id),
 sequence INTEGER NOT NULL CHECK(sequence > 0), operation TEXT NOT NULL,
 work_center TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','in_progress','done')),
 started_at TEXT, finished_at TEXT, UNIQUE(work_order_id,sequence)
);
CREATE TRIGGER IF NOT EXISTS bom_lines_no_update_active BEFORE UPDATE ON bom_lines
WHEN (SELECT status FROM boms WHERE id=OLD.bom_id)!='draft'
BEGIN SELECT RAISE(ABORT,'activated BOM revision is immutable'); END;
CREATE TRIGGER IF NOT EXISTS bom_lines_no_delete_active BEFORE DELETE ON bom_lines
WHEN (SELECT status FROM boms WHERE id=OLD.bom_id)!='draft'
BEGIN SELECT RAISE(ABORT,'activated BOM revision is immutable'); END;
CREATE TRIGGER IF NOT EXISTS bom_lines_no_insert_active BEFORE INSERT ON bom_lines
WHEN (SELECT status FROM boms WHERE id=NEW.bom_id)!='draft'
BEGIN SELECT RAISE(ABORT,'activated BOM revision is immutable'); END;
"""


class BomComponent(BaseModel):
    item_id: int = Field(gt=0)
    per_unit: int = Field(gt=0, le=1000000)

class BomCreate(BaseModel):
    product_sku: Code
    product_name: Label
    revision: Revision
    components: list[BomComponent] = Field(min_length=1, max_length=100)
    actor: Label = 'demo.engineering'

    @model_validator(mode='after')
    def validate_unique_items(self):
        if len({x.item_id for x in self.components}) != len(self.components):
            raise ValueError('Duplicate components in BOM')
        return self

class BomOrder(BaseModel):
    number: Code
    quantity: int = Field(gt=0, le=1000000)
    actor: Label = 'demo.planner'

class Operation(BaseModel):
    sequence: int = Field(gt=0, le=10000)
    operation: Label
    work_center: Label

class Routing(BaseModel):
    operations: list[Operation] = Field(min_length=1, max_length=100)
    actor: Label = 'demo.planner'

    @model_validator(mode='after')
    def validate_unique_sequences(self):
        if len({x.sequence for x in self.operations}) != len(self.operations):
            raise ValueError('Duplicate operation sequence')
        return self

class Actor(BaseModel):
    actor: Label = 'demo.operator'


def reserved_total(db, item_id: int, location_id: int | None = None) -> int:
    if location_id is None:
        row = db.execute('''SELECT COALESCE(SUM(reserved_qty-consumed_qty-released_qty),0) AS q
          FROM stock_reservations WHERE item_id=?''', (item_id,)).fetchone()
    else:
        row = db.execute('''SELECT COALESCE(SUM(reserved_qty-consumed_qty-released_qty),0) AS q
          FROM stock_reservations WHERE item_id=? AND location_id=?''',
          (item_id,location_id)).fetchone()
    return int(row['q'])


def own_reserved(db, work_order_id: int, item_id: int, location_id: int) -> int:
    row = db.execute('''SELECT COALESCE(SUM(reserved_qty-consumed_qty-released_qty),0) AS q
      FROM stock_reservations WHERE work_order_id=? AND item_id=? AND location_id=?''',
      (work_order_id,item_id,location_id)).fetchone()
    return int(row['q'])


def consume_reserved(db, wo: int, item: int, loc: int, qty: int) -> None:
    db.execute('''UPDATE stock_reservations SET consumed_qty=consumed_qty+?
       WHERE work_order_id=? AND item_id=? AND location_id=?''', (qty,wo,item,loc))


def view_reservations(db, wo: int | None = None):
    sql = '''SELECT r.id,r.work_order_id,w.number AS work_order,r.item_id,i.sku,
       r.location_id,l.code AS location,r.reserved_qty,r.consumed_qty,r.released_qty,
       (r.reserved_qty-r.consumed_qty-r.released_qty) AS outstanding
       FROM stock_reservations r JOIN work_orders w ON w.id=r.work_order_id
       JOIN items i ON i.id=r.item_id JOIN locations l ON l.id=r.location_id'''
    args: tuple = ()
    if wo is not None:
        sql += ' WHERE r.work_order_id=?'
        args = (wo,)
    sql += ' ORDER BY r.id'
    return [dict(x) for x in db.execute(sql, args)]


def view_operations(db, wo: int):
    return [dict(x) for x in db.execute('''SELECT id,sequence,operation,work_center,status,
      started_at,finished_at FROM work_order_operations WHERE work_order_id=? ORDER BY sequence''', (wo,))]


def get_bom(db, bom_id, fail):
    b = db.execute('SELECT * FROM boms WHERE id=?', (bom_id,)).fetchone()
    if b is None: fail('BOM not found',404)
    lines = db.execute('''SELECT bl.item_id,i.sku,i.name,bl.per_unit FROM bom_lines bl
       JOIN items i ON bl.item_id=i.id WHERE bl.bom_id=? ORDER BY i.sku''', (bom_id,)).fetchall()
    return {**dict(b),'components':[dict(x) for x in lines]}


def register_routes(app: FastAPI, path: Path, *, view_wo, stock_at, audit, fail, exists) -> None:
    """Mount optional manufacturing routes onto the original FastAPI app."""
    @app.get('/api/boms')
    def list_boms():
        db=connect(path)
        try:
            ids=[r['id'] for r in db.execute('SELECT id FROM boms ORDER BY product_sku,revision')]
            return [get_bom(db,i,fail) for i in ids]
        finally: db.close()

    @app.get('/api/boms/{bom_id}')
    def one_bom(bom_id:int):
        db=connect(path)
        try: return get_bom(db,bom_id,fail)
        finally: db.close()

    @app.post('/api/boms',status_code=201)
    def create_bom(body:BomCreate):
        with db_write(path) as db:
            for line in body.components:
                if not exists(db,'items',line.item_id):fail(f'Component {line.item_id} not found',404)
            existing=db.execute('SELECT 1 FROM boms WHERE product_sku=? AND revision=?',
                                (body.product_sku.upper(),body.revision.upper())).fetchone()
            if existing: fail('That BOM revision already exists',409)
            cur=db.execute('''INSERT INTO boms(product_sku,product_name,revision)
              VALUES (?,?,?)''',(body.product_sku.upper(),body.product_name,body.revision.upper()))
            for line in body.components:
                db.execute('INSERT INTO bom_lines(bom_id,item_id,per_unit) VALUES (?,?,?)',
                           (cur.lastrowid,line.item_id,line.per_unit))
            audit(db,'bom.created','bom',cur.lastrowid,body.actor,{'revision':body.revision,'components':len(body.components)})
            return get_bom(db,cur.lastrowid,fail)

    @app.post('/api/boms/{bom_id}/activate')
    def activate_bom(bom_id:int,body:Actor):
        with db_write(path) as db:
            bom=get_bom(db,bom_id,fail)
            if bom['status']!='draft':fail('Only draft BOM revisions can be activated',409)
            db.execute("UPDATE boms SET status='superseded' WHERE product_sku=? AND status='active'",(bom['product_sku'],))
            db.execute("UPDATE boms SET status='active' WHERE id=?",(bom_id,))
            audit(db,'bom.activated','bom',bom_id,body.actor,{'product_sku':bom['product_sku'],'revision':bom['revision']})
            return get_bom(db,bom_id,fail)

    @app.post('/api/boms/{bom_id}/work-orders',status_code=201)
    def new_bom_wo(bom_id:int,body:BomOrder):
        with db_write(path) as db:
            bom=get_bom(db,bom_id,fail)
            if bom['status']!='active':fail('Work orders require an active BOM',409)
            if db.execute('SELECT 1 FROM work_orders WHERE number=?',(body.number.upper(),)).fetchone():
                fail('Work order number already exists',409)
            cur=db.execute('INSERT INTO work_orders(number,product_name,quantity) VALUES (?,?,?)',
                           (body.number.upper(),bom['product_name'],body.quantity))
            db.execute('INSERT INTO work_order_boms(work_order_id,bom_id) VALUES (?,?)',(cur.lastrowid,bom_id))
            for c in bom['components']:
                db.execute('INSERT INTO work_order_lines(work_order_id,item_id,per_unit) VALUES (?,?,?)',
                           (cur.lastrowid,c['item_id'],c['per_unit']))
            audit(db,'work_order.from_bom','work_order',cur.lastrowid,body.actor,{'bom_id':bom_id,'revision':bom['revision']})
            return view_wo(db,cur.lastrowid)

    @app.get('/api/reservations')
    def list_reservations(work_order_id:int|None=None):
        db=connect(path)
        try:return view_reservations(db,work_order_id)
        finally:db.close()

    @app.post('/api/work-orders/{wo_id}/reserve')
    def reserve_wo(wo_id:int,body:Actor):
        with db_write(path) as db:
            wo=view_wo(db,wo_id)
            if wo['status']!='released':fail('Only released work orders can reserve components',409)
            for component in wo['components']:
                item=component['item_id']
                already=db.execute('''SELECT COALESCE(SUM(reserved_qty-consumed_qty-released_qty),0) AS q
                   FROM stock_reservations WHERE work_order_id=? AND item_id=?''',(wo_id,item)).fetchone()['q']
                needed=component['remaining']-already
                if needed<0:fail('Reservation exceeds work order requirement',409)
                if needed==0:continue
                locations=db.execute('SELECT id FROM locations ORDER BY id').fetchall()
                for loc in locations:
                    available=stock_at(db,item,loc['id'])-reserved_total(db,item,loc['id'])
                    take=min(needed,max(0,available))
                    if take>0:
                        exists_row=db.execute('''SELECT id FROM stock_reservations
                            WHERE work_order_id=? AND item_id=? AND location_id=?''',(wo_id,item,loc['id'])).fetchone()
                        if exists_row:
                            db.execute('UPDATE stock_reservations SET reserved_qty=reserved_qty+? WHERE id=?',
                                       (take,exists_row['id']))
                        else:
                            db.execute('''INSERT INTO stock_reservations(work_order_id,item_id,location_id,reserved_qty)
                                VALUES (?,?,?,?)''',(wo_id,item,loc['id'],take))
                        audit(db,'stock.reserved','work_order',wo_id,body.actor,{'item_id':item,'location_id':loc['id'],'quantity':take})
                        needed-=take
                    if needed==0:break
                if needed:fail(f'Insufficient unreserved stock for {component["sku"]}',409)
            return {'work_order':view_wo(db,wo_id),'reservations':view_reservations(db,wo_id)}

    @app.post('/api/work-orders/{wo_id}/release-reservations')
    def release_reservations(wo_id:int,body:Actor):
        with db_write(path) as db:
            wo=view_wo(db,wo_id)
            if wo['status'] not in ('released','materials_issued'):
                fail('Reservations can only be released for in-progress work orders',409)
            rows=view_reservations(db,wo_id)
            total=0
            for x in rows:
                if x['outstanding']>0:
                    db.execute('UPDATE stock_reservations SET released_qty=released_qty+? WHERE id=?',
                               (x['outstanding'],x['id']))
                    total+=x['outstanding']
            audit(db,'stock.reservations_released','work_order',wo_id,body.actor,{'quantity':total})
            return {'released':total,'reservations':view_reservations(db,wo_id)}

    @app.post('/api/work-orders/{wo_id}/routing',status_code=201)
    def add_routing(wo_id:int,body:Routing):
        with db_write(path) as db:
            wo=view_wo(db,wo_id)
            if wo['status']!='planned':fail('Routing must be set before work order release',409)
            if view_operations(db,wo_id):fail('Routing already exists for work order',409)
            for op in sorted(body.operations,key=lambda x:x.sequence):
                db.execute('''INSERT INTO work_order_operations(work_order_id,sequence,operation,work_center)
                  VALUES (?,?,?,?)''',(wo_id,op.sequence,op.operation,op.work_center))
            audit(db,'routing.created','work_order',wo_id,body.actor,{'sequences':[x.sequence for x in body.operations]})
            return {'work_order_id':wo_id,'operations':view_operations(db,wo_id)}

    @app.get('/api/work-orders/{wo_id}/operations')
    def list_operations(wo_id:int):
        db=connect(path)
        try:
            view_wo(db,wo_id)
            return view_operations(db,wo_id)
        finally:db.close()

    def change_operation(wo_id,sequence,body,mode):
        with db_write(path) as db:
            wo=view_wo(db,wo_id)
            if wo['status']!='materials_issued':fail('Operations require fully issued materials',409)
            ops=view_operations(db,wo_id)
            op=next((o for o in ops if o['sequence']==sequence),None)
            if op is None:fail('Operation not found',404)
            if mode=='start':
                if op['status']!='pending':fail('Operation must be pending',409)
                if any(x['sequence']<sequence and x['status']!='done' for x in ops):
                    fail('Earlier operation must be completed',409)
                if any(x['status']=='in_progress' for x in ops):
                    fail('Another operation is already in progress',409)
                db.execute("UPDATE work_order_operations SET status='in_progress',started_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(op['id'],))
            else:
                if op['status']!='in_progress':fail('Operation must be in progress',409)
                db.execute("UPDATE work_order_operations SET status='done',finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(op['id'],))
            audit(db,'operation.'+mode,'work_order',wo_id,body.actor,{'sequence':sequence,'operation':op['operation']})
            return {'work_order_id':wo_id,'operations':view_operations(db,wo_id)}

    @app.post('/api/work-orders/{wo_id}/operations/{sequence}/start')
    def start_operation(wo_id:int,sequence:int,body:Actor):
        return change_operation(wo_id,sequence,body,'start')

    @app.post('/api/work-orders/{wo_id}/operations/{sequence}/finish')
    def finish_operation(wo_id:int,sequence:int,body:Actor):
        return change_operation(wo_id,sequence,body,'finish')
