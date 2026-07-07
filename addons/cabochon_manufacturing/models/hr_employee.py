from odoo import fields, models, tools
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    cabochon_allowed_operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_employee_operation_rel",
        "employee_id",
        "operation_id",
        string="Допущен к операциям",
        groups="cabochon_base.group_cabochon_workshop_manager,cabochon_base.group_cabochon_admin",
    )
    cabochon_active_request_count = fields.Integer(
        string="Активные заявки",
        compute="_compute_cabochon_active_request_count",
    )

    def write(self, vals):
        if (
            self.env.user.has_group("cabochon_base.group_cabochon_workshop_manager")
            and not self.env.user.has_group("cabochon_base.group_cabochon_admin")
            and set(vals) - {"cabochon_allowed_operation_ids"}
        ):
            raise UserError("Технолог может менять только допуски сотрудников к операциям.")
        return super().write(vals)

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


class CabochonEmployeeOperationAccess(models.Model):
    _name = "cabochon.employee.operation.access"
    _description = "Допуски сотрудников к операциям"
    _auto = False
    _rec_name = "employee_id"
    _order = "name, id"

    employee_id = fields.Many2one("hr.employee", string="Карточка сотрудника", readonly=True)
    name = fields.Char(string="Сотрудник", readonly=True)
    cabochon_allowed_operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        string="Допущен к операциям",
        compute="_compute_cabochon_allowed_operation_ids",
        inverse="_inverse_cabochon_allowed_operation_ids",
    )
    cabochon_active_request_count = fields.Integer(
        string="Активные заявки",
        compute="_compute_cabochon_active_request_count",
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    employee.id AS id,
                    employee.id AS employee_id,
                    employee.name AS name
                FROM hr_employee employee
            )
            """
        )

    def write(self, vals):
        allowed_operation_commands = vals.pop("cabochon_allowed_operation_ids", None)
        if vals:
            raise UserError("В этом разделе можно менять только допуски сотрудников к операциям.")
        if allowed_operation_commands is not None:
            for access in self:
                access.employee_id.sudo().write({"cabochon_allowed_operation_ids": allowed_operation_commands})
        return True

    def _compute_cabochon_allowed_operation_ids(self):
        for access in self:
            access.cabochon_allowed_operation_ids = access.employee_id.sudo().cabochon_allowed_operation_ids

    def _inverse_cabochon_allowed_operation_ids(self):
        for access in self:
            access.employee_id.sudo().write(
                {"cabochon_allowed_operation_ids": [(6, 0, access.cabochon_allowed_operation_ids.ids)]}
            )

    def _compute_cabochon_active_request_count(self):
        employee_ids = self.mapped("employee_id").ids
        grouped = {
            worker.id: count
            for worker, count in self.env["cabochon.production.request"]._read_group(
                [
                    ("worker_id", "in", employee_ids),
                    ("state", "in", ["confirmed", "in_progress", "partially_done"]),
                ],
                groupby=["worker_id"],
                aggregates=["__count"],
            )
        }
        for access in self:
            access.cabochon_active_request_count = grouped.get(access.employee_id.id, 0)
