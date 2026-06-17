r"""Populate the Cabachon database with test data for the current raw-material flow.

Run through Odoo shell, for example:
Get-Content -Raw -Encoding UTF8 scripts\populate_cabochon_test_database.py |
    docker exec -i odoo19-web odoo shell -d Cabachon --db_host db --db_port 5432 --db_user odoo --db_password 123321
"""

# ruff: noqa: F821

admin_env = env(user=env.ref("base.user_admin"))


def get_or_create(model, domain, values):
    record = admin_env[model].search(domain, limit=1)
    if record:
        record.write(values)
        return record
    return admin_env[model].create(values)


def clean_question_mark_records(model_name):
    model = admin_env[model_name]
    if "name" not in model._fields:
        return
    records = model.search([("name", "ilike", "?")])
    records.unlink()


def ensure_user_employee(name, login, groups):
    group_ids = [group.id for group in groups]
    user = admin_env["res.users"].search([("login", "=", login)], limit=1)
    values = {
        "name": name,
        "login": login,
        "email": login,
        "password": "123321",
        "group_ids": [(6, 0, group_ids)],
    }
    if user:
        user.write(values)
    else:
        user = admin_env["res.users"].create(values)
    employee = admin_env["hr.employee"].search(["|", ("work_email", "=", login), ("user_id", "=", user.id)], limit=1)
    values = {"name": name, "work_email": login, "user_id": user.id}
    if employee:
        employee.write(values)
    else:
        employee = admin_env["hr.employee"].create(values)
    return employee


def ensure_personal_location(employee):
    location = admin_env["cabochon.manufacturing.location"].search(
        [("code", "=", "employee"), ("employee_id", "=", employee.id)],
        limit=1,
    )
    values = {
        "name": f"Личный склад: {employee.name}",
        "code": "employee",
        "employee_id": employee.id,
        "manager_id": employee.id,
        "sequence": 80,
    }
    if location:
        location.write(values)
        return location
    return admin_env["cabochon.manufacturing.location"].create(values)


manager_group = env.ref("cabochon_base.group_cabochon_manager")
finished_group = env.ref("cabochon_base.group_cabochon_finished_manager")
worker_group = env.ref("cabochon_base.group_cabochon_fixer")
workshop_group = env.ref("cabochon_base.group_cabochon_workshop_manager")
internal_user_group = env.ref("base.group_user")

for model_name in (
    "cabochon.stone.type",
    "cabochon.form.type",
    "cabochon.shape",
    "cabochon.color",
    "cabochon.size",
    "cabochon.extra.option",
    "cabochon.defect.type",
):
    clean_question_mark_records(model_name)

bad_operations = admin_env["cabochon.manufacturing.operation"].search([("name", "ilike", "?")])
if bad_operations:
    try:
        bad_operations.unlink()
    except Exception:
        bad_operations.write({"active": False})

locations = {
    "raw": env.ref("cabochon_manufacturing.location_raw"),
    "prepared": env.ref("cabochon_manufacturing.location_prepared"),
    "semi_finished": env.ref("cabochon_manufacturing.location_semi_finished"),
    "finished": env.ref("cabochon_manufacturing.location_finished"),
    "loss": env.ref("cabochon_manufacturing.location_loss"),
}
location_names = {
    "raw": "Склад сырья",
    "prepared": "Склад подготовленного сырья",
    "semi_finished": "Склад полуфабрикатов",
    "finished": "Склад готовых камней",
    "loss": "Потери и списания",
}
for code, location in locations.items():
    location.write({"name": location_names[code]})

managers = {
    "raw": ensure_user_employee("Менеджер складов сырья и подготовки", "raw_prepared_manager", [internal_user_group, manager_group]),
    "prepared": ensure_user_employee(
        "Менеджер складов сырья и подготовки",
        "raw_prepared_manager",
        [internal_user_group, manager_group],
    ),
    "semi_finished": ensure_user_employee(
        "Менеджер склада полуфабрикатов",
        "semi_manager",
        [internal_user_group, manager_group],
    ),
    "finished": ensure_user_employee(
        "Менеджер склада готовых камней",
        "finished_manager",
        [internal_user_group, finished_group],
    ),
}
old_prepared_user = admin_env["res.users"].search([("login", "=", "prepared_manager")], limit=1)
if old_prepared_user:
    old_prepared_user.active = False
technologist = ensure_user_employee("Технолог тестовый", "technologist", [internal_user_group, workshop_group])

locations["raw"].write({"manager_id": managers["raw"].id})
locations["prepared"].write({"manager_id": managers["prepared"].id})
locations["semi_finished"].write({"manager_id": managers["semi_finished"].id})
locations["finished"].write({"manager_id": managers["finished"].id})

