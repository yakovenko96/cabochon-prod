import math

from odoo import api, fields, models, tools
from odoo.addons.cabochon_base.internal import INTERNAL
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_cabochon_contractor = fields.Boolean(string="Контрагент производства")

    def _check_cabochon_contractor(self, company):
        self.ensure_one()
        self.check_access("read")
        if not self.active or not self.is_cabochon_contractor:
            raise UserError("Выберите действующего контрагента производства.")
        if company not in self.env.companies or (self.company_id and self.company_id != company):
            raise UserError("Контрагент должен быть общим или принадлежать компании документа.")


class CabochonContractorIssueWizard(models.TransientModel):
    _name = "cabochon.contractor.issue.wizard"
    _inherit = "cabochon.once.mixin"
    _description = "Выдача исходного сырья контрагенту"

    contractor_id = fields.Many2one(
        "res.partner", string="Контрагент", required=True, ondelete="restrict",
        domain=[("is_cabochon_contractor", "=", True)],
    )
    lot_id = fields.Many2one(
        "cabochon.stone.lot", string="Исходный мешок", required=True, ondelete="restrict",
        domain=[("location_id.code", "=", "raw"), ("state", "=", "available"),
                ("is_defect_lot", "=", False), ("is_return_loss_lot", "=", False),
                ("reserved_request_id", "=", False), ("current_weight_g", ">", 0)],
    )
    company_id = fields.Many2one(related="lot_id.company_id", string="Компания")
    available_weight_g = fields.Float(related="lot_id.current_weight_g", string="Доступно, г", digits=(16, 1))
    weight_g = fields.Float(string="Вес к выдаче, г", required=True, digits=(16, 1))
    issue_date = fields.Datetime(string="Дата выдачи", required=True, default=fields.Datetime.now)
    note = fields.Text(string="Комментарий")

    @api.model
    def _check_weight_input(self, values):
        if "weight_g" in values:
            try:
                finite = math.isfinite(float(values["weight_g"] or 0))
            except (TypeError, ValueError):
                finite = False
            if not finite:
                raise UserError("Вес выдачи должен быть конечным числом.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_weight_input(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_weight_input(vals)
        return super().write(vals)

    def action_issue(self):
        self.ensure_one()
        self._lock_execution()
        lot = self.lot_id
        lot.check_access("read")
        self.env.cr.execute("SELECT id FROM cabochon_stone_lot WHERE id = %s FOR UPDATE", [lot.id])
        lot.invalidate_recordset()
        self.contractor_id._check_cabochon_contractor(lot.company_id)
        if not self.env.user.has_group("cabochon_base.group_cabochon_admin") and lot.location_id.manager_id.user_id != self.env.user:
            raise UserError("Выдавать сырье контрагенту может только ответственный менеджер этого склада или администратор.")
        if (
            lot.location_id.code != "raw" or lot.state != "available" or lot.owner_employee_id
            or lot.is_defect_lot or lot.is_return_loss_lot or lot.reserved_request_id
            or lot._completed_operation_ids()
        ):
            raise UserError("Контрагенту можно выдать только свободное обычное сырье со склада сырья, не проходившее операций.")
        if not math.isfinite(self.weight_g) or float_compare(self.weight_g, 0, precision_digits=4) <= 0:
            raise UserError("Вес выдачи должен быть конечным числом больше нуля.")
        if float_compare(self.weight_g, lot.current_weight_g, precision_digits=4) > 0:
            raise UserError("Вес выдачи не может превышать остаток мешка.")
        remaining = lot.current_weight_g - self.weight_g
        lot.sudo().with_context(cabochon_inventory_movement=INTERNAL).write({
            "current_weight_g": remaining,
            "state": "written_off" if float_is_zero(remaining, precision_digits=4) else "available",
        })
        self.env["cabochon.manufacturing.movement"].sudo().with_context(cabochon_contractor_movement=INTERNAL).create({
            "kind": "issue", "lot_id": lot.id, "contractor_id": self.contractor_id.id,
            "source_location_id": lot.location_id.id, "weight_g": self.weight_g,
            "manager_id": lot.location_id.manager_id.id, "movement_date": self.issue_date,
            "company_id": lot.company_id.id, "note": self.note,
        })
        self._mark_executed()
        return {"type": "ir.actions.act_window_close"}


class CabochonContractorReport(models.Model):
    _name = "cabochon.contractor.report"
    _description = "Передано контрагентам и получено от контрагентов"
    _auto = False
    _order = "movement_date desc, id desc"

    contractor_id = fields.Many2one("res.partner", string="Контрагент", readonly=True)
    company_id = fields.Many2one("res.company", string="Компания", readonly=True)
    movement_id = fields.Many2one("cabochon.manufacturing.movement", string="Движение", readonly=True)
    movement_date = fields.Datetime(string="Дата", readonly=True)
    direction = fields.Selection([("issue", "Выдали"), ("receipt", "Получили")], string="Направление", readonly=True)
    lot_id = fields.Many2one("cabochon.stone.lot", string="Мешок / позиция", readonly=True)
    location_id = fields.Many2one("cabochon.manufacturing.location", string="Склад", readonly=True)
    material_description = fields.Char(string="Характеристики", readonly=True)
    fraction_id = fields.Many2one("cabochon.fraction", string="Фракция", readonly=True)
    color_id = fields.Many2one("cabochon.color", string="Цвет", readonly=True)
    stone_size_id = fields.Many2one("cabochon.size", string="Размер", readonly=True)
    shape_id = fields.Many2one("cabochon.shape", string="Форма", readonly=True)
    form_type_id = fields.Many2one("cabochon.form.type", string="Тип формы", readonly=True)
    source_location_id = fields.Many2one("cabochon.manufacturing.location", string="Со склада", readonly=True)
    destination_location_id = fields.Many2one("cabochon.manufacturing.location", string="На склад", readonly=True)
    manager_id = fields.Many2one("hr.employee", string="Ответственный", readonly=True)
    issued_weight_g = fields.Float(string="Выдали, г", digits=(16, 1), readonly=True)
    received_weight_g = fields.Float(string="Получили, г", digits=(16, 1), readonly=True)

    def init(self):
        self.env.cr.execute("SELECT to_regclass('cabochon_manufacturing_movement'), to_regclass('cabochon_stone_lot')")
        if not all(self.env.cr.fetchone()):
            return
        self.env.cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_schema = current_schema() AND table_name = 'cabochon_manufacturing_movement'
               AND column_name = 'contractor_id'
        """)
        if not self.env.cr.fetchone():
            return
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW cabochon_contractor_report AS
            SELECT movement.id AS id, movement.id AS movement_id, movement.contractor_id,
                   movement.company_id, movement.movement_date, movement.kind AS direction,
                   lot.id AS lot_id, lot.fraction_id, lot.color_id, lot.stone_size_id,
                   CASE WHEN movement.kind = 'issue' THEN movement.source_location_id
                        ELSE movement.destination_location_id END AS location_id,
                   CONCAT_WS(' / ', NULLIF(lot.fraction, ''), NULLIF(lot.color, ''),
                       NULLIF(lot.stone_size, ''), NULLIF(lot.shape, ''), NULLIF(lot.form_type, '')) AS material_description,
                   lot.shape_id, lot.form_type_id, movement.source_location_id,
                   movement.destination_location_id, movement.manager_id,
                   CASE WHEN movement.kind = 'issue' THEN movement.weight_g ELSE 0 END AS issued_weight_g,
                   CASE WHEN movement.kind = 'receipt' THEN movement.weight_g ELSE 0 END AS received_weight_g
              FROM cabochon_manufacturing_movement movement
              JOIN cabochon_stone_lot lot ON lot.id = COALESCE(movement.new_lot_id, movement.lot_id)
             WHERE movement.contractor_id IS NOT NULL AND movement.kind IN ('issue', 'receipt')
        """)
