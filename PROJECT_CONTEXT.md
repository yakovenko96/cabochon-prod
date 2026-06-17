# Контекст проекта Cabochon Odoo

Это короткий живой файл контекста проекта. Его нужно читать перед сканированием
репозитория. После каждого функционального изменения обновляйте здесь поведение,
модели, команды или заметки о проверках.

## Текущий снимок

Cabochon Odoo — кастомизация Odoo 19 Community для учета изготовления
кабошонов. Система отслеживает партии/мешки камней, складские зоны,
последовательные производственные операции, назначение работников, выдачу и
сдачу материалов, брак, потери, неизменяемую историю движений, этикетки,
уведомления, справочники с ограниченным доступом и отчеты.

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

В текущей итерации активны только эти custom-модули:

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

Линтинг:

```powershell
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
```

## Карта модулей

`cabochon_base` отвечает за:

- корневые меню;
- группы доступа Кабошонов;
- базовые справочники;
- поля Cabochon на шаблоне продукта;
- журнал аудита;
- защиту действий `mail.activity` для документов Кабошонов.

Важные файлы:

```text
addons/cabochon_base/security/cabochon_groups.xml
addons/cabochon_base/security/ir.model.access.csv
addons/cabochon_base/security/cabochon_activity_rules.xml
addons/cabochon_base/models/cabochon_references.py
addons/cabochon_base/models/audit_log.py
addons/cabochon_base/models/mail_activity.py
addons/cabochon_base/models/product_template.py
```

`cabochon_manufacturing` отвечает за:

- производственные операции;
- складские зоны;
- годы добычи и фракции;
- партии/мешки камней;
- внешний приход сырья/подготовленного сырья;
- производственные заявки;
- документы выдачи/сдачи;
- строки документов;
- неизменяемый журнал движений;
- мастер корректировок;
- допуски работников к операциям;
- панель нагрузки и отчет по браку/потерям;
- A6-этикетки мешков.

Важные файлы:

```text
addons/cabochon_manufacturing/models/cabochon_manufacturing.py
addons/cabochon_manufacturing/models/cabochon_reports.py
addons/cabochon_manufacturing/models/hr_employee.py
addons/cabochon_manufacturing/data/cabochon_manufacturing_data.xml
addons/cabochon_manufacturing/security/ir.model.access.csv
addons/cabochon_manufacturing/security/cabochon_manufacturing_rules.xml
addons/cabochon_manufacturing/views/cabochon_manufacturing_views.xml
addons/cabochon_manufacturing/views/cabochon_manufacturing_menus.xml
addons/cabochon_manufacturing/views/hr_employee_views.xml
```

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
```

## Текущий бизнес-процесс

1. Менеджер склада создает внешний приход сырья или подготовленного сырья.
2. Приход создает мешок с фракцией, годом/месяцем добычи, весом, складской
   зоной и начальным движением прихода.
3. Технолог создает заявку на одну или несколько операций, указывает работника,
   исходный мешок, плановый вес к выдаче, срок и приоритет.
4. Выбор работника ограничен допусками к операциям в `hr.employee`.
5. При повторном выборе исходного мешка плановый вес обновляется из текущего
   веса выбранного мешка.
6. Подтверждение заявки создает документ выдачи для менеджера исходного склада.
7. Подтверждение выдачи переносит вес на личную складскую зону работника.
   Частичная выдача создает дочерний выданный мешок.
8. После выдачи заявка автоматически переходит в работу, запускается первая
   строка операции и создается черновик сдачи для менеджера склада назначения.
9. В строках сдачи фиксируются годный вес, вес брака и автоматические потери:
   `weight_before_g - weight_g - defect_weight_g`.
10. Подтверждение сдачи проверяет назначенного менеджера склада и не позволяет
    сдать больше исходного веса.
11. Подтверждение сдачи создает движения прихода, брака и потерь, создает
    дочерние мешки для годных строк и обновляет исходный выданный мешок.
12. Заявку можно закрыть после сдачи; открытые строки операций завершаются.
13. Подтвержденные движения неизменяемы. Исправления создаются отдельными
    корректирующими движениями.

## Склады и операции

Складские зоны:

```text
raw
prepared
semi_finished
finished
employee
loss
```

Операции по умолчанию:

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
sorting
drilling
tinting
```

