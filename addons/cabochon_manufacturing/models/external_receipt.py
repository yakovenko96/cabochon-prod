from odoo import api, fields, models
from odoo.addons.cabochon_base.internal import INTERNAL
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

from .constants import EXTRACTION_MONTHS

WEIGHT_DIGITS = (16, 1)
PREPARED_OPERATION_CODES = {
    "manual_sorting",
    "auto_separator",
    "tubes",
    "tumble_wash",
    "toluene_wash",
}
SORT_OPERATION_CODES = {"manual_sorting", "auto_separator"}
MACHINE_OPERATION_CODES = {"cnc", "cabochon_machine", "ball_machine"}
SIZE_FLAG_BY_OPERATION = {
    "manual_sorting": "use_for_sorting",
    "auto_separator": "use_for_sorting",
    "tubes": "use_for_tubes",
    "press": "use_for_press",
    "cutting": "use_for_cutting",
    "cnc": "use_for_machine",
    "cabochon_machine": "use_for_machine",
    "ball_machine": "use_for_machine",
    "drilling": "use_for_drilling",
}
SHAPE_FLAG_BY_OPERATION = {
    "press": "use_for_press",
    "cutting": "use_for_cutting",
    "cnc": "use_for_machine",
    "cabochon_machine": "use_for_machine",
    "ball_machine": "use_for_machine",
}


