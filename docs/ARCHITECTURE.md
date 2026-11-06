# Architecture — Meridian ERP MVP

```text
Browser (vanilla HTML/CSS/JS)
           |
      FastAPI JSON
           |
 Application validation & work-order state machine
           |
     SQLite BEGIN IMMEDIATE
           |
 Items · Locations · Work Orders · Lines
 Stock Ledger (append-only) · Audit Log (append-only)
```

## Transactional flow

- **Receive**: validate SKU/location; ensure command ID is new or identical; insert positive ledger entry and audit event in one transaction.
- **Release**: inspect synthetic BOM requirements and current aggregate on-hand; block shortages; update status and audit in one transaction. Release does **not reserve stock**.
- **Issue**: validate work-order state, component, remaining requirement, and *location-specific* stock; write negative ledger entry and increment issued quantity atomically. Serializes competing writes in local SQLite.
- **Complete**: block until every component has been issued in full, then mark completed and audit.

## Modeling choices

- Quantities use **integer eaches** in this first milestone; fractional or conversion-based UOM requires a separate precision and conversion design.
- Inventory is derived with `SUM(quantity_delta)` per item/location. No direct balance updates.
- There is no production receipt of a finished good yet; that is a later feature.
- Work order `components` are a **snapshot captured at creation**, not an engineering-managed versioned BOM.
- This MVP has no reservations or allocations; release can pass even though a different order later consumes stock, but the final issue is protected.
- Demo actor is client-supplied and untrusted. For any actual business use, identity must come from an authenticated session, not the request body.
- SQLite provides single-node serialized writes; enterprise multi-node deployment would use PostgreSQL and well-specified row locks/isolation.
- Append-only triggers prevent SQL UPDATE/DELETE on stock and audit entries; admins can still change DB files or definitions. Tamper-resistance requires further protections.

## Security boundaries

The development server binds to `127.0.0.1`. Never deploy to a public host without auth/RBAC, secrets policy, authorization tests, CSRF consideration, abuse controls, HTTPS, audit-hardening, validation, backups, and penetration testing.

## v0.2 optional manufacturing extension

New tables: `boms`, `bom_lines`, `work_order_boms`, `stock_reservations`, and `work_order_operations`. These are added with idempotent `CREATE TABLE IF NOT EXISTS` statements at startup, preserving existing records. Activated BOM lines are immutable at the SQLite trigger layer; superseded BOM revisions remain queryable.

Reservations are outstanding quantities, calculated as `reserved_qty - consumed_qty - released_qty`. Available-to-promise is location on-hand minus outstanding reservations. Allocations and material issues occur in a single `BEGIN IMMEDIATE` write transaction to avoid overspending the same stock on a local SQLite instance. Work-order completion checks sequential routing steps if a routing is configured.

**Caveat:** Releasing a work order does not itself reserve stock; users must call the separate reserve action, and planning does not guarantee future availability. No authentication, user permissions, production-grade migration rollback, finished-good stock receipts, multi-tenancy, or external ERP integration exists.
