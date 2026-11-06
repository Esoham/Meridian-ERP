# Meridian ERP Roadmap

| Stage | Product capability | Exit criteria |
| --- | --- | --- |
| 0 — now | Local demo: item master, location, receipt, work order, material issue, immutable ledger, audit | Pass automated workflow/rollback/idempotency tests; demo with synthetic data |
| 1 | Reliable inventory core: adjustments with reversal references, transfers, reservations, batch/lot, UOM precision | Financially and operationally consistent scenarios; reconciled stock snapshots |
| 2 | True manufacturing: versioned BOMs, routes/operations, WIP, scrap, partial completion, finished-good receipts | End-to-end simulated manufacturing lifecycle |
| 3 | Integration and migration: imports, event feeds, read-only connectors, mapping, exception validation | Repeatable migration reconciliation using fictional representative data |
| 4 | Enterprise security: identity/SSO, scoped RBAC, tenant isolation, PostgreSQL, migrations, backups, restore tests | Threat model and security review before customer pilot |
| 5 | AI intelligence: explanation and prioritization with source-linked evidence, human approval gates | Evaluation dataset, negative controls, documented limitations, audit traces |
| 6 | Commercial readiness: implementation support, monitoring, documentation, pricing, compliance evidence | Approved customer pilot, support and operational SLAs |

**Positioning:** Start with smaller manufacturers needing better inventory/material reconciliation and a low-friction overlay to existing ERPs. Replacing Fortune 500 systems is a distant commercial ambition, not a current capability or claimed market share.