Финальные операции маршрутизируются на `finished`.

## Справочники

`cabochon.extraction.year` изначально содержит годы `2020`-`2027`.

`cabochon.fraction` изначально содержит:

```text
5
6
7
8
```

Работники не имеют прямого доступа к справочникам. Менеджеры складов сырья,
подготовленного сырья и полуфабрикатов могут вести годы добычи, фракции и тип
сырья. Технолог и администратор могут вести все справочники. Менеджер готового
склада не видит меню справочников.

## Статусы, сортировка и интерфейс

Статусы производственной заявки:

```text
draft = Новая
confirmed = Ожидает выдачи
issued = Выдано
in_progress = В работе
partially_done = Частично сдано
done = Закрыта
cancelled = Отменена
```

Статусы выдачи/сдачи:

```text
draft = Ожидает обработки
confirmed = Подтверждено
```

Списки сортируются по техническому `state_order`: активные и ожидающие записи
идут выше подтвержденных/закрытых.

Цвета списков:

- желтый — нужно действие или идет работа;
- красный — просроченная производственная заявка;
- приглушенный — закрытая, отмененная или подтвержденная история.

У работника нет кнопок действий по заявкам, операциям, выдачам и сдачам.

Фильтры есть для активных/ожидающих заявок, просрочки, заявок в работе, заявок
технолога, заявок работника, черновиков выдачи/сдачи назначенного менеджера,
типов выдачи/сдачи и подтвержденной истории.

## Уведомления

Используется `mail.activity`:

- менеджеры складов получают действия по черновикам выдачи/сдачи, назначенным
  на них;
- технологи получают действия по просроченным производственным заявкам;
- действия по выдаче/сдаче удаляются автоматически после подтверждения или
  удаления черновика;
- действия по просрочке удаляются после закрытия, отмены или устранения
  просрочки.

Cron:

```text
Кабошоны: уведомления о просроченных заявках
```

Запускается каждые 15 минут и вызывает:

```python
model._cron_notify_overdue_requests()
```

Правила Cabochon activity ограничивают обычных пользователей их собственными
назначенными действиями.

## Отчеты и этикетки

Отчеты строятся на `cabochon.manufacturing.movement` и связанных views.

Доступные области отчетов:

- журнал движений;
- отчет по браку и потерям по работнику и операции;
- отчет по времени операций;
- панель нагрузки работников.

Этикетки мешков печатаются в PDF на формате A6:

```text
105mm x 148mm
```

## Модель доступа

Текущие группы:

```text
cabochon_base.group_cabochon_user
cabochon_base.group_cabochon_manager
cabochon_base.group_cabochon_workshop_manager
cabochon_base.group_cabochon_finished_manager
cabochon_base.group_cabochon_admin
```

Роли:

- технолог: `group_cabochon_workshop_manager`;
- менеджер склада сырья/подготовки: `group_cabochon_manager`;
- менеджер склада полуфабрикатов: `group_cabochon_manager`;
- менеджер готового склада: `group_cabochon_finished_manager`;
- работник: `group_cabochon_user`;
- администратор: `group_cabochon_admin`.

Record rules ограничивают мешки, заявки, выдачи/сдачи, строки, складские зоны и
движения по работнику, ответственности менеджера склада или полному доступу
технолога.

`cabochon.stone.lot` хранит `security_manager_user_ids` для правил доступа
менеджеров. Это убирает глубокий обход через строки выдачи/сдачи в основном
правиле складских остатков.

`cabochon.worker.load.report` вынесен в:

