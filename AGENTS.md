# Agent Project Context

Read `PROJECT_CONTEXT.md` first. It is the living project file and should be
updated after each functional change.

This file is the bootstrap instruction file for agents working in:

```text
C:\Users\Asus\data\cabochon-prod
```

## First Step

Before scanning the repository, open:

```text
PROJECT_CONTEXT.md
```

Use it as the current source of truth for:

- active modules;
- commands;
- business flow;
- roles and access;
- current models;
- reports and labels;
- test notes;
- recent functional decisions.

If you change behavior, models, XML views, security rules, data, commands, or
test status, update `PROJECT_CONTEXT.md` in the same turn.

## Project

Cabochon Odoo is an Odoo 19 Community customization for tracking cabochon
manufacturing by stone lots/bags, production operations, employee assignments,
material issue/receipt, defects, losses, labels, notifications, reports, and
immutable movement history.

Main workspace:

```text
C:\Users\Asus\data\cabochon-prod
```

Custom addons:

```text
C:\Users\Asus\data\cabochon-prod\addons
```

Docker Compose lives outside this repository:

```text
C:\Users\Asus\data\odoo-local\docker-compose.yml
```

Current database:

```text
Cabachon
```

Do not use old database names in commands.

## Active Modules

Only these custom modules are part of the current iteration:

```text
cabochon_base
cabochon_manufacturing
```

Do not add modules or flows outside the current lot-and-operation specification
unless the user asks for them explicitly.

## Commands

Install/update active modules:

```powershell
docker exec odoo19-web odoo -d Cabachon -i cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Update after code changes:

```powershell
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Helper script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_cabochon_modules.ps1 -Database Cabachon
```

Restart Odoo:

```powershell
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Lint:

```powershell
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
```

## Module Map

`addons/cabochon_base`

Base module. Defines root menu, access groups, active reference catalogs, audit
log, and Cabochon mail activity rules.

`addons/cabochon_manufacturing`

Current business module for the lot-and-operation manufacturing specification.
It owns operations, storage zones, stone lots/bags, production requests,
issue/receipt documents, defect and loss registration, notifications, labels,
reports, and the movement journal.

## Editing Notes

- Keep changes scoped to `cabochon_base` and `cabochon_manufacturing`.
- Do not add dependencies on removed legacy modules.
- When adding XML/CSV/data files, include them in the manifest before views that
  need them.
- Preserve Russian user-facing text as UTF-8.
- Prefer structured Odoo models, record rules, reports, and actions over manual
  SQL or ad hoc string parsing.
- After Python, XML, CSV, data, or manifest changes, run lint and an Odoo module
  update when Docker is available.
- After every meaningful change, update `PROJECT_CONTEXT.md`.
