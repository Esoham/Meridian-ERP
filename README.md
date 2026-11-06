# Meridian ERP — Inventory to Production MVP

**Independent concept prototype | Python / FastAPI / SQLite | Synthetic manufacturing data**

Meridian ERP is a local-first prototype demonstrating receiving materials, checking stock availability, releasing production work orders, issuing components, completing jobs, and viewing inventory/audit history.

> **Not production ERP.** The prototype has no authentication, tenant separation, financial ledger, migration tooling, backups, or production security controls. Do not expose it to the internet or connect employer/customer information. All demo data is fictional.

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m scripts.seed_demo
uvicorn meridian.api:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** for the operator dashboard or **http://127.0.0.1:8000/docs** for interactive API documentation.

## Complete manufacturing workflow

1. Seed `BOLT-001` and `PANEL-001` into the `MAIN` warehouse.
2. Record receipts of sample materials.
3. Create a work order for three Control Box Assemblies.
4. Verify sufficient material and release the work order.
5. Issue exact component quantities to production.
6. Complete the job and inspect ledger and audit events.

## Data-integrity design

- Inventory balances are derived from append-only stock transactions.
- Idempotency keys prevent duplicated receipts and issues.
- SQLite `BEGIN IMMEDIATE` protects single-database read/check/write operations.
- Business rules prevent negative stock and excess material issues.
- Work orders transition through planned, released, materials-issued, and completed statuses.
- Foreign keys and validation enforce references and positive quantities.

## Tests

Run `pytest -q` after installing development dependencies. **10 tests passed locally on November 6, 2026** against the supplied prototype; this does not establish production readiness.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [API implementation](meridian/api.py)
- [SQLite persistence](meridian/db.py)
- [Operator dashboard](meridian/index.html)
- [Automated tests](tests/test_workflow.py)

## Scope and safety

The current API accepts a demo `actor` field from clients but does **not authenticate** the actor. It lacks enterprise authorization, migrations, resilient backups, monitoring, and operational controls. For a commercial platform, begin by addressing these issues before onboarding users or processing real business data.

The project is designed around generic manufacturing concepts and synthetic records, not copied ERP source code or confidential employer records.

---
**Built as an independent manufacturing ERP learning and product-design project.**
