from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

from .constants import EXTRACTION_MONTHS

WEIGHT_DIGITS = (16, 1)


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
    extraction_month = fields.Selection(EXTRACTION_MONTHS, string="Месяц добычи")
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

