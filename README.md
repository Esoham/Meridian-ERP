# Meridian ERP v0.6 — Integrated Manufacturing Portfolio Release

[![ERP regression validation](https://github.com/Esoham/Meridian-ERP/actions/workflows/mvp-tests.yml/badge.svg)](https://github.com/Esoham/Meridian-ERP/actions/workflows/mvp-tests.yml)

**Portfolio-complete local prototype | Python, FastAPI, SQLite, vanilla JavaScript | Fictional data only**

Meridian ERP is an independently designed, customizable manufacturing workspace demonstrating realistic business workflows. It is **not** Infor software or an enterprise-ready replacement. The v0.6 milestone connects supplier purchasing, warehouse receipts, revision-controlled BOMs, work orders, production routing, finished-goods receipts, quality review, and **optional** illustrative financial postings.

## Quick start — Windows

Install standard Python 3.12 (recommended). From the extracted project folder, run:

```cmd
START_WINDOWS.bat
```

The launcher uses regular Python rather than free-threaded 3.13t, installs dependencies without persisting the pip download cache, backs up an existing pre-v0.6 database before schema migration, seeds fictional data idempotently, and starts the server on `127.0.0.1:8000`.

Open **http://127.0.0.1:8000/** for the dashboard or **http://127.0.0.1:8000/docs** for the documented API.

For manual launch:

```bash
python -m venv .venv
# Activate the venv for your operating system.
python -m pip install --no-cache-dir -e '.[dev]'
python -m scripts.migrate_db
python -m scripts.seed_demo
python -m uvicorn meridian.api:app --host 127.0.0.1 --port 8000
```

**Upgrading v0.5:** Stop the old server with `Ctrl+C`. Make an independent copy of `meridian.db`. Copy **all v0.6 source files** over your existing installation without replacing `meridian.db` or `.venv`, and run `START_WINDOWS.bat`. Do not use the ZIP as a replacement database. New tables are additive. Keep a separate backup outside the project folder.

## Major modules

| Module | What is implemented | Key limitations |
| --- | --- | --- |
| Inventory | Item and warehouse master data; receipts, issues, reservations, append-only stock ledger | No transfers, cycle-count adjustments, lots, serials or true multi-company isolation |
| Engineering | Multi-component BOMs, draft/active revisions, work-order snapshots | No effectivity dates, ECO approval workflow, alternates |
| Production | Work orders, material reservations/issues, sequential routing, completion, **finished-goods receipt** | Full completion only; no scrap, partial builds, labor or overhead capture |
| Purchasing | Supplier master, approvals, multi-line PO, partial/final stock receiving | No AP matching, returns, tax, or purchase-price-variance treatment |
| Quality | Nonconformance cases and resolution; **high-severity open WO cases block FG receipt** | No lot quarantine, full inspection execution or regulatory certification |
| Finance | Manual balanced entries, chart of accounts, trial balance, standard costs, **opt-in automatic standard-cost postings** | No fiscal periods, AR/AP, cash, taxes, price variance, GAAP/IFRS system |
| Integrations | Read-only CSV receiving preview and local checksum-verified SQLite backups | No real ERP connectors, EDI, scheduled offsite backups |
| UI and customization | Role-themed dashboard, module navigation, search, custom item fields, light/dark, table density, widget preferences | Most workspace preferences are browser-local |
| Access controls | Optional local hashed passwords, session tokens and basic role restrictions | Demo login off by default; no production identity, SSO/MFA or security certification |

## Demonstrate an end-to-end work order

1. In **Inventory**, use synthetic `BOLT-001`, `PANEL-001`, `BOX-002` and the `MAIN` warehouse. Initial demo stock includes 30 bolts, 10 panels and zero finished boxes.
2. In **BOMs**, create and activate `BOX-002` Revision A using 4 bolts and 1 panel per finished product.
3. Create `WO-2002` from the active BOM with a build quantity of 3. Add Assembly and Inspection routing.
4. In **Production**, release and reserve materials, issue 12 bolts and 3 panels, finish both routing operations, and complete the work order.
5. Under **Finished-goods receipt**, select `WO-2002`, finished SKU `BOX-002`, and `MAIN`, then post a receipt. The system adds three finished boxes in one transaction. A second receipt is blocked; a retry with the exact same command ID is idempotent.
6. Inspect the **stock ledger**, **audit** and **finished-goods receipt history**. In a clean seed scenario, stock should show bolts 18, panels 7 and finished boxes 3.

You can also use **Purchasing** to receive additional components against an approved supplier purchase order before manufacturing.

## Optional integrated accounting demo

**Off by default.** To enable: first create a finance company, then four distinct accounts: Raw Inventory (asset), GRNI (liability), WIP (asset), and Finished Goods Inventory (asset). Assign **positive standard costs** to any components you intend to buy or issue. In **Finance & Costing → Connected workflow accounting**, map and activate those four accounts. Configuration becomes locked for this local database.

After activation, the following posting examples are **atomic with their inventory movement**:

| Trigger | Debit | Credit | Basis |
| --- | --- | --- | --- |
| Approved PO received | Raw Inventory | GRNI | Received quantity × standard unit cost |
| Component issued | Work In Process | Raw Inventory | Issued quantity × standard unit cost |
| Finished box received | Finished Goods Inventory | Work In Process | Accumulated posted component issue cost |

If a required standard cost is missing, the entire transaction fails without creating an inventory movement or journal. Existing legacy receipts and issues are **not backposted**, and a finished-goods receipt with unposted issue history is blocked while accounting is enabled. The accounting example omits price variances, labor, overhead, vendor invoices and fiscal close; it is **not a complete financial system**. All manufacturing inventory is still globally shared demo data rather than isolated by finance company.

## Tests and source

```bash
python -m pytest -q
```

GitHub Actions validates Python 3.11/3.12/3.13 and the modular dashboard JavaScript. Read [Final Release & Workflow Guide](docs/FINAL_RELEASE.md), [Enterprise Foundations](docs/ENTERPRISE_FOUNDATIONS.md), [Architecture](docs/ARCHITECTURE.md), and [Capability Matrix](docs/ERP_CAPABILITIES.md) for implementation and limitations. Source code is in `meridian/` and regression tests in `tests/`.

## Safety and commercial scope

This release is **portfolio-complete, not commercially production-ready**. It lacks authenticated audit attribution, enforced company/tenant isolation, certified accounting, PostgreSQL operations, business-document reversals, offsite disaster recovery, external integrations and enterprise security reviews. The app binds to `127.0.0.1`; never expose this prototype to the internet, use real employer/customer data, or claim replacement of Infor, SAP or Oracle systems. Code and synthetic data are independent of proprietary employer systems.
