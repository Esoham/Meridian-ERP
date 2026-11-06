# Meridian ERP v0.4 — User Guide

**For fictional local data only. Do not enter real employer, customer, or private information.**

## Start

On Windows, open a Command Prompt in the project folder and run `START_WINDOWS.bat`. The launcher selects a standard Python 3.12 or 3.13 installation, installs dependencies without pip caching, checks/backups the SQLite database if migrating from an older version, seeds demonstration items and starts the API at `http://127.0.0.1:8000`.

From macOS/Linux, create a virtual environment, install `pip install -e '.[dev]'`, run `python -m scripts.migrate_db`, `python -m scripts.seed_demo`, then start `uvicorn meridian.api:app --host 127.0.0.1 --port 8000`.

### Core manufacturing walk-through

1. **Inventory → Item master:** `BOLT-001`, `PANEL-001`, with 30 and 10 units in `MAIN` by default. Receive more material with a reference if necessary.
2. **BOMs:** Create a product such as `BOX-002` revision `A`, adding both `BOLT-001` (quantity 4) and `PANEL-001` (quantity 1). Save as draft and activate.
3. **BOMs → Create work order:** Select active `BOX-002` and enter build quantity `3`. This requires 12 bolts and 3 panels.
4. **Production:** Add Assembly and Inspection routing to the *planned* work order before releasing it.
5. **Production:** Release the work order, reserve stock, issue exactly 12 bolts and 3 panels from the correct warehouse.
6. **Production:** Start/finish Assembly, then start/finish Inspection, then complete the work order.
7. **Audit:** Read ledger and activity events. Stock availability changes as materials are issued.

### Purchasing and receiving

1. Go to **Purchasing** and add a fictional supplier.
2. Create a PO with one or more lines and unit costs. Save the draft, then click **Approve PO** in the register.
3. Choose the approved PO in **Receive against PO**, pick an item, warehouse and quantity. You may receive partially; the outstanding quantity updates after each posting.
4. Check Inventory and Audit to see the posted receipt and audit record.

### Quality cases

1. In **Quality Cases**, create a case with a unique NCR number, source, severity, optional related item, and summary.
2. Click **Start review** and then enter a resolution explaining the disposition.
3. Click **Resolve case**. Closed cases are retained in the register and audit events.

**Important:** Quality records are informational only in v0.4; they do not automatically quarantine stock.

### Personalization

- **Settings:** change workspace label, color, density, light/dark theme, desktop navigation width, and dashboard role preset.
- **Widget catalog:** show/hide homepage widgets individually.
- **Export/import:** save appearance preferences to a JSON file for another browser. This does not transfer business records.
- **Item custom fields:** define text, number or yes/no fields, then choose an item to set validated values. These values are saved in the local SQLite DB and are audited.
- **Search records:** click the search control in the header or press `Ctrl+K` to find modules, SKUs, work orders, BOMs, quality cases and PO numbers.

### Data safety and backups

Before upgrading from v0.3, **stop the old server** and make a manual copy of the existing `meridian.db` file. Extract v0.4 and copy the **full** source into your existing working folder, without overwriting `meridian.db`, `.venv`, or the `backups` directory. The Windows launcher backs up databases with an older SQLite `PRAGMA user_version` before adding the v0.4 tables. Backups are development safeguards; use proper professional backup and restore controls before a customer deployment.

### Troubleshooting

- **Port in use:** Press `Ctrl+C` in the other running Meridian window, then start again.
- **No space left:** Free disk space, then rerun; the launcher installs pip packages without caching.
- **Changes not showing:** Press `Ctrl+F5`, and verify that **all** v0.4 files, including `enterprise.js`, `enterprise.css` and `enterprise.py`, are in the same source tree.
- **Production-ready?** No. Authentication, authorization, financial controls, recovery, and enterprise integrations are not implemented.

## v0.5 additions

Finance & Costing and Integrations appear in the sidebar. The [Enterprise Foundations guide](ENTERPRISE_FOUNDATIONS.md) explains company/account/journal workflows, cost previews, CSV preflight and optional local login. This does not enable production access controls or company-separated inventory.
