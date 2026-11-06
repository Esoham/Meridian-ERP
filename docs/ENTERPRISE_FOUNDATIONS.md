# Meridian ERP v0.5 — Enterprise Foundations (Demo Scope)

This release adds **learning-oriented foundations**, not an enterprise-complete ERP. Everything is for synthetic data on a single machine.

## Capabilities added

| Area | Working now | Still missing |
| --- | --- | --- |
| Authentication | Optional local login, PBKDF2-HMAC passwords, server-side hashed bearer sessions, demo roles: admin/operator/viewer | Default login disabled for backwards compatibility; no SSO/MFA, lockouts, HTTPS, password recovery, or exhaustive permission matrix |
| Companies | Independent finance entities, charts of accounts, journal entries, trial balance | Existing inventory, warehouse, purchasing and manufacturing records are **not** company isolated. **Not multi-tenancy.** |
| Accounting | Manual balanced two-sided journal posting with USD cents, append-only posted journals | No automated postings, AP/AR, tax, bank, fiscal periods, reconciliation, GAAP/IFRS controls or official GL |
| Costing | User-defined standard costs and calculated informational stock values | No FIFO/weighted-average, WIP, COGS, variance or cost-layer accounting; existing stock is global demo data |
| Backup and restore | SQLite online backup, integrity check and SHA-256 manifest; explicit offline restore into a new destination | No automatic schedules, encryption, offsite replication, recovery-time promise or high availability |
| Integration | CSV stock-import **preview** with row validation against known SKU and warehouse | Preview only: no posting, ERP connectors, EDI, authentication for external systems or retry pipeline |

## Try finance in the browser

Open the **Finance & Costing** sidebar page. Create a fictional company, add two accounts (for example 1000 Cash and 3000 Owner Equity), then post a balanced journal. Trial balance updates immediately. Add a standard unit cost to a sample item to view the **indicative** value of its global demo stock.

## Enable optional local sign-in (development only)

By default, the existing demo stays accessible to preserve old workflows. If you want to exercise password-based local roles, stop the server first and create an account:

```cmd
.venv\Scripts\python.exe -m scripts.create_user --username adminlocal --role admin
set MERIDIAN_REQUIRE_LOGIN=1
START_WINDOWS.bat
```

Choose a strong unique password interactively when prompted. The app presents a login screen on loading. The demo uses eight-hour bearer sessions. An admin can create additional accounts through `scripts.create_user` with `--role operator` or `--role viewer` while the server is stopped.

**Limitations:** Do not open the server to the LAN or public internet. It lacks TLS, MFA, SSO, brute-force protection and production-quality authorization. The selector called *Role-based homepage* in Settings only changes visible widgets; the optional actual login role determines basic API write access.

To return to the original unrestricted demo in the same Windows terminal:

```cmd
set MERIDIAN_REQUIRE_LOGIN=0
START_WINDOWS.bat
```

## Backup and restore

The Windows launcher runs `scripts.migrate_db` to create a pre-upgrade backup when upgrading from an older schema version. To create an additional manual backup while the demo is stopped or running:

```cmd
.venv\Scripts\python.exe -m scripts.backup_db backup --db meridian.db --out backups
```

The backup creates a `.db` file plus a `.sha256.json` verification manifest. To rehearse a restore, **stop Meridian ERP** (`Ctrl+C`), and restore to a **new filename** instead of overwriting the original:

```cmd
.venv\Scripts\python.exe -m scripts.backup_db restore --from-backup backups\YOUR-BACKUP-FILENAME.db --to meridian-restored.db --confirm
```

To start using that restored copy, the existing main database would first need to be safely moved aside and the restored database renamed. Do not delete the original until the data has been inspected. Store copies off the device yourself; these utilities do not perform cloud backup or disaster-recovery automation.

## CSV input preflight

In **Integrations**, try:

```csv
sku,location,quantity,reference
BOLT-001,MAIN,5,DEMO-RECEIPT-1
PANEL-001,MAIN,2,DEMO-RECEIPT-2
```

`POST /api/integrations/stock-import/preview` validates values and checks matching existing items and locations. It does not write inventory or create purchase orders.

## Development guardrails

- Keep `meridian.db`, backup copies, secrets, customer data, and real employee files out of GitHub.
- Do not treat client-supplied audit `actor` strings as authenticated user identity. This is not yet impersonation-resistant audit evidence.
- Existing module records are globally shared; *only the finance accounting records* use company IDs. Never describe this as enterprise-wide tenant isolation.
- Code and dashboard are independent and inspired by common ERP conventions. They are not proprietary Infor source or a certified replacement.
