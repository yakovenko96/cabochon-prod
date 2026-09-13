from odoo import fields, models
from odoo.addons.cabochon_base.internal import INTERNAL, is_internal
from odoo.exceptions import UserError
from odoo.tools import SQL


class CabochonOnceMixin(models.AbstractModel):
    _name = "cabochon.once.mixin"
    _description = "Однократное выполнение складского действия"

    executed = fields.Boolean(readonly=True, copy=False)

    def _lock_execution(self):
        self.ensure_one()
        self.check_access("write")
        self.env.cr.execute(SQL("SELECT id FROM %s WHERE id = %s FOR UPDATE", SQL.identifier(self._table), self.id))
        self.invalidate_recordset()
        if self.executed:
            raise UserError("Этот документ уже выполнен. Повторное списание или поступление запрещено.")

    def _mark_executed(self):
        self.with_context(cabochon_once_internal=INTERNAL).write({"executed": True})

    def write(self, vals):
        if "executed" in vals and not is_internal(self.env, "cabochon_once_internal"):
            raise UserError("Признак выполнения устанавливается автоматически.")
        if any(self.mapped("executed")):
            raise UserError("Выполненный документ нельзя изменять.")
        return super().write(vals)
