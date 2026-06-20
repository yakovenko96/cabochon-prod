# Cabochon Odoo

Кастомизация Odoo 19 Community для учета изготовления кабошонов: партии и
мешки камней, складские зоны, операции, назначения работников, выдачи/сдачи,
брак, потери, этикетки, уведомления, отчеты и неизменяемый журнал движений.

Перед работой с проектом читайте [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

## Структура

```text
addons/
  cabochon_base/
  cabochon_manufacturing/
scripts/
  install_cabochon_modules.ps1
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

## Локальный запуск

Docker Compose находится здесь:

```text
C:\Users\Asus\data\odoo-local\docker-compose.yml
```

Запуск:

```powershell
cd C:\Users\Asus\data\odoo-local
docker compose up -d
docker compose ps
```

Веб-интерфейс:

```text
http://127.0.0.1:8069/
```

Текущая база:

```text
Cabachon
```

Рабочий каталог проекта:

```text
C:\Users\Asus\data\cabochon-prod
```

Ожидаемое подключение custom addons:

```yaml
volumes:
  - C:/Users/Asus/data/cabochon-prod/addons:/mnt/extra-addons
```

## Команды

Обновить активные модули:

```powershell
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Установить активные модули:

```powershell
docker exec odoo19-web odoo -d Cabachon -i cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Helper-скрипт обновления:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_cabochon_modules.ps1 -Database Cabachon
```

Перезапустить Odoo:

```powershell
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Проверки:

```powershell
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_base addons/cabochon_manufacturing scripts
```

Odoo-тесты Cabochon:

```powershell
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --test-enable --test-tags /cabochon_base,/cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --http-port 8070
```

## Модули

`cabochon_base` содержит меню, группы доступа, активные справочники, журнал
действий и защиту `mail.activity`.

`cabochon_manufacturing` содержит операции, складские зоны, мешки, внешний
приход, заявки, выдачи/сдачи, движения, корректировки, отчеты и этикетки.

## Основной процесс

1. Менеджер склада оформляет внешний приход.
2. Технолог создает заявку на операции и выбирает работника.
3. Подтверждение заявки создает выдачу.
4. Менеджер подтверждает выдачу, затем работник подтверждает получение.
5. Сдача фиксирует годный вес, брак и потери.
6. Менеджер подтверждает прием сдачи, затем работник подтверждает передачу.
7. Второе подтверждение создает неизменяемые движения и результирующие мешки.
8. Ошибки исправляются корректирующими движениями, а не изменением истории.

## Документация

Актуальные детали бизнес-правил, ролей, моделей и последних проверок находятся
в [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
