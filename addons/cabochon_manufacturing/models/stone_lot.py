from odoo import api, fields, models
from odoo.addons.cabochon_base.internal import is_internal
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero

from ..inventory import lock_position
from .constants import EXTRACTION_MONTHS

WEIGHT_DIGITS = (16, 1)


class CabochonStoneLot(models.Model):
    _name = "cabochon.stone.lot"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Партия/мешок камней"
    _order = "receipt_date desc, id desc"

    def init(self):
        self.env.cr.execute("CREATE TABLE IF NOT EXISTS cabochon_inventory_guard (key text PRIMARY KEY, revision bigint NOT NULL)")

    name = fields.Char(string="ID мешка", default="Новый", required=True, copy=False, tracking=True)
    barcode = fields.Char(string="Штрихкод/QR", copy=False, readonly=True, index=True)
    parent_id = fields.Many2one("cabochon.stone.lot", string="Исходный мешок", ondelete="restrict", index=True)
    reserved_request_id = fields.Many2one("cabochon.production.request", string="Резерв заявки", readonly=True, index=True, ondelete="restrict", copy=False)
    is_finished_stock = fields.Boolean(compute="_compute_is_finished_stock", store=True)

    source_lot_ids = fields.Many2many(
        "cabochon.stone.lot",
        "cabochon_stone_lot_mixed_source_rel",
        "result_lot_id",
        "source_lot_id",
        string="Смешанные исходные мешки",
        readonly=True,
        copy=False,
    )
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
        compute_sudo=True,
    )
    completed_operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        string="Проведенные операции",
        compute="_compute_completed_operation_ids",
        compute_sudo=True,
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
    supplier_id = fields.Many2one("cabochon.supplier", string="Поставщик", ondelete="restrict", index=True)
    supplier_name = fields.Char(string="Поставщик (текст)")
    fraction = fields.Char(string="Фракция (текст)")
    fraction_id = fields.Many2one("cabochon.fraction", string="Фракция", ondelete="restrict", index=True)
    extraction_year = fields.Integer(string="Год добычи (число)")
    extraction_year_id = fields.Many2one(
        "cabochon.extraction.year",
        string="Год добычи",
        ondelete="restrict",
    )
    extraction_month = fields.Selection(EXTRACTION_MONTHS, string="Месяц добычи")
    waybill_number = fields.Char(string="Номер накладной")
    receipt_date = fields.Datetime(string="Дата поступления", default=fields.Datetime.now)
    accepted_by_id = fields.Many2one("hr.employee", string="Кто принял", ondelete="restrict", index=True)
    location_id = fields.Many2one(
        "cabochon.manufacturing.location",
        string="Текущая зона",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    owner_employee_id = fields.Many2one("hr.employee", string="На руках", ondelete="restrict", tracking=True)
    initial_weight_g = fields.Float(string="Начальный вес, г", digits=WEIGHT_DIGITS, required=True)
    current_weight_g = fields.Float(string="Текущий вес, г", digits=WEIGHT_DIGITS, required=True, tracking=True)
    estimated_quantity = fields.Float(
        string="Расчетное количество, шт.",
        compute="_compute_estimated_quantity",
        digits=(16, 2),
    )
    standard_weight_g = fields.Float(string="Эталонный вес 1 шт., г", digits=(16, 4), tracking=True)
    color_id = fields.Many2one("cabochon.color", string="Цвет", ondelete="restrict", index=True)
    stone_size_id = fields.Many2one("cabochon.size", string="Размер", ondelete="restrict", index=True)
    shape_id = fields.Many2one("cabochon.shape", string="Форма", ondelete="restrict", index=True)
    form_type_id = fields.Many2one("cabochon.form.type", string="Тип формы", ondelete="restrict", index=True)
    return_loss_operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        string="Операция возвратных потерь",
        ondelete="restrict",
    )
    defect_operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        string="Операция брака",
        ondelete="restrict",
    )
    color = fields.Char(string="Цвет (текст)")
    stone_size = fields.Char(string="Размер (текст)")
    shape = fields.Char(string="Форма (текст)")
    form_type = fields.Char(string="Тип формы (текст)")
    is_defect_lot = fields.Boolean(string="Бракованный мешок")
    is_return_loss_lot = fields.Boolean(string="Сводный мешок возвратных потерь")
    state = fields.Selection(
        [
            ("available", "На складе"),
            ("issued", "Выдан работнику"),
            ("inventory_difference", "Ожидает инвентаризации"),
            ("consumed", "Преобразован"),
            ("written_off", "Списан"),
        ],
        default="available",
        string="Статус",
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

    @api.depends("location_id.code", "is_defect_lot", "is_return_loss_lot")
    def _compute_is_finished_stock(self):
        for lot in self:
            lot.is_finished_stock = lot.location_id.code == "finished" and not lot.is_defect_lot and not lot.is_return_loss_lot

    @api.model
    def _find_finished_position(self, values):
        location_id = values["location_id"]
        company_id = values.get("company_id") or self.env.company.id
        attributes = [values.get(key) or False for key in ("color_id", "stone_size_id", "shape_id", "form_type_id")]
        lock_position(self.env, "finished", [location_id, company_id, *attributes])
        domain = [("location_id", "=", location_id), ("company_id", "=", company_id), ("state", "=", "available"), ("is_defect_lot", "=", False), ("is_return_loss_lot", "=", False)]
        domain += list(zip(("color_id", "stone_size_id", "shape_id", "form_type_id"), ["="] * 4, attributes, strict=True))
        return self.sudo().search(domain, order="id", limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        if not is_internal(self.env, "cabochon_inventory_movement") and any(vals.get("reserved_request_id") for vals in vals_list):
            raise UserError("Резерв устанавливается только заявкой.")
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            self._sync_extraction_year_values(vals)
            self._sync_fraction_values(vals)
            self._sync_supplier_values(vals)
            self._sync_reference_values(vals)
            if vals.get("name", "Новый") == "Новый":
                vals["name"] = sequence.next_by_code("cabochon.stone.lot") or "Новый"
            vals.setdefault("barcode", vals["name"])
            if not vals.get("current_weight_g") and vals.get("initial_weight_g"):
                vals["current_weight_g"] = vals["initial_weight_g"]
        lots = super().create(vals_list)
        if not is_internal(self.env, "skip_initial_lot_movement"):
            lots._create_initial_receipt_movements()
        return lots

    def write(self, vals):
        if (
            self.env.user.has_group("cabochon_base.group_cabochon_finished_manager")
            and not self.env.user.has_group("cabochon_base.group_cabochon_admin")
            and not is_internal(self.env, "cabochon_inventory_movement")
            and set(vals) - {"standard_weight_g"}
        ):
            raise UserError("Менеджер готового склада может менять в складской позиции только эталонный вес.")
        protected_fields = {
            "reserved_request_id",
            "barcode",
            "parent_id",
            "location_id",
            "owner_employee_id",
            "initial_weight_g",
            "current_weight_g",
            "state",
        }
        if protected_fields.intersection(vals) and not is_internal(self.env, "cabochon_inventory_movement"):
            raise UserError(
                "Наличие, вес и склад мешка нельзя редактировать вручную. "
                "Создайте выдачу, сдачу или корректирующее движение."
            )
        vals = dict(vals)
        self._sync_extraction_year_values(vals)
        self._sync_fraction_values(vals)
        self._sync_supplier_values(vals)
        self._sync_reference_values(vals)
        return super().write(vals)

    @api.onchange("supplier_id")
    def _onchange_supplier_id(self):
        self.supplier_name = self.supplier_id.name if self.supplier_id else False

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
    def _sync_supplier_values(self, vals):
        if vals.get("supplier_id"):
            supplier = self.env["cabochon.supplier"].sudo().browse(vals["supplier_id"])
            vals["supplier_name"] = supplier.name
        elif vals.get("supplier_name") and not vals.get("supplier_id"):
            vals["supplier_id"] = self._get_or_create_supplier(vals["supplier_name"]).id
        elif "supplier_name" in vals and not vals.get("supplier_name"):
            vals["supplier_id"] = False
        elif "supplier_id" in vals and not vals.get("supplier_id"):
            vals["supplier_name"] = False

    @api.model
    def _get_or_create_supplier(self, supplier_name):
        supplier_name = str(supplier_name).strip()
        supplier_model = self.env["cabochon.supplier"].sudo()
        return supplier_model.search([("name", "=", supplier_name)], limit=1) or supplier_model.create(
            {"name": supplier_name}
        )

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
        operation_ids = self.env.context.get("cabochon_initial_operation_ids") or []
        for lot in self.filtered(lambda item: not item.parent_id):
            movement_model.sudo().create(
                {
                    "kind": "receipt",
                    "new_lot_id": lot.id,
                    "operation_ids": [(6, 0, operation_ids)],
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
        "child_ids.location_id.manager_id.user_id",
        "child_ids.transfer_line_ids.transfer_id.manager_id.user_id",
        "child_ids.new_lot_transfer_line_ids.transfer_id.manager_id.user_id",
        "transfer_line_ids.transfer_id.manager_id.user_id",
        "new_lot_transfer_line_ids.transfer_id.manager_id.user_id",
    )
    def _compute_security_manager_user_ids(self):
        for lot in self:
            users = (
                lot.location_id.manager_id.user_id
                | lot.location_id.employee_id.user_id
                | lot.child_ids.location_id.manager_id.user_id
                | lot.child_ids.transfer_line_ids.transfer_id.manager_id.user_id
                | lot.child_ids.new_lot_transfer_line_ids.transfer_id.manager_id.user_id
                | lot.transfer_line_ids.transfer_id.manager_id.user_id
                | lot.new_lot_transfer_line_ids.transfer_id.manager_id.user_id
            )
            lot.security_manager_user_ids = users

    @api.depends("current_weight_g", "standard_weight_g", "location_id.code")
    def _compute_estimated_quantity(self):
        for lot in self:
            standard_weight = lot.standard_weight_g if lot.location_id.code == "finished" else 0.0
            lot.estimated_quantity = (
                lot.current_weight_g / standard_weight
                if standard_weight and not float_is_zero(standard_weight, precision_digits=4)
                else 0.0
            )

    @api.constrains("initial_weight_g", "current_weight_g", "extraction_year", "standard_weight_g", "location_id")
    def _check_lot_values(self):
        for lot in self:
            if float_compare(lot.initial_weight_g, 0.0, precision_digits=4) <= 0:
                raise ValidationError("Начальный вес мешка должен быть больше нуля.")
            if float_compare(lot.current_weight_g, 0.0, precision_digits=4) < 0:
                raise ValidationError("Текущий вес мешка не может быть отрицательным.")
            if lot.extraction_year and (lot.extraction_year < 1900 or lot.extraction_year > 2100):
                raise ValidationError("Проверьте год добычи.")
            if float_compare(lot.standard_weight_g, 0.0, precision_digits=4) < 0:
                raise ValidationError("Эталонный вес не может быть отрицательным.")
            if lot.standard_weight_g and lot.location_id.code != "finished":
                raise ValidationError("Эталонный вес можно задавать только для позиции готового склада.")

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

    def action_open_defect_recovery_wizard(self):
        self.ensure_one()
        if not self.is_defect_lot:
            raise UserError("Обратное преобразование доступно только для сводных мешков брака.")
        return {
            "type": "ir.actions.act_window",
            "name": "Возврат брака в полуфабрикаты",
            "res_model": "cabochon.defect.recovery.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_defect_lot_id": self.id,
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
                ("kind", "in", ("receipt", "defect", "loss", "recovery")),
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
        if self.is_return_loss_lot:
            return True
        completed_codes = self._completed_operation_codes()
        return self.env["cabochon.production.request"]._operation_route_error(operations, completed_codes) is False

    def _lineage_lot_ids(self):
        self.ensure_one()
        lots = self
        frontier = self
        while frontier:
            sources = frontier.mapped("parent_id") | frontier.mapped("source_lot_ids")
            sources -= lots
            if not sources:
                break
            lots |= sources
            frontier = sources
        return lots.ids

    def _route_lot_ids(self):
        self.ensure_one()
        lots = self.browse(self._lineage_lot_ids())
        frontier = lots
        while frontier:
            children = self.search(
                ["|", ("parent_id", "in", frontier.ids), ("source_lot_ids", "in", frontier.ids)]
            )
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

