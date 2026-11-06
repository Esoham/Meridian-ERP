"""Incremental finance and integration foundations for the local demonstration.

Ledger entries are explicitly company-scoped. Legacy manufacturing/inventory
records are NOT tenant-scoped. Nothing here is a full multi-company ERP or
an audited accounting system.
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field, StringConstraints, model_validator

from .db import connect, db_write

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=40, pattern=r'^[A-Za-z0-9._-]+$')]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]

FINANCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS erp_companies (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 currency TEXT NOT NULL DEFAULT 'USD', created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE TABLE IF NOT EXISTS gl_accounts (
 id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES erp_companies(id),
 code TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL
 CHECK(category IN ('asset','liability','equity','revenue','expense')),
 UNIQUE(company_id,code), UNIQUE(company_id,id));
CREATE TABLE IF NOT EXISTS journal_entries (
 id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES erp_companies(id),
 reference TEXT NOT NULL, memo TEXT NOT NULL, actor TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(company_id,reference), UNIQUE(company_id,id));
CREATE TABLE IF NOT EXISTS journal_lines (
 id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL,
 journal_id INTEGER NOT NULL, account_id INTEGER NOT NULL,
 debit_cents INTEGER NOT NULL DEFAULT 0 CHECK(debit_cents>=0),
 credit_cents INTEGER NOT NULL DEFAULT 0 CHECK(credit_cents>=0),
 CHECK((debit_cents>0 AND credit_cents=0) OR (credit_cents>0 AND debit_cents=0)),
 FOREIGN KEY(company_id,journal_id) REFERENCES journal_entries(company_id,id),
 FOREIGN KEY(company_id,account_id) REFERENCES gl_accounts(company_id,id));
CREATE TABLE IF NOT EXISTS item_standard_costs (
 company_id INTEGER NOT NULL REFERENCES erp_companies(id),
 item_id INTEGER NOT NULL REFERENCES items(id),
 cost_cents INTEGER NOT NULL CHECK(cost_cents>=0),
 PRIMARY KEY(company_id,item_id));
CREATE INDEX IF NOT EXISTS idx_journal_company ON journal_entries(company_id);
CREATE INDEX IF NOT EXISTS idx_journal_lines_company ON journal_lines(company_id,account_id);
CREATE TRIGGER IF NOT EXISTS gl_journal_no_edit BEFORE UPDATE ON journal_entries
 BEGIN SELECT RAISE(ABORT,'posted journal is immutable'); END;
CREATE TRIGGER IF NOT EXISTS gl_journal_no_delete BEFORE DELETE ON journal_entries
 BEGIN SELECT RAISE(ABORT,'posted journal is immutable'); END;
CREATE TRIGGER IF NOT EXISTS gl_lines_no_edit BEFORE UPDATE ON journal_lines
 BEGIN SELECT RAISE(ABORT,'posted journal line is immutable'); END;
CREATE TRIGGER IF NOT EXISTS gl_lines_no_delete BEFORE DELETE ON journal_lines
 BEGIN SELECT RAISE(ABORT,'posted journal line is immutable'); END;
"""

class CompanyIn(BaseModel):
    code: Code
    name: Name

class AccountIn(BaseModel):
    company_id: int = Field(gt=0)
    code: Code
    name: Name
    category: Literal['asset','liability','equity','revenue','expense']

class JournalLineIn(BaseModel):
    account_id: int = Field(gt=0)
    debit_cents: int = Field(ge=0, le=10**12, default=0)
    credit_cents: int = Field(ge=0, le=10**12, default=0)
    @model_validator(mode='after')
    def single_side(self):
        if (self.debit_cents>0)==(self.credit_cents>0):
            raise ValueError('Exactly one of debit_cents or credit_cents must be positive')
        return self

class JournalIn(BaseModel):
    company_id: int = Field(gt=0)
    reference: Code
    memo: Name
    actor: Name = 'demo.finance'
    lines: list[JournalLineIn] = Field(min_length=2, max_length=100)
    @model_validator(mode='after')
    def balanced(self):
        if sum(x.debit_cents for x in self.lines)!=sum(x.credit_cents for x in self.lines):
            raise ValueError('Journal debits and credits must balance')
        return self

class CostIn(BaseModel):
    company_id: int = Field(gt=0)
    item_id: int = Field(gt=0)
    cost_cents: int = Field(ge=0, le=10**10)
    actor: Name = 'demo.costing'

