# Meridian ERP 0.4 — Capability Matrix & Enterprise Gap Analysis

**Status: Independent local manufacturing demonstration. No commercial deployment, no Infor code or brand copied.**

| Workstream | v0.4 capability | Gaps before production |
| --- | --- | --- |
| Workspace | 9 navigation views, role-based *presentation* presets, widget catalog, personal colors/theme, dense tables, command search | SSO/RBAC, user identity and tenant-specific settings, saved server-side views, audit of configuration |
| Inventory | Item master, locations, receiving, available/reserved stock, append-only ledger | Transfers, adjustments/reversals, costing/valuation, UOM conversions, lot/serial, bin management, stock counts, valuation |
| Engineering | Revisioned draft/active BOM, immutable active component lines, multi-line editor | BOM change approvals, effective dates, alternates, phantom BOMs, engineering document attachments |
| Manufacturing | Work order, release, reservations, issue, routings, operation sequence/completion | Labor capture, WIP costing, scrap, finished goods receipt, partial completions, scheduling/capacity |
| Purchasing | Supplier master, draft/approved PO, multi-line PO, partial receiving, idempotent receipts, audit events | Requisitions, price agreements, sales tax, receiving inspection/quarantine, returns, AP matching, vendor communication |
| Quality | NCR create/review/resolve, severity, source, audit | Inspections, dispositions, holds, CAPA, NCR linkage to blocked stock, regulatory compliance |
| Reporting | Live stock, order, purchase, quality counts; exports | Historical BI, time-zone reporting, GL reconciliation, analytics permissions, paginated full-history exports |
| Custom fields | User-defined typed item attributes, validation, audit | Custom fields on all entities, schema migrations, custom workflows, rules engine, RBAC |
| Operations | Local SQLite schema upgrade with pre-upgrade backup | PostgreSQL, HA/DR, restore drills, observability, migration tooling, security hardening |

## Data and concurrency controls

- `BEGIN IMMEDIATE` SQLite writes for single-node read-check-write operations.
- Positive/negative stock is represented by immutable ledger events. Subtracting stock checks availability and reservation ownership.
- Purchase receiving checks approved/open PO status, remaining line quantities, and idempotent command IDs in one transaction.
- Audit records are append-only through SQL triggers. They are **not cryptographic audit proofs**.
- User-supplied `actor` strings **are not authenticated identities**.
- The demo uses integer quantities and integer cents; there is no financial general ledger.

## Versioned upgrades

Run `python -m scripts.migrate_db` from the project root with the standard Python environment before `scripts.seed_demo` or the API server. When the existing SQLite `PRAGMA user_version` is below 4, a `sqlite3.Connection.backup()` copy is created before adding new tables. Existing `items`, `work_orders`, `stock_ledger`, `audit_log`, BOMs and reservations remain intact. Backups are created only for an upgrade, not every start. Also keep an external backup before overwriting files.

## Product direction

The next engineering milestones are multi-user auth/RBAC, PostgreSQL and migrations, traceable stock holds and corrections, completed-item receipts and inventory costing, real integration adapters, scheduled backups/restore tests, manufacturing planning, and rigorous security/financial assurance. Avoid claims of Fortune 500 market penetration until verified customer adoption.
