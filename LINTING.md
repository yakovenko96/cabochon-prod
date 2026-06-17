# Линтинг Odoo-модулей

Для проверки Python-кода используется `ruff`.

## Установка

```powershell
python -m pip install ruff
```

## Проверка

```powershell
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts
```

## Автоисправление

```powershell
python -m ruff check addons/cabochon_base addons/cabochon_manufacturing scripts --fix
python -m ruff format addons/cabochon_base addons/cabochon_manufacturing scripts
```

Конфигурация лежит в `pyproject.toml`. Для Odoo `__init__.py` отключено
правило `F401`, потому что импорт моделей нужен фреймворку.
