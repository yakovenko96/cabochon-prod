---
name: odoo19-development
description: Safely implement, review and test Cabochon Odoo 19 Community customizations in cabochon_base and cabochon_manufacturing; use for Odoo models, XML views, access controls, workflow transitions, movements, migrations and regression testing.
---

# Cabochon Odoo 19 development

## Start
1. Read `PROJECT_CONTEXT.md`; read `docs/BUSINESS_RULES.md` for affected workflow and `docs/MODELS_AND_ROLES.md` for roles/models.
2. Inspect actual code, manifest, existing tests and Odoo version; note documentation discrepancies.
3. Identify affected company, role, state transition, stock/weight invariant and upgrade implications.

## Implementation rules
- Change only active modules unless user explicitly extends scope.
- Use ORM for business writes; avoid ad-hoc SQL and broad `sudo()`.
- Security: inspect `ir.model.access.csv`, record rules, group inheritance, multi-company boundaries and whether a worker can bypass UI restrictions via RPC.
- Workflow: draft vs final timestamps, double confirmation, idempotency and reservations. Do not mutate posted movement history.
- Stock: check nonnegative quantities, source/target balancing, defect/loss and finished-position aggregation, concurrent commits.
- XML: ensure external IDs, action references, dependencies and manifest load order.
- Data migrations and SQL views: check clean install, upgrades from an existing backup and rollback strategy.

## Tests
- Add Odoo regression tests around business behavior rather than only field existence.
- Prefer `TransactionCase` for ORM rules; use `HttpCase`/browser verification for UI pathways where appropriate.
- Test positive + negative permissions per role and other-company boundaries.
- Test partial/final/zero receipts, repeated confirmation and concurrency whenever related logic changes.
- Run Ruff, compileall, XML validation and existing Odoo tests on disposable DB only.
- Do not fabricate a passing test status; report blocked checks explicitly.

## Completion report
Summarize changed files, key behavior, validations and observed outcomes, unrun checks, database/migration risks, and documentation updates.
