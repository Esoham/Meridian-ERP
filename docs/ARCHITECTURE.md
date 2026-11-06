# Architecture — Meridian ERP MVP

Browser (vanilla HTML/CSS/JS) → FastAPI JSON → Application validation & work-order state machine → SQLite BEGIN IMMEDIATE → Items, Locations, Work Orders, Lines, Stock Ledger, Audit Log.

## Transactional flow

- **Receive:** Validate SKU/location; ensure command ID is new or identical; insert positive ledger entry and audit event in one transaction.
- **Release:** Inspect synthetic BOM requirements and current aggregate on-hand; block shortages; update status and audit in one transaction. Release does **not** reserve stock.
- **Issue:** Validate work-order state, component, remaining requirement, and location-specific stock; write negative ledger entry and increment issued quantity atomically.
- **Complete:** Block until every component has been issued in full, then mark completed and audit.

## Modeling choices

- Quantities use integer eaches; fractional UOM requires further work.
- Inventory is derived with SUM(quantity_delta), not direct balance updates.
- There is no finished-good inventory receipt yet.
- Work order components are a snapshot, not a versioned BOM.
- The MVP has no reservations; another order can consume stock before issue.
- The demo actor is client-supplied and untrusted.
- SQLite serializes single-node writes; multi-node enterprise use needs a stronger database.
- Append-only triggers prevent ordinary SQL update/delete but do not make the database tamper-proof.

## Security boundaries

The development server binds to 127.0.0.1. Never deploy publicly without authentication, RBAC, secret management, proper authorization tests, HTTPS, abuse controls, recovery, and security review.
