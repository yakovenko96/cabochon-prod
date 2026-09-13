from odoo import fields, models
from odoo.exceptions import UserError


class CabochonScanLot(models.TransientModel):
    _name = "cabochon.scan.lot"
    _description = "Найти мешок по коду"

    code = fields.Char(string="Штрихкод или ID мешка", required=True)

    def action_open(self):
        self.ensure_one()
        self.check_access("read")
        code = (self.code or "").strip()
        lot = self.env["cabochon.stone.lot"].search(["|", ("barcode", "=", code), ("name", "=", code)], limit=2)
        if not lot:
            raise UserError("Мешок не найден среди доступных вам остатков.")
        if len(lot) > 1:
            raise UserError("Найдено несколько мешков. Используйте уникальный штрихкод.")
        return {"type": "ir.actions.act_window", "res_model": lot._name, "res_id": lot.id, "view_mode": "form"}
