# Проверки Cabochon Odoo 19

## Безопасность
Тесты Odoo, чистая установка и smoke выполняются **только** на одноразовой базе, не на `Prod`. Не удаляйте чужие базы и не запускайте `dropdb` автоматически. База/пользователь/контейнеры должны быть сверены в реальном проекте. Если нет подтверждённой тестовой конфигурации — ограничиться статическими проверками.

## 1. Локальные статические проверки
```powershell
python -m pip install ruff
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
python -m compileall -q addons/cabochon_base addons/cabochon_manufacturing scripts
python scripts/validate_xml.py
git diff --check
```

## 2. Odoo tests (ручной запуск только на выделенной тестовой базе)
Если `CabochonCodexTest` — созданная вами пустая временная база и `odoo19-web` корректно подключён к тестовому PostgreSQL:
```powershell
# Illustrative: validate the container's DB connectivity/config first.
docker exec odoo19-web odoo -d CabochonCodexTest -i cabochon_base,cabochon_manufacturing --stop-after-init --test-tags /cabochon_base,/cabochon_manufacturing
```
Не запускать, пока не установлены правильные addons-path, db-host, db-user и механизм получения секретов в контейнере. `--test-tags` включает тесты; всегда проверять код выхода и фактические логи (включая failures/errors). Для уже установленной временной базы `-u` запускается только при осознанной необходимости.

## 3. Существующие проверки
- `scripts/smoke_zero_start.py` — согласно исходному контексту проверяет чистый старт; смотреть код перед использованием.
- `scripts/check_concurrency.py` — проверка конкурентных операций; смотреть код и данные перед использованием.
- Исторические результаты перенесены в `VERIFICATION_HISTORY.md`; необходимо сверить наличие тестовых модулей и схемы актуального checkout.

### Полный прогон на новой базе

`scripts/run_odoo_tests.py` запускается внутри отдельного тестового контейнера
с Odoo, `psycopg2` и стандартными переменными подключения `HOST`, `PORT`,
`USER`, `PASSWORD`. Он создает только новую базу `Cabochon*Test`, отказывается
работать с уже существующим именем и не удаляет базы. Затем выполняет чистую
установку, Odoo-тесты, smoke и пять конкурентных сценариев. База и filestore
остаются в тестовой среде; учетные данные передаются через временную конфигурацию.

Пример для заранее подготовленного **тестового** контейнера `cabochon-test`
с подключенным `/mnt/extra-addons`:

```powershell
docker cp scripts cabochon-test:/tmp/cabochon-tests
docker exec cabochon-test python3 /tmp/cabochon-tests/run_odoo_tests.py --database CabochonFreshTest --addons-path /mnt/extra-addons
```

CI использует этот же runner. Для 19.0.2.40.0 регрессия содержит 55 тестов;
пять конкурентных сценариев проверяют объединение готовых позиций, единый резерв,
однократную выдачу, гонку отмены с приемкой и выдачу контрагенту. Запуск нового задания на GitHub
Actions проверяется отдельно от локального успешного прогона runner.

`test_operation_workflows.py` дополнительно проводит все 16 активных операций,
сквозной маршрут от сырья до готовых камней, совместные задачи, возврат обрезков
через пресс, возврат брака, корректировки, продажи и уведомления. Проверяет
формирование доступных представлений меню и запросы SQL-отчетов под пятью ролями.
Фактические результаты и ограничения: `FUNCTIONAL_CHECK_2026-11-13.md`.

## 4. UI test (Playwright MCP)
- Запускайте отдельный test Odoo URL (не Prod), с тестовыми аккаунтами ролей.
- Сценарии: открыть списки, заполнить форму заявки и проверить реакцию полей, создать черновик выдачи, проверить ошибки доступа/валидации.
- Выдачу/сдачу с изменением движения запускать только на тестовых данных и тестовой БД.
- Playwright MCP — браузерная интерактивная проверка, а не замена Odoo TransactionCase/HttpCase.
