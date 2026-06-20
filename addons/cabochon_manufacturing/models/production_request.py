from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

from .constants import EXCLUSIVE_OPERATION_GROUPS, SINGLE_REQUEST_OPERATION_GROUPS, SORT_OPERATION_TYPES


class CabochonProductionRequest(models.Model):
    _name = "cabochon.production.request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Заявка на изготовление кабошонов"
    _order = "id desc"

    name = fields.Char(string="Номер", default="Новый", copy=False, readonly=True)
    technologist_id = fields.Many2one(
        "hr.employee",
        string="Технолог",
        required=True,
        default=lambda self: self.env.user.sudo().employee_id,
        ondelete="restrict",
        tracking=True,
    )
    worker_id = fields.Many2one(
        "hr.employee",
        string="Работник",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_request_operation_rel",
        "request_id",
        "operation_id",
        string="Операции",
        required=True,
        tracking=True,
    )
    sort_type = fields.Char(string="Тип сортировки")
    show_sort_type = fields.Boolean(compute="_compute_show_sort_type")
    receipt_destination_stage = fields.Selection(
        [("semi_finished", "Склад полуфабрикатов"), ("finished", "Склад готовых камней")],
        string="Склад сдачи",
        default="semi_finished",
        required=True,
        tracking=True,
    )
    show_receipt_destination_stage = fields.Boolean(compute="_compute_show_receipt_destination_stage")
    source_lot_id = fields.Many2one(
        "cabochon.stone.lot",
        string="Исходный мешок",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    planned_weight_g = fields.Float(string="Плановый вес к выдаче, г", digits=(16, 4), required=True)
    deadline = fields.Datetime(string="Срок выполнения", required=True, tracking=True)
    priority = fields.Selection(
        [("0", "Обычный"), ("1", "Срочно"), ("2", "Очень срочно")],
        string="Приоритет",
        default="0",
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Новая"),
            ("confirmed", "Ожидает выдачи"),
            ("in_progress", "В работе"),
            ("partially_done", "Частично сдано"),
            ("done", "Закрыта"),
            ("cancelled", "Отменена"),
        ],
        default="draft",
        readonly=True,
        required=True,
        tracking=True,
    )
    issue_id = fields.Many2one("cabochon.material.transfer", string="Заявка на выдачу", readonly=True, copy=False)
    receipt_ids = fields.One2many("cabochon.material.transfer", "request_id", string="Сдачи")
    movement_ids = fields.One2many("cabochon.manufacturing.movement", "request_id", string="Движения", readonly=True)
    operation_line_ids = fields.One2many(
        "cabochon.production.request.operation.line",
        "request_id",
        string="Маршрут операций",
        copy=True,
    )
    eligible_operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_request_eligible_operation_rel",
        "request_id",
        "operation_id",
        compute="_compute_eligible_operation_ids",
        compute_sudo=True,
        string="Доступные операции для мешка",
    )
    eligible_worker_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_eligible_worker_ids",
        compute_sudo=True,
        string="Допущенные работники",
    )
    eligible_lot_ids = fields.Many2many(
        "cabochon.stone.lot",
        compute="_compute_eligible_lot_ids",
        compute_sudo=True,
        string="Доступные мешки для операции",
    )
    worker_load = fields.Integer(string="Текущая нагрузка работника", related="worker_id.cabochon_active_request_count")
    issued_weight_g = fields.Float(string="Выдано, г", compute="_compute_weights", store=True)
    received_weight_g = fields.Float(string="Сдано, г", compute="_compute_weights", store=True)
    defect_weight_g = fields.Float(string="Брак, г", compute="_compute_weights", store=True)
    detected_defect_weight_g = fields.Float(string="Выявленный брак, г", compute="_compute_weights", store=True)
    made_defect_weight_g = fields.Float(string="Сделанный брак, г", compute="_compute_weights", store=True)
    lost_weight_g = fields.Float(string="Потери, г", compute="_compute_weights", store=True)
    confirmed_at = fields.Datetime(string="Подтверждена")
    issued_at = fields.Datetime(string="Выдана")
    started_at = fields.Datetime(string="Начата")
    first_receipt_at = fields.Datetime(string="Первая сдача")
    closed_at = fields.Datetime(string="Закрыта")
    is_overdue = fields.Boolean(string="Просрочена", compute="_compute_is_overdue", search="_search_is_overdue")
    state_order = fields.Integer(string="Порядок статуса", compute="_compute_state_order", store=True)
    actual_duration_hours = fields.Float(
        string="Фактическое время, ч",
        compute="_compute_actual_duration_hours",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Компания",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        source_lot_ids = [vals.get("source_lot_id") for vals in vals_list if vals.get("source_lot_id")]
        if len(source_lot_ids) != len(set(source_lot_ids)):
            raise ValidationError("Один исходный мешок нельзя использовать в нескольких заявках.")
        self._check_source_lots_available(source_lot_ids)
        for vals in vals_list:
            if vals.get("name", "Новый") == "Новый":
                vals["name"] = sequence.next_by_code("cabochon.production.request") or "Новый"
        requests = super().create(vals_list)
        requests._sync_operation_lines()
        requests._notify_overdue_technologists()
        return requests

    def write(self, vals):
        business_fields = {
            "technologist_id",
            "worker_id",
            "operation_ids",
            "sort_type",
            "receipt_destination_stage",
            "source_lot_id",
            "planned_weight_g",
            "deadline",
            "priority",
        }
        if business_fields.intersection(vals) and any(request.state != "draft" for request in self):
            raise UserError("Параметры заявки можно менять только в черновике.")
        if vals.get("source_lot_id"):
            self._check_source_lots_available([vals["source_lot_id"]], exclude_request_ids=self.ids)
        result = super().write(vals)
        if "operation_ids" in vals and not self.env.context.get("skip_operation_line_sync"):
            self._sync_operation_lines()
        if {"deadline", "state", "technologist_id"}.intersection(vals):
            self._clear_overdue_activities()
            self._notify_overdue_technologists()
        return result

    @api.model
    def _check_source_lots_available(self, source_lot_ids, exclude_request_ids=None):
        if not source_lot_ids:
            return
        domain = [
            ("source_lot_id", "in", source_lot_ids),
            ("state", "!=", "cancelled"),
        ]
        if exclude_request_ids:
            domain.append(("id", "not in", exclude_request_ids))
        existing = self.sudo().search(domain, limit=1)
        if existing:
            raise ValidationError(
                f"Мешок {existing.source_lot_id.display_name} уже используется в заявке {existing.display_name}."
            )

    @api.depends("deadline", "state")
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for request in self:
            request.is_overdue = bool(request.deadline and request.deadline < now and request.state not in ("done", "cancelled"))

    @api.model
    def _search_is_overdue(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError("Поиск по просрочке поддерживает только операторы '=' и '!='.")
        now = fields.Datetime.now()
        positive = (operator == "=" and value) or (operator == "!=" and not value)
        if positive:
            return [("deadline", "<", now), ("state", "not in", ["done", "cancelled"])]
        return [
            "|",
            ("deadline", "=", False),
            "|",
            ("deadline", ">=", now),
            ("state", "in", ["done", "cancelled"]),
        ]

    @api.depends("state")
    def _compute_state_order(self):
        order_by_state = {
            "in_progress": 0,
            "partially_done": 0,
            "draft": 1,
            "confirmed": 2,
            "done": 9,
            "cancelled": 9,
        }
        for request in self:
            request.state_order = order_by_state.get(request.state, 5)

    @api.depends("movement_ids.kind", "movement_ids.defect_kind", "movement_ids.weight_g")
    def _compute_weights(self):
        for request in self:
            request.issued_weight_g = sum(request.movement_ids.filtered(lambda item: item.kind == "issue").mapped("weight_g"))
            request.received_weight_g = sum(request.movement_ids.filtered(lambda item: item.kind == "receipt").mapped("weight_g"))
            request.defect_weight_g = sum(request.movement_ids.filtered(lambda item: item.kind == "defect").mapped("weight_g"))
            request.detected_defect_weight_g = sum(
                request.movement_ids.filtered(
                    lambda item: item.kind == "defect" and item.defect_kind == "detected"
                ).mapped("weight_g")
            )
            request.made_defect_weight_g = sum(
                request.movement_ids.filtered(
                    lambda item: item.kind == "defect" and item.defect_kind == "made"
                ).mapped("weight_g")
            )
            request.lost_weight_g = sum(request.movement_ids.filtered(lambda item: item.kind == "loss").mapped("weight_g"))

    @api.depends("started_at", "closed_at")
    def _compute_actual_duration_hours(self):
        for request in self:
            if request.started_at and request.closed_at:
                request.actual_duration_hours = (request.closed_at - request.started_at).total_seconds() / 3600.0
            else:
                request.actual_duration_hours = 0.0

    @api.depends("operation_ids")
    def _compute_eligible_worker_ids(self):
        workers = self.env["hr.employee"].sudo().search([("cabochon_allowed_operation_ids", "!=", False)])
        for request in self:
            required_operation_ids = set(request.operation_ids.ids)
            if not required_operation_ids:
                request.eligible_worker_ids = workers
                continue
            request.eligible_worker_ids = workers.filtered(
                lambda employee, operation_ids=required_operation_ids: operation_ids.issubset(
                    set(employee.cabochon_allowed_operation_ids.ids)
                )
            )

    @api.depends("source_lot_id", "operation_ids")
    def _compute_eligible_operation_ids(self):
        operation_model = self.env["cabochon.manufacturing.operation"].sudo()
        operations = operation_model.search([("active", "=", True)])
        for request in self:
            selected = request.operation_ids
            if not request.source_lot_id:
                request.eligible_operation_ids = operations
                continue
            request.eligible_operation_ids = operations.filtered(
                lambda operation, lot=request.source_lot_id, selected=selected: operation in selected
                or lot._is_operation_route_allowed(selected | operation)
            )

    @api.depends("operation_ids.code")
    def _compute_show_sort_type(self):
        for request in self:
            request.show_sort_type = bool(set(request.operation_ids.mapped("code")) & set(SORT_OPERATION_TYPES))

    @api.depends("operation_ids.final_operation")
    def _compute_show_receipt_destination_stage(self):
        for request in self:
            request.show_receipt_destination_stage = bool(request.operation_ids.filtered("final_operation"))

    @api.depends("operation_ids", "source_lot_id")
    def _compute_eligible_lot_ids(self):
        lot_model = self.env["cabochon.stone.lot"].sudo()
        for request in self:
            used_lot_ids = self.sudo().search_fetch(
                [
                    ("id", "!=", request.id or 0),
                    ("state", "!=", "cancelled"),
                    ("source_lot_id", "!=", False),
                ],
                ["source_lot_id"],
            ).mapped("source_lot_id").ids
            lot_domain = [
                ("state", "=", "available"),
                ("is_defect_lot", "=", False),
                ("id", "not in", used_lot_ids),
            ]
            if request.source_lot_id:
                lot_domain = ["|", ("id", "=", request.source_lot_id.id), *lot_domain]
            available_lots = lot_model.search(lot_domain)
            if not request.operation_ids:
                request.eligible_lot_ids = available_lots
                continue
            request.eligible_lot_ids = available_lots.filtered(
                lambda lot, operations=request.operation_ids: lot._is_operation_route_allowed(operations)
            )

    def _operation_selection_domain(self):
        self.ensure_one()
        if not self.source_lot_id:
            return [("active", "=", True)]
        return [("id", "in", self.eligible_operation_ids.ids)]

    @api.onchange("source_lot_id")
    def _onchange_source_lot_id(self):
        if self.source_lot_id:
            self.planned_weight_g = self.source_lot_id.current_weight_g
            self.operation_ids = self.operation_ids.filtered(lambda operation: operation in self.eligible_operation_ids)
            self._normalize_selected_operations()
            self._set_sort_type_from_operations()
            self._set_default_receipt_destination_stage()
        return {
            "domain": {
                "operation_ids": self._operation_selection_domain(),
                "source_lot_id": [("id", "in", self.eligible_lot_ids.ids)],
            }
        }

    @api.onchange("operation_ids")
    def _onchange_operation_ids(self):
        self._normalize_selected_operations()
        self._set_sort_type_from_operations()
        self._set_default_receipt_destination_stage()
        if not self.worker_id:
            return {
                "domain": {
                    "operation_ids": self._operation_selection_domain(),
                    "source_lot_id": [("id", "in", self.eligible_lot_ids.ids)],
                }
            }
        required_operation_ids = set(self.operation_ids.ids)
        worker_operation_ids = set(self.worker_id.sudo().cabochon_allowed_operation_ids.ids)
        if not worker_operation_ids or not required_operation_ids.issubset(worker_operation_ids):
            self.worker_id = False
        return {
            "domain": {
                "operation_ids": self._operation_selection_domain(),
                "source_lot_id": [("id", "in", self.eligible_lot_ids.ids)],
            }
        }

    def _normalize_selected_operations(self):
        for request in self:
            completed_codes = request.source_lot_id._completed_operation_codes() if request.source_lot_id else set()
            kept_operations = self.env["cabochon.manufacturing.operation"]
            for operation in request.operation_ids.sorted("sequence"):
                if not operation.code or not request._operation_route_error(
                    kept_operations | operation,
                    completed_codes,
                    enforce_prerequisites=bool(request.source_lot_id),
                ):
                    kept_operations |= operation
            if kept_operations != request.operation_ids:
                request.operation_ids = kept_operations

    def _set_sort_type_from_operations(self):
        for request in self:
            sort_codes = [operation.code for operation in request.operation_ids.sorted("sequence") if operation.code in SORT_OPERATION_TYPES]
            request.sort_type = SORT_OPERATION_TYPES[sort_codes[-1]] if sort_codes else False

    def _set_default_receipt_destination_stage(self):
        for request in self:
            if not request.operation_ids.filtered("final_operation"):
                request.receipt_destination_stage = "semi_finished"

    @api.constrains("worker_id", "operation_ids", "source_lot_id", "planned_weight_g")
    def _check_request_values(self):
        for request in self:
            if float_compare(request.planned_weight_g, 0.0, precision_digits=4) <= 0:
                raise ValidationError("Плановый вес к выдаче должен быть больше нуля.")
            if not request.operation_ids:
                raise ValidationError("Добавьте хотя бы одну операцию в заявку.")
            if request.source_lot_id.is_defect_lot:
                raise ValidationError("Сводный мешок брака нельзя использовать как исходный мешок заявки.")
            if request.state in ("draft", "confirmed") and float_compare(
                request.planned_weight_g,
                request.source_lot_id.current_weight_g,
                precision_digits=4,
            ) > 0:
                raise ValidationError("Плановый вес не может превышать текущий остаток исходного мешка.")
            allowed_ids = set(request.worker_id.sudo().cabochon_allowed_operation_ids.ids)
            if request.operation_ids and not set(request.operation_ids.ids).issubset(allowed_ids):
                raise ValidationError("Работник не допущен ко всем операциям заявки.")
            completed_operation_ids = request.source_lot_id._completed_operation_ids() if request.source_lot_id else set()
            repeated_operations = request.operation_ids.filtered(
                lambda operation, done=completed_operation_ids: operation.id in done
            )
            if repeated_operations:
                operation_names = ", ".join(repeated_operations.mapped("display_name"))
                raise ValidationError(
                    f"Операции уже были выполнены для этого мешка или его исходного мешка: {operation_names}."
                )
            route_error = request._operation_route_error(
                request.operation_ids,
                request.source_lot_id._completed_operation_codes() if request.source_lot_id else set(),
            )
            if route_error:
                raise ValidationError(route_error)
            if request.receipt_destination_stage == "finished" and not request.operation_ids.filtered("final_operation"):
                raise ValidationError("Склад готовых камней можно выбрать только для финальной операции.")

    @api.model
    def _operation_route_error(self, operations, completed_codes, enforce_prerequisites=True):
        codes = [operation.code for operation in operations.sorted("sequence") if operation.code]
        if not codes:
            return False
        selected_codes = set(codes)
        repeated_codes = selected_codes & completed_codes
        if repeated_codes:
            names = ", ".join(
                self.env["cabochon.manufacturing.operation"].sudo().search([("code", "in", list(repeated_codes))]).mapped("name")
            )
            return f"Операции уже были выполнены для этого мешка или его исходного мешка: {names}."
        for group in EXCLUSIVE_OPERATION_GROUPS:
            selected_group_codes = selected_codes & group
            if completed_codes & group and selected_group_codes:
                names = ", ".join(
                    self.env["cabochon.manufacturing.operation"].sudo().search([("code", "in", list(group))]).mapped("name")
                )
                return f"Операции из этой группы уже были выполнены для мешка, выберите другой этап: {names}."
            if len(selected_group_codes) > 1:
                names = ", ".join(
                    self.env["cabochon.manufacturing.operation"].sudo().search([("code", "in", list(group))]).mapped("name")
                )
                return f"Операции взаимоисключающие, выберите только одну из группы: {names}."
        for group in SINGLE_REQUEST_OPERATION_GROUPS:
            selected_group_codes = selected_codes & group
            if len(selected_group_codes) > 1:
                names = ", ".join(
                    self.env["cabochon.manufacturing.operation"].sudo().search([("code", "in", list(group))]).mapped("name")
                )
                return f"Эти операции выполняют разные сотрудники, выберите только одну операцию в заявке: {names}."
        wash_codes = {"tumble_wash", "toluene_wash"}
        sorting_codes = {"manual_sorting", "auto_separator"}
        if not enforce_prerequisites:
            return False
        non_wash_codes = selected_codes - wash_codes
        if non_wash_codes and not ((completed_codes | selected_codes) & wash_codes):
            return "Перед другими операциями мешок должен пройти помывку в галтовке или толуоле."
        after_sort_codes = selected_codes - wash_codes - sorting_codes
        if after_sort_codes and not ((completed_codes | selected_codes) & sorting_codes):
            return "Перед дальнейшими операциями мешок должен пройти ручную сортировку или авто-сепаратор."
        return False

    def action_confirm(self):
        for request in self:
            if request.state != "draft":
                continue
            request._sync_operation_lines()
            request._ensure_issue_transfer()
            request.write(
                {
                    "state": "confirmed",
                    "confirmed_at": request.confirmed_at or fields.Datetime.now(),
                }
            )
            request.issue_id._notify_manager_activity()

    def action_create_receipt(self):
        for request in self:
            request._ensure_receipt_transfer()
        return True

    def action_close(self):
        for request in self:
            if request.state not in ("in_progress", "partially_done"):
                continue
            now = fields.Datetime.now()
            request._finish_open_operation_lines(now)
            request.write(
                {
                    "state": "done",
                    "closed_at": request.closed_at or now,
                }
            )
            request._clear_overdue_activities()
            request._clear_loss_over_norm_activities()

    def action_cancel(self):
        for request in self:
            if request.movement_ids:
                raise UserError("Заявку с движениями нельзя отменить. Создайте корректирующие движения.")
            request.state = "cancelled"
            request._clear_overdue_activities()
            request._clear_loss_over_norm_activities()

    def _sync_operation_lines(self):
        line_model = self.env["cabochon.production.request.operation.line"]
        for request in self:
            operations = request.operation_ids.sorted("sequence")
            operation_ids = set(operations.ids)
            obsolete_lines = request.operation_line_ids.filtered(
                lambda line, ids=operation_ids: line.operation_id.id not in ids
            )
            obsolete_lines.unlink()
            existing_by_operation = {line.operation_id.id: line for line in request.operation_line_ids}
            for index, operation in enumerate(operations, start=1):
                sequence = index * 10
                existing_line = existing_by_operation.get(operation.id)
                if existing_line:
                    existing_line.sequence = sequence
                else:
                    line_model.create(
                        {
                            "request_id": request.id,
                            "operation_id": operation.id,
                            "sequence": sequence,
                        }
                    )

    def _start_next_operation_line(self, started_at=False):
        for request in self:
            line = request.operation_line_ids.filtered(lambda item: item.state == "pending").sorted("sequence")[:1]
            if line:
                line.action_start(started_at=started_at)

    def _finish_open_operation_lines(self, finished_at=False):
        for request in self:
            lines = request.operation_line_ids.filtered(lambda item: item.state in ("pending", "in_progress"))
            for line in lines.sorted("sequence"):
                line_finished_at = finished_at
                if line.started_at and line_finished_at and line_finished_at < line.started_at:
                    line_finished_at = line.started_at
                if line.state == "pending":
                    line.action_start(started_at=line_finished_at)
                line.action_finish(finished_at=line_finished_at)

    def _notify_overdue_technologists(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        today = fields.Date.context_today(self)
        overdue_requests = self.filtered(lambda item: item.is_overdue and item.technologist_id.user_id)
        for request in overdue_requests:
            user = request.technologist_id.user_id
            existing = self.env["mail.activity"].sudo().search(
                [
                    ("res_model_id", "=", model_id),
                    ("res_id", "=", request.id),
                    ("activity_type_id", "=", activity_type.id),
                    ("user_id", "=", user.id),
                    ("summary", "=", "Просрочена заявка на изготовление"),
                ],
                limit=1,
            )
            if existing:
                continue
            request.sudo().with_context(cabochon_activity_system_update=True).activity_schedule(
                activity_type_id=activity_type.id,
                date_deadline=today,
                summary="Просрочена заявка на изготовление",
                note="Срок выполнения заявки истек. Проверьте выдачу, сдачу или закрытие работ.",
                user_id=user.id,
            )

    def _clear_overdue_activities(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        activities = self.env["mail.activity"].sudo().search(
            [
                ("res_model_id", "=", model_id),
                ("res_id", "in", self.ids),
                ("activity_type_id", "=", activity_type.id),
                ("summary", "=", "Просрочена заявка на изготовление"),
            ]
        )
        activities.with_context(cabochon_activity_system_update=True).unlink()

    def _sync_loss_over_norm_activities(self):
        for request in self:
            request._clear_loss_over_norm_activities()
            if request.state not in ("done", "cancelled"):
                request.movement_ids.filtered(lambda movement: movement.is_loss_over_norm)._notify_loss_over_norm()

    def _clear_loss_over_norm_activities(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        activities = self.env["mail.activity"].sudo().search(
            [
                ("res_model_id", "=", model_id),
                ("res_id", "in", self.ids),
                ("activity_type_id", "=", activity_type.id),
                ("summary", "=", "Потери выше нормы"),
            ]
        )
        activities.with_context(cabochon_activity_system_update=True).unlink()

    @api.model
    def _cron_notify_overdue_requests(self):
        requests = self.search([("deadline", "<", fields.Datetime.now()), ("state", "not in", ("done", "cancelled"))])
        requests._notify_overdue_technologists()

    def _ensure_issue_transfer(self):
        self.ensure_one()
        if self.issue_id:
            return self.issue_id
        manager = self.source_lot_id.location_id.manager_id
        if not manager:
            raise UserError("Укажите ответственного кладовщика на складе исходного мешка.")
        issue = self.env["cabochon.material.transfer"].sudo().create(
            {
                "transfer_type": "issue",
                "request_id": self.id,
                "worker_id": self.worker_id.id,
                "manager_id": manager.id,
                "operation_ids": [(6, 0, self.operation_ids.ids)],
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "lot_id": self.source_lot_id.id,
                            "weight_g": self.planned_weight_g,
                        },
                    )
                ],
                "company_id": self.company_id.id,
            }
        )
        self.issue_id = issue
        return issue

    def _ensure_receipt_transfer(self, issue_lines=None):
        self.ensure_one()
        existing = self.receipt_ids.filtered(
            lambda item: item.transfer_type == "receipt" and item.state in ("draft", "manager_confirmed")
        )
        if existing:
            receipt = existing[:1]
            if issue_lines and not receipt.line_ids:
                receipt.sudo().write({"line_ids": self._receipt_line_commands(issue_lines)})
            return receipt
        destination = self._get_receipt_destination_location()
        if not destination.manager_id:
            raise UserError("Укажите ответственного кладовщика на складе назначения для сдачи.")
        receipt = self.env["cabochon.material.transfer"].sudo().create(
            {
                "transfer_type": "receipt",
                "request_id": self.id,
                "worker_id": self.worker_id.id,
                "manager_id": destination.manager_id.id,
                "operation_ids": [(6, 0, self.operation_ids.ids)],
                "line_ids": self._receipt_line_commands(issue_lines),
                "company_id": self.company_id.id,
            }
        )
        receipt._notify_manager_activity()
        return receipt

    def _get_receipt_destination_location(self):
        self.ensure_one()
        if not self.operation_ids.filtered("final_operation"):
            return self.env["cabochon.material.transfer"]._get_destination_location_for_operations(self.operation_ids)
        stage = self.receipt_destination_stage or "semi_finished"
        location = self.env["cabochon.manufacturing.location"].sudo().search([("code", "=", stage)], limit=1)
        if not location:
            raise UserError("Не найдена складская зона назначения для сдачи.")
        return location

    def _receipt_line_commands(self, issue_lines):
        return [
            (
                0,
                0,
                {
                    "lot_id": lot.id,
                    "weight_before_g": weight,
                    "sort_type": self.sort_type,
                },
            )
            for lot, weight in (issue_lines or [])
            if lot
        ]


class CabochonProductionRequestOperationLine(models.Model):
    _name = "cabochon.production.request.operation.line"
    _description = "Операция в маршруте заявки на изготовление"
    _order = "request_id, sequence, id"

    request_id = fields.Many2one(
        "cabochon.production.request",
        string="Заявка",
        required=True,
        ondelete="cascade",
    )
    operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        string="Операция",
        required=True,
        ondelete="restrict",
    )
    sequence = fields.Integer(string="Порядок", default=10)
    state = fields.Selection(
        [
            ("pending", "Ожидает"),
            ("in_progress", "В работе"),
            ("done", "Готово"),
        ],
        string="Статус",
        default="pending",
        required=True,
    )
    planned_weight_g = fields.Float(
        string="Плановый вес, г",
        related="request_id.planned_weight_g",
        readonly=True,
    )
    started_at = fields.Datetime(string="Начало")
    finished_at = fields.Datetime(string="Окончание")
    duration_hours = fields.Float(string="Время, ч", compute="_compute_duration_hours", store=True)
    worker_id = fields.Many2one("hr.employee", string="Работник", related="request_id.worker_id", store=True)
    company_id = fields.Many2one("res.company", string="Компания", related="request_id.company_id", store=True)
    note = fields.Text(string="Комментарий")

    @api.depends("started_at", "finished_at")
    def _compute_duration_hours(self):
        for line in self:
            if line.started_at and line.finished_at:
                line.duration_hours = (line.finished_at - line.started_at).total_seconds() / 3600.0
            else:
                line.duration_hours = 0.0

    def action_start(self, started_at=False):
        started_at = started_at or fields.Datetime.now()
        for line in self:
            if line.state == "pending":
                line.write(
                    {
                        "state": "in_progress",
                        "started_at": line.started_at or started_at,
                    }
                )
                if not line.request_id.started_at:
                    line.request_id.started_at = started_at

    def action_finish(self, finished_at=False):
        finished_at = finished_at or fields.Datetime.now()
        for line in self:
            if line.state != "done":
                line_finished_at = finished_at
                if line.started_at and line_finished_at < line.started_at:
                    line_finished_at = line.started_at
                values = {
                    "state": "done",
                    "finished_at": line.finished_at or line_finished_at,
                }
                if not line.started_at:
                    values["started_at"] = line_finished_at
                line.write(values)

    @api.constrains("started_at", "finished_at")
    def _check_operation_line_dates(self):
        for line in self:
            if line.started_at and line.finished_at and line.finished_at < line.started_at:
                raise ValidationError("Время окончания операции не может быть раньше начала.")


