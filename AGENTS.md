# Agent Instructions — Cabochon Odoo

## Purpose and scope

This repository customizes **Odoo 19 Community** for cabochon manufacturing:
stone lots/bags, production operations, employee assignments, issue/receipt,
defects and losses, labels, notifications, reports, and an immutable movement journal.

Active custom modules:
- `addons/cabochon_base` — root menu, access groups, reference catalogs, audit log, mail activity rules.
- `addons/cabochon_manufacturing` — operations, zones, lots/bags, requests, issue/receipt,
  defects/losses, notifications, labels, reports, movement journal.

Do not introduce legacy modules, extra modules, or unrelated workflows without a user request.
Keep paths repository-relative; development happens in multiple workspaces.
Preserve Russian user-facing strings and UTF-8 encoding.

## Start of each task

1. Read `PROJECT_CONTEXT.md` **first**, then inspect only the relevant code, manifests,
   security files, views, and tests. Do not scan the whole repository unless necessary.
2. Confirm the desired behavior and identify impacted models, methods, views,
   security rules, reports, and data files.
3. For a nontrivial change, state a short implementation plan and the validation
   steps before editing. For a small, clear change, implement directly.
4. Follow the latest explicit user requirements. Treat `PROJECT_CONTEXT.md` as a
   navigation/decision record, not a substitute for validating current code.
   If it conflicts with code or the current request, report the discrepancy.

## Development rules

- Make the smallest cohesive change that fully solves the request; avoid unrelated refactors.
- Follow existing Odoo patterns and conventions. Prefer ORM, models, fields,
  constraints, access rules, actions and reports over ad hoc SQL.
- When changing a model, check its callers, computed fields, dependencies,
  constraints, security, XML views, reports and tests.
- When adding XML/CSV/data files, include them in `__manifest__.py` in the correct
  dependency order. Keep existing external IDs stable; do not rename/delete them
  casually, especially for installed records.
- Do not bypass `ir.model.access.csv`, record rules or company/user boundaries via
  `sudo()` without a narrowly justified need.
- Use Odoo-compatible transactions. Do not commit manually inside business methods
  unless an explicit architectural requirement warrants it.
- Preserve existing data and workflow states; explicitly assess the impact of
  schema changes, defaults, constraints, and migration requirements.
- Do not modify generated, unrelated, or legacy files just to silence checks.

## Manufacturing invariants

- Preserve traceability of stone lots/bags and their movements.
- Treat the movement journal as append-only/immutable; never silently edit or
  delete history. Corrections should use an explicit, auditable business mechanism.
- Validate quantities, ownership/assignment, state transitions, and permitted
  roles before changing production or inventory state.
- Prevent duplicate posting/receipt or double counting on retries where relevant.
- Never infer a specific business rule not documented in code or context: identify
  uncertainty instead of inventing a workflow.

## Data and execution safety

- **Database `Prod` is potentially production.** Do not assume it is safe for tests.
- Do not execute module installation/update (`-i`, `-u`), migrations, destructive
  SQL, resets, data deletion, or seed/test-data writes against `Prod` without
  explicit authorization for that operation.
- Prefer a dedicated disposable/dev/test database for Odoo installation, module
  updates, and integration tests.
- Never embed database passwords, tokens, or other secrets in this file, commands,
  logs, or responses. Use approved environment/configuration mechanisms.
- Do not change infrastructure, deployment configuration, or permissions beyond
  the requested scope without explaining the impact first.

## Verification

Choose checks appropriate to the touched files, and report their actual outcomes:

1. Inspect the diff for unintended changes and whitespace/encoding problems.
2. Run lint for Python changes, when available:
   `python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts`
3. For XML, CSV, security, and manifest changes, inspect schema/reference integrity,
   external IDs, access rights, load order, and Odoo view compatibility.
4. Run applicable unit/integration tests; for changes to workflows, also test both
   success and rejection paths and role-specific access.
5. Run an Odoo module update only on an explicitly approved target database and
   when Docker/Odoo is available. Use existing project scripts/configuration; do
   not invent credentials or claim that an update ran if it did not.
6. If a check cannot be run, specify why, what remains unverified, and the exact
   safe command or manual step for a developer to run.

Definition of done: requested behavior implemented, relevant error/permission paths
considered, validations completed or explicitly marked blocked, and necessary
project context updated.

## Working commands

Use project scripts where possible; check their options before running.

```powershell
# Static lint (safe)
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts

# Odoo module commands only with an approved development/test database.
# Project helper examples (do not point them at Prod without authorization):
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database <approved_db> -Install
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database <approved_db>
```

The environment may use the `odoo19-web` Docker container and `db` Postgres host.
Check actual local settings instead of assuming they are available.

## Project context maintenance

`PROJECT_CONTEXT.md` stores the active module map, business flow, roles/access,
models, reports/labels, safe commands, testing notes, and important decisions.
Update it in the same task **only if** a meaningful behavior, model, security rule,
command, test status, or architectural decision changes. Keep changes concise,
remove outdated statements, and do not append repetitive task diaries.
Do not write unverified claims as facts.

## Response format

At completion, summarize:
- **Changed:** files and observable behavior.
- **Verified:** commands/tests run and results.
- **Not verified / risks:** remaining checks, especially database/module updates.
- **Context:** whether `PROJECT_CONTEXT.md` changed and why.

Ask before risky execution; otherwise proceed autonomously within the requested scope.