```text
addons/cabochon_manufacturing/models/cabochon_reports.py
```

ACL панели нагрузки ограничен технологом/администратором.

## Заметки о проверках

Последний полный прогон:

```text
TEST-FULL-20260614-144332
```

Покрывал:

- внешний приход сырья и подготовленного сырья;
- тестовые стартовые остатки для полуфабрикатов и готового склада;
- заявки технолога;
- все 15 операций;
- маршруты из нескольких операций;
- выдачу и сдачу менеджерами сырья/подготовки, полуфабрикатов и готового склада;
- движения выдачи, прихода, брака и потерь;
- автоматический расчет потерь на server-side write строки сдачи;
- сортировку по статусам;
- действие отчета по браку;
- рендеринг PDF-этикетки A6.

Результат:

```text
FULL TEST RUN PASSED
```

Smoke-заявки из проверки сортировки были закрыты/отменены после прогона.

Последнее обновление модулей после улучшений доступа, отчетов и уведомлений:

```text
2026-06-14 15:48 Europe/Moscow
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Результат:

```text
ruff passed
module update passed
odoo restarted
```

## Правила редактирования

- Держите функциональные изменения в рамках `cabochon_base` и
  `cabochon_manufacturing`.
- Обновляйте этот файл после каждого значимого изменения кода, XML, security,
  data или workflow.
- Сохраняйте русские пользовательские тексты в UTF-8.
- Предпочитайте ORM, views, actions, reports и record rules ручному SQL.
- Если нужна миграция данных, явно укажите это в ответе и по возможности
  сделайте ее идемпотентной.
- После изменений Python/XML/CSV/manifest/data запускайте lint и обновление
  модулей, если Docker доступен.

## Последние изменения

2026-06-16 устранены замечания по приходу, выдаче/сдаче, маршрутам, доступам и отображению полей:

- внешний приход больше не содержит параметры сырья; при ручном вводе ID мешка проверяется, что мешок или штрихкод с таким ID еще не существует; номера накладных остаются обычным реквизитом и могут повторяться на разные даты;
- выдача работнику больше не создает новый ID для выданного мешка: исходный мешок переходит на личный склад работника; если выдается часть веса, остаток остается отдельным складским мешком, а ID выданного работнику мешка сохраняется;
- для заявок добавлен серверный контроль маршрута: помывка в галтовке/толуоле, ручная сортировка/авто-сепаратор, пресс/подготовка камня, шарокрутка/кабошонерка/ЧПУ взаимоисключающие; операции после помывки недоступны без одной из помывок, операции после сортировки недоступны без ручной сортировки или авто-сепаратора;
- доступные мешки в заявке фильтруются по выбранным операциям, а доступные операции — по текущему маршруту выбранного мешка;
- в сдаче общие потери по нескольким строкам одного исходного мешка пересчитываются уже в черновике при редактировании строк;
- сдачи после помывки в галтовке или толуоле автоматически закрывают заявку полностью;
- поле `Вес годного` переименовано в `Фактический вес`; блок фактического времени скрыт в черновой заявке;
- строки сдачи используют справочники цвета, размера, формы и типа формы; для сортировки обязательны тип сортировки, цвет и размер, для пресса обязательны форма, размер и цвет; лишние поля скрываются по операции, поле результата `Новый мешок` видно только после подтверждения;
- при обновлении модуля старые текстовые значения цвета, размера, формы и типа формы идемпотентно переносятся в новые справочники для мешков и строк сдачи;
- отчетный мешок для движения прихода теперь берется из полученного мешка, а исходный вес движения не суммируется в списке/сводной истории маршрута;
- активности `Потери выше нормы` синхронизируются с условием: удаляются при закрытии/отмене заявки или после изменения нормы потерь, если превышения больше нет;
- менеджеры склада видят документы выдачи/сдачи по назначенному кладовщику/приемщику, поэтому менеджер полуфабрикатов не видит сдачи, назначенные менеджеру готовых камней;
- менеджерам складов и менеджерам готовых камней разрешено добавлять значения справочников цвета, размера, формы и типа формы из выпадающих списков.

Проверка:

```text
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_manufacturing addons/cabochon_base
XML parse addons/cabochon_manufacturing/views/cabochon_manufacturing_views.xml
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Результат:

