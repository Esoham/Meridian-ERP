# Meridian ERP — Customizable Manufacturing Workspace v0.4

**Independent concept prototype | Python / FastAPI / SQLite | Synthetic manufacturing data**

Meridian ERP is a local-first prototype that shows **receiving parts into a warehouse, checking material availability, releasing a work order, issuing components to production, and completing the job** with an append-only inventory ledger and audit history.

> **Not production ERP.** It has no authentication, company/tenant isolation, general ledger, automated enterprise backup/restore program, EDI, real ERP connectors, or production security controls. Do not expose the API to the internet or use it with employer/customer data. All sample records are fictional.

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e '.[dev]'
python -m scripts.migrate_db  # backs up pre-v0.4 SQLite once
python -m scripts.seed_demo
uvicorn meridian.api:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** for the operator console, or **http://127.0.0.1:8000/docs** for the interactive API. For Windows PowerShell, run `pip install -e ".[dev]"` using double quotes.

## Demonstrate a complete flow

1. **Items & locations:** Seeded `BOLT-001` and `PANEL-001` in the `MAIN` warehouse.
2. **Receipt:** The seed records +30 fasteners and +10 control panels (receipts are idempotent).
3. **Work order:** `WO-DEMO-1001` is for three Control Box Assemblies, requiring 12 fasteners and 3 panels.
4. **Release:** Verify sufficient on-hand stock, then release the planned work order.
5. **Issue:** Issue 12 fasteners and 3 panels from `MAIN` using distinct command IDs.
6. **Complete:** Once all requirements are issued, complete the work order.
7. **Trace:** Read stock ledger and audit events to see each write.

The v0.4 workspace has nine screens, including purchasing, quality, management reports and configurable workspace settings. It supports a searchable item/PO/job catalog, multi-component BOM and work-order entry, validations, role-based presentation presets, and CSV exports. API endpoints remain accessible in the OpenAPI docs.

## What changed in v0.3

- Reorganized the dashboard into five navigable sections with a persistent desktop sidebar and collapsible mobile menu.
- Added **multi-component BOM editing** in the browser: add or remove lines, select distinct inventory items, and set per-unit quantity. Client-side validation rejects duplicate SKU rows and invalid quantities before posting to the existing BOM API.
- Added a multi-component custom work-order form and a live component demand preview for active BOM revisions.
- Made inventory and audit tables searchable, added an inventory warehouse filter, and CSV export of the currently fetched local data (most-recent 200 events for audit/ledger).
- Preserved all existing backend/database workflows, tables, and migration behavior; **this is primarily a UI release**.
- Browser-tested one full two-component manufacturing cycle and narrow-screen navigation against the local API using synthetic data; this is not a browser compatibility certification.

**Upgrading an existing v0.2/v0.3 folder:** Stop the server with `Ctrl+C`, back up `meridian.db`, then extract v0.4 and copy **all** updated source files (including `meridian/enterprise.py`, `meridian/enterprise.js`, and `meridian/enterprise.css`) into your original folder. Do **not** overwrite or delete `meridian.db` or `.venv`. Run `START_WINDOWS.bat`, which creates another versioned SQLite backup before adding v0.4 tables. Replacing only `index.html` is **not sufficient** for v0.4.

## Implemented guarantees

- On-hand balance is **derived from immutable stock ledger entries**, not adjusted by editing a balance cell.
- Each stock command has a **unique idempotency key**; exact replays return the existing entry; conflicting replays fail.
- SQLite `BEGIN IMMEDIATE` serializes read-check-write operations to protect against concurrent overspending **within the single local database**.
- Material issues never exceed the associated work-order requirement or on-hand balance at the chosen location.
- Work orders follow the state machine `planned → released → materials_issued → completed`.
- Failed validations roll back their writes; audit history is append-only.
- Schema enforces foreign keys, uniqueness, positive quantities, and reference consistency.

## Run tests

```bash
python -m pytest -q
```

See [Architecture](docs/ARCHITECTURE.md), [Product roadmap](docs/ROADMAP.md), and `tests/` for verified behavior. These tests validate a prototype, **not** deployment readiness.

## Deploying responsibly later

Before real usage, add organization/user identity and authorization, comprehensive audit attribution, PostgreSQL, migrations, managed secrets, privacy controls, backups/restore drills, observability, business-document reversal flows, multi-warehouse policy, compliance review, and operational support. The current API accepts a demo `actor` string from clients and **does not authenticate it**.

## Portfolio positioning

This is a separate proof-of-concept for a potential manufacturing ERP platform—not a copy of Infor or any employer-owned system. It deliberately models public generic concepts using fictional records; the code, documentation, and unit tests can be independently reviewed.

## Windows quick launch

You can also run `START_WINDOWS.bat` from this folder. It creates a local virtual environment, installs the dependencies, seeds the fictional data, and starts the server on `127.0.0.1:8000`. Review scripts before running them; this is an independent demo, not an official ERP installer.


## What v0.4 adds — independent ERP workspace

The interface uses familiar enterprise ERP concepts (role-focused workspaces, dense registers, search, controls and customizable widgets) without copying any proprietary UI or claiming compatibility with Infor.

**Nine functional workspace views:** Overview, Inventory, BOM revisions, Production, Purchasing, Quality, Reports, Audit and Workspace Settings. The dashboard includes a cross-module command search (`Ctrl+K`) and mobile navigation.

**Purchasing:** supplier master; purchase order draft and approval; multiple PO lines with integer-cent unit prices; partial or final PO receiving with a duplicate-request guard; inbound receipts post atomically to the existing stock ledger and audit log. This is not a financial accounting or payments module.

**Quality:** an auditable nonconformance register with source, severity, review status, and documented resolution. Quality cases do not yet enforce lot quarantine or issue blocking.

**Customizations:** workspace label, colors, theme, table density, collapsed navigation, role-oriented homepage presets, individual dashboard widgets and cross-browser preference JSON export/import. These *appearance* settings are saved in the browser only; they do not confer permissions. Item custom fields (text, numeric, yes/no) and validated values are persisted in SQLite with audit records.

**Safe upgrades:** `START_WINDOWS.bat` uses regular Python 3.12/3.13, runs `scripts.migrate_db` before loading sample data, and automatically backs up an existing pre-v0.4 SQLite database once to `backups/`. Backups are local development safeguards, not disaster recovery. **Before upgrading, close the server and keep an independent copy of `meridian.db`.**

**Tests:** `python -m python -m pytest -q` covers core workflows, BOM/revisions, reservations, routing, purchasing, quality, custom fields and migration. See [docs/ERP_CAPABILITIES.md](docs/ERP_CAPABILITIES.md) for completed features, limitations and future enterprise work.

### Commercial readiness disclaimer

This is a **single-node local prototype** and educational product foundation. No authentication or authorization, robust tenant isolation, tax/accounting controls, secure deployments, inventory costing, lot/serial traceability, regulated quality workflows, or real integrations are provided. It is **not** ready to replace an organization's ERP or to process actual employer/customer data.
