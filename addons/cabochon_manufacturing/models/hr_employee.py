from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    cabochon_allowed_operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_employee_operation_rel",
        "employee_id",
        "operation_id",
        string="Допущен к операциям",
    )
    cabochon_active_request_count = fields.Integer(
        string="Активные заявки",
        compute="_compute_cabochon_active_request_count",
    )

    def _compute_cabochon_active_request_count(self):
        grouped = {
            item["worker_id"][0]: item["worker_id_count"]
            for item in self.env["cabochon.production.request"].read_group(
                [("worker_id", "in", self.ids), ("state", "in", ["confirmed", "issued", "in_progress"])],
                ["worker_id"],
                ["worker_id"],
            )
            if item.get("worker_id")
        }
        for employee in self:
            employee.cabochon_active_request_count = grouped.get(employee.id, 0)

    @api.onchange("cabochon_allowed_operation_ids")
    def _onchange_cabochon_allowed_operation_ids(self):
        return


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    cabochon_allowed_operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        compute="_compute_cabochon_public_manufacturing_fields",
        string="Допущен к операциям",
        readonly=True,
    )
    cabochon_active_request_count = fields.Integer(
        compute="_compute_cabochon_public_manufacturing_fields",
        string="Активные заявки",
        readonly=True,
    )

    def _compute_cabochon_public_manufacturing_fields(self):
        self._compute_from_employee(["cabochon_allowed_operation_ids", "cabochon_active_request_count"])