```text
ruff passed
compileall passed
xml parse passed
module update passed
odoo restarted
```

2026-06-17 исправлены два замечания по заявке технолога:

- поле `cabochon.production.request.lost_weight_g` переименовано с `Потери без сдачи, г` на `Потери, г`;
- выбор операций в заявке технолога больше не блокируется до выбора исходного мешка: при пустом `source_lot_id` домен операций показывает все активные операции, после выбора мешка снова применяет ограничения маршрута через `eligible_operation_ids`;
- onchange-домены заявки синхронизированы с тем же правилом.

Проверка:

```text
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_manufacturing addons/cabochon_base
XML parse addons/cabochon_manufacturing/views/cabochon_manufacturing_views.xml
XML parse addons/cabochon_manufacturing/data/cabochon_manufacturing_data.xml
```

Результат:

```text
ruff passed
compileall passed
xml parse passed
```

Примечание: обновление модулей в базе `Cabachon` не выполнено в этой сессии,
потому что `docker exec` потребовал elevated-доступ, а auto-review отклонил
запрос из-за usage limit. После восстановления доступа нужно выполнить стандартную
команду обновления `cabochon_base,cabochon_manufacturing`.

2026-06-15 уточнен цикл операций и разбивки мешков:

- в `cabochon.stone.lot` добавлена вычисляемая вкладка `История операций`, показывающая движения по мешку, его родителям и дочерним мешкам в хронологическом порядке;
- в `cabochon.production.request` добавлен вычисляемый список доступных операций для выбранного мешка: операции, уже подтвержденно выполненные на самом мешке или по цепочке его исходных мешков, больше не доступны технологу и дополнительно блокируются серверной проверкой; соседние дочерние мешки не влияют друг на друга;
- при сдаче нескольких строк по одному исходному мешку общий годный вес плюс общий брак проверяются против входного веса исходного мешка; потери считаются один раз по итогу группы строк, а не отдельно от полного веса на каждой строке;
- дочерние мешки при сдаче получают ID вида `исходный-1`, `исходный-2` и наследуют справочные признаки исходного мешка, если в строке сдачи они не указаны явно;
- в списке строк документа выдачи/сдачи явно разрешено удаление строк в черновике; подтвержденные документы и строки по-прежнему неизменяемы.

Проверка:

```text
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_manufacturing addons/cabochon_base
XML parse addons/cabochon_manufacturing/views/cabochon_manufacturing_views.xml
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Результат:

```text
ruff passed
compileall passed
xml parse passed
module update passed
odoo restarted
```

2026-06-14 добавлены функции контроля качества:

- в `cabochon.manufacturing.operation` добавлено поле `expected_loss_percent`
  (`Норма потерь, %`);
- в `cabochon.manufacturing.movement` добавлены поля исходного веса строки,
  фактического процента потерь, нормы потерь, отклонения от нормы и признака
  `Потери выше нормы`;
- при создании loss-движения выше нормы технолог получает `mail.activity`
  `Потери выше нормы`;
- отчет `cabochon.worker.operation.quality.report` добавлен в
  `addons/cabochon_manufacturing/models/cabochon_reports.py`;
- меню `Качество по работникам и операциям` добавлено в раздел отчетов;
- кнопка мешка `История маршрута` теперь открывает движения по выбранному
  мешку, его родителям и дочерним мешкам;
- роль-схема складов не менялась: менеджер сырья/подготовки и менеджер
  полуфабрикатов остаются в складской группе с доступом через закрепленные
  складские зоны, менеджер готового склада остается отдельной группой.

Проверка:

```text
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Результат:

