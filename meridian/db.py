"""SQLite persistence, constraints and append-only evidence for Meridian ERP."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY,
  sku TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  uom TEXT NOT NULL DEFAULT 'EA',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS locations (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS work_orders (
  id INTEGER PRIMARY KEY,
  number TEXT NOT NULL UNIQUE,
  product_name TEXT NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','released','materials_issued','completed')),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS work_order_lines (
  id INTEGER PRIMARY KEY,
  work_order_id INTEGER NOT NULL REFERENCES work_orders(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  per_unit INTEGER NOT NULL CHECK (per_unit > 0),
  issued_qty INTEGER NOT NULL DEFAULT 0 CHECK (issued_qty >= 0),
  UNIQUE(work_order_id,item_id)
);
CREATE TABLE IF NOT EXISTS stock_ledger (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES items(id),
  location_id INTEGER NOT NULL REFERENCES locations(id),
  work_order_id INTEGER REFERENCES work_orders(id),
  quantity_delta INTEGER NOT NULL CHECK (quantity_delta != 0),
  entry_type TEXT NOT NULL CHECK (entry_type IN ('receipt','issue')),
  reference TEXT NOT NULL,
  command_id TEXT NOT NULL UNIQUE,
  actor TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  CHECK ((entry_type='receipt' AND quantity_delta > 0 AND work_order_id IS NULL)
      OR (entry_type='issue' AND quantity_delta < 0 AND work_order_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_stock_item_location ON stock_ledger(item_id,location_id);
CREATE INDEX IF NOT EXISTS idx_stock_work_order ON stock_ledger(work_order_id);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  event_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id INTEGER NOT NULL,
  actor TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TRIGGER IF NOT EXISTS stock_ledger_no_update BEFORE UPDATE ON stock_ledger
BEGIN SELECT RAISE(ABORT,'stock ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS stock_ledger_no_delete BEFORE DELETE ON stock_ledger
BEGIN SELECT RAISE(ABORT,'stock ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT,'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT,'audit log is append-only'); END;
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db(path: str | Path) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


@contextmanager
def db_write(path: str | Path) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE serializes read-check-write sequences for a single SQLite DB."""
    conn = connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
