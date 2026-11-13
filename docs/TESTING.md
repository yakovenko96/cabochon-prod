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

## 4. UI test (Playwright MCP)
- Запускайте отдельный test Odoo URL (не Prod), с тестовыми аккаунтами ролей.
- Сценарии: открыть списки, заполнить форму заявки и проверить реакцию полей, создать черновик выдачи, проверить ошибки доступа/валидации.
- Выдачу/сдачу с изменением движения запускать только на тестовых данных и тестовой БД.
- Playwright MCP — браузерная интерактивная проверка, а не замена Odoo TransactionCase/HttpCase.
