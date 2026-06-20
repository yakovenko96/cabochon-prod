from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

from .constants import EXTRACTION_MONTHS


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
    completed_operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        string="Проведенные операции",
        compute="_compute_completed_operation_ids",
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
    extraction_month = fields.Selection(EXTRACTION_MONTHS, string="Месяц добычи")
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
    state = fields.Selection(
        [
            ("available", "На складе"),
            ("issued", "Выдан работнику"),
            ("inventory_difference", "Ожидает инвентаризации"),
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

    def _compute_completed_operation_ids(self):
        operation_model = self.env["cabochon.manufacturing.operation"].sudo()
        for lot in self:
            lot.completed_operation_ids = operation_model.browse(
                lot._completed_operation_ids()
            ).sorted("sequence")

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