class StockImportPreview(BaseModel):
    csv_text: str = Field(min_length=1, max_length=250_000)


def parse_stock_csv(text: str) -> list[dict]:
    """Strict read-only preflight; no stock mutations happen here."""
    reader=csv.DictReader(io.StringIO(text, newline=''))
    if not reader.fieldnames or reader.fieldnames!=['sku','location','quantity','reference']:
        raise ValueError('CSV header must be: sku,location,quantity,reference')
    rows=[]
    for index,row in enumerate(reader,2):
        if index>501: raise ValueError('Maximum 500 data rows')
        if None in row or any(x is None for x in row.values()):
            raise ValueError(f'Line {index}: malformed CSV row')
        sku=row['sku'].strip().upper(); loc=row['location'].strip().upper(); ref=row['reference'].strip(); q=row['quantity'].strip()
        if not sku or not loc or not ref or len(sku)>60 or len(loc)>60 or len(ref)>120:
            raise ValueError(f'Line {index}: missing/oversized value')
        if not q.isascii() or not q.isdecimal() or not 1<=int(q)<=1_000_000:
            raise ValueError(f'Line {index}: quantity must be positive integer')
        rows.append({'sku':sku,'location':loc,'quantity':int(q),'reference':ref})
    if not rows: raise ValueError('At least one data row required')
    return rows


