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
