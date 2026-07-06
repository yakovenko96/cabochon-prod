# Cabochon Odoo

Кастомизация Odoo 19 Community для учета изготовления кабошонов: мешки камней,
складские зоны, операции, заявки, выдачи/сдачи, брак, потери, этикетки,
уведомления, отчеты и неизменяемый журнал движений.

Актуальные рабочие правила и последние проверки ведутся в
[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

## Структура

```text
addons/
  cabochon_base/
  cabochon_manufacturing/
scripts/
  install_modules.ps1
AGENTS.md
PROJECT_CONTEXT.md
README.md
pyproject.toml
```

Активные модули:

```text
cabochon_base
cabochon_manufacturing
```

## Установка Модулей

База разработки:

```text
Cabachon
```

Скрипт `scripts/install_modules.ps1` не создает базу Odoo. Он работает с уже
созданной базой и устанавливает или обновляет в ней активные модули:

```text
cabochon_base,cabochon_manufacturing
```

После установки в базе появятся меню, группы, права, системные операции и
складские зоны. Бизнес-данные при чистой установке остаются пустыми: без
мешков, заявок, выдач/сдач и движений. Пользователей, сотрудников, группы
пользователей и менеджеров складских зон нужно настроить отдельно.

### Docker

Первый запуск на уже созданной базе, где модули еще не установлены:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon -Install
```

Повторный запуск после изменений кода:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon
```

Ручная команда установки через Docker:

```powershell
docker exec odoo19-web odoo -d Cabachon -i cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Ручная команда обновления через Docker:

```powershell
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

### Без Docker

Так тоже можно. На машине должен быть развернут Odoo 19 и создана база. Папку
`addons` этого проекта нужно добавить в `addons_path` конфигурации Odoo,
например:

```ini
addons_path = C:\path\to\odoo\addons,C:\path\to\cabochon-prod\addons
```

После этого обновите список приложений в Odoo или запустите установку из
консоли.

Первый запуск через локальный `odoo-bin`:

```powershell
odoo-bin -d Cabachon -i cabochon_base,cabochon_manufacturing --stop-after-init --config C:\path\to\odoo.conf
```

Обновление через локальный `odoo-bin`:

```powershell
odoo-bin -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --config C:\path\to\odoo.conf
```

Первый запуск через helper-скрипт без Docker:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon -Install -OdooBin C:\path\to\odoo-bin.exe -Config C:\path\to\odoo.conf -DbHost localhost -DbPort 5432 -DbUser odoo -DbPassword 123321
```

Обновление через helper-скрипт без Docker:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon -OdooBin C:\path\to\odoo-bin.exe -Config C:\path\to\odoo.conf -DbHost localhost -DbPort 5432 -DbUser odoo -DbPassword 123321
```

Проверки:

```powershell
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_base addons/cabochon_manufacturing scripts
```

## Модули

`cabochon_base` содержит корневое меню, группы доступа, активные справочники,
журнал действий и защиту Cabochon-активностей.

`cabochon_manufacturing` содержит операции, складские зоны, мешки, внешний
приход, заявки, выдачи/сдачи, движения, корректировки, отчеты, продажу/выдачу
готовых камней и этикетки.
