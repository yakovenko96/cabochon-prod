# Cabochon Odoo

Кастомизация Odoo 19 Community для учета изготовления кабошонов: мешки камней,
складские зоны, операции, заявки, выдачи/сдачи, брак, потери, готовый склад,
этикетки, отчеты и неизменяемый журнал движений.

Актуальный рабочий контекст, проверенные команды и статус чистого запуска
ведутся в [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

## Состав

Активные модули:

```text
cabochon_base
cabochon_manufacturing
```

`cabochon_base` содержит корневое меню, группы доступа, справочники, аудит и
защиту Cabochon-активностей.

`cabochon_manufacturing` содержит операции, складские зоны, мешки, внешний
приход, производственные заявки, выдачи/сдачи, брак, возврат брака, готовый
склад, корректировки, отчеты и этикетки.

## Установка

Текущая рабочая база:

```text
Prod
```

База Odoo должна быть создана заранее. Первый запуск модулей:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Prod -Install
```

Обновление после изменений:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Prod
```

Ручные Docker-команды:

```powershell
docker exec odoo19-web odoo -d Prod -i cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
docker exec odoo19-web odoo -d Prod -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Без Docker добавьте папку `addons` проекта в `addons_path` Odoo 19 и запускайте
`odoo-bin` с `-i` для первой установки или `-u` для обновления.

## Старт с нуля

При чистой установке создаются меню, права, системные операции и складские
зоны. Бизнес-данные остаются пустыми: без мешков, заявок, выдач, сдач и
движений.

После установки нужно настроить пользователей и сотрудников, назначить группы
Cabochon, указать менеджеров зон `raw`, `prepared`, `semi_finished`,
`finished`, заполнить справочники и разрешенные операции работников.

Smoke-проверку запускайте только на временной базе, потому что сценарий создает
тестовые записи:

```powershell
docker exec odoo19-db createdb -U odoo CabochonSmoke
docker exec odoo19-web odoo -d CabochonSmoke -i cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
Get-Content -Raw -Encoding UTF8 scripts\smoke_zero_start.py | docker exec -i odoo19-web odoo shell -d CabochonSmoke --db_host db --db_port 5432 --db_user odoo --db_password 123321
docker exec odoo19-db dropdb -U odoo --if-exists --force CabochonSmoke
```

Успешный результат smoke-сценария:

```text
SMOKE_ZERO_START_OK
```

## Проверки

```powershell
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_base addons/cabochon_manufacturing scripts
python -c "from pathlib import Path; import xml.etree.ElementTree as ET; [ET.parse(p) for p in Path('addons').rglob('*.xml')]; print('XML OK')"
```

## Текущие правила учета

- Несколько исходных мешков разрешены только для операции `Трубы` и только с
  одинаковым годом и месяцем добычи.
- На формах сдачи остаток считается от выданного веса с учетом частичных сдач.
- Брак агрегируется по операции, форме, типу формы и цвету; размер при возврате
  брака выбирается вручную.
- Готовый склад объединяет вес по форме, типу формы, размеру и цвету; количество
  считается от эталонного веса размера.
