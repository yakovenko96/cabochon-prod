from odoo import fields, models, tools
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    CABOCHON_ROLE_GROUP_XMLIDS = {
        "user": "cabochon_base.group_cabochon_user",
        "worker": "cabochon_base.group_cabochon_fixer",
        "manager": "cabochon_base.group_cabochon_manager",
        "technologist": "cabochon_base.group_cabochon_workshop_manager",
        "finished_manager": "cabochon_base.group_cabochon_finished_manager",
        "admin": "cabochon_base.group_cabochon_admin",
    }
    CABOCHON_ROLE_PRIORITY = (
        "admin",
        "technologist",
        "finished_manager",
        "manager",
        "worker",
        "user",
    )

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
    cabochon_role = fields.Selection(
        [
            ("none", "Без роли"),
            ("user", "Пользователь"),
            ("worker", "Работник"),
            ("manager", "Менеджер склада"),
            ("technologist", "Технолог"),
            ("finished_manager", "Менеджер готовых кабошонов"),
            ("admin", "Администратор"),
        ],
        string="Роль",
        compute="_compute_cabochon_role",
        inverse="_inverse_cabochon_role",
        groups="cabochon_base.group_cabochon_admin",
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

    def _compute_cabochon_role(self):
        groups_by_role = {
            role: self.env.ref(xmlid, raise_if_not_found=False)
            for role, xmlid in self.CABOCHON_ROLE_GROUP_XMLIDS.items()
        }
        for employee in self:
            user = employee.user_id
            employee.cabochon_role = "none"
            if not user:
                continue
            for role in self.CABOCHON_ROLE_PRIORITY:
                group = groups_by_role[role]
                if group and group in user.group_ids:
                    employee.cabochon_role = role
                    break

    def _inverse_cabochon_role(self):
        all_groups = self._cabochon_role_groups()
        for employee in self:
            role = employee.cabochon_role
            user = employee.user_id
            if role != "none" and not user:
                raise UserError("Чтобы назначить роль Cabochon, сначала свяжите сотрудника с пользователем Odoo.")
            if not user:
                continue
            commands = [(3, group.id) for group in all_groups]
            if role != "none":
                group = self.env.ref(self.CABOCHON_ROLE_GROUP_XMLIDS[role], raise_if_not_found=False)
                if group:
                    commands.append((4, group.id))
            user.sudo().write({"group_ids": commands})

    def _cabochon_role_groups(self):
        groups = self.env["res.groups"]
        for xmlid in self.CABOCHON_ROLE_GROUP_XMLIDS.values():
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                groups |= group
        return groups


class CabochonEmployeeOperationAccess(models.Model):
    _name = "cabochon.employee.operation.access"
    _description = "Допуски сотрудников к операциям"
    _auto = False
    _rec_name = "employee_id"
    _order = "name, id"

    company_id = fields.Many2one("res.company", readonly=True)

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
                    employee.name AS name,
                    employee.company_id AS company_id
                FROM hr_employee employee
            )
            """
        )

    def write(self, vals):
        self.check_access("write")
        vals = dict(vals)
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
