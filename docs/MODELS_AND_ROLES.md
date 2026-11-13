# Модули, модели и роли

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
cabochon.contractor.issue.wizard
cabochon.contractor.report
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

Контрагенты используют `res.partner` с признаком `is_cabochon_contractor`;
старые справочники поставщиков и покупателей не переименовываются и не переносятся.
Выдача сырья контрагенту доступна менеджеру назначенного склада и администратору.
SQL-отчет контрагентов доступен складским менеджерам в рамках их складов,
технологу и администратору — в рамках разрешенных компаний; работник к нему
доступа не имеет. Отчет только для чтения, основан на неизменяемых движениях.

Расход толуола хранится в `cabochon.material.transfer`, использует существующие
права документов, разделение компаний и подтверждения. Отдельной роли или
складского учета запасов толуола не добавляется.

Складской менеджер может читать мешки, связанные с его выдачами/сдачами,
после их перемещения работнику: отдельное правило `rule_cabochon_lot_manager_history_read`
использует `security_manager_user_ids`. Оно не расширяет права записи, создания
или удаления и не отменяет глобальное разделение компаний.
