from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero

EXCLUSIVE_OPERATION_GROUPS = (
    {"tumble_wash", "toluene_wash"},
    {"manual_sorting", "auto_separator"},
    {"press", "stone_preparation"},
    {"ball_machine", "cabochon_machine", "cnc"},
)

SINGLE_REQUEST_OPERATION_GROUPS = (
    {"grinding_polishing", "husking", "drilling", "tinting"},
)

SORT_OPERATION_TYPES = {
    "manual_sorting": "Ручная",
    "auto_separator": "Авто",
}

OPERATION_CODE_SUFFIXES = {
    "tumble_wash": "WASH",
    "toluene_wash": "TLN",
    "manual_sorting": "SORT-M",
    "auto_separator": "SORT-A",
    "stone_preparation": "PREP",
    "press": "PRS",
    "normalization": "NORM",
    "cabochon_machine": "CAB",
    "ball_machine": "BALL",
    "cnc": "CNC",
    "grinding_polishing": "POL",
    "husking": "HUSK",
    "sorting": "SORT",
    "drilling": "DRILL",
    "tinting": "TINT",
}


class CabochonManufacturingOperation(models.Model):
    _name = "cabochon.manufacturing.operation"
    _description = "Операция изготовления кабошонов"
    _order = "sequence, name"

    name = fields.Char(string="Операция", required=True, translate=True)
    code = fields.Char(string="Код", required=True)
    sequence = fields.Integer(string="Последовательность", default=10)
    warehouse_stage = fields.Selection(
        [
            ("raw", "Сырье"),
            ("prepared", "Подготовленное сырье"),
            ("semi_finished", "Полуфабрикаты"),
            ("finished", "Готовые камни"),
        ],
        string="Основная зона",
        required=True,
        default="semi_finished",
    )
    creates_split_lots = fields.Boolean(string="Может дробить мешок")
    final_operation = fields.Boolean(string="Финальная операция")
    accepts_weighed_defect = fields.Boolean(string="Принимает брак в граммах", default=True)
    expected_loss_percent = fields.Float(string="Норма потерь, %", digits=(16, 4))
    active = fields.Boolean(default=True)

    _operation_code_unique = models.Constraint(
        "UNIQUE(code)",
        "Код операции должен быть уникальным.",
    )

    @api.constrains("expected_loss_percent")
    def _check_expected_loss_percent(self):
        for operation in self:
            if operation.expected_loss_percent < 0 or operation.expected_loss_percent > 100:
                raise ValidationError("Норма потерь должна быть от 0 до 100%.")

    def write(self, vals):
        result = super().write(vals)
        if "expected_loss_percent" in vals:
            movements = self.env["cabochon.manufacturing.movement"].sudo().search(
                [("kind", "=", "loss"), ("primary_operation_id", "in", self.ids)]
            )
            movements.mapped("request_id")._sync_loss_over_norm_activities()
        return result


