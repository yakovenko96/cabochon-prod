# Контекст проекта Cabochon Odoo

Живой рабочий контекст для Codex и разработчиков. Обновлять после изменений
моделей, views, security, данных, команд или проверочного статуса.

## Проект

Cabochon Odoo - кастомизация Odoo 19 Community для учета изготовления
кабошонов по мешкам, операциям, сотрудникам, складам, выдачам, сдачам, браку,
потерям, готовым остаткам, отчетам и неизменяемому журналу движений.

Рабочая база разработки:

```text
Cabachon
```

Активные кастомные модули текущей итерации:

```text
cabochon_base
cabochon_manufacturing
```

Не добавлять зависимости от удаленных legacy-модулей.

## Команды

Установка на уже созданную базу:

```powershell
docker exec odoo19-web odoo -d Cabachon -i cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Обновление после изменения кода:

```powershell
docker exec odoo19-web odoo -d Cabachon -u cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
```

Helper-скрипт:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon -Install
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon
```

Проверки:

```powershell
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_base addons/cabochon_manufacturing scripts
python -c "from pathlib import Path; import xml.etree.ElementTree as ET; [ET.parse(p) for p in Path('addons').rglob('*.xml')]; print('XML OK')"
```

Smoke-проверка только на временной базе:

```powershell
docker exec odoo19-db createdb -U odoo CabochonSmoke
docker exec odoo19-web odoo -d CabochonSmoke -i cabochon_base,cabochon_manufacturing --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password 123321 --log-handler odoo.tools.convert:DEBUG
Get-Content -Raw -Encoding UTF8 scripts\smoke_zero_start.py | docker exec -i odoo19-web odoo shell -d CabochonSmoke --db_host db --db_port 5432 --db_user odoo --db_password 123321
docker exec odoo19-db dropdb -U odoo --if-exists --force CabochonSmoke
```

## Модули

`cabochon_base`:

- корневое меню `Производство`;
- группы доступа Cabochon;
- справочники типа формы, формы, цвета и размера;
- аудит действий;
- защита Cabochon-активностей.

`cabochon_manufacturing`:

- операции и складские зоны;
- мешки камней и готовых остатков;
- внешний приход;
- производственные заявки;
- выдачи и сдачи с двойным подтверждением;
- брак, возврат брака, возвратные потери и обычные потери;
- продажа/выдача готовых камней;
- неизменяемые движения и админские корректировки;
- допуски сотрудников;
- отчеты, панель технолога и этикетки.

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
cabochon.manufacturing.movement
cabochon.external.receipt.wizard
cabochon.defect.recovery.wizard
cabochon.finished.issue.wizard
cabochon.movement.correction.wizard
cabochon.worker.load.report
cabochon.worker.operation.quality.report
cabochon.employee.operation.access
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
- менеджер сырья/подготовленного сырья/полуфабрикатов:
  `group_cabochon_manager`;
- менеджер готового склада: `group_cabochon_finished_manager`;
- работник: `group_cabochon_fixer` или `group_cabochon_user`;
- администратор: `group_cabochon_admin`.

Администратор Cabochon наследует складские и технологические роли, а также
стандартные HR-группы пользователя и менеджера сотрудников. Пользователь
`base.user_admin` добавляется в группу Cabochon admin данными модуля.

## Старт с нуля

После установки на чистую базу создаются системные зоны и операции, но
бизнес-данные пустые.

Обязательная первичная настройка:

1. Создать или связать пользователей Odoo с сотрудниками `hr.employee`.
2. Назначить пользователям группы Cabochon.
3. Назначить менеджеров зонам `raw`, `prepared`, `semi_finished`, `finished`.
4. Заполнить справочники: годы добычи, фракции, цвета, размеры, формы,
   типы форм, поставщики и покупатели.
5. Для работников заполнить `cabochon_allowed_operation_ids`.

Зона `loss` не требует менеджера для обычного производственного потока.
Личная зона `employee` создается автоматически при первой выдаче сотруднику.

## Производственный поток

1. Менеджер оформляет внешний приход сырья или полуфабриката.
2. Технолог создает заявку, выбирает исходный мешок, маршрут, работника,
   плановый вес и срок.
3. Несколько исходных мешков разрешены только для операции `Трубы`; год и
   месяц добычи всех исходных мешков должны совпадать.
4. Подтверждение заявки создает выдачу.
5. Менеджер нажимает `Выдать`, работник нажимает `Принять`; движение
   создается только после второго подтверждения.
6. Сдача создается на текущий остаток выданного работнику сырья. Менеджер
   нажимает `Принять сдачу`, работник нажимает `Подтвердить сдачу`.
7. Частичная сдача списывает годный вес, брак и возвратные потери, затем
   создает следующую сдачу на остаток.
8. Окончательная сдача закрывает остаток, считает обычные потери и закрывает
   заявку.

Производственные задачи нужны только операциям:

```text
press
cnc
cabochon_machine
ball_machine
cutting
drilling
```

## Остатки, брак и готовый склад

`cabochon.stone.lot` хранит текущий вес, зону, исходные/дочерние мешки,
характеристики изделия, историю маршрута и расчетное количество.

Брак накапливается в сводных мешках по:

```text
склад + компания + операция + форма + тип формы + цвет
```

При возврате брака в работу операция, форма, тип формы и цвет подставляются из
мешка брака, размер выбирается вручную, ID нового мешка генерируется
автоматически.

Готовый склад (`finished`) объединяет годный вес по:

```text
форма + тип формы + размер + цвет
```

Количество считается как `current_weight_g / stone_size_id.standard_weight_g`.

## Отчеты и SQL-view

SQL-модели:

```text
cabochon.worker.load.report
cabochon.worker.operation.quality.report
cabochon.employee.operation.access
```

Отчеты по нагрузке и качеству безопасны для чистой установки: если зависимые
таблицы еще не созданы во время `init()`, view пропускается, а `post_init_hook`
создает их после завершения установки всех таблиц.

## Проверочный статус

2026-07-10:

- `cabochon_manufacturing` версия `19.0.2.31.0`;
- чистая установка активных модулей в `CabochonSmoke` прошла успешно;
- smoke-сценарий `scripts/smoke_zero_start.py` прошел с результатом
  `SMOKE_ZERO_START_OK`;
- установка `cabochon_manufacturing` в новую базу `Prod` прошла успешно;
- обновление `Cabachon` прошло успешно;
- SQL-отчеты в новых базах создаются как PostgreSQL view;
- `ruff`, `compileall` и XML parse прошли успешно;
- `odoo19-web` перезапущен, селектор баз отвечает HTTP 200.
