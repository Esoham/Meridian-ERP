# Meridian ERP v0.6 — Verified Capability Matrix

**Portfolio scope:** Working local synthetic-data manufacturing workflows; commercial deployment prohibited without substantial engineering.

| Workstream | Working local prototype | Not implemented / production blockers |
| --- | --- | --- |
| Inventory | Master data, receipts, issues, reservations, append-only ledger, availability | Transfers, adjustments/reversals, lots, serials, bins, cycle counts, UOM conversions |
| Engineering | BOM revisions, active/superseded approvals, frozen work-order component snapshots | ECO governance, alternates, effectivity dates, drawing attachments |
| Manufacturing | Work-order state machine, material reservation/issue, routing execution, finished-goods receiving | Partial builds, labor, scrap, warehouse putaway automation, capacity planning |
| Purchasing | Suppliers, PO approvals, partial receipts, duplicate guards, stock ledger integration | Invoices, three-way match, returns, price variance, payment |
| Quality | Nonconformance tracking; unresolved high-severity WO cases block FG receipt | Lot hold, quarantine, test equipment, CAPA, regulated approvals |
| Finance | Company-specific sample accounts/manual journals, trial balance, standard costs, **opt-in atomic operational posting** | Fiscal periods, AR/AP, GAAP/IFRS certification, real company-wide tenant isolation, actual cost accounting |
| UI | Enterprise-style navigation, flexible widgets, themes, quick search and custom item fields | Server-side user-specific dashboards, accessible internationalization, offline state |
| Integration | Read-only CSV preflight, auditable stock trace | Real adapters, EDI, transactional import processing, reliable event bus |
| Operations | SQLite integrity checks, additive schema migrations, manual verified backup/restore, CI | PostgreSQL HA, disaster recovery plans, observability, external security certification |
| Access | Optional local hashed-password demo roles | Default-enforced RBAC, real identity-asserted audit events, SSO/MFA, fine-grained permissions |

**Accounting-specific warning:** Any physical transactions posted before activation or from generic stock receiving remain unposted financially; historical reconciliation is not automated. Posting rules use standard unit costs and material consumption only.

## Evidence

See [`tests/test_workflow_v6.py`](../tests/test_workflow_v6.py) for complete PO → received stock → BOM → work order → issue → routing → finished goods → sample journals and idempotency/quality guard tests. See [Final Release](FINAL_RELEASE.md) for a practical walkthrough and upgrade steps.
