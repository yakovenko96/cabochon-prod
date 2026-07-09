from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

from .constants import EXTRACTION_MONTHS

WEIGHT_DIGITS = (16, 1)


class CabochonExternalReceiptWizard(models.TransientModel):
    _name = "cabochon.external.receipt.wizard"
    _description = "Приход внешнего мешка сырья"

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
            wizard.show_operation_fields = location_code in ("semi_finished", "finished")
            if location_code == "semi_finished":
                wizard.eligible_source_operation_ids = operation_model.search(
                    [("active", "=", True), ("warehouse_stage", "=", "semi_finished"), ("final_operation", "=", False)]
                )
            elif location_code == "finished":
                wizard.eligible_source_operation_ids = operation_model.search(
                    [("active", "=", True), ("final_operation", "=", True)]
                )
            else:
                wizard.eligible_source_operation_ids = operation_model.browse()
            wizard.show_color_fields = location_code in ("semi_finished", "finished") or operation_code in (
                "manual_sorting",
                "auto_separator",
            )
            wizard.show_size_fields = location_code == "finished" or operation_code in (
                "manual_sorting",
                "auto_separator",
                "tubes",
                "press",
                "cutting",
                "cnc",
                "cabochon_machine",
                "ball_machine",
                "drilling",
            )
            wizard.show_shape_fields = location_code == "finished" or operation_code in (
                "press",
                "cutting",
                "cnc",
                "cabochon_machine",
                "ball_machine",
            )
            wizard.show_form_type_fields = location_code == "finished" or operation_code in (
                "cnc",
                "cabochon_machine",
                "ball_machine",
            )

    @api.onchange("location_id")
    def _onchange_location_id(self):
        self.source_operation_id = False

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
        if float_compare(self.initial_weight_g, 0.0, precision_digits=4) <= 0:
            raise UserError("Вес прихода должен быть больше нуля.")
        if self.location_id not in self._available_receipt_locations():
            raise UserError("Вы можете оформлять внешний приход только на закрепленный за вами склад.")
        if self.show_operation_fields and not self.source_operation_id:
            raise UserError("Для прихода полуфабриката или готового изделия укажите операцию происхождения.")
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
            "supplier_name": self.supplier_name,
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
        create_context = {}
        if self.source_operation_id:
            create_context["cabochon_initial_operation_ids"] = [self.source_operation_id.id]
        lot = self.env["cabochon.stone.lot"].sudo().with_context(**create_context).create(lot_values)
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

