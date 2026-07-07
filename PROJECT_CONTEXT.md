# Контекст проекта Cabochon Odoo

Живой контекст для работы с проектом. Обновлять после каждого функционального
изменения моделей, представлений, security, данных, команд или проверочного
статуса.

## Проект

Cabochon Odoo - кастомизация Odoo 19 Community для учета изготовления
кабошонов по мешкам, операциям, сотрудникам, складам, выдачам, сдачам, браку,
потерям и неизменяемому журналу движений.

Проект ведется на нескольких рабочих местах, поэтому в документации и коде не
фиксируются абсолютные пути конкретного пользователя. Рабочая база разработки:

```text
Cabachon
```

## Активные модули

```text
cabochon_base
cabochon_manufacturing
```

Не добавлять зависимости от удаленных legacy-модулей.

## Команды

Обновление модулей:

```powershell
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Установка модулей:

```powershell
docker exec odoo19-web odoo -d Cabachon -i cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Helper-скрипт не создает базу Odoo. Он работает с уже созданной базой и
устанавливает или обновляет активные модули. Первый запуск на базе, где модули
еще не установлены:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon -Install
```

Повторное обновление после изменений кода:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon
```

Установка/обновление без Docker возможна, если на машине развернут Odoo 19 и
папка `addons` проекта добавлена в `addons_path` Odoo. Тогда модули ставятся
локальным бинарником:

```powershell
odoo-bin -d Cabachon -i cabochon_base,cabochon_manufacturing --stop-after-init --config C:\path\to\odoo.conf
odoo-bin -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --config C:\path\to\odoo.conf
```

Или через helper-скрипт. Первый запуск:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon -Install -OdooBin C:\path\to\odoo-bin.exe -Config C:\path\to\odoo.conf -DbHost localhost -DbPort 5432 -DbUser odoo -DbPassword 123321
```

Повторное обновление:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon -OdooBin C:\path\to\odoo-bin.exe -Config C:\path\to\odoo.conf -DbHost localhost -DbPort 5432 -DbUser odoo -DbPassword 123321
```

Проверки:

```powershell
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_base addons/cabochon_manufacturing scripts
```

## Модули

`cabochon_base`:

- корневое меню `Производство`;
- группы доступа;
- активные справочники;
- аудит;
- правила Cabochon-активностей.

`cabochon_manufacturing`:

- операции и складские зоны;
- мешки камней;
- производственные заявки;
- выдачи и сдачи;
- внешний приход сырья;
- продажа/выдача готовых камней;
- брак и потери;
- неизменяемые движения и админские корректировки;
- допуски сотрудников;
- отчеты, панель технолога и этикетки.

Складские зоны ведутся только моделью `cabochon.manufacturing.location` и не
связаны со стандартным складом Odoo. Системные зоны создаются данными модуля:
`raw`, `prepared`, `semi_finished`, `finished`, `loss`. Личная зона
`employee` создается автоматически при первой выдаче сотруднику. У складских
зон нет ручного порядка `sequence`, сортировка выполняется по названию.

Для работы после чистой установки администратор назначает менеджеров зонам
`raw`, `prepared`, `semi_finished` и `finished`. Зона `loss` не требует
менеджера для обычного производственного потока.

## Основные модели

```text
cabochon.manufacturing.operation
cabochon.manufacturing.location
cabochon.stone.lot
cabochon.production.request
cabochon.production.request.source.line
cabochon.production.request.task.line
cabochon.production.request.operation.line
cabochon.material.transfer
cabochon.material.transfer.line
cabochon.supplier
cabochon.finished.customer
cabochon.finished.issue.wizard
cabochon.finished.issue.wizard.line
cabochon.manufacturing.movement
cabochon.movement.correction.wizard
cabochon.external.receipt.wizard
cabochon.employee.operation.access
cabochon.worker.load.report
cabochon.worker.operation.quality.report
```

## Роли

```text
cabochon_base.group_cabochon_user
cabochon_base.group_cabochon_fixer
cabochon_base.group_cabochon_manager
cabochon_base.group_cabochon_workshop_manager
cabochon_base.group_cabochon_finished_manager
cabochon_base.group_cabochon_admin
```

- технолог: `group_cabochon_workshop_manager`;
- менеджер сырья/подготовленного сырья: `group_cabochon_manager`;
- менеджер готового склада: `group_cabochon_finished_manager`;
- работник: `group_cabochon_fixer` или `group_cabochon_user`;
- администратор: `group_cabochon_admin`.