for name, description in (
    ("Минеральное сырье", "Куски, пластины и фракции до обработки."),
    ("Подготовленное сырье", "Отсортированное или распиленное сырье."),
    ("Полуфабрикат камня", "Заготовка перед финальной обработкой."),
):
    get_or_create("cabochon.stone.type", [("name", "=", name)], {"name": name, "description": description})

for name, description in (
    ("Кусок", "Неровный исходный материал."),
    ("Пластина", "Плоская заготовка для распила."),
    ("Калиброванная заготовка", "Заготовка, близкая к форме камня."),
):
    get_or_create("cabochon.form.type", [("name", "=", name)], {"name": name, "description": description})

for name, description in (
    ("Неровная", "Исходная неровная форма сырья."),
    ("Овал", "Форма заготовки или готового камня."),
    ("Круг", "Форма заготовки или готового камня."),
):
    get_or_create("cabochon.shape", [("name", "=", name)], {"name": name, "description": description})

for name, hex_code in (("Зеленый", "#2E7D32"), ("Синий", "#1565C0"), ("Красный", "#C62828")):
    get_or_create("cabochon.color", [("name", "=", name)], {"name": name, "hex_code": hex_code})

for name, size in (("Мелкая фракция", "до 10 мм"), ("Средняя фракция", "10-25 мм"), ("Крупная фракция", "25+ мм")):
    get_or_create("cabochon.size", [("name", "=", name)], {"name": name, "size": size})

for name, description in (
    ("Высокий приоритет", "Партия идет вне общей очереди."),
    ("Парная подборка", "Нужно подбирать камни попарно."),
    ("Контроль цвета", "Требуется дополнительная проверка оттенка."),
):
    get_or_create("cabochon.extra.option", [("name", "=", name)], {"name": name, "description": description})

for values in (
    {
        "name": "Скол",
        "description": "Механический скол.",
        "is_employee_caused": True,
        "is_returnable": True,
        "default_action": "rework",
    },
    {
        "name": "Трещина",
        "description": "Внутренняя или внешняя трещина.",
        "is_employee_caused": False,
        "is_returnable": True,
        "default_action": "keep_on_defect_stock",
    },
    {
        "name": "Потеря цвета",
        "description": "Цвет не соответствует партии.",
        "is_employee_caused": False,
        "is_returnable": False,
        "default_action": "write_off_final",
    },
):
    get_or_create("cabochon.defect.type", [("name", "=", values["name"])], values)

operation_specs = (
    ("tumble_wash", "Промывка в галтовке", 10, "prepared", False, False),
    ("toluene_wash", "Промывка в толуоле", 20, "prepared", False, False),
    ("auto_separator", "Авто-сепаратор", 30, "prepared", True, False),
    ("manual_sorting", "Ручная сортировка", 40, "prepared", True, False),
    ("stone_preparation", "Подготовка сырья", 50, "prepared", False, False),
    ("press", "Пресс", 60, "semi_finished", False, False),
    ("normalization", "Нормализация", 70, "semi_finished", False, False),
    ("cabochon_machine", "Кабошонерка", 80, "semi_finished", False, False),
    ("ball_machine", "Шарокрутка", 90, "semi_finished", False, False),
    ("cnc", "ЧПУ", 100, "semi_finished", False, False),
    ("grinding_polishing", "Шлифовка и полировка", 110, "finished", False, True),
    ("husking", "Лузговка", 120, "finished", False, True),
    ("sorting", "Финальная сортировка камней", 130, "finished", True, True),
    ("drilling", "Сверление готового камня", 140, "finished", False, True),
    ("tinting", "Тонировка готового камня", 150, "finished", False, True),
)
operations = []
for code, name, sequence, stage, split, final in operation_specs:
    operation = get_or_create(
        "cabochon.manufacturing.operation",
        [("code", "=", code)],
        {
            "name": name,
            "code": code,
            "sequence": sequence,
            "warehouse_stage": stage,
            "creates_split_lots": split,
            "final_operation": final,
            "accepts_weighed_defect": not final,
            "active": True,
        },
    )
    operations.append(operation)

workers = [
    ensure_user_employee("Работник 1: мойка и сортировка", "worker1", [internal_user_group, worker_group]),
    ensure_user_employee("Работник 2: подготовка сырья", "worker2", [internal_user_group, worker_group]),
    ensure_user_employee("Работник 3: станки полуфабрикатов", "worker3", [internal_user_group, worker_group]),
    ensure_user_employee("Работник 4: ЧПУ и полировка", "worker4", [internal_user_group, worker_group]),
    ensure_user_employee("Работник 5: финальные операции", "worker5", [internal_user_group, worker_group]),
]
for employee in set(managers.values()) | {technologist} | set(workers):
    ensure_personal_location(employee)
