# Контекст проекта Cabochon Odoo

Живой краткий контекст для работы с проектом. Читайте этот файл перед
изменениями и обновляйте его после функциональных правок, изменений моделей,
XML, security, data, команд или статуса проверок.

## Снимок

Cabochon Odoo — кастомизация Odoo 19 Community для учета изготовления
кабошонов: партии/мешки камней, складские зоны, производственные операции,
назначения работников, выдачи/сдачи, брак, потери, этикетки, уведомления,
отчеты и неизменяемый журнал движений.

Рабочая папка:

```text
C:\Users\Asus\data\cabochon-prod
```

Custom addons:

```text
C:\Users\Asus\data\cabochon-prod\addons
```

Docker Compose:

```text
C:\Users\Asus\data\odoo-local\docker-compose.yml
```

Текущая база:

```text
Cabachon
```

Не используйте старые имена баз в командах.

## Активные модули

Текущая итерация включает только:

```text
cabochon_base
cabochon_manufacturing
```

Не добавляйте зависимости от удаленных legacy-модулей.

## Команды

Обновить активные модули:

```powershell
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Установить активные модули:

```powershell
docker exec odoo19-web odoo -d Cabachon -i cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Helper-скрипт:

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

## Карта модулей

`cabochon_base`:

- корневое меню Кабошонов;
- группы доступа;
- базовые справочники;
- поля Cabochon на `product.template`;
- журнал действий `cabochon.audit.log`;
- защита Cabochon `mail.activity`.

`cabochon_manufacturing`:

- операции и складские зоны;
- годы добычи и фракции;
- партии/мешки камней;
- внешний приход;
- производственные заявки;
- документы выдачи/сдачи;
- строки документов;
- неизменяемый журнал движений;
- корректировки движений;
- допуски работников к операциям;
- отчеты и A6-этикетки.

## Ключевые модели

База:

```text
cabochon.stone.type
cabochon.form.type
cabochon.shape
cabochon.color
cabochon.size
cabochon.defect.type
cabochon.audit.log
product.template
```

Производство:

```text
cabochon.manufacturing.operation
cabochon.extraction.year
cabochon.fraction
cabochon.manufacturing.location
cabochon.stone.lot
cabochon.production.request
cabochon.production.request.operation.line
cabochon.material.transfer
cabochon.material.transfer.line
cabochon.manufacturing.movement
cabochon.movement.correction.wizard
cabochon.external.receipt.wizard
cabochon.worker.load.report
cabochon.worker.operation.quality.report
```

## Бизнес-процесс

1. Менеджер склада создает внешний приход сырья или подготовленного сырья.
2. Приход создает мешок и начальное движение.
3. Технолог создает заявку, выбирает работника, операции, исходный мешок,
   плановый вес, срок и приоритет.
4. Работник фильтруется по допускам к выбранным операциям.
5. Операции в заявке проверяются по маршруту мешка: помывка, сортировка,
   взаимоисключающие группы и запрет повтора уже выполненных этапов.
6. Подтверждение заявки создает документ выдачи.
7. Подтверждение выдачи переносит вес на личный склад работника, запускает
   первую строку операции и создает черновик сдачи.
8. Сдача фиксирует годный вес, брак и потери. Потери считаются как
   `weight_before_g - weight_g - defect_weight_g`.
9. Подтверждение сдачи создает движения прихода, брака и потерь, а для годного
   веса создает результирующие мешки.
10. Подтвержденные движения неизменяемы. Исправления создаются корректировками.

## Операции и склады

Складские зоны:

```text
raw
prepared
semi_finished
finished
employee
loss
```

Активные операции по умолчанию:

```text
tumble_wash
toluene_wash
auto_separator
manual_sorting
stone_preparation
press
normalization
cabochon_machine
ball_machine
cnc
grinding_polishing
husking
drilling
tinting
```

`sorting` остается в справочнике как неактивная legacy-операция и не доступна
для новых заявок.

Для финальных операций технолог выбирает склад сдачи: полуфабрикаты или готовые
камни. Без явного выбора результат идет на полуфабрикаты.

## Роли и доступ

Группы:

```text
cabochon_base.group_cabochon_user
cabochon_base.group_cabochon_fixer
cabochon_base.group_cabochon_manager
cabochon_base.group_cabochon_workshop_manager
cabochon_base.group_cabochon_finished_manager
cabochon_base.group_cabochon_admin
```

Роли:

- технолог: `group_cabochon_workshop_manager`;
- менеджер сырья/подготовки/полуфабрикатов: `group_cabochon_manager`;
- менеджер готового склада: `group_cabochon_finished_manager`;
- работник: `group_cabochon_fixer` или базовый `group_cabochon_user`;
- администратор: `group_cabochon_admin`.

Record rules ограничивают мешки, заявки, выдачи/сдачи, строки, складские зоны и
движения по работнику, ответственности менеджера склада или полному доступу
технолога.

## Отчеты и уведомления

Отчеты:

- журнал движений;
- качество по работникам и операциям;
- время операций;
- панель нагрузки работников.

`mail.activity` используется для черновиков выдачи/сдачи, просроченных заявок и
потерь выше нормы. Cron просрочки запускает:

```python
model._cron_notify_overdue_requests()
```

## Справочники

Начальные годы добычи: `2020`-`2027`.

Начальные фракции:

```text
5
6
7
8
```

Работники не имеют прямого доступа к справочникам. Технолог и администратор
могут вести все справочники. Менеджер готового склада не видит меню
справочников.

## Статусы

Заявки:

```text
draft = Новая
confirmed = Ожидает выдачи
issued = Выдано
in_progress = В работе
partially_done = Частично сдано
done = Закрыта
cancelled = Отменена
```

Выдачи/сдачи:

```text
draft = Ожидает обработки
confirmed = Подтверждено
```

Списки сортируются по техническому `state_order`: активные и ожидающие записи
идут выше закрытой/подтвержденной истории.

## Правила редактирования

- Держите изменения в рамках `cabochon_base` и `cabochon_manufacturing`.
- Сохраняйте русские пользовательские строки в UTF-8.
- Предпочитайте ORM, views, actions, reports и record rules ручному SQL.
- При XML/CSV/data/manifest изменениях добавляйте файлы в manifest до views,
  которые на них ссылаются.
- После изменений Python/XML/CSV/data/manifest запускайте lint и обновление
  модулей, если Docker доступен.
- После значимых изменений обновляйте этот файл.

## Последняя проверка

2026-06-17 выполнена уборка проектных артефактов:

- удалены устаревшие `SYSTEM_FUNCTIONS.md`, `LINTING.md`, `Project_info.docx`;
- удален старый сломанный скрипт `scripts/populate_cabochon_test_database.py`;
- удалена пустая неиспользуемая группа `group_cabochon_supervisor`;
- `README.md` и этот файл сокращены до актуального состояния;
- старый Odoo-тест аудита оставлен, он проходит и проверяет важное поведение.

Проверка перед уборкой:

```text
ruff passed
compileall passed
xml parse passed
csv parse passed
module update passed
odoo test /cabochon_base passed
database mojibake checks passed
odoo restarted
git status clean
```