Допуски к операциям назначают администратор Cabochon и технолог в стандартной
карточке сотрудника на вкладке `Изготовление кабошонов`. Технолог может менять
только поле `cabochon_allowed_operation_ids`; прочие поля сотрудника для этой
роли заблокированы Python-проверкой. Администратор Cabochon имеет полный доступ
к созданию, редактированию и удалению сотрудников `hr.employee` и наследует
стандартные HR-группы пользователя и менеджера сотрудников.

## Производственный поток

1. Менеджер оформляет внешний приход сырья. Поставщик хранится как простой
   текст `Поставщик`, без связи с сотрудниками или контактами.
2. Технолог создает заявку, выбирает свободный мешок, маршрут, сотрудника,
   плановый вес, срок и приоритет.
3. Производственные задачи заполняются только для пресса и станков
   (`press`, `cnc`, `cabochon_machine`, `ball_machine`). Для мойки,
   ручной сортировки и авто-сепаратора задачи не нужны.
4. Подтверждение заявки создает документ выдачи.
5. Менеджер склада нажимает `Выдать`, затем работник нажимает `Принять`.
   Только второе подтверждение создает движение и переносит мешок.
6. При сдаче менеджер нажимает `Принять сдачу`, затем работник нажимает
   `Подтвердить сдачу`. Движения создаются после второго подтверждения.
7. Сдача фиксирует годный вес, выявленный брак, сделанный брак и потери.
8. Брак накапливается в одном активном сводном мешке по складу и компании.
9. Потери всех операций направляются в зону `loss`.
10. Готовые камни можно выдать/продать наружу через мастер
    `Продажа/выдача готовых камней`.
11. Движения неизменяемы; корректировки движений доступны только
    администратору Cabochon.

## Статусы

Заявка:

```text
draft
confirmed
in_progress
partially_done
done
cancelled
```

Выдача/сдача:

```text
draft = ожидает менеджера
manager_confirmed = ожидает работника
confirmed = подтверждено обеими сторонами
```

В пользовательских таблицах поле `state` отображается как `Статус`.

## Остатки и отчеты

`Остатки на складе` открываются с фильтром `На складе` и показывают мешки с
положительным остатком в статусах `available`, `issued` и
`inventory_difference`.

В остатках вместо устаревшей последней операции показываются все проведенные
операции маршрута.

Отчет `Брак и потери по сотрудникам и операциям` использует SQL-модель
`cabochon.worker.operation.quality.report` и показывает выявленный брак,
сделанный брак, потери, нормы и проценты.

Панель технолога показывает `Сдано`, `Выявленный брак` и `Сделанный брак`
отдельными колонками. SQL-отчеты группируют данные по фактическому
`worker_id`, поэтому включают менеджеров-исполнителей.

Работник в меню отчетов использует личный отчет `Мой брак и потери`.

## Активные справочники

Удалены legacy-модели и интерфейсы:

```text
Тип сырья
Дополнительно
Тип брака
Просверлен
Номенклатура Cabochon на product.template
```

Активные справочники базы: тип формы, форма, цвет, размер, фракция, год
добычи, поставщики сырья и покупатели готовых изделий. Годы добычи и фракции
пользователь создает вручную. У фракции нет ручного порядка `sequence`,
сортировка выполняется по названию. Месяц добычи хранится кодом `1-12`, но в
интерфейсах отображается русским названием месяца.

Все основные весовые поля отображаются с точностью 1 знак после запятой.

## Последняя проверка

2026-07-06:

- версия `cabochon_manufacturing` поднята до `19.0.2.17.0`;
- action `Допуски сотрудников` переведен с прямого `hr.employee` на SQL-view
  модель `cabochon.employee.operation.access`: технолог видит сотрудников и
  меняет только `cabochon_allowed_operation_ids`, а стандартные HR-поля вроде
  `version_id` не читаются в этом экране;
- проверки `ruff`, `compileall`, XML parse, обновление модулей в базе
  `Cabachon` и перезапуск `odoo19-web` прошли успешно; Odoo shell от имени
  пользователя `technologist` подтвердил чтение списка и сохранение текущих
  допусков без ошибки доступа к `hr.employee.version_id`.

2026-07-06:

- версия `cabochon_manufacturing` поднята до `19.0.2.15.0`;
- после обновления модулей web-контейнер Odoo нужно перезапускать, чтобы живой
  registry не оставался со старым набором Python-полей. Без перезапуска UI
  может видеть новые views, но старые модели, что дает ошибки вида
  `Unknown field supplier_id` или чтение удаленного `sequence`;
- добавлены отдельные views и меню `Допуски сотрудников` для технолога и
  администратора, чтобы редактировать `cabochon_allowed_operation_ids` без
  перехода в стандартное HR-приложение;