def register_routes(app: FastAPI, path: Path, *, audit, fail, exists):
    def company_exists(db, company_id):
        if not exists(db,'erp_companies',company_id): fail('Company not found',404)

    def journal_view(db, id):
        j=db.execute('SELECT * FROM journal_entries WHERE id=?',(id,)).fetchone()
        if not j: fail('Journal not found',404)
        lines=[dict(x) for x in db.execute('''SELECT l.account_id,a.code AS account_code,a.name AS account_name,
            l.debit_cents,l.credit_cents FROM journal_lines l JOIN gl_accounts a ON a.id=l.account_id WHERE l.journal_id=? ORDER BY l.id''',(id,))]
        return {**dict(j),'lines':lines,'total_debit_cents':sum(x['debit_cents'] for x in lines)}

    @app.get('/api/finance/companies')
    def companies():
        with connect(path) as db:return [dict(x) for x in db.execute('SELECT * FROM erp_companies ORDER BY code')]

    @app.post('/api/finance/companies',status_code=201)
    def add_company(body:CompanyIn):
        with db_write(path) as db:
            if db.execute('SELECT 1 FROM erp_companies WHERE code=?',(body.code.upper(),)).fetchone():fail('Company code already exists',409)
            c=db.execute('INSERT INTO erp_companies(code,name) VALUES (?,?)',(body.code.upper(),body.name))
            audit(db,'company.created','erp_company',c.lastrowid,'demo.admin',body.model_dump())
            return {'id':c.lastrowid,'code':body.code.upper(),'name':body.name,'currency':'USD'}

    @app.get('/api/finance/accounts')
    def accounts(company_id:int):
        with connect(path) as db:
            company_exists(db,company_id)
            return [dict(x) for x in db.execute('SELECT * FROM gl_accounts WHERE company_id=? ORDER BY code',(company_id,))]

    @app.post('/api/finance/accounts',status_code=201)
    def add_account(body:AccountIn):
        with db_write(path) as db:
            company_exists(db,body.company_id)
            if db.execute('SELECT 1 FROM gl_accounts WHERE company_id=? AND code=?',(body.company_id,body.code.upper())).fetchone():fail('Account code already exists in company',409)
            c=db.execute('INSERT INTO gl_accounts(company_id,code,name,category) VALUES (?,?,?,?)',(body.company_id,body.code.upper(),body.name,body.category))
            audit(db,'account.created','gl_account',c.lastrowid,'demo.finance',body.model_dump())
            return {'id':c.lastrowid,'company_id':body.company_id,'code':body.code.upper(),'name':body.name,'category':body.category}

    @app.get('/api/finance/journals')
    def journals(company_id:int):
        with connect(path) as db:
            company_exists(db,company_id)
            ids=[x['id'] for x in db.execute('SELECT id FROM journal_entries WHERE company_id=? ORDER BY id DESC LIMIT 100',(company_id,))]
            return [journal_view(db,id) for id in ids]

    @app.post('/api/finance/journals',status_code=201)
    def post_journal(body:JournalIn):
        with db_write(path) as db:
            company_exists(db,body.company_id)
            if db.execute('SELECT 1 FROM journal_entries WHERE company_id=? AND reference=?',(body.company_id,body.reference.upper())).fetchone():fail('Journal reference already exists in company',409)
            for line in body.lines:
                found=db.execute('SELECT 1 FROM gl_accounts WHERE id=? AND company_id=?',(line.account_id,body.company_id)).fetchone()
                if not found:fail('Journal account does not belong to selected company',409)
            c=db.execute('INSERT INTO journal_entries(company_id,reference,memo,actor) VALUES (?,?,?,?)',(body.company_id,body.reference.upper(),body.memo,body.actor))
            for line in body.lines:
                db.execute('INSERT INTO journal_lines(company_id,journal_id,account_id,debit_cents,credit_cents) VALUES (?,?,?,?,?)',
                    (body.company_id,c.lastrowid,line.account_id,line.debit_cents,line.credit_cents))
            audit(db,'journal.posted','journal_entry',c.lastrowid,body.actor,{'company_id':body.company_id,'reference':body.reference.upper(),'total_cents':sum(x.debit_cents for x in body.lines)})
            return journal_view(db,c.lastrowid)

    @app.get('/api/finance/trial-balance')
    def trial_balance(company_id:int):
        with connect(path) as db:
            company_exists(db,company_id)
            return [dict(x) for x in db.execute('''SELECT a.id,a.code,a.name,a.category,
                COALESCE(SUM(l.debit_cents),0) AS debit_cents,
                COALESCE(SUM(l.credit_cents),0) AS credit_cents,
                COALESCE(SUM(l.debit_cents-l.credit_cents),0) AS net_debit_cents
                FROM gl_accounts a LEFT JOIN journal_lines l ON l.account_id=a.id
                WHERE a.company_id=? GROUP BY a.id ORDER BY a.code''',(company_id,))]

    @app.put('/api/finance/costs')
    def standard_cost(body:CostIn):
        with db_write(path) as db:
            company_exists(db,body.company_id)
            if not exists(db,'items',body.item_id):fail('Item not found',404)
            db.execute('''INSERT INTO item_standard_costs(company_id,item_id,cost_cents) VALUES (?,?,?)
                ON CONFLICT(company_id,item_id) DO UPDATE SET cost_cents=excluded.cost_cents''',(body.company_id,body.item_id,body.cost_cents))
            audit(db,'item.standard_cost.updated','item',body.item_id,body.actor,{'company_id':body.company_id,'cost_cents':body.cost_cents})
            return {'company_id':body.company_id,'item_id':body.item_id,'cost_cents':body.cost_cents}

    @app.get('/api/finance/valuation')
    def valuation(company_id:int):
        with connect(path) as db:
            company_exists(db,company_id)
            rows=[dict(x) for x in db.execute('''SELECT i.id AS item_id,i.sku,i.name,
                COALESCE(s.cost_cents,0) AS standard_cost_cents,
                COALESCE((SELECT SUM(quantity_delta) FROM stock_ledger WHERE item_id=i.id),0) AS on_hand
                FROM items i LEFT JOIN item_standard_costs s ON s.item_id=i.id AND s.company_id=? ORDER BY i.sku''',(company_id,))]
            for row in rows:row['indicative_value_cents']=row['on_hand']*row['standard_cost_cents']
            return {'company_id':company_id,'informational_only':True,'warning':'Global sample stock is not segregated by company. Not GAAP/IFRS inventory valuation.',
                    'rows':rows,'total_cents':sum(r['indicative_value_cents'] for r in rows)}

    @app.post('/api/integrations/stock-import/preview')
    def preview_import(body:StockImportPreview):
        try:rows=parse_stock_csv(body.csv_text)
        except ValueError as ex:fail(str(ex),422)
        with connect(path) as db:
            items={x['sku'] for x in db.execute('SELECT sku FROM items')}
            locs={x['code'] for x in db.execute('SELECT code FROM locations')}
        annotated=[{**row,'valid':row['sku'] in items and row['location'] in locs,
            'issues':(["Unknown SKU"] if row['sku'] not in items else [])+(["Unknown location"] if row['location'] not in locs else [])} for row in rows]
        return {'preview_only':True,'rows':annotated,'valid_count':sum(x['valid'] for x in annotated),'total_rows':len(annotated),'posted':0}
