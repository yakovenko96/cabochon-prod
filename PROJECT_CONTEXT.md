# Контекст проекта Cabochon Odoo

Живой контекст для работы с проектом. Обновлять после каждого функционального
изменения моделей, представлений, security, данных, команд или тестового статуса.

## Проект

Cabochon Odoo - кастомизация Odoo 19 Community для учета изготовления
кабошонов по мешкам, операциям, сотрудникам, складам, выдачам, сдачам, браку,
потерям и неизменяемому журналу движений.

Рабочая папка:

```text
C:\Users\Asus\data\cabochon-prod
```

Docker Compose:

```text
C:\Users\Asus\data\odoo-local\docker-compose.yml
```

Текущая база:

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

Перезапуск Odoo:

```powershell
docker compose -f C:\Users\Asus\data\odoo-local\docker-compose.yml restart odoo
```

Проверки:

```powershell
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_base addons/cabochon_manufacturing scripts
```

## Модули

`cabochon_base`:

- корневое меню;
- группы доступа;
- справочники;
- поля товаров;
- аудит;
- правила `mail.activity`.

`cabochon_manufacturing`:

- операции и складские зоны;
- мешки камней;
- производственные заявки;
- выдачи и сдачи;
- брак и потери;
- движения;
- допуски сотрудников;
- отчеты, панель технолога и этикетки.

## Основные модели

```text
cabochon.manufacturing.operation
cabochon.manufacturing.location
cabochon.stone.lot
cabochon.production.request
cabochon.production.request.operation.line
cabochon.material.transfer
cabochon.material.transfer.line
cabochon.manufacturing.movement
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
- складской менеджер: `group_cabochon_manager`;
- менеджер готового склада: `group_cabochon_finished_manager`;
- работник: `group_cabochon_fixer` или `group_cabochon_user`;
- администратор: `group_cabochon_admin`.

Технолог редактирует допуски сотрудников к операциям через
`Изготовление -> Работа -> Допуски сотрудников`.

## Производственный поток

1. Менеджер приходует сырье и создает исходный мешок.
2. Технолог создает заявку, выбирает свободный мешок, маршрут, сотрудника,
   плановый вес, обязательный срок и приоритет.
3. Мешок, уже выбранный в незакрытой или завершенной заявке, не предлагается
   для новой заявки. Отмененная заявка освобождает мешок.
4. Новые заявки показываются выше старых.
5. Подтверждение заявки создает документ выдачи.
6. Менеджер склада нажимает `Выдать`, после чего назначенный работник нажимает
   `Принять`. Только второе подтверждение создает движение и переносит мешок.
7. При сдаче менеджер нажимает `Принять сдачу`, затем работник нажимает
   `Подтвердить сдачу`. Движения создаются после второго подтверждения.
8. Сдача фиксирует годный вес, выявленный брак, сделанный брак и потери.
9. Для каждого склада и компании существует не более одного активного сводного
   мешка брака. Оба вида брака увеличивают его вес; вид брака остается в
   движении для отчетности.
10. Сводный мешок брака нельзя использовать как исходный мешок заявки.
11. Брак разрешен при сдаче на склад готовых камней.

## Статусы

Заявка:

```text
draft
confirmed
issued
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

## Остатки и отчеты

`Остатки на складе` показывает только мешки с фактическим положительным
остатком в состояниях `available` и `issued`. В списке скрыты штрихкод и
исходный мешок.

Отчет `Брак и потери по сотрудникам и операциям` использует SQL-модель
`cabochon.worker.operation.quality.report` и показывает выявленный брак,
сделанный брак, потери и проценты.

Панель технолога показывает `Сдано`, `Выявленный брак` и `Сделанный брак`
отдельными колонками.

В меню справочников скрыты:

```text
Тип сырья
Дополнительно
Тип брака
```

## Последняя проверка

2026-06-19:

- `ruff passed`;
- `compileall passed`;
- XML parse passed;
- обновление `cabochon_base,cabochon_manufacturing` в `Cabachon` passed;
- SQL-представление отчета читается;
- активных дубликатов мешков брака по складу нет;
- ORM-тест двойного подтверждения passed с откатом тестовых данных.
- ORM-тест накопления брака в одном мешке passed с откатом тестовых данных;
- Odoo restarted.
