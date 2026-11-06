"""Local-only JSON API for a synthetic manufacturing inventory-to-production flow.

This is *not* production ERP: there is no authentication, tenant isolation,
enterprise accounting, backup orchestration or external-system integration.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StringConstraints, model_validator

from .db import connect, db_write, init_db
from .manufacturing import (register_routes, reserved_total, own_reserved, consume_reserved,
                            view_reservations, view_operations)

Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60, pattern=r'^[A-Za-z0-9._-]+$')]

class ItemIn(BaseModel):
    sku: Code
    name: Nonempty
    uom: Code = "EA"

class LocationIn(BaseModel):
    code: Code
    name: Nonempty

class WorkOrderLineIn(BaseModel):
    item_id: int = Field(gt=0)
    per_unit: int = Field(gt=0, le=1000000)

class WorkOrderIn(BaseModel):
    number: Code
    product_name: Nonempty
    quantity: int = Field(gt=0, le=1000000)
    components: list[WorkOrderLineIn] = Field(min_length=1, max_length=100)
    actor: Nonempty = "demo.operator"

    @model_validator(mode="after")
    def no_duplicate_components(self):
        ids = [line.item_id for line in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("Each component item can appear only once")
        return self

class ReceiptIn(BaseModel):
    item_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000000)
    reference: Nonempty
    command_id: Code
    actor: Nonempty = "demo.operator"

class IssueIn(BaseModel):
    item_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000000)
    reference: Nonempty
    command_id: Code
    actor: Nonempty = "demo.operator"

class ActionIn(BaseModel):
    actor: Nonempty = "demo.operator"


def fail(message: str, status: int = 400):
    raise HTTPException(status_code=status, detail=message)


def exists(conn: sqlite3.Connection, table: str, row_id: int) -> bool:
    # table always caller's hardcoded value, not user input
    return conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (row_id,)).fetchone() is not None


def audit(conn, event: str, entity: str, entity_id: int, actor: str, details: dict):
    conn.execute(
        "INSERT INTO audit_log(event_type,entity_type,entity_id,actor,details_json) VALUES (?,?,?,?,?)",
        (event, entity, entity_id, actor, json.dumps(details, sort_keys=True)),
    )


def stock_at(conn, item_id: int, location_id: int | None = None) -> int:
    if location_id is None:
        r = conn.execute("SELECT COALESCE(SUM(quantity_delta),0) AS q FROM stock_ledger WHERE item_id=?", (item_id,)).fetchone()
    else:
        r = conn.execute("SELECT COALESCE(SUM(quantity_delta),0) AS q FROM stock_ledger WHERE item_id=? AND location_id=?", (item_id, location_id)).fetchone()
    return int(r["q"])


def view_wo(conn, wo_id: int) -> dict:
    wo = conn.execute("SELECT * FROM work_orders WHERE id=?", (wo_id,)).fetchone()
    if wo is None:
        fail("Work order not found", 404)
    lines = conn.execute("""SELECT l.item_id,i.sku,i.name,l.per_unit,l.issued_qty
        FROM work_order_lines l JOIN items i ON i.id=l.item_id
        WHERE l.work_order_id=? ORDER BY l.id""", (wo_id,)).fetchall()
    comps = []
    for x in lines:
        needed = x["per_unit"] * wo["quantity"]
        onhand = stock_at(conn, x["item_id"])
        comps.append(dict(item_id=x["item_id"], sku=x["sku"], name=x["name"], per_unit=x["per_unit"],
                          required=needed, issued=x["issued_qty"], remaining=needed-x["issued_qty"],
                          on_hand=onhand, shortage=max(0,needed-x["issued_qty"]-onhand)))
    linked = conn.execute("""SELECT b.id,b.product_sku,b.revision FROM work_order_boms wb
        JOIN boms b ON b.id=wb.bom_id WHERE wb.work_order_id=?""",(wo_id,)).fetchone()
    return {"id":wo["id"], "number":wo["number"], "product_name":wo["product_name"],
            "quantity":wo["quantity"],"status":wo["status"],"components":comps,"created_at":wo["created_at"],
            "bom":dict(linked) if linked else None,"reservations":view_reservations(conn,wo_id),
            "operations":view_operations(conn,wo_id)}


def get_existing_command(conn, cmd: str, expected: dict):
    r = conn.execute("SELECT * FROM stock_ledger WHERE command_id=?", (cmd,)).fetchone()
    if r is None:
        return None
    if all(r[key] == value for key, value in expected.items()):
        return {"ledger_id":r["id"], "entry_type":r["entry_type"], "idempotent_replay":True}
    fail("Command ID already used for a different operation", 409)


def create_app(db_path: str | Path | None = None) -> FastAPI:
    path = Path(db_path or os.environ.get("MERIDIAN_DB_PATH", "./meridian.db"))
    static_home = Path(__file__).resolve().parent / "index.html"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(path)
        yield

    app = FastAPI(title="Meridian ERP — Local MVP",version="0.4.0",lifespan=lifespan,
                  description="Synthetic, local-only inventory-to-production system; not a production ERP")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(static_home)

    @app.get('/enterprise.css', include_in_schema=False)
    def enterprise_css():
        return FileResponse(static_home.parent / 'enterprise.css', media_type='text/css')

    @app.get('/enterprise.js', include_in_schema=False)
    def enterprise_js():
        return FileResponse(static_home.parent / 'enterprise.js', media_type='text/javascript')

    @app.get("/api/health")
    def health():
        return {"status":"ok", "product":"Meridian ERP MVP", "production_ready":False}

    @app.post("/api/items", status_code=201)
    def add_item(body: ItemIn):
        try:
            with db_write(path) as db:
                cur = db.execute("INSERT INTO items(sku,name,uom) VALUES (?,?,?)",(body.sku.upper(),body.name,body.uom.upper()))
                audit(db,"item.created","item",cur.lastrowid,"demo.operator",body.model_dump())
                return {"id":cur.lastrowid,"sku":body.sku.upper(),"name":body.name,"uom":body.uom.upper()}
        except sqlite3.IntegrityError:
            fail("Item SKU already exists",409)

    @app.get("/api/items")
    def list_items():
        db=connect(path)
        try:return [dict(x) for x in db.execute("SELECT * FROM items ORDER BY sku")]
        finally:db.close()

    @app.post("/api/locations", status_code=201)
    def add_location(body: LocationIn):
        try:
            with db_write(path) as db:
                cur=db.execute("INSERT INTO locations(code,name) VALUES (?,?)", (body.code.upper(),body.name))
                audit(db,"location.created","location",cur.lastrowid,"demo.operator",body.model_dump())
                return {"id":cur.lastrowid,"code":body.code.upper(),"name":body.name}
        except sqlite3.IntegrityError:
            fail("Location code already exists",409)

    @app.get("/api/locations")
    def list_locations():
        db=connect(path)
        try:return [dict(x) for x in db.execute("SELECT * FROM locations ORDER BY code")]
        finally:db.close()

    @app.post("/api/stock/receive",status_code=201)
    def receive(body: ReceiptIn):
        with db_write(path) as db:
            duplicate=get_existing_command(db,body.command_id,{
                "item_id":body.item_id,"location_id":body.location_id,"work_order_id":None,
                "quantity_delta":body.quantity,"entry_type":"receipt","reference":body.reference,"actor":body.actor})
            if duplicate:return duplicate
            if not exists(db,"items",body.item_id) or not exists(db,"locations",body.location_id):
                fail("Item or location does not exist",404)
            cur=db.execute("""INSERT INTO stock_ledger(item_id,location_id,quantity_delta,entry_type,reference,command_id,actor)
                VALUES (?,?,?,'receipt',?,?,?)""",(body.item_id,body.location_id,body.quantity,body.reference,body.command_id,body.actor))
            audit(db,"stock.received","stock_ledger",cur.lastrowid,body.actor,body.model_dump())
            return {"ledger_id":cur.lastrowid,"entry_type":"receipt","idempotent_replay":False,
                    "on_hand":stock_at(db,body.item_id,body.location_id)}

    @app.get("/api/stock")
    def list_stock():
        db=connect(path)
        try:
            rows=[dict(x) for x in db.execute("""SELECT i.id AS item_id,i.sku,i.name,l.id AS location_id,
                l.code AS location_code,COALESCE(SUM(s.quantity_delta),0) AS on_hand
                FROM items i CROSS JOIN locations l
                LEFT JOIN stock_ledger s ON s.item_id=i.id AND s.location_id=l.id
                GROUP BY i.id,l.id ORDER BY i.sku,l.code""")]
            for row in rows:
                row["reserved"] = reserved_total(db,row["item_id"],row["location_id"])
                row["available"] = row["on_hand"]-row["reserved"]
            return rows
        finally:db.close()

    @app.get("/api/ledger")
    def list_ledger(limit: int = 50):
        limit = min(max(1,limit),200)
        db=connect(path)
        try:return [dict(x) for x in db.execute("""SELECT s.id,s.entry_type,s.item_id,i.sku,s.location_id,l.code AS location_code,
          s.work_order_id,s.quantity_delta,s.reference,s.command_id,s.actor,s.created_at
          FROM stock_ledger s JOIN items i ON s.item_id=i.id JOIN locations l ON s.location_id=l.id
          ORDER BY s.id DESC LIMIT ?""",(limit,))]
        finally:db.close()

    @app.post("/api/work-orders",status_code=201)
    def create_wo(body: WorkOrderIn):
        try:
            with db_write(path) as db:
                for component in body.components:
                    if not exists(db,"items",component.item_id):fail(f"Item {component.item_id} does not exist",404)
                cur=db.execute("INSERT INTO work_orders(number,product_name,quantity) VALUES (?,?,?)",
                               (body.number.upper(),body.product_name,body.quantity))
                for component in body.components:
                    db.execute("INSERT INTO work_order_lines(work_order_id,item_id,per_unit) VALUES (?,?,?)",
                               (cur.lastrowid,component.item_id,component.per_unit))
                audit(db,"work_order.created","work_order",cur.lastrowid,body.actor,body.model_dump())
                return view_wo(db,cur.lastrowid)
        except sqlite3.IntegrityError:
            fail("Work order number already exists",409)

    @app.get("/api/work-orders")
    def list_wo():
        db=connect(path)
        try:
            return [view_wo(db,x["id"]) for x in db.execute("SELECT id FROM work_orders ORDER BY id DESC").fetchall()]
        finally:db.close()

    @app.get("/api/work-orders/{wo_id}")
    def get_wo(wo_id:int):
        db=connect(path)
        try:return view_wo(db,wo_id)
        finally:db.close()

    @app.post("/api/work-orders/{wo_id}/release")
    def release_wo(wo_id:int,body: ActionIn):
        with db_write(path) as db:
            wo=view_wo(db,wo_id)
            if wo["status"] != "planned":fail("Only planned work orders can be released",409)
            if any(c["remaining"] > stock_at(db,c["item_id"])-reserved_total(db,c["item_id"])
                   for c in wo["components"]):
                fail("Cannot release: shortage of unreserved components",409)
            db.execute("UPDATE work_orders SET status='released' WHERE id=?",(wo_id,))
            audit(db,"work_order.released","work_order",wo_id,body.actor,{"components":len(wo["components"])})
            return view_wo(db,wo_id)

    @app.post("/api/work-orders/{wo_id}/issue",status_code=201)
    def issue_wo(wo_id:int,body: IssueIn):
        with db_write(path) as db:
            duplicate=get_existing_command(db,body.command_id,{
                "item_id":body.item_id,"location_id":body.location_id,"work_order_id":wo_id,
                "quantity_delta":-body.quantity,"entry_type":"issue","reference":body.reference,"actor":body.actor})
            if duplicate:return duplicate
            wo=view_wo(db,wo_id)
            if wo["status"] != "released":fail("Only released work orders accept material issues",409)
            line=db.execute("SELECT * FROM work_order_lines WHERE work_order_id=? AND item_id=?",(wo_id,body.item_id)).fetchone()
            if line is None:fail("Item is not a component on this work order",409)
            if not exists(db,"locations",body.location_id):fail("Location does not exist",404)
            max_allowed=line["per_unit"]*wo["quantity"]-line["issued_qty"]
            if body.quantity > max_allowed:fail(f"Issue exceeds remaining requirement ({max_allowed})",409)
            on_hand=stock_at(db,body.item_id,body.location_id)
            if on_hand < body.quantity:
                fail("Insufficient on-hand stock at selected location",409)
            owned=own_reserved(db,wo_id,body.item_id,body.location_id)
            free=on_hand-reserved_total(db,body.item_id,body.location_id)
            if owned:
                if body.quantity > owned:
                    fail("Issue exceeds the work order's reserved quantity at this location",409)
                consume_reserved(db,wo_id,body.item_id,body.location_id,body.quantity)
                audit(db,"reservation.consumed","work_order",wo_id,body.actor,
                      {"item_id":body.item_id,"location_id":body.location_id,"quantity":body.quantity})
            elif body.quantity > free:
                fail("Insufficient unreserved stock at selected location",409)
            cur=db.execute("""INSERT INTO stock_ledger(item_id,location_id,work_order_id,quantity_delta,entry_type,reference,command_id,actor)
                VALUES (?,?,?,?,'issue',?,?,?)""",(body.item_id,body.location_id,wo_id,-body.quantity,body.reference,body.command_id,body.actor))
            db.execute("UPDATE work_order_lines SET issued_qty=issued_qty+? WHERE id=?",(body.quantity,line["id"]))
            all_lines=db.execute("SELECT per_unit,issued_qty FROM work_order_lines WHERE work_order_id=?",(wo_id,)).fetchall()
            if all(x["issued_qty"] == x["per_unit"]*wo["quantity"] for x in all_lines):
                db.execute("UPDATE work_orders SET status='materials_issued' WHERE id=?",(wo_id,))
            audit(db,"stock.issued","stock_ledger",cur.lastrowid,body.actor,{**body.model_dump(),"work_order_id":wo_id})
            return {"ledger_id":cur.lastrowid,"entry_type":"issue","idempotent_replay":False,
                    "on_hand":stock_at(db,body.item_id,body.location_id),"work_order":view_wo(db,wo_id)}

    @app.post("/api/work-orders/{wo_id}/complete")
    def complete_wo(wo_id:int,body: ActionIn):
        with db_write(path) as db:
            wo=view_wo(db,wo_id)
            if wo["status"] != "materials_issued":fail("All required materials must be issued before completion",409)
            if any(op["status"]!="done" for op in view_operations(db,wo_id)):
                fail("All routing operations must be finished before completing the work order",409)
            db.execute("UPDATE work_orders SET status='completed' WHERE id=?",(wo_id,))
            audit(db,"work_order.completed","work_order",wo_id,body.actor,{})
            return view_wo(db,wo_id)

    @app.get("/api/audit")
    def list_audit(limit: int=50):
        limit=min(max(1,limit),200)
        db=connect(path)
        try:
            return [dict(x) for x in db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",(limit,))]
        finally:db.close()

    register_routes(app,path,view_wo=view_wo,stock_at=stock_at,audit=audit,fail=fail,exists=exists)
    from .enterprise import register_routes as register_enterprise_routes
    register_enterprise_routes(app,path,audit=audit,fail=fail,exists=exists,stock_at=stock_at)
    return app

app = create_app()
