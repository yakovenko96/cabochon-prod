from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    cabochon_allowed_operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_employee_operation_rel",
        "employee_id",
        "operation_id",
        string="Допущен к операциям",
        groups="cabochon_base.group_cabochon_admin",
    )
    cabochon_active_request_count = fields.Integer(
        string="Активные заявки",
        compute="_compute_cabochon_active_request_count",
    )

    def _compute_cabochon_active_request_count(self):
        grouped = {
            worker.id: count
            for worker, count in self.env["cabochon.production.request"]._read_group(
                [
                    ("worker_id", "in", self.ids),
                    ("state", "in", ["confirmed", "in_progress", "partially_done"]),
                ],
                groupby=["worker_id"],
                aggregates=["__count"],
            )
        }
        for employee in self:
            employee.cabochon_active_request_count = grouped.get(employee.id, 0)