class CabochonExtractionYear(models.Model):
    _name = "cabochon.extraction.year"
    _description = "Год добычи камней"
    _order = "year desc"
    _rec_name = "name"

    name = fields.Char(string="Год", required=True)
    year = fields.Integer(string="Числовой год", required=True)
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("year") and not vals.get("name"):
                vals["name"] = str(vals["year"])
            elif vals.get("name") and not vals.get("year"):
                vals["year"] = self._parse_year(vals["name"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("year") and "name" not in vals:
            vals["name"] = str(vals["year"])
        elif vals.get("name") and "year" not in vals:
            vals["year"] = self._parse_year(vals["name"])
        return super().write(vals)

    @api.model
    def _parse_year(self, value):
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise ValidationError("Год добычи должен быть числом.") from error

    @api.constrains("year")
    def _check_year(self):
        for record in self:
            if record.year < 1900 or record.year > 2100:
                raise ValidationError("Проверьте год добычи.")

    _year_unique = models.Constraint(
        "UNIQUE(year)",
        "Год добычи должен быть уникальным.",
    )


class CabochonFraction(models.Model):
    _name = "cabochon.fraction"
    _description = "Фракция камней"
    _order = "sequence, name"

    name = fields.Char(string="Фракция", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _fraction_name_unique = models.Constraint(
        "UNIQUE(name)",
        "Фракция должна быть уникальной.",
    )


class CabochonManufacturingLocation(models.Model):
    _name = "cabochon.manufacturing.location"
    _description = "Складская зона изготовления кабошонов"
    _order = "sequence, name"

    name = fields.Char(string="Зона", required=True)
    code = fields.Selection(
        [
            ("raw", "Склад сырья"),
            ("prepared", "Склад подготовленного сырья"),
            ("semi_finished", "Склад полуфабрикатов"),
            ("finished", "Склад готовых камней"),
            ("employee", "Личный склад работника"),
            ("loss", "Потери и списания"),
        ],
        string="Тип зоны",
        required=True,
    )
    stock_location_id = fields.Many2one(
        "stock.location",
        string="Локация Odoo",
        domain=[("usage", "=", "internal")],
        ondelete="restrict",
    )
    employee_id = fields.Many2one("hr.employee", string="Работник", ondelete="restrict")
    manager_id = fields.Many2one("hr.employee", string="Ответственный менеджер", ondelete="restrict")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _location_code_employee_unique = models.Constraint(
        "UNIQUE(code, employee_id)",
        "Для одного работника может быть только одна зона каждого типа.",
    )


class CabochonStoneLot(models.Model):
    _name = "cabochon.stone.lot"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Партия/мешок камней"
    _order = "receipt_date desc, id desc"

    name = fields.Char(string="ID мешка", default="Новый", required=True, copy=False, tracking=True)
    barcode = fields.Char(string="Штрихкод/QR", copy=False, readonly=True, index=True)
    parent_id = fields.Many2one("cabochon.stone.lot", string="Исходный мешок", ondelete="restrict")
    child_ids = fields.One2many("cabochon.stone.lot", "parent_id", string="Полученные мешки")
    transfer_line_ids = fields.One2many("cabochon.material.transfer.line", "lot_id", string="Строки документов")
    new_lot_transfer_line_ids = fields.One2many(
        "cabochon.material.transfer.line",
        "new_lot_id",
        string="Строки создания мешка",
    )
    route_movement_ids = fields.Many2many(
        "cabochon.manufacturing.movement",
        "cabochon_stone_lot_route_movement_rel",
        "lot_id",
        "movement_id",
        string="История операций",
        compute="_compute_route_movement_ids",
    )
    security_manager_user_ids = fields.Many2many(
        "res.users",
        "cabochon_stone_lot_security_manager_user_rel",
        "lot_id",
        "user_id",
        string="Пользователи менеджеров для доступа",
        compute="_compute_security_manager_user_ids",
        store=True,
    )
    supplier_id = fields.Many2one("res.partner", string="Поставщик", ondelete="restrict")
    fraction = fields.Char(string="Фракция (текст)")
    fraction_id = fields.Many2one("cabochon.fraction", string="Фракция", ondelete="restrict")
    extraction_year = fields.Integer(string="Год добычи (число)")
    extraction_year_id = fields.Many2one(
        "cabochon.extraction.year",
        string="Год добычи",
        ondelete="restrict",
    )
    extraction_month = fields.Selection(
        [(str(month), str(month)) for month in range(1, 13)],
        string="Месяц добычи",
    )
    waybill_number = fields.Char(string="Номер накладной")
    receipt_date = fields.Datetime(string="Дата поступления", default=fields.Datetime.now)
    accepted_by_id = fields.Many2one("hr.employee", string="Кто принял", ondelete="restrict")
    operation_id = fields.Many2one("cabochon.manufacturing.operation", string="Последняя операция", ondelete="restrict")
    location_id = fields.Many2one(
        "cabochon.manufacturing.location",
        string="Текущая зона",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    owner_employee_id = fields.Many2one("hr.employee", string="На руках у работника", ondelete="restrict", tracking=True)
    initial_weight_g = fields.Float(string="Начальный вес, г", digits=(16, 4), required=True)
    current_weight_g = fields.Float(string="Текущий вес, г", digits=(16, 4), required=True, tracking=True)
    color_id = fields.Many2one("cabochon.color", string="Цвет", ondelete="restrict")
    stone_size_id = fields.Many2one("cabochon.size", string="Размер", ondelete="restrict")
    shape_id = fields.Many2one("cabochon.shape", string="Форма", ondelete="restrict")
    form_type_id = fields.Many2one("cabochon.form.type", string="Тип формы", ondelete="restrict")
    color = fields.Char(string="Цвет (текст)")
    stone_size = fields.Char(string="Размер (текст)")
    shape = fields.Char(string="Форма (текст)")
    form_type = fields.Char(string="Тип формы (текст)")
    is_defect_lot = fields.Boolean(string="Бракованный мешок")
    defect_kind = fields.Selection(
        [("detected", "Выявленный брак"), ("made", "Сделанный брак")],
        string="Тип брака",
    )
    state = fields.Selection(
        [
            ("available", "На складе"),
            ("issued", "Выдан работнику"),
            ("consumed", "Преобразован"),
            ("written_off", "Списан"),
        ],
        default="available",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Компания",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            self._sync_extraction_year_values(vals)
            self._sync_fraction_values(vals)
            self._sync_reference_values(vals)
            if vals.get("name", "Новый") == "Новый":
                vals["name"] = sequence.next_by_code("cabochon.stone.lot") or "Новый"
            vals.setdefault("barcode", vals["name"])
            if not vals.get("current_weight_g") and vals.get("initial_weight_g"):
                vals["current_weight_g"] = vals["initial_weight_g"]
        lots = super().create(vals_list)
        if not self.env.context.get("skip_initial_lot_movement"):
            lots._create_initial_receipt_movements()
        return lots

    def write(self, vals):
        protected_fields = {
            "barcode",
            "parent_id",
            "location_id",
            "owner_employee_id",
            "initial_weight_g",
            "current_weight_g",
            "state",
        }
        if protected_fields.intersection(vals) and not self.env.context.get("cabochon_inventory_movement"):
            raise UserError(
                "Наличие, вес и склад мешка нельзя редактировать вручную. "
                "Создайте выдачу, сдачу или корректирующее движение."
            )
        vals = dict(vals)
        self._sync_extraction_year_values(vals)
        self._sync_fraction_values(vals)
        self._sync_reference_values(vals)
        return super().write(vals)

    @api.onchange("fraction_id")
    def _onchange_fraction_id(self):
        self.fraction = self.fraction_id.name if self.fraction_id else False

    @api.onchange("extraction_year_id")
    def _onchange_extraction_year_id(self):
        self.extraction_year = self.extraction_year_id.year if self.extraction_year_id else False

    @api.onchange("color_id")
    def _onchange_color_id(self):
        self.color = self.color_id.name if self.color_id else False

    @api.onchange("stone_size_id")
    def _onchange_stone_size_id(self):
        self.stone_size = self.stone_size_id.name if self.stone_size_id else False

    @api.onchange("shape_id")
    def _onchange_shape_id(self):
        self.shape = self.shape_id.name if self.shape_id else False

    @api.onchange("form_type_id")
    def _onchange_form_type_id(self):
        self.form_type = self.form_type_id.name if self.form_type_id else False

    @api.model
    def _sync_fraction_values(self, vals):
        if vals.get("fraction_id"):
            fraction = self.env["cabochon.fraction"].sudo().browse(vals["fraction_id"])
            vals["fraction"] = fraction.name
        elif vals.get("fraction") and not vals.get("fraction_id"):
            vals["fraction_id"] = self._get_or_create_fraction(vals["fraction"]).id
        elif "fraction" in vals and not vals.get("fraction"):
            vals["fraction_id"] = False
        elif "fraction_id" in vals and not vals.get("fraction_id"):
            vals["fraction"] = False

    @api.model
    def _get_or_create_fraction(self, fraction):
        fraction = str(fraction).strip()
        fraction_model = self.env["cabochon.fraction"].sudo()
        return fraction_model.search([("name", "=", fraction)], limit=1) or fraction_model.create({"name": fraction})

    @api.model
    def _sync_extraction_year_values(self, vals):
        if vals.get("extraction_year_id"):
            year = self.env["cabochon.extraction.year"].sudo().browse(vals["extraction_year_id"])
            vals["extraction_year"] = year.year
        elif vals.get("extraction_year") and not vals.get("extraction_year_id"):
            vals["extraction_year_id"] = self._get_or_create_extraction_year(vals["extraction_year"]).id
        elif "extraction_year" in vals and not vals.get("extraction_year"):
            vals["extraction_year_id"] = False
        elif "extraction_year_id" in vals and not vals.get("extraction_year_id"):
            vals["extraction_year"] = False

    @api.model
    def _get_or_create_extraction_year(self, year):
        year = int(year)
        year_model = self.env["cabochon.extraction.year"].sudo()
        return year_model.search([("year", "=", year)], limit=1) or year_model.create(
            {
                "name": str(year),
                "year": year,
            }
        )

    @api.model
    def _sync_reference_values(self, vals):
        references = (
            ("color_id", "color", "cabochon.color"),
            ("stone_size_id", "stone_size", "cabochon.size"),
            ("shape_id", "shape", "cabochon.shape"),
            ("form_type_id", "form_type", "cabochon.form.type"),
        )
        for id_field, text_field, model_name in references:
            if vals.get(id_field):
                vals[text_field] = self.env[model_name].sudo().browse(vals[id_field]).name
            elif vals.get(text_field) and not vals.get(id_field):
                vals[id_field] = self._get_or_create_reference(model_name, vals[text_field]).id
            elif text_field in vals and not vals.get(text_field):
                vals[id_field] = False
            elif id_field in vals and not vals.get(id_field):
                vals[text_field] = False

    @api.model
    def _get_or_create_reference(self, model_name, name):
        name = str(name).strip()
        model = self.env[model_name].sudo()
        return model.search([("name", "=", name)], limit=1) or model.create({"name": name})

    def _create_initial_receipt_movements(self):
        movement_model = self.env["cabochon.manufacturing.movement"]
        for lot in self.filtered(lambda item: not item.parent_id):
            movement_model.sudo().create(
                {
                    "kind": "receipt",
                    "new_lot_id": lot.id,
                    "destination_location_id": lot.location_id.id,
                    "manager_id": lot.accepted_by_id.id if lot.accepted_by_id else False,
                    "weight_g": lot.initial_weight_g,
                    "movement_date": lot.receipt_date or fields.Datetime.now(),
                    "company_id": lot.company_id.id,
                }
            )

    @api.depends(
        "location_id.manager_id.user_id",
        "location_id.employee_id.user_id",
        "transfer_line_ids.transfer_id.manager_id.user_id",
        "new_lot_transfer_line_ids.transfer_id.manager_id.user_id",
    )
    def _compute_security_manager_user_ids(self):
        for lot in self:
            users = (
                lot.location_id.manager_id.user_id
                | lot.location_id.employee_id.user_id
                | lot.transfer_line_ids.transfer_id.manager_id.user_id
                | lot.new_lot_transfer_line_ids.transfer_id.manager_id.user_id
            )
            lot.security_manager_user_ids = users

    @api.constrains("initial_weight_g", "current_weight_g", "extraction_year")
    def _check_lot_values(self):
        for lot in self:
            if float_compare(lot.initial_weight_g, 0.0, precision_digits=4) <= 0:
                raise ValidationError("Начальный вес мешка должен быть больше нуля.")
            if float_compare(lot.current_weight_g, 0.0, precision_digits=4) < 0:
                raise ValidationError("Текущий вес мешка не может быть отрицательным.")
            if lot.extraction_year and (lot.extraction_year < 1900 or lot.extraction_year > 2100):
                raise ValidationError("Проверьте год добычи.")

    def action_open_movements(self):
        self.ensure_one()
        lot_ids = self._route_lot_ids()
        return {
            "type": "ir.actions.act_window",
            "name": "История маршрута мешка",
            "res_model": "cabochon.manufacturing.movement",
            "view_mode": "list,form,pivot,graph",
            "domain": [
                "|",
                "|",
                ("lot_id", "in", lot_ids),
                ("new_lot_id", "in", lot_ids),
                ("report_lot_id", "in", lot_ids),
            ],
            "context": {
                "search_default_group_lot": 1,
            },
        }

    def _compute_route_movement_ids(self):
        movement_model = self.env["cabochon.manufacturing.movement"].sudo()
        for lot in self:
            lot_ids = lot._route_lot_ids()
            movements = movement_model.search(
                [
                    "|",
                    "|",
                    ("lot_id", "in", lot_ids),
                    ("new_lot_id", "in", lot_ids),
                    ("report_lot_id", "in", lot_ids),
                ],
                order="movement_date, id",
            )
            lot.route_movement_ids = movements

    def _completed_operation_ids(self):
        self.ensure_one()
        lot_ids = self._lineage_lot_ids()
        movements = self.env["cabochon.manufacturing.movement"].sudo().search(
            [
                ("kind", "in", ("receipt", "defect", "loss")),
                "|",
                "|",
                ("lot_id", "in", lot_ids),
                ("new_lot_id", "in", lot_ids),
                ("report_lot_id", "in", lot_ids),
            ]
        )
        return set(movements.mapped("operation_ids").ids)

    def _completed_operation_codes(self):
        self.ensure_one()
        if not self:
            return set()
        operations = self.env["cabochon.manufacturing.operation"].sudo().browse(self._completed_operation_ids())
        return set(operations.mapped("code"))

    def _is_operation_route_allowed(self, operations):
        self.ensure_one()
        completed_codes = self._completed_operation_codes()
        return self.env["cabochon.production.request"]._operation_route_error(operations, completed_codes) is False

    def _lineage_lot_ids(self):
        self.ensure_one()
        lots = self
        current = self
        while current.parent_id and current.parent_id not in lots:
            current = current.parent_id
            lots |= current
        return lots.ids

    def _route_lot_ids(self):
        self.ensure_one()
        lots = self
        current = self
        while current.parent_id and current.parent_id not in lots:
            current = current.parent_id
            lots |= current
        frontier = lots
        while frontier:
            children = self.search([("parent_id", "in", frontier.ids)])
            children -= lots
            if not children:
                break
            lots |= children
            frontier = children
        return lots.ids

    _barcode_unique = models.Constraint(
        "UNIQUE(barcode)",
        "Штрихкод мешка должен быть уникальным.",
    )

    def init(self):
        super().init()
        self._backfill_reference_field("cabochon_stone_lot", "color", "color_id", "cabochon_color")
        self._backfill_reference_field("cabochon_stone_lot", "stone_size", "stone_size_id", "cabochon_size")
        self._backfill_reference_field("cabochon_stone_lot", "shape", "shape_id", "cabochon_shape")
        self._backfill_reference_field("cabochon_stone_lot", "form_type", "form_type_id", "cabochon_form_type")
        self._backfill_reference_field("cabochon_material_transfer_line", "color", "color_id", "cabochon_color")
        self._backfill_reference_field("cabochon_material_transfer_line", "stone_size", "stone_size_id", "cabochon_size")
        self._backfill_reference_field("cabochon_material_transfer_line", "shape", "shape_id", "cabochon_shape")
        self._backfill_reference_field("cabochon_material_transfer_line", "form_type", "form_type_id", "cabochon_form_type")
    def _backfill_reference_field(self, source_table, text_column, id_column, reference_table):
        self.env.cr.execute(
            f"""
            INSERT INTO {reference_table} (name, active, create_uid, create_date, write_uid, write_date)
            SELECT DISTINCT trim(src.{text_column}), TRUE, 1, now(), 1, now()
              FROM {source_table} src
             WHERE src.{id_column} IS NULL
               AND src.{text_column} IS NOT NULL
               AND trim(src.{text_column}) != ''
               AND NOT EXISTS (
                   SELECT 1
                     FROM {reference_table} ref
                    WHERE ref.name = trim(src.{text_column})
               )
            """
        )
        self.env.cr.execute(
            f"""
            UPDATE {source_table} src
               SET {id_column} = ref.id
              FROM {reference_table} ref
             WHERE src.{id_column} IS NULL
               AND src.{text_column} IS NOT NULL
               AND trim(src.{text_column}) != ''
               AND ref.name = trim(src.{text_column})
            """
        )


class CabochonProductionRequest(models.Model):
    _name = "cabochon.production.request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Заявка на изготовление кабошонов"
    _order = "state_order, priority desc, deadline, id desc"

    name = fields.Char(string="Номер", default="Новый", copy=False, readonly=True)
    technologist_id = fields.Many2one(
        "hr.employee",
        string="Технолог",
        default=lambda self: self.env.user.sudo().employee_id,
        ondelete="restrict",
        tracking=True,
    )
    worker_id = fields.Many2one(
        "hr.employee",
        string="Работник",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_request_operation_rel",
        "request_id",
        "operation_id",
        string="Операции",
        required=True,
        tracking=True,
    )
    sort_type = fields.Char(string="Тип сортировки")
    show_sort_type = fields.Boolean(compute="_compute_show_sort_type")
    receipt_destination_stage = fields.Selection(
        [("semi_finished", "Склад полуфабрикатов"), ("finished", "Склад готовых камней")],
        string="Склад сдачи",
        default="semi_finished",
        required=True,
        tracking=True,
    )
    show_receipt_destination_stage = fields.Boolean(compute="_compute_show_receipt_destination_stage")
    source_lot_id = fields.Many2one(
        "cabochon.stone.lot",
        string="Исходный мешок",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    planned_weight_g = fields.Float(string="Плановый вес к выдаче, г", digits=(16, 4), required=True)
    deadline = fields.Datetime(string="Срок выполнения", tracking=True)
    priority = fields.Selection(
        [("0", "Обычный"), ("1", "Срочно"), ("2", "Очень срочно")],
        string="Приоритет",
        default="0",
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Новая"),
            ("confirmed", "Ожидает выдачи"),
            ("issued", "Выдано"),
            ("in_progress", "В работе"),
            ("partially_done", "Частично сдано"),
            ("done", "Закрыта"),
            ("cancelled", "Отменена"),
        ],
        default="draft",
        readonly=True,
        required=True,
        tracking=True,
    )
    issue_id = fields.Many2one("cabochon.material.transfer", string="Заявка на выдачу", readonly=True, copy=False)
    receipt_ids = fields.One2many("cabochon.material.transfer", "request_id", string="Сдачи")
    movement_ids = fields.One2many("cabochon.manufacturing.movement", "request_id", string="Движения", readonly=True)
    operation_line_ids = fields.One2many(
        "cabochon.production.request.operation.line",
        "request_id",
        string="Маршрут операций",
        copy=True,
    )
    eligible_operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_request_eligible_operation_rel",
        "request_id",
        "operation_id",
        compute="_compute_eligible_operation_ids",
        compute_sudo=True,
        string="Доступные операции для мешка",
    )
    eligible_worker_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_eligible_worker_ids",
        compute_sudo=True,
        string="Допущенные работники",
    )
    eligible_lot_ids = fields.Many2many(
        "cabochon.stone.lot",
        compute="_compute_eligible_lot_ids",
        compute_sudo=True,
        string="Доступные мешки для операции",
    )
    worker_load = fields.Integer(string="Текущая нагрузка работника", related="worker_id.cabochon_active_request_count")
    issued_weight_g = fields.Float(string="Выдано, г", compute="_compute_weights", store=True)
    received_weight_g = fields.Float(string="Сдано годного, г", compute="_compute_weights", store=True)
    defect_weight_g = fields.Float(string="Брак, г", compute="_compute_weights", store=True)
    lost_weight_g = fields.Float(string="Потери, г", compute="_compute_weights", store=True)
    confirmed_at = fields.Datetime(string="Подтверждена")
    issued_at = fields.Datetime(string="Выдана")
    started_at = fields.Datetime(string="Начата")
    first_receipt_at = fields.Datetime(string="Первая сдача")
    closed_at = fields.Datetime(string="Закрыта")
    is_overdue = fields.Boolean(string="Просрочена", compute="_compute_is_overdue", search="_search_is_overdue")
    state_order = fields.Integer(string="Порядок статуса", compute="_compute_state_order", store=True)
    actual_duration_hours = fields.Float(
        string="Фактическое время, ч",
        compute="_compute_actual_duration_hours",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Компания",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "Новый") == "Новый":
                vals["name"] = sequence.next_by_code("cabochon.production.request") or "Новый"
        requests = super().create(vals_list)
        requests._sync_operation_lines()
        requests._notify_overdue_technologists()
        return requests

    def write(self, vals):
        if "operation_ids" in vals and any(request.state != "draft" for request in self):
            raise UserError("Маршрут операций можно менять только в черновике заявки.")
        result = super().write(vals)
        if "operation_ids" in vals and not self.env.context.get("skip_operation_line_sync"):
            self._sync_operation_lines()
        if {"deadline", "state", "technologist_id"}.intersection(vals):
            self._clear_overdue_activities()
            self._notify_overdue_technologists()
        return result

    @api.depends("deadline", "state")
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for request in self:
            request.is_overdue = bool(request.deadline and request.deadline < now and request.state not in ("done", "cancelled"))

    @api.model
    def _search_is_overdue(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError("Поиск по просрочке поддерживает только операторы '=' и '!='.")
        now = fields.Datetime.now()
        positive = (operator == "=" and value) or (operator == "!=" and not value)
        if positive:
            return [("deadline", "<", now), ("state", "not in", ["done", "cancelled"])]
        return [
            "|",
            ("deadline", "=", False),
            "|",
            ("deadline", ">=", now),
            ("state", "in", ["done", "cancelled"]),
        ]

    @api.depends("state")
    def _compute_state_order(self):
        order_by_state = {
            "in_progress": 0,
            "partially_done": 0,
            "draft": 1,
            "confirmed": 2,
            "issued": 2,
            "done": 9,
            "cancelled": 9,
        }
        for request in self:
            request.state_order = order_by_state.get(request.state, 5)

    @api.depends("movement_ids.kind", "movement_ids.weight_g")
    def _compute_weights(self):
        for request in self:
            request.issued_weight_g = sum(request.movement_ids.filtered(lambda item: item.kind == "issue").mapped("weight_g"))
            request.received_weight_g = sum(request.movement_ids.filtered(lambda item: item.kind == "receipt").mapped("weight_g"))
            request.defect_weight_g = sum(request.movement_ids.filtered(lambda item: item.kind == "defect").mapped("weight_g"))
            request.lost_weight_g = sum(request.movement_ids.filtered(lambda item: item.kind == "loss").mapped("weight_g"))

    @api.depends("started_at", "closed_at")
    def _compute_actual_duration_hours(self):
        for request in self:
            if request.started_at and request.closed_at:
                request.actual_duration_hours = (request.closed_at - request.started_at).total_seconds() / 3600.0
            else:
                request.actual_duration_hours = 0.0

    @api.depends("operation_ids")
    def _compute_eligible_worker_ids(self):
        workers = self.env["hr.employee"].sudo().search([("cabochon_allowed_operation_ids", "!=", False)])
        for request in self:
            required_operation_ids = set(request.operation_ids.ids)
            if not required_operation_ids:
                request.eligible_worker_ids = workers
                continue
            request.eligible_worker_ids = workers.filtered(
                lambda employee, operation_ids=required_operation_ids: operation_ids.issubset(
                    set(employee.cabochon_allowed_operation_ids.ids)
                )
            )

    @api.depends("source_lot_id", "operation_ids")
    def _compute_eligible_operation_ids(self):
        operation_model = self.env["cabochon.manufacturing.operation"].sudo()
        operations = operation_model.search([("active", "=", True)])
        for request in self:
            selected = request.operation_ids
            if not request.source_lot_id:
                request.eligible_operation_ids = operations
                continue
            request.eligible_operation_ids = operations.filtered(
                lambda operation, lot=request.source_lot_id, selected=selected: operation in selected
                or lot._is_operation_route_allowed(selected | operation)
            )

    @api.depends("operation_ids.code")
    def _compute_show_sort_type(self):
        for request in self:
            request.show_sort_type = bool(set(request.operation_ids.mapped("code")) & set(SORT_OPERATION_TYPES))

    @api.depends("operation_ids.final_operation")
    def _compute_show_receipt_destination_stage(self):
        for request in self:
            request.show_receipt_destination_stage = bool(request.operation_ids.filtered("final_operation"))

    @api.depends("operation_ids")
    def _compute_eligible_lot_ids(self):
        lot_model = self.env["cabochon.stone.lot"].sudo()
        lots = lot_model.search([("state", "=", "available")])
        for request in self:
            if not request.operation_ids:
                request.eligible_lot_ids = lots
                continue
            request.eligible_lot_ids = lots.filtered(
                lambda lot, operations=request.operation_ids: lot._is_operation_route_allowed(operations)
            )

    def _operation_selection_domain(self):
        self.ensure_one()
        if not self.source_lot_id:
            return [("active", "=", True)]
        return [("id", "in", self.eligible_operation_ids.ids)]

    @api.onchange("source_lot_id")
    def _onchange_source_lot_id(self):
        if self.source_lot_id:
            self.planned_weight_g = self.source_lot_id.current_weight_g
            self.operation_ids = self.operation_ids.filtered(lambda operation: operation in self.eligible_operation_ids)
            self._normalize_selected_operations()
            self._set_sort_type_from_operations()
            self._set_default_receipt_destination_stage()
        return {
            "domain": {
                "operation_ids": self._operation_selection_domain(),
                "source_lot_id": [("id", "in", self.eligible_lot_ids.ids)],
            }
        }

    @api.onchange("operation_ids")
    def _onchange_operation_ids(self):
        self._normalize_selected_operations()
        self._set_sort_type_from_operations()
        self._set_default_receipt_destination_stage()
        if self.source_lot_id and self.source_lot_id not in self.eligible_lot_ids:
            self.source_lot_id = False
        if not self.worker_id:
            return {
                "domain": {
                    "operation_ids": self._operation_selection_domain(),
                    "source_lot_id": [("id", "in", self.eligible_lot_ids.ids)],
                }
            }
        required_operation_ids = set(self.operation_ids.ids)
        worker_operation_ids = set(self.worker_id.sudo().cabochon_allowed_operation_ids.ids)
        if not worker_operation_ids or not required_operation_ids.issubset(worker_operation_ids):
            self.worker_id = False
        return {
            "domain": {
                "operation_ids": self._operation_selection_domain(),
                "source_lot_id": [("id", "in", self.eligible_lot_ids.ids)],
            }
        }

    def _normalize_selected_operations(self):
        for request in self:
            completed_codes = request.source_lot_id._completed_operation_codes() if request.source_lot_id else set()
            kept_operations = self.env["cabochon.manufacturing.operation"]
            for operation in request.operation_ids.sorted("sequence"):
                if not operation.code or not request._operation_route_error(
                    kept_operations | operation,
                    completed_codes,
                    enforce_prerequisites=bool(request.source_lot_id),
                ):
                    kept_operations |= operation
            if kept_operations != request.operation_ids:
                request.operation_ids = kept_operations

    def _set_sort_type_from_operations(self):
        for request in self:
            sort_codes = [operation.code for operation in request.operation_ids.sorted("sequence") if operation.code in SORT_OPERATION_TYPES]
            request.sort_type = SORT_OPERATION_TYPES[sort_codes[-1]] if sort_codes else False

    def _set_default_receipt_destination_stage(self):
        for request in self:
            if not request.operation_ids.filtered("final_operation"):
                request.receipt_destination_stage = "semi_finished"

    @api.constrains("worker_id", "operation_ids", "source_lot_id", "planned_weight_g")
    def _check_request_values(self):
        for request in self:
            if float_compare(request.planned_weight_g, 0.0, precision_digits=4) <= 0:
                raise ValidationError("Плановый вес к выдаче должен быть больше нуля.")
            allowed_ids = set(request.worker_id.sudo().cabochon_allowed_operation_ids.ids)
            if request.operation_ids and not set(request.operation_ids.ids).issubset(allowed_ids):
                raise ValidationError("Работник не допущен ко всем операциям заявки.")
            completed_operation_ids = request.source_lot_id._completed_operation_ids() if request.source_lot_id else set()
            repeated_operations = request.operation_ids.filtered(
                lambda operation, done=completed_operation_ids: operation.id in done
            )
            if repeated_operations:
                operation_names = ", ".join(repeated_operations.mapped("display_name"))
                raise ValidationError(
                    f"Операции уже были выполнены для этого мешка или его исходного мешка: {operation_names}."
                )
            route_error = request._operation_route_error(
                request.operation_ids,
                request.source_lot_id._completed_operation_codes() if request.source_lot_id else set(),
            )
            if route_error:
                raise ValidationError(route_error)
            if request.receipt_destination_stage == "finished" and not request.operation_ids.filtered("final_operation"):
                raise ValidationError("Склад готовых камней можно выбрать только для финальной операции.")

    @api.model
    def _operation_route_error(self, operations, completed_codes, enforce_prerequisites=True):
        codes = [operation.code for operation in operations.sorted("sequence") if operation.code]
        if not codes:
            return False
        selected_codes = set(codes)
        repeated_codes = selected_codes & completed_codes
        if repeated_codes:
            names = ", ".join(
                self.env["cabochon.manufacturing.operation"].sudo().search([("code", "in", list(repeated_codes))]).mapped("name")
            )
            return f"Операции уже были выполнены для этого мешка или его исходного мешка: {names}."
        for group in EXCLUSIVE_OPERATION_GROUPS:
            selected_group_codes = selected_codes & group
            if completed_codes & group and selected_group_codes:
                names = ", ".join(
                    self.env["cabochon.manufacturing.operation"].sudo().search([("code", "in", list(group))]).mapped("name")
                )
                return f"Операции из этой группы уже были выполнены для мешка, выберите другой этап: {names}."
            if len(selected_group_codes) > 1:
                names = ", ".join(
                    self.env["cabochon.manufacturing.operation"].sudo().search([("code", "in", list(group))]).mapped("name")
                )
                return f"Операции взаимоисключающие, выберите только одну из группы: {names}."
        for group in SINGLE_REQUEST_OPERATION_GROUPS:
            selected_group_codes = selected_codes & group
            if len(selected_group_codes) > 1:
                names = ", ".join(
                    self.env["cabochon.manufacturing.operation"].sudo().search([("code", "in", list(group))]).mapped("name")
                )
                return f"Эти операции выполняют разные сотрудники, выберите только одну операцию в заявке: {names}."
        wash_codes = {"tumble_wash", "toluene_wash"}
        sorting_codes = {"manual_sorting", "auto_separator"}
        if not enforce_prerequisites:
            return False
        non_wash_codes = selected_codes - wash_codes
        if non_wash_codes and not ((completed_codes | selected_codes) & wash_codes):
            return "Перед другими операциями мешок должен пройти помывку в галтовке или толуоле."
        after_sort_codes = selected_codes - wash_codes - sorting_codes
        if after_sort_codes and not ((completed_codes | selected_codes) & sorting_codes):
            return "Перед дальнейшими операциями мешок должен пройти ручную сортировку или авто-сепаратор."
        return False

    def action_confirm(self):
        for request in self:
            if request.state != "draft":
                continue
            request._sync_operation_lines()
            request._ensure_issue_transfer()
            request.write(
                {
                    "state": "confirmed",
                    "confirmed_at": request.confirmed_at or fields.Datetime.now(),
                }
            )
            request.issue_id._notify_manager_activity()

    def action_start(self):
        for request in self:
            if request.state == "issued":
                now = fields.Datetime.now()
                request.write(
                    {
                        "state": "in_progress",
                        "started_at": request.started_at or now,
                    }
                )
                request._start_next_operation_line(now)

    def action_create_receipt(self):
        for request in self:
            request._ensure_receipt_transfer()
        return True

    def action_close(self):
        for request in self:
            if request.state not in ("in_progress", "partially_done"):
                continue
            now = fields.Datetime.now()
            request._finish_open_operation_lines(now)
            request.write(
                {
                    "state": "done",
                    "closed_at": request.closed_at or now,
                }
            )
            request._clear_overdue_activities()
            request._clear_loss_over_norm_activities()

    def action_cancel(self):
        for request in self:
            if request.movement_ids:
                raise UserError("Заявку с движениями нельзя отменить. Создайте корректирующие движения.")
            request.state = "cancelled"
            request._clear_overdue_activities()
            request._clear_loss_over_norm_activities()

    def _sync_operation_lines(self):
        line_model = self.env["cabochon.production.request.operation.line"]
        for request in self:
            operations = request.operation_ids.sorted("sequence")
            operation_ids = set(operations.ids)
            obsolete_lines = request.operation_line_ids.filtered(
                lambda line, ids=operation_ids: line.operation_id.id not in ids
            )
            obsolete_lines.unlink()
            existing_by_operation = {line.operation_id.id: line for line in request.operation_line_ids}
            for index, operation in enumerate(operations, start=1):
                sequence = index * 10
                existing_line = existing_by_operation.get(operation.id)
                if existing_line:
                    existing_line.sequence = sequence
                else:
                    line_model.create(
                        {
                            "request_id": request.id,
                            "operation_id": operation.id,
                            "sequence": sequence,
                        }
                    )

    def _start_next_operation_line(self, started_at=False):
        for request in self:
            line = request.operation_line_ids.filtered(lambda item: item.state == "pending").sorted("sequence")[:1]
            if line:
                line.action_start(started_at=started_at)

    def _finish_open_operation_lines(self, finished_at=False):
        for request in self:
            lines = request.operation_line_ids.filtered(lambda item: item.state in ("pending", "in_progress"))
            for line in lines.sorted("sequence"):
                line_finished_at = finished_at
                if line.started_at and line_finished_at and line_finished_at < line.started_at:
                    line_finished_at = line.started_at
                if line.state == "pending":
                    line.action_start(started_at=line_finished_at)
                line.action_finish(finished_at=line_finished_at)

    def _notify_overdue_technologists(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        today = fields.Date.context_today(self)
        overdue_requests = self.filtered(lambda item: item.is_overdue and item.technologist_id.user_id)
        for request in overdue_requests:
            user = request.technologist_id.user_id
            existing = self.env["mail.activity"].sudo().search(
                [
                    ("res_model_id", "=", model_id),
                    ("res_id", "=", request.id),
                    ("activity_type_id", "=", activity_type.id),
                    ("user_id", "=", user.id),
                    ("summary", "=", "Просрочена заявка на изготовление"),
                ],
                limit=1,
            )
            if existing:
                continue
            request.sudo().with_context(cabochon_activity_system_update=True).activity_schedule(
                activity_type_id=activity_type.id,
                date_deadline=today,
                summary="Просрочена заявка на изготовление",
                note="Срок выполнения заявки истек. Проверьте выдачу, сдачу или закрытие работ.",
                user_id=user.id,
            )

    def _clear_overdue_activities(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        activities = self.env["mail.activity"].sudo().search(
            [
                ("res_model_id", "=", model_id),
                ("res_id", "in", self.ids),
                ("activity_type_id", "=", activity_type.id),
                ("summary", "=", "Просрочена заявка на изготовление"),
            ]
        )
        activities.with_context(cabochon_activity_system_update=True).unlink()

    def _sync_loss_over_norm_activities(self):
        for request in self:
            request._clear_loss_over_norm_activities()
            if request.state not in ("done", "cancelled"):
                request.movement_ids.filtered(lambda movement: movement.is_loss_over_norm)._notify_loss_over_norm()

    def _clear_loss_over_norm_activities(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        activities = self.env["mail.activity"].sudo().search(
            [
                ("res_model_id", "=", model_id),
                ("res_id", "in", self.ids),
                ("activity_type_id", "=", activity_type.id),
                ("summary", "=", "Потери выше нормы"),
            ]
        )
        activities.with_context(cabochon_activity_system_update=True).unlink()

    @api.model
    def _cron_notify_overdue_requests(self):
        requests = self.search([("deadline", "<", fields.Datetime.now()), ("state", "not in", ("done", "cancelled"))])
        requests._notify_overdue_technologists()

    def _ensure_issue_transfer(self):
        self.ensure_one()
        if self.issue_id:
            return self.issue_id
        manager = self.source_lot_id.location_id.manager_id
        if not manager:
            raise UserError("Укажите ответственного кладовщика на складе исходного мешка.")
        issue = self.env["cabochon.material.transfer"].sudo().create(
            {
                "transfer_type": "issue",
                "request_id": self.id,
                "worker_id": self.worker_id.id,
                "manager_id": manager.id,
                "operation_ids": [(6, 0, self.operation_ids.ids)],
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "lot_id": self.source_lot_id.id,
                            "weight_g": self.planned_weight_g,
                        },
                    )
                ],
                "company_id": self.company_id.id,
            }
        )
        self.issue_id = issue
        return issue

    def _ensure_receipt_transfer(self, issue_lines=None):
        self.ensure_one()
        existing = self.receipt_ids.filtered(lambda item: item.transfer_type == "receipt" and item.state == "draft")
        if existing:
            receipt = existing[:1]
            if issue_lines and not receipt.line_ids:
                receipt.sudo().write({"line_ids": self._receipt_line_commands(issue_lines)})
            return receipt
        destination = self._get_receipt_destination_location()
        if not destination.manager_id:
            raise UserError("Укажите ответственного кладовщика на складе назначения для сдачи.")
        receipt = self.env["cabochon.material.transfer"].sudo().create(
            {
                "transfer_type": "receipt",
                "request_id": self.id,
                "worker_id": self.worker_id.id,
                "manager_id": destination.manager_id.id,
                "operation_ids": [(6, 0, self.operation_ids.ids)],
                "line_ids": self._receipt_line_commands(issue_lines),
                "company_id": self.company_id.id,
            }
        )
        receipt._notify_manager_activity()
        return receipt

    def _get_receipt_destination_location(self):
        self.ensure_one()
        if not self.operation_ids.filtered("final_operation"):
            return self.env["cabochon.material.transfer"]._get_destination_location_for_operations(self.operation_ids)
        stage = self.receipt_destination_stage or "semi_finished"
        location = self.env["cabochon.manufacturing.location"].sudo().search([("code", "=", stage)], limit=1)
        if not location:
            raise UserError("Не найдена складская зона назначения для сдачи.")
        return location

    def _receipt_line_commands(self, issue_lines):
        return [
            (
                0,
                0,
                {
                    "lot_id": lot.id,
                    "weight_before_g": weight,
                    "sort_type": self.sort_type,
                },
            )
            for lot, weight in (issue_lines or [])
            if lot
        ]


class CabochonProductionRequestOperationLine(models.Model):
    _name = "cabochon.production.request.operation.line"
    _description = "Операция в маршруте заявки на изготовление"
    _order = "request_id, sequence, id"

    request_id = fields.Many2one(
        "cabochon.production.request",
        string="Заявка",
        required=True,
        ondelete="cascade",
    )
    operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        string="Операция",
        required=True,
        ondelete="restrict",
    )
    sequence = fields.Integer(string="Порядок", default=10)
    state = fields.Selection(
        [
            ("pending", "Ожидает"),
            ("in_progress", "В работе"),
            ("done", "Готово"),
        ],
        string="Статус",
        default="pending",
        required=True,
    )
    planned_weight_g = fields.Float(
        string="Плановый вес, г",
        related="request_id.planned_weight_g",
        readonly=True,
    )
    started_at = fields.Datetime(string="Начало")
    finished_at = fields.Datetime(string="Окончание")
    duration_hours = fields.Float(string="Время, ч", compute="_compute_duration_hours", store=True)
    worker_id = fields.Many2one("hr.employee", string="Работник", related="request_id.worker_id", store=True)
    company_id = fields.Many2one("res.company", string="Компания", related="request_id.company_id", store=True)
    note = fields.Text(string="Комментарий")

    @api.depends("started_at", "finished_at")
    def _compute_duration_hours(self):
        for line in self:
            if line.started_at and line.finished_at:
                line.duration_hours = (line.finished_at - line.started_at).total_seconds() / 3600.0
            else:
                line.duration_hours = 0.0

    def action_start(self, started_at=False):
        started_at = started_at or fields.Datetime.now()
        for line in self:
            if line.state == "pending":
                line.write(
                    {
                        "state": "in_progress",
                        "started_at": line.started_at or started_at,
                    }
                )
                if not line.request_id.started_at:
                    line.request_id.started_at = started_at

    def action_finish(self, finished_at=False):
        finished_at = finished_at or fields.Datetime.now()
        for line in self:
            if line.state != "done":
                line_finished_at = finished_at
                if line.started_at and line_finished_at < line.started_at:
                    line_finished_at = line.started_at
                values = {
                    "state": "done",
                    "finished_at": line.finished_at or line_finished_at,
                }
                if not line.started_at:
                    values["started_at"] = line_finished_at
                line.write(values)

    @api.constrains("started_at", "finished_at")
    def _check_operation_line_dates(self):
        for line in self:
            if line.started_at and line.finished_at and line.finished_at < line.started_at:
                raise ValidationError("Время окончания операции не может быть раньше начала.")


class CabochonMaterialTransfer(models.Model):
    _name = "cabochon.material.transfer"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Выдача/сдача материалов по изготовлению"
    _order = "state_order, transfer_date desc, id desc"

    name = fields.Char(string="Номер", default="Новый", copy=False, readonly=True)
    transfer_type = fields.Selection(
        [("issue", "Выдача работнику"), ("receipt", "Сдача от работника"), ("defect", "Прием брака")],
        string="Тип",
        required=True,
        default="issue",
        tracking=True,
    )
    request_id = fields.Many2one("cabochon.production.request", string="Заявка", ondelete="restrict", tracking=True)
    worker_id = fields.Many2one("hr.employee", string="Работник", ondelete="restrict", tracking=True)
    manager_id = fields.Many2one(
        "hr.employee",
        string="Кладовщик/приемщик",
        ondelete="restrict",
        tracking=True,
    )
    operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_transfer_operation_rel",
        "transfer_id",
        "operation_id",
        string="Операции",
    )
    primary_operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        compute="_compute_primary_operation_id",
        store=True,
        string="Операция для отчетов",
    )
    transfer_date = fields.Datetime(string="Дата и время", default=fields.Datetime.now, required=True, tracking=True)
    state = fields.Selection(
        [("draft", "Ожидает обработки"), ("confirmed", "Подтверждено")],
        default="draft",
        readonly=True,
        required=True,
        tracking=True,
    )
    state_order = fields.Integer(string="Порядок статуса", compute="_compute_state_order", store=True)
    line_ids = fields.One2many("cabochon.material.transfer.line", "transfer_id", string="Строки")
    total_weight_g = fields.Float(string="Фактический вес, г", compute="_compute_totals", store=True)
    total_defect_weight_g = fields.Float(string="Брак, г", compute="_compute_totals", store=True)
    total_detected_defect_weight_g = fields.Float(string="Выявленный брак, г", compute="_compute_totals", store=True)
    total_made_defect_weight_g = fields.Float(string="Сделанный брак, г", compute="_compute_totals", store=True)
    total_lost_weight_g = fields.Float(string="Потери, г", compute="_compute_totals", store=True)
    show_sort_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_press_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_color_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_size_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_shape_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    company_id = fields.Many2one(
        "res.company",
        string="Компания",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "Новый") == "Новый":
                vals["name"] = sequence.next_by_code("cabochon.material.transfer") or "Новый"
        transfers = super().create(vals_list)
        for transfer in transfers.filtered(lambda item: not item.manager_id):
            manager = transfer._get_warehouse_manager()
            if manager:
                transfer.sudo().manager_id = manager.id
        transfers._notify_manager_activity()
        return transfers

    @api.depends(
        "line_ids.weight_g",
        "line_ids.defect_weight_g",
        "line_ids.detected_defect_weight_g",
        "line_ids.made_defect_weight_g",
        "line_ids.lost_weight_g",
    )
    def _compute_totals(self):
        for transfer in self:
            transfer.total_weight_g = sum(transfer.line_ids.mapped("weight_g"))
            transfer.total_defect_weight_g = sum(transfer.line_ids.mapped("defect_weight_g"))
            transfer.total_detected_defect_weight_g = sum(transfer.line_ids.mapped("detected_defect_weight_g"))
            transfer.total_made_defect_weight_g = sum(transfer.line_ids.mapped("made_defect_weight_g"))
            transfer.total_lost_weight_g = sum(transfer.line_ids.mapped("lost_weight_g"))

    @api.depends("state")
    def _compute_state_order(self):
        for transfer in self:
            transfer.state_order = 9 if transfer.state == "confirmed" else 0

    @api.depends("operation_ids")
    def _compute_primary_operation_id(self):
        for transfer in self:
            transfer.primary_operation_id = transfer.operation_ids.sorted("sequence")[-1:] if transfer.operation_ids else False

    @api.depends("transfer_type", "operation_ids.code")
    def _compute_receipt_field_visibility(self):
        for transfer in self:
            codes = set(transfer.operation_ids.mapped("code"))
            is_receipt = transfer.transfer_type == "receipt"
            transfer.show_sort_fields = is_receipt and bool(codes & {"manual_sorting", "auto_separator"})
            transfer.show_press_fields = is_receipt and "press" in codes
            transfer.show_color_fields = transfer.show_sort_fields
            transfer.show_size_fields = transfer.show_sort_fields or transfer.show_press_fields
            transfer.show_shape_fields = transfer.show_press_fields

    def write(self, vals):
        if set(vals) - {"state"} and any(record.state == "confirmed" for record in self):
            raise UserError("Подтвержденную выдачу/сдачу нельзя менять. Создайте корректировку.")
        result = super().write(vals)
        if {"manager_id", "state", "transfer_type", "request_id"}.intersection(vals):
            self._clear_manager_activities()
            self._notify_manager_activity()
        return result

    def unlink(self):
        if any(record.state == "confirmed" for record in self):
            raise UserError("Подтвержденную выдачу/сдачу нельзя удалить. Создайте корректировку.")
        self._clear_manager_activities()
        return super().unlink()

    @api.onchange("request_id", "transfer_type", "operation_ids")
    def _onchange_request_id(self):
        if self.request_id:
            self.worker_id = self.request_id.worker_id
            self.operation_ids = self.request_id.operation_ids
        self.manager_id = self._get_warehouse_manager()

    @api.onchange(
        "line_ids",
        "line_ids.lot_id",
        "line_ids.weight_before_g",
        "line_ids.weight_g",
        "line_ids.detected_defect_weight_g",
        "line_ids.made_defect_weight_g",
    )
    def _onchange_line_ids(self):
        for transfer in self.filtered(lambda item: item.transfer_type != "issue"):
            transfer._set_receipt_loss_weights()

    def action_confirm(self):
        for transfer in self:
            if transfer.state != "draft":
                continue
            transfer._validate_before_confirm()
            if transfer.transfer_type == "issue":
                transfer._confirm_issue()
            else:
                transfer._confirm_receipt()
            transfer.state = "confirmed"
            transfer._clear_manager_activities()

    def _notify_manager_activity(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        today = fields.Date.context_today(self)
        for transfer in self.filtered(lambda item: item.state == "draft" and item.manager_id.user_id):
            user = transfer.manager_id.user_id
            title = "Нужно выдать материалы" if transfer.transfer_type == "issue" else "Нужно принять сдачу"
            existing = self.env["mail.activity"].sudo().search(
                [
                    ("res_model_id", "=", model_id),
                    ("res_id", "=", transfer.id),
                    ("activity_type_id", "=", activity_type.id),
                    ("user_id", "=", user.id),
                    ("summary", "=", title),
                ],
                limit=1,
            )
            if existing:
                continue
            transfer.sudo().with_context(cabochon_activity_system_update=True).activity_schedule(
                activity_type_id=activity_type.id,
                date_deadline=today,
                summary=title,
                note="Появился документ, ожидающий подтверждения ответственным менеджером склада.",
                user_id=user.id,
            )

    def _clear_manager_activities(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        activities = self.env["mail.activity"].sudo().search(
            [
                ("res_model_id", "=", model_id),
                ("res_id", "in", self.ids),
                ("activity_type_id", "=", activity_type.id),
                ("summary", "in", ("Нужно выдать материалы", "Нужно принять сдачу")),
            ]
        )
        activities.with_context(cabochon_activity_system_update=True).unlink()

    def _validate_before_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError("Добавьте строки.")
        if not self.worker_id:
            raise UserError("Укажите работника.")
        if not self.manager_id:
            raise UserError("Укажите ответственного менеджера склада.")
        if (
            not self.env.user.has_group("cabochon_base.group_cabochon_admin")
            and self.manager_id.user_id
            and self.manager_id.user_id != self.env.user
        ):
            raise UserError("Подтвердить документ может только назначенный менеджер склада или администратор.")
        if self.transfer_type != "issue":
            self._set_receipt_loss_weights()
        for line in self.line_ids.with_context(skip_receipt_auto_loss=True):
            line._validate_amounts()

    def _confirm_issue(self):
        employee_location = self._get_employee_location(self.worker_id)
        issued_lines = []
        for line in self.line_ids:
            lot = line.sudo().lot_id
            if float_compare(lot.current_weight_g, line.weight_g, precision_digits=4) < 0:
                raise UserError(f"В мешке {lot.display_name} недостаточно веса.")
            source_location = lot.location_id
            issued_lot = lot
            remaining_weight = lot.current_weight_g - line.weight_g
            if float_compare(remaining_weight, 0.0, precision_digits=4) > 0:
                self._create_remaining_lot(lot, remaining_weight, source_location)
            lot.sudo().with_context(cabochon_inventory_movement=True).write(
                {
                    "location_id": employee_location.id,
                    "owner_employee_id": self.worker_id.id,
                    "current_weight_g": line.weight_g,
                    "state": "issued",
                }
            )
            self.env["cabochon.manufacturing.movement"].sudo().create(
                self._movement_values(line, "issue", lot, line.weight_g, source_location, employee_location, issued_lot)
            )
            issued_lines.append((issued_lot, line.weight_g))
        if self.request_id and self.request_id.state == "confirmed":
            now = self.transfer_date or fields.Datetime.now()
            self.request_id.sudo().write(
                {
                    "state": "in_progress",
                    "issued_at": self.request_id.issued_at or now,
                    "started_at": self.request_id.started_at or now,
                }
            )
            self.request_id.sudo()._start_next_operation_line(now)
            self.request_id.sudo()._ensure_receipt_transfer(issue_lines=issued_lines)

    def _create_remaining_lot(self, source_lot, weight_g, source_location):
        self.ensure_one()
        return self.env["cabochon.stone.lot"].sudo().with_context(skip_initial_lot_movement=True).create(
            {
                "parent_id": source_lot.id,
                "supplier_id": source_lot.supplier_id.id if source_lot.supplier_id else False,
                "fraction": source_lot.fraction,
                "fraction_id": source_lot.fraction_id.id if source_lot.fraction_id else False,
                "extraction_year": source_lot.extraction_year,
                "extraction_year_id": source_lot.extraction_year_id.id if source_lot.extraction_year_id else False,
                "extraction_month": source_lot.extraction_month,
                "waybill_number": source_lot.waybill_number,
                "receipt_date": source_lot.receipt_date,
                "accepted_by_id": source_lot.accepted_by_id.id if source_lot.accepted_by_id else False,
                "operation_id": source_lot.operation_id.id if source_lot.operation_id else False,
                "location_id": source_location.id,
                "initial_weight_g": weight_g,
                "current_weight_g": weight_g,
                "color_id": source_lot.color_id.id if source_lot.color_id else False,
                "color": source_lot.color,
                "stone_size_id": source_lot.stone_size_id.id if source_lot.stone_size_id else False,
                "stone_size": source_lot.stone_size,
                "shape_id": source_lot.shape_id.id if source_lot.shape_id else False,
                "shape": source_lot.shape,
                "form_type_id": source_lot.form_type_id.id if source_lot.form_type_id else False,
                "form_type": source_lot.form_type,
                "is_defect_lot": source_lot.is_defect_lot,
                "defect_kind": source_lot.defect_kind,
                "company_id": self.company_id.id,
            }
        )

    def _confirm_receipt(self):
        destination = self._get_destination_location()
        defect_destination = self._get_defect_destination_location(destination)
        loss_destination = self._get_loss_destination_location()
        source_location = self._get_employee_location(self.worker_id)
        self._set_receipt_loss_weights()
        consumed_weight_by_lot = self._receipt_consumed_weight_by_lot()
        for source_lot_id, consumed_weight in consumed_weight_by_lot.items():
            source_lot = self.env["cabochon.stone.lot"].sudo().browse(source_lot_id)
            if float_compare(source_lot.current_weight_g, consumed_weight, precision_digits=4) < 0:
                raise UserError(f"В мешке {source_lot.display_name} недостаточно веса для сдачи.")
        for line in self.line_ids:
            source_lot = line.sudo().lot_id or self.request_id.sudo().source_lot_id
            consumed_weight = line.weight_g + line.defect_weight_g + line.lost_weight_g
            new_lot = line._create_received_lot(destination)
            line.new_lot_id = new_lot
            if line.weight_g:
                self.env["cabochon.manufacturing.movement"].sudo().create(
                    self._movement_values(line, "receipt", source_lot, line.weight_g, source_location, destination, new_lot)
                )
            if line.detected_defect_weight_g:
                defect_lot = line._create_defect_lot(defect_destination, "detected", line.detected_defect_weight_g)
                self.env["cabochon.manufacturing.movement"].sudo().create(
                    self._movement_values(
                        line,
                        "defect",
                        source_lot,
                        line.detected_defect_weight_g,
                        source_location,
                        defect_destination,
                        defect_lot,
                        defect_kind="detected",
                    )
                )
            if line.made_defect_weight_g:
                defect_lot = line._create_defect_lot(defect_destination, "made", line.made_defect_weight_g)
                self.env["cabochon.manufacturing.movement"].sudo().create(
                    self._movement_values(
                        line,
                        "defect",
                        source_lot,
                        line.made_defect_weight_g,
                        source_location,
                        defect_destination,
                        defect_lot,
                        defect_kind="made",
                    )
                )
            if line.lost_weight_g:
                self.env["cabochon.manufacturing.movement"].sudo().create(
                    self._movement_values(line, "loss", source_lot, line.lost_weight_g, source_location, loss_destination)
                )
            if source_lot:
                remaining_weight = source_lot.current_weight_g - consumed_weight
                source_lot.sudo().with_context(cabochon_inventory_movement=True).write(
                    {
                        "current_weight_g": remaining_weight,
                        "state": "consumed" if float_is_zero(remaining_weight, precision_digits=4) else source_lot.state,
                    }
                )
        if self.request_id and self.request_id.state in ("issued", "in_progress", "partially_done"):
            self.request_id.sudo()._finish_open_operation_lines(self.transfer_date)
            close_request = self.primary_operation_id.code in ("tumble_wash", "toluene_wash")
            self.request_id.sudo().write(
                {
                    "state": "done" if close_request else "partially_done",
                    "started_at": self.request_id.started_at or self.transfer_date,
                    "first_receipt_at": self.request_id.first_receipt_at or self.transfer_date,
                    "closed_at": self.request_id.closed_at or self.transfer_date if close_request else self.request_id.closed_at,
                }
            )
            if close_request:
                self.request_id.sudo()._clear_overdue_activities()
                self.request_id.sudo()._clear_loss_over_norm_activities()

    def _set_receipt_loss_weights(self):
        self.ensure_one()
        if self.transfer_type == "issue":
            return
        grouped_lines = {}
        for line in self.line_ids:
            source_lot = line.sudo().lot_id or self.request_id.sudo().source_lot_id
            source_lot_id = source_lot.id if source_lot else False
            grouped_lines.setdefault(source_lot_id, self.env["cabochon.material.transfer.line"])
            grouped_lines[source_lot_id] |= line
        for source_lot_id, lines in grouped_lines.items():
            source_lot = self.env["cabochon.stone.lot"].sudo().browse(source_lot_id)
            if not source_lot:
                for line in lines:
                    line.lost_weight_g = line._auto_loss_weight()
                continue
            input_weight = max(lines.mapped("weight_before_g")) or source_lot.current_weight_g
            for line in lines.filtered(lambda item: not item.weight_before_g):
                line.weight_before_g = input_weight
            good_weight = sum(lines.mapped("weight_g"))
            defect_weight = sum(lines.mapped("defect_weight_g"))
            if float_compare(good_weight + defect_weight, input_weight, precision_digits=4) > 0:
                raise UserError(
                    f"По мешку {source_lot.display_name} сумма годного веса и брака не может быть больше веса на входе."
                )
            loss_weight = input_weight - good_weight - defect_weight
            if float_compare(loss_weight, 0.0, precision_digits=4) < 0:
                loss_weight = 0.0
            for line in lines:
                line.lost_weight_g = 0.0
            if not float_is_zero(loss_weight, precision_digits=4):
                lines.sorted("id")[-1:].lost_weight_g = loss_weight

    def _receipt_consumed_weight_by_lot(self):
        self.ensure_one()
        consumed_weight_by_lot = {}
        for line in self.line_ids:
            source_lot = line.sudo().lot_id or self.request_id.sudo().source_lot_id
            if not source_lot:
                continue
            consumed_weight_by_lot.setdefault(source_lot.id, 0.0)
            consumed_weight_by_lot[source_lot.id] += line.weight_g + line.defect_weight_g + line.lost_weight_g
        return consumed_weight_by_lot

    def _movement_values(self, line, kind, lot, weight, source_location, destination_location, new_lot=False, defect_kind=False):
        return {
            "kind": kind,
            "defect_kind": defect_kind if kind == "defect" else False,
            "request_id": self.request_id.id if self.request_id else False,
            "transfer_id": self.id,
            "lot_id": lot.id if lot else False,
            "new_lot_id": new_lot.id if new_lot else False,
            "operation_ids": [(6, 0, self.operation_ids.ids)],
            "primary_operation_id": self.primary_operation_id.id if self.primary_operation_id else False,
            "source_location_id": source_location.id if source_location else False,
            "destination_location_id": destination_location.id if destination_location else False,
            "worker_id": self.worker_id.id if self.worker_id else False,
            "manager_id": self.manager_id.id if self.manager_id else False,
            "weight_g": weight,
            "source_weight_before_g": line.weight_before_g or (lot.current_weight_g if lot else 0.0),
            "movement_date": self.transfer_date,
            "company_id": self.company_id.id,
        }

    def _get_employee_location(self, employee):
        location = self.env["cabochon.manufacturing.location"].sudo().search(
            [("code", "=", "employee"), ("employee_id", "=", employee.id)],
            limit=1,
        )
        if location:
            return location
        return self.env["cabochon.manufacturing.location"].sudo().create(
            {
                "name": f"Личный склад: {employee.name}",
                "code": "employee",
                "employee_id": employee.id,
                "manager_id": employee.id,
            }
        )

    def _get_destination_location(self):
        self.ensure_one()
        if self.transfer_type == "receipt" and self.request_id:
            return self.request_id._get_receipt_destination_location()
        return self._get_destination_location_for_operations(self.operation_ids)

    @api.model
    def _get_destination_location_for_operations(self, operations):
        operation = operations.sorted("sequence")[-1:] if operations else False
        stage = operation.warehouse_stage if operation else "semi_finished"
        location = self.env["cabochon.manufacturing.location"].sudo().search([("code", "=", stage)], limit=1)
        if not location:
            raise UserError("Не найдена складская зона назначения.")
        return location

    def _get_warehouse_manager(self):
        self.ensure_one()
        if self.transfer_type == "issue":
            lot = self.request_id.sudo().source_lot_id if self.request_id else self.line_ids[:1].sudo().lot_id
            return lot.location_id.manager_id if lot else self.env["hr.employee"]
        destination = self._get_destination_location()
        return destination.manager_id

    def _get_loss_location(self):
        location = self.env["cabochon.manufacturing.location"].sudo().search([("code", "=", "loss")], limit=1)
        if not location:
            raise UserError("Не найдена зона потерь и списаний.")
        return location

    def _get_defect_destination_location(self, default_location):
        self.ensure_one()
        return default_location

    def _get_loss_destination_location(self):
        self.ensure_one()
        if self.primary_operation_id.final_operation:
            return self._get_stage_location("semi_finished")
        return self._get_loss_location()

    def _get_stage_location(self, code):
        location = self.env["cabochon.manufacturing.location"].sudo().search([("code", "=", code)], limit=1)
        if not location:
            raise UserError("Не найдена складская зона назначения.")
        return location


class CabochonMaterialTransferLine(models.Model):
    _name = "cabochon.material.transfer.line"
    _description = "Строка выдачи/сдачи материалов"
    _order = "id"

    transfer_id = fields.Many2one(
        "cabochon.material.transfer",
        string="Документ",
        required=True,
        ondelete="cascade",
    )
    transfer_type = fields.Selection(related="transfer_id.transfer_type", store=True, readonly=True)
    lot_id = fields.Many2one("cabochon.stone.lot", string="Исходный мешок", ondelete="restrict")
    new_lot_id = fields.Many2one("cabochon.stone.lot", string="Новый мешок", readonly=True, copy=False)
    weight_before_g = fields.Float(string="Вес до операции, г", digits=(16, 4))
    weight_g = fields.Float(string="Фактический вес, г", digits=(16, 4))
    detected_defect_weight_g = fields.Float(string="Выявленный брак, г", digits=(16, 4))
    made_defect_weight_g = fields.Float(string="Сделанный брак, г", digits=(16, 4))
    defect_weight_g = fields.Float(string="Брак итого, г", compute="_compute_defect_weight_g", store=True, readonly=False)
    lost_weight_g = fields.Float(string="Потери, г", digits=(16, 4))
    sort_type = fields.Char(string="Тип сортировки")
    color_id = fields.Many2one("cabochon.color", string="Цвет", ondelete="restrict")
    stone_size_id = fields.Many2one("cabochon.size", string="Размер", ondelete="restrict")
    shape_id = fields.Many2one("cabochon.shape", string="Форма", ondelete="restrict")
    form_type_id = fields.Many2one("cabochon.form.type", string="Тип формы", ondelete="restrict")
    color = fields.Char(string="Цвет (текст)")
    stone_size = fields.Char(string="Размер (текст)")
    shape = fields.Char(string="Форма (текст)")
    form_type = fields.Char(string="Тип формы (текст)")
    operation_code = fields.Char(related="transfer_id.primary_operation_id.code", store=True, readonly=True)
    note = fields.Text(string="Комментарий")

    @api.depends("detected_defect_weight_g", "made_defect_weight_g")
    def _compute_defect_weight_g(self):
        for line in self:
            line.defect_weight_g = line.detected_defect_weight_g + line.made_defect_weight_g

    def init(self):
        super().init()
        self.env.cr.execute(
            """
            UPDATE cabochon_material_transfer_line
               SET made_defect_weight_g = defect_weight_g
             WHERE COALESCE(defect_weight_g, 0.0) != 0.0
               AND COALESCE(detected_defect_weight_g, 0.0) = 0.0
               AND COALESCE(made_defect_weight_g, 0.0) = 0.0
            """
        )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        transfer_id = values.get("transfer_id") or self.env.context.get("default_transfer_id")
        if transfer_id:
            transfer = self.env["cabochon.material.transfer"].browse(transfer_id)
            self._add_receipt_defaults(values, transfer)
        return values

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._split_legacy_defect_value(vals)
            transfer = self.env["cabochon.material.transfer"]
            if vals.get("transfer_id"):
                transfer = transfer.browse(vals["transfer_id"])
            if transfer and transfer.state == "confirmed":
                raise UserError("Нельзя добавлять строки в подтвержденный документ. Создайте корректировку.")
            self._add_receipt_defaults(vals, transfer)
            self.env["cabochon.stone.lot"]._sync_reference_values(vals)
            self._add_auto_loss_to_values(vals)
        return super().create(vals_list)

    def write(self, vals):
        if any(line.transfer_id.state == "confirmed" for line in self):
            raise UserError("Строки подтвержденного документа нельзя менять. Создайте корректировку.")
        vals = dict(vals)
        self._split_legacy_defect_value(vals)
        self.env["cabochon.stone.lot"]._sync_reference_values(vals)
        if self and "lost_weight_g" not in vals and self._loss_trigger_fields(vals):
            for line in self:
                line_vals = dict(vals)
                line._add_auto_loss_to_values(line_vals)
                super(CabochonMaterialTransferLine, line).write(line_vals)
            return True
        return super().write(vals)

    def unlink(self):
        if any(line.transfer_id.state == "confirmed" for line in self):
            raise UserError("Строки подтвержденного документа нельзя удалить. Создайте корректировку.")
        return super().unlink()

    @api.onchange("lot_id")
    def _onchange_lot_id(self):
        if self.transfer_type != "issue" and self.lot_id and not self.weight_before_g:
            self.weight_before_g = self.lot_id.current_weight_g
        self._onchange_receipt_weights()

    @api.onchange("transfer_id")
    def _onchange_transfer_id(self):
        values = {}
        self._add_receipt_defaults(values, self.transfer_id)
        for field_name, value in values.items():
            if not self[field_name]:
                self[field_name] = value

    @api.onchange("weight_before_g", "weight_g", "detected_defect_weight_g", "made_defect_weight_g")
    def _onchange_receipt_weights(self):
        if self.transfer_type != "issue":
            self.lost_weight_g = self._auto_loss_weight()

    @api.model
    def _add_receipt_defaults(self, vals, transfer):
        if not transfer or transfer.transfer_type != "receipt":
            return
        if not vals.get("lot_id"):
            lot = transfer.line_ids[:1].lot_id or transfer.request_id.source_lot_id
            if lot:
                vals["lot_id"] = lot.id
                vals.setdefault("weight_before_g", lot.current_weight_g)
        operation_code = transfer.primary_operation_id.code if transfer.primary_operation_id else False
        if operation_code in SORT_OPERATION_TYPES and not vals.get("sort_type"):
            vals["sort_type"] = SORT_OPERATION_TYPES[operation_code]

    @api.onchange("color_id")
    def _onchange_color_id(self):
        self.color = self.color_id.name if self.color_id else False

    @api.onchange("stone_size_id")
    def _onchange_stone_size_id(self):
        self.stone_size = self.stone_size_id.name if self.stone_size_id else False

    @api.onchange("shape_id")
    def _onchange_shape_id(self):
        self.shape = self.shape_id.name if self.shape_id else False

    @api.onchange("form_type_id")
    def _onchange_form_type_id(self):
        self.form_type = self.form_type_id.name if self.form_type_id else False

    def _auto_loss_weight(self):
        self.ensure_one()
        weight_before = self.weight_before_g or 0.0
        if float_is_zero(weight_before, precision_digits=4):
            return self.lost_weight_g
        loss = weight_before - (self.weight_g or 0.0) - (self.defect_weight_g or 0.0)
        return loss if float_compare(loss, 0.0, precision_digits=4) > 0 else 0.0

    @api.model
    def _split_legacy_defect_value(self, vals):
        if "defect_weight_g" not in vals:
            return
        if "detected_defect_weight_g" not in vals and "made_defect_weight_g" not in vals:
            vals["made_defect_weight_g"] = vals.get("defect_weight_g") or 0.0
        vals.pop("defect_weight_g", None)

    def _set_auto_loss_weight(self):
        for line in self:
            if line.transfer_type != "issue" and not line.env.context.get("skip_receipt_auto_loss"):
                line.lost_weight_g = line._auto_loss_weight()

    @api.model
    def _loss_trigger_fields(self, vals):
        return bool({"lot_id", "weight_before_g", "weight_g", "detected_defect_weight_g", "made_defect_weight_g"}.intersection(vals))

    def _add_auto_loss_to_values(self, vals):
        transfer = self.transfer_id
        if vals.get("transfer_id"):
            transfer = self.env["cabochon.material.transfer"].browse(vals["transfer_id"])
        transfer_type = transfer.transfer_type or vals.get("transfer_type")
        if transfer_type == "issue" or "lost_weight_g" in vals:
            return
        weight_before = vals.get("weight_before_g", self.weight_before_g)
        if not weight_before and vals.get("lot_id"):
            weight_before = self.env["cabochon.stone.lot"].sudo().browse(vals["lot_id"]).current_weight_g
            vals.setdefault("weight_before_g", weight_before)
        if not weight_before:
            return
        weight = vals.get("weight_g", self.weight_g) or 0.0
        detected_defect = vals.get("detected_defect_weight_g", self.detected_defect_weight_g) or 0.0
        made_defect = vals.get("made_defect_weight_g", self.made_defect_weight_g) or 0.0
        defect = detected_defect + made_defect
        loss = weight_before - weight - defect
        vals["lost_weight_g"] = loss if float_compare(loss, 0.0, precision_digits=4) > 0 else 0.0

    def _validate_amounts(self):
        self.ensure_one()
        if not self.env.context.get("skip_receipt_auto_loss"):
            self._set_auto_loss_weight()
        for field_name in ("weight_g", "detected_defect_weight_g", "made_defect_weight_g", "lost_weight_g"):
            if float_compare(self[field_name], 0.0, precision_digits=4) < 0:
                raise UserError("Вес не может быть отрицательным.")
        if self.transfer_type == "issue" and not self.lot_id:
            raise UserError("В строке выдачи укажите мешок.")
        if self.transfer_type == "issue" and float_compare(self.weight_g, 0.0, precision_digits=4) <= 0:
            raise UserError("В строке выдачи укажите вес.")
        if self.transfer_type != "issue" and all(
            float_is_zero(self[field_name], precision_digits=4)
            for field_name in ("weight_g", "defect_weight_g", "lost_weight_g")
        ):
            raise UserError("В строке сдачи укажите годный вес, брак или потери.")
        if self.transfer_type != "issue" and self.weight_before_g:
            consumed_weight = self.weight_g + self.defect_weight_g + self.lost_weight_g
            if float_compare(consumed_weight, self.weight_before_g, precision_digits=4) > 0:
                raise UserError("Сумма годного веса, брака и потерь не может быть больше исходного веса.")
        if self.transfer_type == "defect":
            if float_compare(self.defect_weight_g, 0.0, precision_digits=4) <= 0:
                raise UserError("В документе приема брака укажите вес сданного брака.")
            if not float_is_zero(self.weight_g, precision_digits=4) or not float_is_zero(
                self.lost_weight_g,
                precision_digits=4,
            ):
                raise UserError("В документе приема брака нельзя указывать годный вес или потери.")
        if float_compare(self.defect_weight_g, 0.0, precision_digits=4) > 0:
            forbidden_operations = self.transfer_id.operation_ids.filtered(lambda operation: not operation.accepts_weighed_defect)
            if forbidden_operations:
                operation_names = ", ".join(forbidden_operations.mapped("display_name"))
                raise UserError(
                    f"Для операций {operation_names} прием брака в граммах отключен. "
                    "Укажите потери или выберите операцию, где брак принимается."
                )
        if self.transfer_type == "receipt":
            self._validate_required_receipt_attributes()

    def _validate_required_receipt_attributes(self):
        self.ensure_one()
        operation_code = self.transfer_id.primary_operation_id.code if self.transfer_id.primary_operation_id else False
        if operation_code in ("manual_sorting", "auto_separator"):
            missing = []
            if not self.sort_type:
                missing.append("тип сортировки")
            if not self.color_id:
                missing.append("цвет")
            if not self.stone_size_id:
                missing.append("размер")
            if missing:
                raise UserError(f"Для сдачи после сортировки заполните: {', '.join(missing)}.")
        operation_codes = set(self.transfer_id.operation_ids.mapped("code"))
        if "press" in operation_codes:
            missing = []
            if not self.shape_id:
                missing.append("форма")
            if not self.stone_size_id:
                missing.append("размер")
            if missing:
                raise UserError(f"Для сдачи после пресса заполните: {', '.join(missing)}.")

    def _create_received_lot(self, destination):
        self.ensure_one()
        if float_is_zero(self.weight_g, precision_digits=4):
            return self.env["cabochon.stone.lot"]
        source_lot = self.lot_id or self.transfer_id.request_id.source_lot_id
        values = {
            "name": self._next_received_lot_name(source_lot),
            "parent_id": source_lot.id if source_lot else False,
            "supplier_id": source_lot.supplier_id.id if source_lot else False,
            "fraction": source_lot.fraction if source_lot else False,
            "fraction_id": source_lot.fraction_id.id if source_lot and source_lot.fraction_id else False,
            "extraction_year": source_lot.extraction_year if source_lot else False,
            "extraction_year_id": source_lot.extraction_year_id.id if source_lot and source_lot.extraction_year_id else False,
            "extraction_month": source_lot.extraction_month if source_lot else False,
            "waybill_number": source_lot.waybill_number if source_lot else False,
            "accepted_by_id": self.transfer_id.manager_id.id if self.transfer_id.manager_id else False,
            "operation_id": self.transfer_id.operation_ids.sorted("sequence")[-1:].id if self.transfer_id.operation_ids else False,
            "location_id": destination.id,
            "initial_weight_g": self.weight_g,
            "current_weight_g": self.weight_g,
            "color_id": self.color_id.id if self.color_id else source_lot.color_id.id if source_lot and source_lot.color_id else False,
            "color": self.color or (source_lot.color if source_lot else False),
            "stone_size_id": self.stone_size_id.id
            if self.stone_size_id
            else source_lot.stone_size_id.id
            if source_lot and source_lot.stone_size_id
            else False,
            "stone_size": self.stone_size or (source_lot.stone_size if source_lot else False),
            "shape_id": self.shape_id.id if self.shape_id else source_lot.shape_id.id if source_lot and source_lot.shape_id else False,
            "shape": self.shape or (source_lot.shape if source_lot else False),
            "form_type_id": self.form_type_id.id
            if self.form_type_id
            else source_lot.form_type_id.id
            if source_lot and source_lot.form_type_id
            else False,
            "form_type": self.form_type or (source_lot.form_type if source_lot else False),
            "company_id": self.transfer_id.company_id.id,
        }
        return self.env["cabochon.stone.lot"].sudo().create(values)

    def _create_defect_lot(self, destination, defect_kind, weight_g):
        self.ensure_one()
        if float_is_zero(weight_g, precision_digits=4):
            return self.env["cabochon.stone.lot"]
        source_lot = self.lot_id or self.transfer_id.request_id.source_lot_id
        values = {
            "name": self._next_received_lot_name(source_lot, suffix=defect_kind.upper()),
            "parent_id": source_lot.id if source_lot else False,
            "supplier_id": source_lot.supplier_id.id if source_lot else False,
            "fraction": source_lot.fraction if source_lot else False,
            "fraction_id": source_lot.fraction_id.id if source_lot and source_lot.fraction_id else False,
            "extraction_year": source_lot.extraction_year if source_lot else False,
            "extraction_year_id": source_lot.extraction_year_id.id if source_lot and source_lot.extraction_year_id else False,
            "extraction_month": source_lot.extraction_month if source_lot else False,
            "waybill_number": source_lot.waybill_number if source_lot else False,
            "accepted_by_id": self.transfer_id.manager_id.id if self.transfer_id.manager_id else False,
            "operation_id": self.transfer_id.operation_ids.sorted("sequence")[-1:].id if self.transfer_id.operation_ids else False,
            "location_id": destination.id,
            "initial_weight_g": weight_g,
            "current_weight_g": weight_g,
            "color_id": self.color_id.id if self.color_id else source_lot.color_id.id if source_lot and source_lot.color_id else False,
            "color": self.color or (source_lot.color if source_lot else False),
            "stone_size_id": self.stone_size_id.id
            if self.stone_size_id
            else source_lot.stone_size_id.id
            if source_lot and source_lot.stone_size_id
            else False,
            "stone_size": self.stone_size or (source_lot.stone_size if source_lot else False),
            "shape_id": self.shape_id.id if self.shape_id else source_lot.shape_id.id if source_lot and source_lot.shape_id else False,
            "shape": self.shape or (source_lot.shape if source_lot else False),
            "form_type_id": self.form_type_id.id
            if self.form_type_id
            else source_lot.form_type_id.id
            if source_lot and source_lot.form_type_id
            else False,
            "form_type": self.form_type or (source_lot.form_type if source_lot else False),
            "is_defect_lot": True,
            "defect_kind": defect_kind,
            "company_id": self.transfer_id.company_id.id,
        }
        return self.env["cabochon.stone.lot"].sudo().create(values)

    def _next_received_lot_name(self, source_lot, suffix=False):
        if not source_lot:
            return "Новый"
        lot_model = self.env["cabochon.stone.lot"].sudo()
        operation_suffix = "-".join(
            OPERATION_CODE_SUFFIXES.get(operation.code, operation.code.upper())
            for operation in self.transfer_id.operation_ids.sorted("sequence")
            if operation.code
        )
        parts = [source_lot.name]
        if operation_suffix:
            parts.append(operation_suffix)
        if suffix:
            parts.append(suffix)
        base_name = "-".join(parts)
        index = 1
        while lot_model.search_count(["|", ("name", "=", f"{base_name}-{index}"), ("barcode", "=", f"{base_name}-{index}")]):
            index += 1
        return f"{base_name}-{index}"


class CabochonManufacturingMovement(models.Model):
    _name = "cabochon.manufacturing.movement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Журнал движений изготовления кабошонов"
    _order = "movement_date desc, id desc"

    name = fields.Char(string="Номер", default="Новый", readonly=True, copy=False)
    kind = fields.Selection(
        [
            ("receipt", "Приход"),
            ("issue", "Выдача"),
            ("defect", "Брак"),
            ("loss", "Потеря"),
            ("correction", "Корректировка"),
        ],
        string="Вид движения",
        required=True,
        tracking=True,
    )
    defect_kind = fields.Selection(
        [("detected", "Выявленный брак"), ("made", "Сделанный брак")],
        string="Тип брака",
    )
    request_id = fields.Many2one("cabochon.production.request", string="Заявка", ondelete="restrict")
    transfer_id = fields.Many2one("cabochon.material.transfer", string="Документ", ondelete="restrict")
    lot_id = fields.Many2one("cabochon.stone.lot", string="Исходный мешок", ondelete="restrict")
    new_lot_id = fields.Many2one("cabochon.stone.lot", string="Новый мешок", ondelete="restrict")
    operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_movement_operation_rel",
        "movement_id",
        "operation_id",
        string="Операции",
    )
    primary_operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        compute="_compute_primary_operation_id",
        store=True,
        readonly=False,
        string="Операция для отчетов",
    )
    report_lot_id = fields.Many2one(
        "cabochon.stone.lot",
        compute="_compute_report_lot_id",
        store=True,
        string="Мешок для отчетов",
    )
    report_lot_extraction_year = fields.Integer(
        string="Год добычи мешка",
        related="report_lot_id.extraction_year",
        store=True,
        readonly=True,
        aggregator=False,
    )
    report_lot_extraction_month = fields.Selection(
        string="Месяц добычи мешка",
        related="report_lot_id.extraction_month",
        store=True,
        readonly=True,
    )
    source_weight_before_g = fields.Float(
        string="Исходный вес до операции, г",
        digits=(16, 4),
        readonly=True,
        aggregator=False,
    )
    loss_norm_percent = fields.Float(
        string="Норма потерь, %",
        compute="_compute_loss_quality",
        store=True,
    )
    loss_percent = fields.Float(
        string="Факт потерь, %",
        compute="_compute_loss_quality",
        store=True,
    )
    loss_over_norm_percent = fields.Float(
        string="Отклонение от нормы, %",
        compute="_compute_loss_quality",
        store=True,
    )
    is_loss_over_norm = fields.Boolean(
        string="Потери выше нормы",
        compute="_compute_loss_quality",
        store=True,
    )
    source_location_id = fields.Many2one("cabochon.manufacturing.location", string="Откуда", ondelete="restrict")
    destination_location_id = fields.Many2one("cabochon.manufacturing.location", string="Куда", ondelete="restrict")
    worker_id = fields.Many2one("hr.employee", string="Работник", ondelete="restrict")
    manager_id = fields.Many2one("hr.employee", string="Ответственный", ondelete="restrict")
    weight_g = fields.Float(string="Вес, г", digits=(16, 4), required=True)
    movement_date = fields.Datetime(string="Дата движения", default=fields.Datetime.now, required=True)
    correction_of_id = fields.Many2one("cabochon.manufacturing.movement", string="Корректирует", ondelete="restrict")
    note = fields.Text(string="Комментарий")
    company_id = fields.Many2one(
        "res.company",
        string="Компания",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "Новый") == "Новый":
                vals["name"] = sequence.next_by_code("cabochon.manufacturing.movement") or "Новый"
        movements = super().create(vals_list)
        movements.filtered(lambda movement: movement.is_loss_over_norm)._notify_loss_over_norm()
        return movements

    @api.depends("operation_ids")
    def _compute_primary_operation_id(self):
        for movement in self:
            movement.primary_operation_id = movement.operation_ids.sorted("sequence")[-1:] if movement.operation_ids else False

    @api.depends("kind", "lot_id", "new_lot_id")
    def _compute_report_lot_id(self):
        for movement in self:
            movement.report_lot_id = (
                movement.new_lot_id
                if movement.kind in ("receipt", "defect") and movement.new_lot_id
                else movement.lot_id or movement.new_lot_id
            )

    @api.depends("kind", "weight_g", "source_weight_before_g", "primary_operation_id.expected_loss_percent")
    def _compute_loss_quality(self):
        for movement in self:
            norm = movement.primary_operation_id.expected_loss_percent or 0.0
            fact = 0.0
            if movement.kind == "loss" and movement.source_weight_before_g:
                fact = movement.weight_g / movement.source_weight_before_g * 100.0
            over_norm = fact - norm
            movement.loss_norm_percent = norm if movement.kind == "loss" else 0.0
            movement.loss_percent = fact
            movement.loss_over_norm_percent = over_norm if over_norm > 0 else 0.0
            movement.is_loss_over_norm = bool(movement.kind == "loss" and over_norm > 0)

    def _notify_loss_over_norm(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id("cabochon.production.request")
        today = fields.Date.context_today(self)
        for movement in self.filtered(lambda item: item.request_id.technologist_id.user_id):
            request = movement.request_id
            user = request.technologist_id.user_id
            existing = self.env["mail.activity"].sudo().search(
                [
                    ("res_model_id", "=", model_id),
                    ("res_id", "=", request.id),
                    ("activity_type_id", "=", activity_type.id),
                    ("user_id", "=", user.id),
                    ("summary", "=", "Потери выше нормы"),
                ],
                limit=1,
            )
            if existing:
                continue
            request.sudo().with_context(cabochon_activity_system_update=True).activity_schedule(
                activity_type_id=activity_type.id,
                date_deadline=today,
                summary="Потери выше нормы",
                note=(
                    "По заявке есть потери выше нормы операции. "
                    f"Факт: {movement.loss_percent:.2f}%, норма: {movement.loss_norm_percent:.2f}%."
                ),
                user_id=user.id,
            )

    def write(self, vals):
        raise UserError("Движения нельзя менять. Для исправления создайте корректирующее движение.")

    def unlink(self):
        raise UserError("Движения нельзя удалять. Для исправления создайте корректировку.")

    def action_open_correction_wizard(self):
        self.ensure_one()
        report_lot = self.report_lot_id or self.new_lot_id or self.lot_id
        if not self.env["cabochon.movement.correction.wizard"]._user_can_correct_lot(report_lot):
            raise UserError("У вас нет права корректировать этот мешок на его текущем складе.")
        return {
            "type": "ir.actions.act_window",
            "name": "Корректировка движения",
            "res_model": "cabochon.movement.correction.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_correction_of_id": self.id,
                "default_lot_id": report_lot.id if report_lot else False,
            },
        }


class CabochonMovementCorrectionWizard(models.TransientModel):
    _name = "cabochon.movement.correction.wizard"
    _description = "Мастер корректировки движения Кабошонов"

    correction_type = fields.Selection(
        [
            ("weight", "Корректировка веса"),
            ("location", "Корректировка склада"),
        ],
        string="Тип корректировки",
        default="weight",
        required=True,
    )
    correction_of_id = fields.Many2one(
        "cabochon.manufacturing.movement",
        string="Корректирует движение",
        ondelete="restrict",
    )
    lot_id = fields.Many2one(
        "cabochon.stone.lot",
        string="Мешок",
        required=True,
        ondelete="restrict",
    )
    current_weight_g = fields.Float(string="Текущий вес, г", related="lot_id.current_weight_g", readonly=True)
    current_location_id = fields.Many2one(
        "cabochon.manufacturing.location",
        string="Текущий склад",
        related="lot_id.location_id",
        readonly=True,
    )
    delta_weight_g = fields.Float(string="Изменение веса, г", digits=(16, 4))
    destination_location_id = fields.Many2one(
        "cabochon.manufacturing.location",
        string="Новый склад",
        ondelete="restrict",
    )
    reason = fields.Text(string="Причина", required=True)

    def action_apply(self):
        self.ensure_one()
        self._check_correction_scope()
        if self.correction_type == "weight":
            self._apply_weight_correction()
        else:
            self._apply_location_correction()
        return {"type": "ir.actions.act_window_close"}

    @api.model
    def _user_allowed_correction_location_codes(self):
        user = self.env.user
        if user.has_group("cabochon_base.group_cabochon_admin"):
            return {"raw", "prepared", "semi_finished", "finished", "employee", "loss"}
        allowed_codes = set()
        if user.has_group("cabochon_base.group_cabochon_manager"):
            allowed_codes.update({"raw", "prepared", "semi_finished"})
        if user.has_group("cabochon_base.group_cabochon_finished_manager"):
            allowed_codes.add("finished")
        return allowed_codes

    @api.model
    def _user_can_correct_lot(self, lot):
        if not lot:
            return False
        return self._user_can_correct_location(lot.location_id)

    @api.model
    def _user_can_correct_location(self, location):
        if not location:
            return False
        allowed_codes = self._user_allowed_correction_location_codes()
        if location.code not in allowed_codes:
            return False
        if self.env.user.has_group("cabochon_base.group_cabochon_admin"):
            return True
        return bool(self.env.user.employee_id and location.manager_id == self.env.user.employee_id)

    def _check_correction_scope(self):
        if not self._user_can_correct_location(self.lot_id.location_id):
            raise UserError("У вас нет права корректировать мешок на этом складе.")
        if self.correction_type == "location" and not self._user_can_correct_location(self.destination_location_id):
            raise UserError("У вас нет права переносить мешок на указанный склад.")

    def _apply_weight_correction(self):
        if float_is_zero(self.delta_weight_g, precision_digits=4):
            raise UserError("Укажите ненулевое изменение веса.")
        new_weight = self.lot_id.current_weight_g + self.delta_weight_g
        if float_compare(new_weight, 0.0, precision_digits=4) < 0:
            raise UserError("Корректировка не может сделать текущий вес мешка отрицательным.")
        source_location = self.lot_id.location_id
        self.lot_id.with_context(cabochon_inventory_movement=True).write(
            {
                "current_weight_g": new_weight,
                "state": self._state_for_location(source_location, new_weight),
            }
        )
        self._create_correction_movement(
            weight_g=self.delta_weight_g,
            source_location=source_location,
            destination_location=source_location,
            note_prefix="Корректировка веса",
        )

    def _apply_location_correction(self):
        if not self.destination_location_id:
            raise UserError("Укажите новый склад.")
        source_location = self.lot_id.location_id
        destination_location = self.destination_location_id
        owner_employee = destination_location.employee_id if destination_location.code == "employee" else False
        self.lot_id.with_context(cabochon_inventory_movement=True).write(
            {
                "location_id": destination_location.id,
                "owner_employee_id": owner_employee.id if owner_employee else False,
                "state": self._state_for_location(destination_location, self.lot_id.current_weight_g),
            }
        )
        self._create_correction_movement(
            weight_g=self.lot_id.current_weight_g,
            source_location=source_location,
            destination_location=destination_location,
            note_prefix="Корректировка склада",
        )

    def _create_correction_movement(self, weight_g, source_location, destination_location, note_prefix):
        manager = self.env.user.employee_id
        movement_values = {
            "kind": "correction",
            "correction_of_id": self.correction_of_id.id if self.correction_of_id else False,
            "lot_id": self.lot_id.id,
            "source_location_id": source_location.id if source_location else False,
            "destination_location_id": destination_location.id if destination_location else False,
            "manager_id": manager.id if manager else False,
            "weight_g": weight_g,
            "movement_date": fields.Datetime.now(),
            "note": f"{note_prefix}: {self.reason}",
            "company_id": self.lot_id.company_id.id,
        }
        return self.env["cabochon.manufacturing.movement"].sudo().create(movement_values)

    def _state_for_location(self, location, weight_g):
        if float_is_zero(weight_g, precision_digits=4):
            return "consumed"
        if location.code == "employee":
            return "issued"
        if location.code == "loss":
            return "written_off"
        return "available"


class CabochonExternalReceiptWizard(models.TransientModel):
    _name = "cabochon.external.receipt.wizard"
    _description = "Приход внешнего мешка сырья"

    supplier_id = fields.Many2one("res.partner", string="Поставщик", ondelete="restrict")
    location_id = fields.Many2one(
        "cabochon.manufacturing.location",
        string="Склад прихода",
        required=True,
        domain=[("code", "in", ("raw", "prepared"))],
        ondelete="restrict",
    )
    lot_name = fields.Char(string="ID мешка")
    fraction = fields.Char(string="Материал/фракция")
    fraction_id = fields.Many2one("cabochon.fraction", string="Фракция", ondelete="restrict")
    waybill_number = fields.Char(string="Номер накладной")
    extraction_year = fields.Integer(string="Год добычи (число)")
    extraction_year_id = fields.Many2one(
        "cabochon.extraction.year",
        string="Год добычи",
        ondelete="restrict",
    )
    extraction_month = fields.Selection([(str(month), str(month)) for month in range(1, 13)], string="Месяц добычи")
    initial_weight_g = fields.Float(string="Вес прихода, г", required=True, digits=(16, 4))
    note = fields.Text(string="Комментарий")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "location_id" in fields_list and not values.get("location_id"):
            location = self._available_receipt_locations()[:1]
            if location:
                values["location_id"] = location.id
        return values

    @api.model
    def _available_receipt_locations(self):
        domain = [("code", "in", ("raw", "prepared"))]
        if not self.env.user.has_group("cabochon_base.group_cabochon_admin"):
            domain.append(("manager_id", "=", self.env.user.employee_id.id))
        return self.env["cabochon.manufacturing.location"].search(domain)

    @api.onchange("extraction_year_id")
    def _onchange_extraction_year_id(self):
        self.extraction_year = self.extraction_year_id.year if self.extraction_year_id else False

    @api.onchange("fraction_id")
    def _onchange_fraction_id(self):
        self.fraction = self.fraction_id.name if self.fraction_id else False

    def action_create_receipt(self):
        self.ensure_one()
        if float_compare(self.initial_weight_g, 0.0, precision_digits=4) <= 0:
            raise UserError("Вес прихода должен быть больше нуля.")
        if self.location_id not in self._available_receipt_locations():
            raise UserError("Вы можете оформлять внешний приход только на закрепленный за вами склад сырья.")
        if self.lot_name:
            existing_lot = self.env["cabochon.stone.lot"].sudo().search(
                ["|", ("name", "=", self.lot_name), ("barcode", "=", self.lot_name)],
                limit=1,
            )
            if existing_lot:
                raise UserError(f"Мешок с ID {self.lot_name} уже существует.")
        lot_values = {
            "name": self.lot_name or "Новый",
            "supplier_id": self.supplier_id.id if self.supplier_id else False,
            "fraction": self.fraction,
            "fraction_id": self.fraction_id.id if self.fraction_id else False,
            "waybill_number": self.waybill_number,
            "extraction_year": self.extraction_year,
            "extraction_year_id": self.extraction_year_id.id if self.extraction_year_id else False,
            "extraction_month": self.extraction_month,
            "accepted_by_id": self.env.user.employee_id.id if self.env.user.employee_id else False,
            "location_id": self.location_id.id,
            "initial_weight_g": self.initial_weight_g,
            "current_weight_g": self.initial_weight_g,
        }
        lot = self.env["cabochon.stone.lot"].sudo().create(lot_values)
        if self.note:
            lot.message_post(body=self.note)
        return {
            "type": "ir.actions.act_window",
            "name": "Остаток на складе",
            "res_model": "cabochon.stone.lot",
            "res_id": lot.id,
            "view_mode": "form",
            "target": "current",
        }

