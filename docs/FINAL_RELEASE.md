# Meridian ERP v0.6 — Final Portfolio Release / Connected Manufacturing

**Status:** Locally runnable engineering demonstration, not production ERP.

## Scope completed

- Existing modular ERP-style interface and editable visual preferences remain intact.
- Linked engineering: an active BOM copies immutable component demand into a new work order.
- Transactional inventory: purchasing receipts and production issues use an append-only ledger, atomic reservation changes and idempotent command IDs.
- Added one-time **finished-goods receipt** for **completed BOM-derived** work orders, requiring an item whose SKU exactly matches the BOM product SKU.
- High-severity, unresolved quality cases associated with a work order prevent its finished-goods receipt.
- Optional single-company posting rules connect three stock movements to balanced illustrative journals; no auto-posting until an operator chooses the finance company, mapped accounts and standard costs.
- Audit and source-trace routes show which ledger movements generated which journals.

## Sample complete workflow (synthetic records only)

1. In Inventory, confirm or create `BOLT-001`, `PANEL-001`, `BOX-002` and warehouse `MAIN`.
2. Optional financial preparation: Finance company `DEMO`; accounts `1200 Raw Inventory` (asset), `2100 GRNI` (liability), `1300 WIP` (asset), `1400 Finished Goods Inventory` (asset). Set unit costs on components. Map in **Connected workflow accounting**. *Before enabling*, prior stock and production history will not be backposted.
3. Create supplier and approved PO in Purchasing. Receive components. If automatic postings are enabled, each receipt creates a balanced Dr Raw Inventory / Cr GRNI demo entry at standard cost.
4. Create and activate `BOX-002` Revision A with 4 bolts and 1 panel per unit; create `WO-2002` quantity 3 from the approved revision.
5. Add Assembly sequence 10 and Inspection sequence 20, release work order, reserve components, and issue 12 bolts and 3 panels. In enabled accounting mode, each material issue creates Dr WIP / Cr Raw Inventory.
6. Complete Assembly and Inspection sequentially; complete the work order. (A high-severity unresolved quality case blocks the next step.)
7. Use Production → **Finished-goods receipt** to receive 3 units of `BOX-002` to `MAIN`. The API rejects mismatched SKU, non-BOM work orders, noncompleted jobs, open high-severity work-order quality cases and duplicate receipts.
8. In Finance, inspect three kinds of system-generated balanced journals. The finished-goods entry debits Finished Goods Inventory and credits WIP for the previously posted material costs. No labor or overhead is modeled.
9. Inspect `/api/flow/work-orders/{id}`, `/api/flow/finished-receipts`, `/api/finance/operational-events`, `/api/ledger`, and `/api/audit` for traceability.

## Automated verification

- Original workflow, purchase, BOM, reservation, routing, quality, finance, migration, and security regression tests.
- New end-to-end tests verify balanced postings and trial balance with expected debit/credit totals, idempotency and rollback on missing cost, quality holds, SKU guards, and optional posting behavior.
- GitHub CI tests three Python versions and checks dashboard JavaScript syntax. No customer data was used.

## Upgrade safety

**Do not delete or overwrite the existing database.** Stop the current server, take an independent copy of `meridian.db`, then copy new application code into the project folder. The Windows startup script runs `python -m scripts.migrate_db`, which checks database integrity, saves a pre-v0.6 backup in `backups/` if needed, and adds new tables. This is an additive SQLite schema change—not a promise of full forward/backward migration or offsite recovery.

## Remaining product limitations

- Optional local demo login, not authenticated/attributed business events; inventory and manufacturing data are not tenant-isolated.
- No PostgreSQL migration, performance test at enterprise scale, SSO/MFA, penetration testing, encrypted secrets, high availability, or managed disaster recovery.
- No finished-good partial quantity, scrap, WIP labor, indirect costs, purchase-price variances, vendor AP, customer AR, taxes, bank reconciliation, period close or actual financial audit.
- Receiving via generic stock API and pre-existing transactions do not create automated accounting entries. Automatic journal posting covers **PO receipts**, **work-order material issues**, and **finished-goods receipts** only after setup.
- No real Infor/other ERP adapters or regulated quality features. This is not a commercial enterprise ERP release.

The planned portfolio implementation milestone is now complete. Additional engineering is required only if turning Meridian into a deployed customer product.