```text
ruff passed
module update passed
odoo restarted
```
2026-06-17 устранены замечания по выбору операций, сортировке, подтвержденным документам и сдаче финального этапа:

- выбор операций в заявке теперь нормализуется сразу при onchange: взаимоисключающие операции убираются из выбранного списка, а доступный список учитывает как выбранный мешок, так и уже выбранные операции;
- серверная проверка маршрута блокирует повтор уже выполненной операции и всю взаимоисключающую группу, если одна из операций группы уже была выполнена на мешке или его исходной цепочке; связки вроде `помывка + ручная/авто сортировка` в одной заявке разрешены;
- поле `Тип сортировки` в заявке показывается только для `manual_sorting` и `auto_separator` и автоматически получает значение `Ручная` или `Авто`; строки сдачи сортировки наследуют этот тип;
- при добавлении новой строки в сдачу автоматически подставляется исходный мешок из документа/заявки и вес до операции;
- подтвержденные выдачи/сдачи и их строки защищены от добавления, изменения и удаления; формы заявки и выдачи/сдачи переведены в readonly для ключевых полей после подтверждения;
- новые мешки после сдачи получают ID с кодами операций, например `исходный-SORT-M-1` или `исходный-PRS-NORM-1`, вместо простого числового суффикса;
- для финальной операции годный вес идет на склад готовых камней, а движения брака и потерь по той же сдаче маршрутизируются на склад полуфабрикатов;
- пункт меню отчета `Время операций` переименован в `Отчет по времени операций`, чтобы не путать его со справочником `Операции`.

Проверка:

```text
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_manufacturing addons/cabochon_base
XML parse addons/cabochon_manufacturing/views/cabochon_manufacturing_views.xml
XML parse addons/cabochon_manufacturing/views/cabochon_manufacturing_menus.xml
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Результат:

```text
ruff passed
compileall passed
xml parse passed
module update passed
odoo restarted
```
2026-06-17 уточнен финальный маршрут операций:

- операция `sorting` (`Финальная сортировка`) деактивирована в справочнике операций и больше не доступна для новых заявок;
- операции `grinding_polishing`, `husking`, `drilling`, `tinting` остаются финальными, но теперь не могут выбираться вместе в одной заявке, так как выполняются разными сотрудниками; выполнять их последовательно можно отдельными заявками;
- у производственной заявки добавлено поле `receipt_destination_stage` (`Склад сдачи`) со значениями `semi_finished` и `finished`; по умолчанию используется `semi_finished`;
- поле склада сдачи показывается только для заявок с финальной операцией и доступно технологу в черновике; выбор `finished` для нефинальной операции запрещен серверной проверкой;
- черновик сдачи и фактическая сдача используют склад из заявки: по умолчанию полуфабрикаты, при выборе технологом готового склада — склад готовых камней;
- у финальных операций в data XML основной склад по умолчанию изменен на `semi_finished`, чтобы справочник не отправлял результат на готовый склад без явного выбора технолога.

Проверка:

```text
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_manufacturing addons/cabochon_base
XML parse addons/cabochon_manufacturing/views/cabochon_manufacturing_views.xml
XML parse addons/cabochon_manufacturing/data/cabochon_manufacturing_data.xml
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Результат:

```text
ruff passed
compileall passed
xml parse passed
module update passed
odoo restarted
```
2026-06-17 восстановлен `addons/cabochon_manufacturing/models/cabochon_manufacturing.py` после локального отката файла без сегодняшних правок:

- повторно внесены Python-изменения по взаимоисключающим операциям, одиночным финальным операциям в заявке, выбору склада сдачи, автоподстановке строк сдачи и ID новых мешков с кодами операций;
- data XML и views уже содержали сегодняшние изменения: `sorting` неактивна, финальные операции по умолчанию сдают на полуфабрикаты, поле склада сдачи показано в заявке;
- повторно выполнены lint, compileall, XML parse, обновление модулей в базе `Cabachon` и restart Odoo.

