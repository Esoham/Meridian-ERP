"""Seed fictional example data; safe to rerun without duplicating records."""
import json
import os
from pathlib import Path

from meridian.db import db_write, init_db

path = Path(os.environ.get("MERIDIAN_DB_PATH", "./meridian.db"))
init_db(path)


def record_event(db, event, entity, entity_id, details):
    db.execute("""INSERT INTO audit_log(event_type,entity_type,entity_id,actor,details_json)
        VALUES(?,?,?,'demo.seed',?)""", (event, entity, entity_id, json.dumps(details,sort_keys=True)))


with db_write(path) as db:
    for sku,name in [('BOLT-001','M6 Fastener'),('PANEL-001','Control Panel')]:
        c = db.execute("INSERT OR IGNORE INTO items(sku,name,uom) VALUES (?,?,'EA')", (sku,name))
        item_id = db.execute('SELECT id FROM items WHERE sku=?',(sku,)).fetchone()['id']
        if c.rowcount:
            record_event(db,'item.seeded','item',item_id,{'sku':sku,'synthetic':True})
    c = db.execute("INSERT OR IGNORE INTO locations(code,name) VALUES ('MAIN','Main Warehouse')")
    loc=db.execute("SELECT id FROM locations WHERE code='MAIN'").fetchone()['id']
    if c.rowcount:
        record_event(db,'location.seeded','location',loc,{'code':'MAIN','synthetic':True})
    ids = {x['sku']:x['id'] for x in db.execute('SELECT id,sku FROM items')}
    for sku,qty in [('BOLT-001',30),('PANEL-001',10)]:
        c = db.execute("""INSERT OR IGNORE INTO stock_ledger(item_id,location_id,quantity_delta,entry_type,reference,command_id,actor)
             VALUES (?, ?, ?, 'receipt', 'SYNTHETIC-SEED', ?, 'demo.seed')""", (ids[sku],loc,qty,'SEED-'+sku))
        if c.rowcount:
            record_event(db,'stock.seeded','stock_ledger',c.lastrowid,{'sku':sku,'quantity':qty,'synthetic':True})
    c = db.execute("""INSERT OR IGNORE INTO work_orders(number,product_name,quantity,status)
        VALUES ('WO-DEMO-1001','Control Box Assembly',3,'planned')""")
    wo=db.execute("SELECT id FROM work_orders WHERE number='WO-DEMO-1001'").fetchone()['id']
    if c.rowcount:
        record_event(db,'work_order.seeded','work_order',wo,{'number':'WO-DEMO-1001','synthetic':True})
    for sku,per in [('BOLT-001',4),('PANEL-001',1)]:
        db.execute("INSERT OR IGNORE INTO work_order_lines(work_order_id,item_id,per_unit) VALUES (?,?,?)",(wo,ids[sku],per))
print('Fictional sample data ready. Run: uvicorn meridian.api:app --reload --host 127.0.0.1')