- проверки `ruff`, `compileall`, XML parse, обновление модулей в базе
  `Cabachon` и перезапуск `odoo19-web` прошли успешно. После перезапуска в
  логах успешны открытия заявок, выдач/сдач, журнала движений, прихода сырья и
  продажи готовых камней без ошибок неизвестных полей.

2026-07-06:

- версия `cabochon_manufacturing` поднята до `19.0.2.14.0`;
- исправлено понимание задачи технолога: лишнее назначение работника на строку
  маршрута операции убрано, `worker_id` строки маршрута снова связан с
  работником заявки;
- технолог получил доступ к вкладке `Изготовление кабошонов` в карточке
  сотрудника и может добавлять/изменять/убирать допуски
  `cabochon_allowed_operation_ids`; остальные поля `hr.employee` для технолога
  защищены от записи;
- проверки `ruff`, `compileall`, XML parse и обновление
  `cabochon_base,cabochon_manufacturing` в Docker-базе `Cabachon` прошли
  успешно.

2026-07-06:

- версия `cabochon_manufacturing` поднята до `19.0.2.13.0`;
- у складских зон удален ручной порядок `sequence` из модели, views и данных;
- добавлены справочники `cabochon.supplier` и `cabochon.finished.customer`.
  Приход сырья выбирает поставщика из выпадающего списка с возможностью
  создания нового, продажа/выдача готовых камней выбирает покупателя из
  отдельного списка;
- у мешка добавлено поле `supplier_id`, текст `supplier_name` сохраняется для
  совместимости и отчетов;
- действие `Выдачи и прием от сотрудников` больше не ограничивает доменом
  текущего менеджера: обычных менеджеров ограничивают record rules, а
  администратор видит все документы;
- если администратор подтверждает выдачу, прием сдачи, прием выдачи или сдачу
  за другого сотрудника, в документе `cabochon.material.transfer` сохраняется
  обязательная административная отметка `admin_action_note`, и она попадает в
  примечание создаваемых движений;
- проверки `ruff`, `compileall` и XML parse прошли успешно;
- обновление `cabochon_base,cabochon_manufacturing` в Docker-базе `Cabachon`
  прошло успешно.

2026-07-05:

- удалены старый SQL-скрипт очистки бизнес-данных, встроенные тестовые файлы и
  локальные zip-артефакты;
- версия `cabochon_manufacturing` поднята до `19.0.2.12.0`;
- служебные минимальные views выбора сотрудников имеют priority `1000`, чтобы
  не заменять стандартные list/search/form views приложения `Сотрудники`;
- обновление модулей в Docker-базе после правки priority не выполнено из-за
  лимита среды; применить командой обновления модулей перед проверкой UI;
- администратор Cabochon получил полный доступ к созданию, редактированию и
  удалению сотрудников `hr.employee`;
- из модели мешка удалены legacy-поля поставщика-контакта и старой последней операции;
- поставщик сырья на тот момент хранился текстом `supplier_name`; с
  2026-07-06 основной ввод выполняется через справочник `cabochon.supplier`;
- `state` в пользовательских таблицах и моделях подписан как `Статус`;
- вкладка задач заявки скрыта, если в маршруте нет операций, которым нужны
  производственные задачи;
- корректировки движений строго админские на уровне меню, ACL и Python-логики;
- документация очищена от машинно-зависимых путей и устаревших инструкций.
- helper-скрипт переименован в `scripts/install_modules.ps1`; добавлен режим
  установки `-Install` для новой базы и режим запуска локального
  `odoo`/`odoo-bin` без Docker через параметр `-OdooBin`;
- проверки `ruff`, `compileall` и XML parse прошли успешно;
- security-обновление применено в базе: ACL `hr.employee cabochon admin`
  имеет права `read/write/create/unlink`, группа администратора Cabochon
  наследует `hr.group_hr_user` и `hr.group_hr_manager`;
- обновление `cabochon_base,cabochon_manufacturing` в базе `Cabachon` прошло
  успешно; Odoo удалил метаданные старых полей мешка и нулевые ACL
  корректировок;
- база очищена для нового старта: сохранены 10 активных рабочих пользователей,
  3 технические записи Odoo, 10 сотрудников, 5 системных зон и 15 операций;
  мешки, заявки, выдачи/сдачи, движения, аудит, справочники
  цвета/размера/формы/типа формы/фракций/годов и допуски сотрудников имеют
  нулевые счетчики;
- физические legacy-таблицы старых справочников и связь
  `product_template_cabochon_extra_option_rel` удалены из PostgreSQL;
- Odoo перезапущен, `/web/login` отвечает HTTP 200.
