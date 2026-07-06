from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero

WEIGHT_DIGITS = (16, 1)


class CabochonFinishedIssueWizard(models.TransientModel):
    _name = "cabochon.finished.issue.wizard"
    _description = "Продажа/выдача готовых камней"

    partner_id = fields.Many2one("res.partner", string="Получатель/покупатель", ondelete="restrict")
    issue_date = fields.Datetime(string="Дата выдачи", default=fields.Datetime.now, required=True)
    manager_id = fields.Many2one(
        "hr.employee",
        string="Менеджер готового склада",
        default=lambda self: self.env.user.sudo().employee_id,
        required=True,
        ondelete="restrict",
    )
    line_ids = fields.One2many("cabochon.finished.issue.wizard.line", "wizard_id", string="Строки")
    note = fields.Text(string="Комментарий")
    company_id = fields.Many2one(
        "res.company",
        string="Компания",
        required=True,
        default=lambda self: self.env.company,
    )

    def action_confirm(self):
        finished_location = self.env.ref("cabochon_manufacturing.location_finished").sudo()
        for wizard in self:
            if not wizard.line_ids:
                raise UserError("Добавьте строки выдачи.")
            if not finished_location.manager_id:
                raise UserError("Укажите менеджера склада готовых камней.")
            if (
                not self.env.user.has_group("cabochon_base.group_cabochon_admin")
                and finished_location.manager_id.user_id != self.env.user
            ):
                raise UserError("Выдавать готовые камни может только менеджер готового склада или администратор.")
            lot_ids = wizard.line_ids.mapped("lot_id").ids
            self.env.cr.execute(
                "SELECT id FROM cabochon_stone_lot WHERE id IN %s FOR UPDATE",
                [tuple(lot_ids)],
            )
            wizard.line_ids.mapped("lot_id").invalidate_recordset(["current_weight_g", "state", "location_id"])
            for line in wizard.line_ids:
                line._confirm_finished_issue(finished_location)
        return {"type": "ir.actions.act_window_close"}


class CabochonFinishedIssueWizardLine(models.TransientModel):
    _name = "cabochon.finished.issue.wizard.line"
    _description = "Строка продажи/выдачи готовых камней"
    _order = "id"

    wizard_id = fields.Many2one(
        "cabochon.finished.issue.wizard",
        string="Документ",
        required=True,
        ondelete="cascade",
    )
    lot_id = fields.Many2one("cabochon.stone.lot", string="Мешок готовых камней", required=True, ondelete="restrict")
    available_weight_g = fields.Float(
        string="Доступно, г",
        related="lot_id.current_weight_g",
        readonly=True,
        digits=WEIGHT_DIGITS,
    )
    weight_g = fields.Float(string="Вес к выдаче, г", required=True, digits=WEIGHT_DIGITS)
    note = fields.Char(string="Комментарий")

    @api.constrains("lot_id", "weight_g")
    def _check_values(self):
        for line in self:
            if float_compare(line.weight_g, 0.0, precision_digits=4) <= 0:
                raise ValidationError("Вес к выдаче должен быть больше нуля.")
            if line.lot_id.location_id.code != "finished" or line.lot_id.state != "available":
                raise ValidationError("Выберите доступный мешок со склада готовых камней.")
            if float_compare(line.weight_g, line.lot_id.current_weight_g, precision_digits=4) > 0:
                raise ValidationError("Вес к выдаче не может превышать остаток мешка.")

    def _confirm_finished_issue(self, finished_location):
        self.ensure_one()
        lot = self.lot_id.sudo()
        if lot.location_id != finished_location or lot.state != "available":
            raise UserError("Выберите доступный мешок со склада готовых камней.")
        if float_compare(lot.current_weight_g, self.weight_g, precision_digits=4) < 0:
            raise UserError(f"В мешке {lot.display_name} недостаточно веса.")
        remaining_weight = lot.current_weight_g - self.weight_g
        lot.with_context(cabochon_inventory_movement=True).write(
            {
                "current_weight_g": remaining_weight,
                "state": "written_off" if float_is_zero(remaining_weight, precision_digits=4) else "available",
            }
        )
        note_parts = ["Продажа/выдача готовых камней"]
        if self.wizard_id.partner_id:
            note_parts.append(f"получатель: {self.wizard_id.partner_id.display_name}")
        if self.wizard_id.note:
            note_parts.append(self.wizard_id.note)
        if self.note:
            note_parts.append(self.note)
        self.env["cabochon.manufacturing.movement"].sudo().create(
            {
                "kind": "issue",
                "lot_id": lot.id,
                "source_location_id": finished_location.id,
                "manager_id": self.wizard_id.manager_id.id,
                "weight_g": self.weight_g,
                "movement_date": self.wizard_id.issue_date,
                "note": "; ".join(note_parts),
                "company_id": self.wizard_id.company_id.id,
            }
        )
