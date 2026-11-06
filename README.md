# Meridian ERP — Inventory to Production MVP v0.2

**Independent concept prototype | Python / FastAPI / SQLite | Synthetic manufacturing data**

Meridian ERP is a local-first prototype that shows **receiving parts into a warehouse, checking material availability, releasing a work order, issuing components to production, and completing the job** with an append-only inventory ledger and audit history.

> **Not production ERP.** It has no authentication, company/tenant isolation, financial ledger, backups, EDI, real ERP connectors, or production security controls. Do not expose the API to the internet or use it with employer/customer data. All sample records are fictional.

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e '.[dev]'
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

The UI includes editable forms and action buttons; advanced workflows remain accessible in the OpenAPI docs.

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
pytest -q
```

See [Architecture](docs/ARCHITECTURE.md), [Product roadmap](docs/ROADMAP.md), and `tests/` for verified behavior. These tests validate a prototype, **not** deployment readiness.

## Deploying responsibly later

Before real usage, add organization/user identity and authorization, comprehensive audit attribution, PostgreSQL, migrations, managed secrets, privacy controls, backups/restore drills, observability, business-document reversal flows, multi-warehouse policy, compliance review, and operational support. The current API accepts a demo `actor` string from clients and **does not authenticate it**.

## Portfolio positioning

This is a separate proof-of-concept for a potential manufacturing ERP platform—not a copy of Infor or any employer-owned system. It deliberately models public generic concepts using fictional records; the code, documentation, and unit tests can be independently reviewed.

## Windows quick launch

You can also run `START_WINDOWS.bat` from this folder. It creates a local virtual environment, installs the dependencies, seeds the fictional data, and starts the server on `127.0.0.1:8000`. Review scripts before running them; this is an independent demo, not an official ERP installer.