class CabochonExternalReceiptWizard(models.TransientModel):
    _name = "cabochon.external.receipt.wizard"
    _inherit = "cabochon.once.mixin"
    _description = "Приход внешнего мешка сырья"

    receipt_source = fields.Selection(
        [("supplier", "Внешний приход"), ("contractor", "От контрагента")],
        string="Источник прихода", required=True, default="supplier",
    )
    contractor_id = fields.Many2one(
        "res.partner", string="Контрагент", ondelete="restrict",
        domain=[("is_cabochon_contractor", "=", True)],
    )
    supplier_id = fields.Many2one("cabochon.supplier", string="Поставщик", ondelete="restrict")
    supplier_name = fields.Char(string="Поставщик (текст)")
    location_id = fields.Many2one(
        "cabochon.manufacturing.location",
        string="Склад прихода",
        required=True,
        domain=[("code", "in", ("raw", "prepared", "semi_finished", "finished"))],
        ondelete="restrict",
    )
    location_code = fields.Selection(related="location_id.code")
    source_operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        string="Операция происхождения",
        ondelete="restrict",
    )
    eligible_source_operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        compute="_compute_receipt_form_state",
        string="Доступные операции происхождения",
    )
    show_raw_fields = fields.Boolean(compute="_compute_receipt_form_state")
    show_operation_fields = fields.Boolean(compute="_compute_receipt_form_state")
    show_color_fields = fields.Boolean(compute="_compute_receipt_form_state")
    show_size_fields = fields.Boolean(compute="_compute_receipt_form_state")
    show_shape_fields = fields.Boolean(compute="_compute_receipt_form_state")
    show_form_type_fields = fields.Boolean(compute="_compute_receipt_form_state")
    eligible_color_ids = fields.Many2many("cabochon.color", compute="_compute_receipt_form_state")
    eligible_stone_size_ids = fields.Many2many("cabochon.size", compute="_compute_receipt_form_state")
    eligible_shape_ids = fields.Many2many("cabochon.shape", compute="_compute_receipt_form_state")
    eligible_form_type_ids = fields.Many2many("cabochon.form.type", compute="_compute_receipt_form_state")
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
    extraction_month = fields.Selection(EXTRACTION_MONTHS, string="Месяц добычи")
    color_id = fields.Many2one("cabochon.color", string="Цвет", ondelete="restrict")
    stone_size_id = fields.Many2one("cabochon.size", string="Размер", ondelete="restrict")
    shape_id = fields.Many2one("cabochon.shape", string="Форма", ondelete="restrict")
    form_type_id = fields.Many2one("cabochon.form.type", string="Тип формы", ondelete="restrict")
    initial_weight_g = fields.Float(string="Вес прихода, г", required=True, digits=WEIGHT_DIGITS)
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
        domain = [("code", "in", ("raw", "prepared", "semi_finished", "finished"))]
        if not self.env.user.has_group("cabochon_base.group_cabochon_admin"):
            domain.append(("manager_id", "=", self.env.user.employee_id.id))
        return self.env["cabochon.manufacturing.location"].search(domain)

    @api.depends("location_id.code", "source_operation_id.code")
    def _compute_receipt_form_state(self):
        operation_model = self.env["cabochon.manufacturing.operation"].sudo()
        for wizard in self:
            location_code = wizard.location_id.code
            operation_code = wizard.source_operation_id.code
            wizard.show_raw_fields = location_code in ("raw", "prepared")
            wizard.show_operation_fields = location_code in ("prepared", "semi_finished", "finished")
            if location_code == "prepared":
                wizard.eligible_source_operation_ids = operation_model.search(
                    [("active", "=", True), ("code", "in", tuple(PREPARED_OPERATION_CODES))]
                )
            elif location_code == "semi_finished":
                wizard.eligible_source_operation_ids = operation_model.search(
                    [("active", "=", True), ("warehouse_stage", "=", "semi_finished"), ("final_operation", "=", False)]
                )
            elif location_code == "finished":
                wizard.eligible_source_operation_ids = operation_model.search(
                    [("active", "=", True), ("final_operation", "=", True)]
                )
            else:
                wizard.eligible_source_operation_ids = operation_model.browse()
            wizard.show_color_fields = location_code == "finished" or operation_code in SORT_OPERATION_CODES
            wizard.show_size_fields = location_code == "finished" or operation_code in SIZE_FLAG_BY_OPERATION
            wizard.show_shape_fields = location_code == "finished" or operation_code in SHAPE_FLAG_BY_OPERATION
            wizard.show_form_type_fields = location_code == "finished" or operation_code in MACHINE_OPERATION_CODES
            wizard.eligible_color_ids = self.env["cabochon.color"].sudo().search([("active", "=", True)])
            wizard.eligible_stone_size_ids = wizard._eligible_reference_records(
                "cabochon.size", SIZE_FLAG_BY_OPERATION.get(operation_code)
            )
            wizard.eligible_shape_ids = wizard._eligible_reference_records(
                "cabochon.shape", SHAPE_FLAG_BY_OPERATION.get(operation_code)
            )
            wizard.eligible_form_type_ids = self.env["cabochon.form.type"].sudo().search([("active", "=", True)])

    def _eligible_reference_records(self, model_name, usage_flag):
        domain = [("active", "=", True)]
        if usage_flag:
            domain.append((usage_flag, "=", True))
        return self.env[model_name].sudo().search(domain)

    @api.onchange("location_id")
    def _onchange_location_id(self):
        self.source_operation_id = False

    @api.onchange("source_operation_id")
    def _onchange_source_operation_id(self):
        for wizard in self:
            if not wizard.show_color_fields or wizard.color_id not in wizard.eligible_color_ids:
                wizard.color_id = False
            if not wizard.show_size_fields or wizard.stone_size_id not in wizard.eligible_stone_size_ids:
                wizard.stone_size_id = False
            if not wizard.show_shape_fields or wizard.shape_id not in wizard.eligible_shape_ids:
                wizard.shape_id = False
            if not wizard.show_form_type_fields or wizard.form_type_id not in wizard.eligible_form_type_ids:
                wizard.form_type_id = False

    @api.onchange("extraction_year_id")
    def _onchange_extraction_year_id(self):
        self.extraction_year = self.extraction_year_id.year if self.extraction_year_id else False

    @api.onchange("fraction_id")
    def _onchange_fraction_id(self):
        self.fraction = self.fraction_id.name if self.fraction_id else False

    @api.onchange("supplier_id")
    def _onchange_supplier_id(self):
        self.supplier_name = self.supplier_id.name if self.supplier_id else False

    def action_create_receipt(self):
        self.ensure_one()
        self._lock_execution()
        if self.receipt_source == "contractor":
            if not self.contractor_id:
                raise UserError("Для прихода от контрагента выберите контрагента.")
            self.contractor_id._check_cabochon_contractor(self.env.company)
        if float_compare(self.initial_weight_g, 0.0, precision_digits=4) <= 0:
            raise UserError("Вес прихода должен быть больше нуля.")
        if self.location_id not in self._available_receipt_locations():
            raise UserError("Вы можете оформлять внешний приход только на закрепленный за вами склад.")
        if self.show_operation_fields and not self.source_operation_id:
            raise UserError(
                "Для прихода подготовленного сырья, полуфабриката или готового изделия "
                "укажите операцию происхождения."
            )
        if self.source_operation_id and self.source_operation_id not in self.eligible_source_operation_ids:
            raise UserError("Выбранная операция не подходит для указанного склада прихода.")
        self._validate_operation_attributes()
        if self.lot_name:
            existing_lot = self.env["cabochon.stone.lot"].sudo().search(
                ["|", ("name", "=", self.lot_name), ("barcode", "=", self.lot_name)],
                limit=1,
            )
            if existing_lot:
                raise UserError(f"Мешок с ID {self.lot_name} уже существует.")
        lot_values = {
            "name": self.lot_name or "Новый",
            "supplier_id": self.supplier_id.id if self.receipt_source == "supplier" and self.supplier_id else False,
            "supplier_name": self.supplier_name if self.receipt_source == "supplier" else False,
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
            "color_id": self.color_id.id if self.color_id else False,
            "stone_size_id": self.stone_size_id.id if self.stone_size_id else False,
            "shape_id": self.shape_id.id if self.shape_id else False,
            "form_type_id": self.form_type_id.id if self.form_type_id else False,
        }
        create_context = {"skip_initial_lot_movement": INTERNAL}
        lot_model = self.env["cabochon.stone.lot"].sudo()
        lot = lot_model._find_finished_position(lot_values) if self.location_id.code == "finished" else lot_model
        if lot:
            lot.with_context(cabochon_inventory_movement=INTERNAL).write({
                "current_weight_g": lot.current_weight_g + self.initial_weight_g,
                "initial_weight_g": lot.initial_weight_g + self.initial_weight_g,
            })
        else:
            lot = lot_model.with_context(**create_context).create(lot_values)
        self.env["cabochon.manufacturing.movement"].sudo().with_context(cabochon_contractor_movement=INTERNAL).create({
            "kind": "receipt", "new_lot_id": lot.id, "weight_g": self.initial_weight_g,
            "destination_location_id": self.location_id.id, "company_id": lot.company_id.id,
            "manager_id": self.env.user.sudo().employee_id.id,
            "operation_ids": [(6, 0, self.source_operation_id.ids)],
            "contractor_id": self.contractor_id.id if self.receipt_source == "contractor" else False,
            "note": self.note,
        })
        self._mark_executed()
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

    def _validate_operation_attributes(self):
        self.ensure_one()
        missing = []
        if self.show_color_fields and not self.color_id:
            missing.append("цвет")
        if self.show_size_fields and not self.stone_size_id:
            missing.append("размер")
        if self.show_shape_fields and not self.shape_id:
            missing.append("форма")
        if self.show_form_type_fields and not self.form_type_id:
            missing.append("тип формы")
        if missing:
            raise UserError(f"Заполните характеристики прихода: {', '.join(missing)}.")