Результат:

```text
ruff passed
compileall passed
xml parse passed
module update passed
odoo restarted
```
2026-06-17 исправлена кодировка русских пользовательских строк после восстановления модели:

- проверено, что `cabochon_manufacturing.py` и XML views хранят русские строки как нормальный UTF-8, а не mojibake (`Рџ...`);
- повторно обновлены `cabochon_base,cabochon_manufacturing` в базе `Cabachon`, чтобы `ir.ui.view` и метаданные модели перезаписались корректными строками;
- Odoo перезапущен после обновления.

Проверка:

```text
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_manufacturing addons/cabochon_base
XML parse addons/cabochon_manufacturing/views/cabochon_manufacturing_views.xml
XML parse addons/cabochon_manufacturing/data/cabochon_manufacturing_data.xml
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Результат:

```text
ruff passed
compileall passed
xml parse passed
module update passed
odoo restarted
```
2026-06-17 дополнительно исправлены двойные mojibake-строки в `cabochon_manufacturing.py` и метаданных Odoo:

- восстановлены русские строки модели из смешанного mojibake вида `Р В...`, включая `Исходный мешок`, описания моделей и selection-лейблы;
- повторно обновлены модули `cabochon_base,cabochon_manufacturing` в базе `Cabachon`;
- проверено через Odoo registry, что в базе корректные значения:
  - `cabochon.manufacturing.operation`: `Операция изготовления кабошонов`;
  - `cabochon.manufacturing.location`: `Складская зона изготовления кабошонов`;
  - `cabochon.stone.lot.parent_id`: `Исходный мешок`;
  - `cabochon.production.request.priority`: `Обычный`, `Срочно`, `Очень срочно`;
- Odoo перезапущен после обновления.

Результат:

```text
ruff passed
compileall passed
module update passed
database metadata verified
odoo restarted
```

2026-06-17 уточнено поведение формы заявки технолога:

- поле `cabochon.production.request.priority` получило явную русскую подпись `Приоритет` в модели и в списке/форме заявок;
- если в заявке технолога еще не выбран исходный мешок, домен операций показывает все активные операции. Ограничения по маршруту мешка применяются после выбора `source_lot_id`;
- изменение затрагивает только `cabochon_manufacturing`.

Проверка:

```text
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_manufacturing addons/cabochon_base
XML parse views/data cabochon_manufacturing
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init ...
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Результат:

```text
ruff passed
compileall passed
xml parse passed
module update passed
odoo restarted
```

2026-06-17 исправлено сохранение выбора операции в черновой заявке до выбора исходного мешка:

- `_normalize_selected_operations()` больше не применяет маршрутные требования `сначала помывка` и `сначала сортировка`, пока в заявке не выбран `source_lot_id`;
- при этом взаимоисключающие операции и одиночные финальные операции по-прежнему нормализуются сразу;
- серверная проверка маршрута при сохранении заявки с выбранным мешком не ослаблена.

Проверка:

```text
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_manufacturing addons/cabochon_base
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init ...
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Результат:

```text
ruff passed
compileall passed
module update passed
odoo restarted
```

2026-06-17 очищены старые mojibake-описания моделей в журнале действий:

- `ir_model` после обновления модулей содержит корректные описания `Операция изготовления кабошонов` и `Складская зона изготовления кабошонов`;
- в существующих строках `cabochon.audit.log` точечно обновлен только `model_description` для `cabochon.manufacturing.operation` и `cabochon.manufacturing.location`;
- исправлено 20 старых строк журнала: 15 для операций и 5 для складских зон.

Проверка:

```text
select model, name from ir_model where model in ('cabochon.manufacturing.operation','cabochon.manufacturing.location');
select model_name, model_description, count(1) from cabochon_audit_log where model_name in (...) group by model_name, model_description;
```

Результат:

```text
database metadata verified
audit model descriptions fixed
```