worker_operation_codes = (
    ("tumble_wash", "toluene_wash", "manual_sorting"),
    ("auto_separator", "manual_sorting", "stone_preparation", "press"),
    ("press", "normalization", "cabochon_machine", "ball_machine"),
    ("cnc", "cabochon_machine", "grinding_polishing"),
    ("grinding_polishing", "husking", "sorting", "drilling", "tinting"),
)
operations_by_code = {operation.code: operation for operation in operations}
for worker, codes in zip(workers, worker_operation_codes, strict=False):
    worker.write({"cabochon_allowed_operation_ids": [(6, 0, [operations_by_code[code].id for code in codes])]})

supplier = get_or_create("res.partner", [("name", "=", "Тестовый поставщик сырья")], {"name": "Тестовый поставщик сырья"})
raw_lots = (
    ("RAW-AGATE-001", "Агат", "Кусок", "Микс", "25+ мм", "Неровная", 5200.0),
    ("RAW-JASPER-002", "Яшма", "Пластина", "Красный", "25+ мм", "Пластина", 4100.0),
    ("RAW-ONYX-003", "Оникс", "Кусок", "Черный", "25+ мм", "Неровная", 6300.0),
    ("RAW-QUARTZ-004", "Кварц", "Мелкая фракция", "Прозрачный", "10-25 мм", "Неровная", 2800.0),
    ("RAW-MALACHITE-005", "Малахит", "Кусок", "Зеленый", "25+ мм", "Неровная", 3600.0),
    ("RAW-LAPIS-006", "Лазурит", "Кусок", "Синий", "25+ мм", "Неровная", 4500.0),
    ("RAW-AMBER-007", "Янтарь", "Кусок", "Медовый", "10-25 мм", "Неровная", 2400.0),
    ("RAW-TURQUOISE-008", "Бирюза", "Мелкая фракция", "Голубой", "до 10 мм", "Неровная", 1900.0),
    ("RAW-OBSIDIAN-009", "Обсидиан", "Пластина", "Черный", "25+ мм", "Пластина", 3900.0),
    ("RAW-RHODONITE-010", "Родонит", "Кусок", "Розовый", "10-25 мм", "Неровная", 3300.0),
)
for name, material, form_type, color, size, shape, weight in raw_lots:
    lot = admin_env["cabochon.stone.lot"].search([("name", "=", name)], limit=1)
    values = {
        "supplier_id": supplier.id,
        "fraction": material,
        "accepted_by_id": managers["raw"].id,
        "color": color,
        "stone_size": size,
        "shape": shape,
        "form_type": form_type,
    }
    if lot:
        lot.write(values)
    else:
        values.update(
            {
                "name": name,
                "location_id": locations["raw"].id,
                "initial_weight_g": weight,
                "current_weight_g": weight,
            }
        )
        admin_env["cabochon.stone.lot"].create(values)

downstream_lots = (
    ("PREP-AGATE-001", "prepared", "Агат", "Калиброванная заготовка", "Микс", "10-25 мм", "Овал", 1800.0),
    ("SEMI-JASPER-001", "semi_finished", "Яшма", "Калиброванная заготовка", "Красный", "10-25 мм", "Овал", 920.0),
    ("FIN-ONYX-001", "finished", "Оникс", "Готовый камень", "Черный", "до 10 мм", "Круг", 480.0),
)
for name, location_code, material, form_type, color, size, shape, weight in downstream_lots:
    lot = admin_env["cabochon.stone.lot"].search([("name", "=", name)], limit=1)
    values = {
        "supplier_id": supplier.id,
        "fraction": material,
        "accepted_by_id": managers["raw"].id,
        "color": color,
        "stone_size": size,
        "shape": shape,
        "form_type": form_type,
    }
    if lot:
        lot.write(values)
    else:
        values.update(
            {
                "name": name,
                "location_id": locations[location_code].id,
                "initial_weight_g": weight,
                "current_weight_g": weight,
            }
        )
        admin_env["cabochon.stone.lot"].create(values)

env.cr.commit()
print("OK Cabochon test database populated")
print("Warehouse managers:", len(managers))
print("Workers:", len(workers))
print("Operations:", len(operations))
print("Raw lots:", admin_env["cabochon.stone.lot"].search_count([("name", "ilike", "RAW-")]))
