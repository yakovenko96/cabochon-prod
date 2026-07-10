from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

from .constants import EXCLUSIVE_OPERATION_GROUPS, SINGLE_REQUEST_OPERATION_GROUPS, SORT_OPERATION_TYPES

WEIGHT_DIGITS = (16, 1)
MACHINE_OPERATION_CODES = {"cnc", "cabochon_machine", "ball_machine"}
CUTTING_OPERATION_CODES = {"cutting"}
DRILLING_OPERATION_CODES = {"drilling"}
TUBE_OPERATION_CODES = {"tubes"}
REPEATABLE_OPERATION_CODES = {"grinding_polishing"}
TASK_OPERATION_CODES = {"press"} | MACHINE_OPERATION_CODES | CUTTING_OPERATION_CODES | DRILLING_OPERATION_CODES


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
    show_task_lines = fields.Boolean(compute="_compute_show_task_lines")
    show_tube_source_lines = fields.Boolean(compute="_compute_show_tube_source_lines")
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
    source_lot_ids = fields.Many2many(
        "cabochon.stone.lot",
        string="Исходные мешки",
        compute="_compute_source_lot_ids",
        inverse="_inverse_source_lot_ids",
        readonly=False,
        compute_sudo=True,
    )
    additional_source_line_ids = fields.One2many(
        "cabochon.production.request.source.line",
        "request_id",
        string="Дополнительные исходные мешки",
        copy=True,
    )
    task_line_ids = fields.One2many(
        "cabochon.production.request.task.line",
        "request_id",
        string="Производственные задачи",
        copy=True,
    )
    total_planned_weight_g = fields.Float(
        string="Общий плановый вес, г", compute="_compute_total_planned_weight", store=True, digits=WEIGHT_DIGITS
    )
    planned_weight_g = fields.Float(string="Плановый вес к выдаче, г", digits=WEIGHT_DIGITS, required=True)
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
        string="Статус",
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
    issued_weight_g = fields.Float(string="Выдано, г", compute="_compute_weights", store=True, digits=WEIGHT_DIGITS)
    received_weight_g = fields.Float(string="Сдано, г", compute="_compute_weights", store=True, digits=WEIGHT_DIGITS)
    defect_weight_g = fields.Float(string="Брак, г", compute="_compute_weights", store=True, digits=WEIGHT_DIGITS)
    detected_defect_weight_g = fields.Float(
        string="Выявленный брак, г", compute="_compute_weights", store=True, digits=WEIGHT_DIGITS
    )
    made_defect_weight_g = fields.Float(
        string="Сделанный брак, г", compute="_compute_weights", store=True, digits=WEIGHT_DIGITS
    )
    lost_weight_g = fields.Float(string="Потери, г", compute="_compute_weights", store=True, digits=WEIGHT_DIGITS)
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

    @api.depends("planned_weight_g", "additional_source_line_ids.weight_g")
    def _compute_total_planned_weight(self):
        for request in self:
            request.total_planned_weight_g = request.planned_weight_g + sum(
                request.additional_source_line_ids.mapped("weight_g")
            )

    @api.depends("source_lot_id", "additional_source_line_ids.lot_id")
    def _compute_source_lot_ids(self):
        for request in self:
            request.source_lot_ids = request.source_lot_id | request.additional_source_line_ids.mapped("lot_id")

    def _inverse_source_lot_ids(self):
        for request in self:
            request._sync_source_lines_from_lots()

    def _sync_source_lines_from_lots(self):
        for request in self:
            lots = request.source_lot_ids
            primary_lot = lots[:1]
            request.source_lot_id = primary_lot
            request.planned_weight_g = primary_lot.current_weight_g if primary_lot else 0.0
            request.additional_source_line_ids = [(5, 0, 0)] + [
                (0, 0, {"lot_id": lot.id, "weight_g": lot.current_weight_g})
                for lot in lots[1:]
            ]

    @api.onchange("source_lot_ids")
    def _onchange_source_lot_ids(self):
        self._sync_source_lines_from_lots()

    @api.onchange("source_lot_id")
    def _onchange_source_lot_id(self):
        for request in self:
            request.planned_weight_g = request.source_lot_id.current_weight_g if request.source_lot_id else 0.0

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
            "additional_source_line_ids",
            "task_line_ids",
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
            self._clear_obsolete_task_lines()
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
        line_domain = [("lot_id", "in", source_lot_ids), ("request_id.state", "!=", "cancelled")]
        if exclude_request_ids:
            line_domain.append(("request_id", "not in", exclude_request_ids))
        existing_line = self.env["cabochon.production.request.source.line"].sudo().search(line_domain, limit=1)
        if existing_line:
            raise ValidationError(
                f"Мешок {existing_line.lot_id.display_name} уже используется в заявке "
                f"{existing_line.request_id.display_name}."
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

    @api.depends("operation_ids.code")
    def _compute_show_task_lines(self):
        for request in self:
            request.show_task_lines = bool(set(request.operation_ids.mapped("code")) & TASK_OPERATION_CODES)

    @api.depends("operation_ids.code")
    def _compute_show_tube_source_lines(self):
        for request in self:
            request.show_tube_source_lines = "tubes" in request.operation_ids.mapped("code")

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
            used_lot_ids += self.env["cabochon.production.request.source.line"].sudo().search(
                [
                    ("request_id", "!=", request.id or 0),
                    ("request_id.state", "!=", "cancelled"),
                ]
            ).mapped("lot_id").ids
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

    @api.onchange("source_lot_ids")
    def _onchange_source_lot_ids(self):
        self._sync_source_lines_from_lots()
        if self.source_lot_id:
            if not self.planned_weight_g:
                self.planned_weight_g = self.source_lot_id.current_weight_g
            self.operation_ids = self.operation_ids.filtered(lambda operation: operation in self.eligible_operation_ids)
            self._normalize_selected_operations()
            self._set_sort_type_from_operations()
            self._set_default_receipt_destination_stage()
        return {
            "domain": {
                "operation_ids": self._operation_selection_domain(),
                "source_lot_ids": [("id", "in", self.eligible_lot_ids.ids)],
            }
        }

    @api.onchange("source_lot_id")
    def _onchange_source_lot_id(self):
        if self.source_lot_id:
            self.source_lot_ids = self.source_lot_id | self.additional_source_line_ids.mapped("lot_id")
            if not self.planned_weight_g:
                self.planned_weight_g = self.source_lot_id.current_weight_g
            self.operation_ids = self.operation_ids.filtered(lambda operation: operation in self.eligible_operation_ids)
            self._normalize_selected_operations()
            self._set_sort_type_from_operations()
            self._set_default_receipt_destination_stage()
        return {
            "domain": {
                "operation_ids": self._operation_selection_domain(),
                "source_lot_id": [("id", "in", self.eligible_lot_ids.ids)],
                "source_lot_ids": [("id", "in", self.eligible_lot_ids.ids)],
            }
        }

    @api.onchange("operation_ids")
    def _onchange_operation_ids(self):
        self._normalize_selected_operations()
        self._set_sort_type_from_operations()
        self._set_default_receipt_destination_stage()
        self._clear_obsolete_task_lines()
        if not self.worker_id:
            return {
                "domain": {
                    "operation_ids": self._operation_selection_domain(),
                    "source_lot_id": [("id", "in", self.eligible_lot_ids.ids)],
                    "source_lot_ids": [("id", "in", self.eligible_lot_ids.ids)],
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
                "source_lot_ids": [("id", "in", self.eligible_lot_ids.ids)],
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

    def _clear_obsolete_task_lines(self):
        for request in self:
            operation_ids = set(request.operation_ids.ids)
            obsolete_lines = request.task_line_ids.filtered(
                lambda line, ids=operation_ids: line.operation_id.id not in ids
            )
            obsolete_lines.unlink()

    @api.constrains(
        "worker_id", "operation_ids", "source_lot_id", "planned_weight_g", "additional_source_line_ids"
    )
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
            all_source_lots = request.source_lot_id | request.additional_source_line_ids.mapped("lot_id")
            if len(all_source_lots) != 1 + len(request.additional_source_line_ids):
                raise ValidationError("Один мешок нельзя добавить в заявку дважды.")
            operation_codes = set(request.operation_ids.mapped("code"))
            if request.additional_source_line_ids and not (operation_codes & TUBE_OPERATION_CODES):
                raise ValidationError("Несколько исходных мешков разрешены только для операции труб.")
            if request.additional_source_line_ids and operation_codes & TUBE_OPERATION_CODES:
                source_year_id = request.source_lot_id.extraction_year_id.id
                source_year = request.source_lot_id.extraction_year
                source_month = request.source_lot_id.extraction_month
                different_period_lots = request.additional_source_line_ids.mapped("lot_id").filtered(
                    lambda lot, year_id=source_year_id, year=source_year, month=source_month: (
                        lot.extraction_year_id.id != year_id if year_id or lot.extraction_year_id else lot.extraction_year != year
                    )
                    or lot.extraction_month != month
                )
                if different_period_lots:
                    raise ValidationError("Для операции труб исходные мешки должны быть одного года и месяца добычи.")
            route_error_lots = all_source_lots.filtered(
                lambda lot, operations=request.operation_ids: not lot._is_operation_route_allowed(operations)
            )
            if route_error_lots:
                raise ValidationError("Выбранный маршрут недоступен для одного из исходных мешков.")
            allowed_ids = set(request.worker_id.sudo().cabochon_allowed_operation_ids.ids)
            if request.operation_ids and not set(request.operation_ids.ids).issubset(allowed_ids):
                raise ValidationError("Работник не допущен ко всем операциям заявки.")
            completed_operation_ids = (
                set()
                if request.source_lot_id.is_return_loss_lot
                else request.source_lot_id._completed_operation_ids()
                if request.source_lot_id
                else set()
            )
            repeated_operations = request.operation_ids.filtered(
                lambda operation, done=completed_operation_ids: operation.id in done
                and operation.code not in REPEATABLE_OPERATION_CODES
            )
            if repeated_operations:
                operation_names = ", ".join(repeated_operations.mapped("display_name"))
                raise ValidationError(
                    f"Операции уже были выполнены для этого мешка или его исходного мешка: {operation_names}."
                )
            route_error = request._operation_route_error(
                request.operation_ids,
                set()
                if request.source_lot_id.is_return_loss_lot
                else request.source_lot_id._completed_operation_codes()
                if request.source_lot_id
                else set(),
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
        repeated_codes = (selected_codes & completed_codes) - REPEATABLE_OPERATION_CODES
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
        tube_codes = {"tubes"}
        if tube_codes & selected_codes and (completed_codes or (selected_codes - tube_codes)):
            return "Операция Трубы выполняется отдельным первым этапом перед всеми остальными операциями."
        wash_codes = {"tumble_wash", "toluene_wash"}
        sorting_codes = {"manual_sorting", "auto_separator"}
        if not enforce_prerequisites:
            return False
        non_wash_codes = selected_codes - wash_codes - tube_codes
        if non_wash_codes and not ((completed_codes | selected_codes) & wash_codes):
            return "Перед другими операциями мешок должен пройти помывку в галтовке или толуоле."
        after_sort_codes = selected_codes - wash_codes - sorting_codes - tube_codes
        if after_sort_codes and not ((completed_codes | selected_codes) & sorting_codes):
            return "Перед дальнейшими операциями мешок должен пройти ручную сортировку или авто-сепаратор."
        return False

    def action_confirm(self):
        for request in self:
            if request.state != "draft":
                continue
            request._validate_task_lines()
            request._sync_operation_lines()
            request._ensure_issue_transfer()
            request.write(
                {
                    "state": "confirmed",
                    "confirmed_at": request.confirmed_at or fields.Datetime.now(),
                }
            )
            request.issue_id._notify_manager_activity()

    def _validate_task_lines(self):
        for request in self:
            task_operations = request.operation_ids.filtered(lambda operation: operation.code in TASK_OPERATION_CODES)
            if not task_operations:
                continue
            if not request.task_line_ids:
                raise UserError("Добавьте производственные задачи для операций со справочниками.")
            missing_operations = task_operations - request.task_line_ids.mapped("operation_id")
            if missing_operations:
                names = ", ".join(missing_operations.mapped("display_name"))
                raise UserError(f"Добавьте производственные задачи для операций: {names}.")
            request.task_line_ids._check_task_line_values()

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
            lines = request.operation_line_ids.filtered(lambda item: item.state == "pending").sorted("sequence")
            if lines:
                lines.action_start(started_at=started_at)

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
                ]
                + [
                    (0, 0, {"lot_id": line.lot_id.id, "weight_g": line.weight_g})
                    for line in self.additional_source_line_ids
                ],
                "company_id": self.company_id.id,
            }
        )
        self.issue_id = issue
        return issue


    def _ensure_receipt_transfer(self, issue_lines=None):
        self.ensure_one()
        exclude_transfer_id = self.env.context.get("exclude_receipt_transfer_id")
        existing = self.receipt_ids.filtered(
            lambda item: item.transfer_type == "receipt"
            and item.state in ("draft", "manager_confirmed")
            and item.id != exclude_transfer_id
        )
        if existing:
            receipt = existing[:1]
            if issue_lines and not receipt.line_ids:
                receipt.sudo().write(
                    {
                        "weight_before_g": self._receipt_weight_before(issue_lines),
                        "line_ids": self._receipt_line_commands(issue_lines),
                    }
                )
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
                "weight_before_g": self._receipt_weight_before(issue_lines),
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
        issue_lines = issue_lines or self._open_issue_lines_for_receipt()
        if self.task_line_ids:
            receipt_weight_before = self._receipt_weight_before(issue_lines)
            issued_pairs = [(lot, weight) for lot, weight in (issue_lines or []) if lot]
            if len(issued_pairs) == len(self.task_line_ids):
                pairs = zip(self.task_line_ids, issued_pairs, strict=False)
            else:
                default_lot = issued_pairs[:1][0][0] if issued_pairs else self.source_lot_id
                default_weight = receipt_weight_before
                pairs = ((task, (default_lot, default_weight)) for task in self.task_line_ids)
            return [
                (0, 0, task._receipt_line_values(lot=lot, weight_before=weight))
                for task, (lot, weight) in pairs
            ]
        return [
            (
                0,
                0,
                {
                    "lot_id": lot.id,
                    "weight_before_g": weight,
                },
            )
            for lot, weight in (issue_lines or [])
            if lot
        ]

    def _receipt_weight_before(self, issue_lines):
        issue_lines = issue_lines or self._open_issue_lines_for_receipt()
        weights = [weight for lot, weight in (issue_lines or []) if lot]
        if weights:
            return sum(weights)
        issued_lots = self._open_issued_lots_for_receipt()
        if issued_lots:
            return sum(issued_lots.mapped("current_weight_g"))
        issue_line_weights = self.issue_id.line_ids.mapped("weight_g") if self.issue_id else []
        if issue_line_weights:
            return sum(issue_line_weights)
        return self.source_lot_id.current_weight_g or self.source_lot_id.initial_weight_g

    def _open_issue_lines_for_receipt(self):
        self.ensure_one()
        return [(lot, lot.current_weight_g) for lot in self._open_issued_lots_for_receipt()]

    def _open_issued_lots_for_receipt(self):
        self.ensure_one()
        if not self.issue_id:
            return self.env["cabochon.stone.lot"]
        issue_lots = self.issue_id.line_ids.mapped("new_lot_id") | self.issue_id.line_ids.mapped("lot_id")
        return issue_lots.sudo().filtered(
            lambda lot: lot.owner_employee_id == self.worker_id
            and lot.state == "issued"
            and lot.current_weight_g > 0
        )


class CabochonProductionRequestTaskLine(models.Model):
    _name = "cabochon.production.request.task.line"
    _description = "Производственная задача заявки"
    _order = "request_id, sequence, id"

    request_id = fields.Many2one(
        "cabochon.production.request",
        string="Заявка",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Порядок", default=10)
    operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        string="Операция",
        required=True,
        ondelete="restrict",
    )
    operation_code = fields.Char(related="operation_id.code", store=True, readonly=True)
    sort_type = fields.Char(string="Тип сортировки")
    color_id = fields.Many2one("cabochon.color", string="Цвет", ondelete="restrict")
    stone_size_id = fields.Many2one("cabochon.size", string="Размер", ondelete="restrict")
    shape_id = fields.Many2one("cabochon.shape", string="Форма", ondelete="restrict")
    form_type_id = fields.Many2one("cabochon.form.type", string="Тип формы", ondelete="restrict")
    show_sort_fields = fields.Boolean(compute="_compute_field_visibility")
    show_tube_fields = fields.Boolean(compute="_compute_field_visibility")
    show_press_fields = fields.Boolean(compute="_compute_field_visibility")
    show_machine_fields = fields.Boolean(compute="_compute_field_visibility")
    show_color_fields = fields.Boolean(compute="_compute_field_visibility")
    show_size_fields = fields.Boolean(compute="_compute_field_visibility")
    show_shape_fields = fields.Boolean(compute="_compute_field_visibility")
    show_form_type_fields = fields.Boolean(compute="_compute_field_visibility")
    show_cutting_fields = fields.Boolean(compute="_compute_field_visibility")
    eligible_stone_size_ids = fields.Many2many(
        "cabochon.size",
        compute="_compute_eligible_reference_ids",
        compute_sudo=True,
        string="Доступные размеры",
    )
    eligible_shape_ids = fields.Many2many(
        "cabochon.shape",
        compute="_compute_eligible_reference_ids",
        compute_sudo=True,
        string="Доступные формы",
    )
    eligible_form_type_ids = fields.Many2many(
        "cabochon.form.type",
        compute="_compute_eligible_reference_ids",
        compute_sudo=True,
        string="Доступные типы формы",
    )
    note = fields.Text(string="Комментарий")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            operation = self.env["cabochon.manufacturing.operation"].browse(vals.get("operation_id"))
            if operation.code in SORT_OPERATION_TYPES and not vals.get("sort_type"):
                vals["sort_type"] = SORT_OPERATION_TYPES[operation.code]
        return super().create(vals_list)

    @api.depends("operation_id.code")
    def _compute_field_visibility(self):
        for line in self:
            code = line.operation_id.code
            line.show_sort_fields = code in SORT_OPERATION_TYPES
            line.show_tube_fields = code in TUBE_OPERATION_CODES
            line.show_press_fields = code == "press"
            line.show_machine_fields = code in MACHINE_OPERATION_CODES
            line.show_cutting_fields = code in CUTTING_OPERATION_CODES
            line.show_color_fields = line.show_sort_fields
            line.show_size_fields = (
                line.show_sort_fields
                or line.show_tube_fields
                or line.show_press_fields
                or line.show_machine_fields
                or line.show_cutting_fields
                or code in DRILLING_OPERATION_CODES
            )
            line.show_shape_fields = line.show_press_fields or line.show_machine_fields or line.show_cutting_fields
            line.show_form_type_fields = line.show_machine_fields

    @api.depends("operation_id.code")
    def _compute_eligible_reference_ids(self):
        size_model = self.env["cabochon.size"].sudo()
        shape_model = self.env["cabochon.shape"].sudo()
        form_type_model = self.env["cabochon.form.type"].sudo()
        for line in self:
            code = line.operation_id.code
            size_flags = []
            shape_flags = []
            if code in SORT_OPERATION_TYPES:
                size_flags.append("use_for_sorting")
            if code in TUBE_OPERATION_CODES:
                size_flags.append("use_for_tubes")
            if code == "press":
                size_flags.append("use_for_press")
                shape_flags.append("use_for_press")
            if code in CUTTING_OPERATION_CODES:
                size_flags.append("use_for_cutting")
                shape_flags.append("use_for_cutting")
            if code in MACHINE_OPERATION_CODES:
                size_flags.append("use_for_machine")
                shape_flags.append("use_for_machine")
            if code in DRILLING_OPERATION_CODES:
                size_flags.append("use_for_drilling")
            line.eligible_stone_size_ids = self._eligible_reference_records(size_model, size_flags)
            line.eligible_shape_ids = self._eligible_reference_records(shape_model, shape_flags)
            line.eligible_form_type_ids = form_type_model.search([("active", "=", True)])

    @api.model
    def _eligible_reference_records(self, model, usage_flags):
        all_records = model.search([("active", "=", True)])
        if not usage_flags:
            return all_records
        tagged_records = model.browse()
        for flag in usage_flags:
            tagged_records |= all_records.filtered(flag)
        return tagged_records or all_records

    @api.onchange("operation_id")
    def _onchange_operation_id(self):
        if self.operation_id.code in SORT_OPERATION_TYPES and not self.sort_type:
            self.sort_type = SORT_OPERATION_TYPES[self.operation_id.code]

    @api.constrains(
        "request_id",
        "operation_id",
        "color_id",
        "stone_size_id",
        "shape_id",
        "form_type_id",
    )
    def _check_task_line_values(self):
        for line in self:
            if line.operation_id not in line.request_id.operation_ids:
                raise ValidationError("Операция задачи должна быть выбрана в маршруте заявки.")
            code = line.operation_id.code
            if code not in TASK_OPERATION_CODES:
                raise ValidationError("Задачи добавляются только для операций со справочниками.")
            missing = []
            if code in SORT_OPERATION_TYPES:
                if not line.color_id:
                    missing.append("цвет")
                if not line.stone_size_id:
                    missing.append("размер")
            if code in TUBE_OPERATION_CODES and not line.stone_size_id:
                missing.append("размер трубы")
            if code == "press":
                if not line.stone_size_id:
                    missing.append("размер")
                if not line.shape_id:
                    missing.append("форма")
            if code in MACHINE_OPERATION_CODES:
                if not line.stone_size_id:
                    missing.append("размер")
                if not line.form_type_id:
                    missing.append("тип формы")
                if not line.shape_id:
                    missing.append("форма")
            if code in CUTTING_OPERATION_CODES:
                if not line.stone_size_id:
                    missing.append("размер")
                if not line.shape_id:
                    missing.append("форма")
            if code in DRILLING_OPERATION_CODES and not line.stone_size_id:
                missing.append("диаметр отверстия")
            if missing:
                raise ValidationError(
                    f"В задаче операции {line.operation_id.display_name} заполните: {', '.join(missing)}."
                )

    def _receipt_line_values(self, lot=False, weight_before=0.0):
        self.ensure_one()
        return {
            "task_line_id": self.id,
            "lot_id": lot.id if lot else False,
            "weight_before_g": weight_before,
            "color_id": self.color_id.id if self.color_id else lot.color_id.id if lot and lot.color_id else False,
            "stone_size_id": self.stone_size_id.id if self.stone_size_id else False,
            "shape_id": self.shape_id.id if self.shape_id else False,
            "form_type_id": self.form_type_id.id if self.form_type_id else False,
        }


class CabochonProductionRequestSourceLine(models.Model):
    _name = "cabochon.production.request.source.line"
    _description = "Дополнительный исходный мешок заявки"
    _order = "id"

    request_id = fields.Many2one(
        "cabochon.production.request", string="Заявка", required=True, ondelete="cascade"
    )
    lot_id = fields.Many2one("cabochon.stone.lot", string="Исходный мешок", required=True, ondelete="restrict")
    weight_g = fields.Float(string="Плановый вес, г", required=True, digits=WEIGHT_DIGITS)

    @api.constrains("lot_id", "weight_g", "request_id")
    def _check_values(self):
        for line in self:
            if float_compare(line.weight_g, 0.0, precision_digits=4) <= 0:
                raise ValidationError("Плановый вес дополнительного мешка должен быть больше нуля.")
            if float_compare(line.weight_g, line.lot_id.current_weight_g, precision_digits=4) > 0:
                raise ValidationError("Плановый вес не может превышать остаток дополнительного мешка.")
            if line.lot_id == line.request_id.source_lot_id:
                raise ValidationError("Основной мешок нельзя повторять в дополнительных строках.")
            line.request_id._check_source_lots_available(
                [line.lot_id.id], exclude_request_ids=line.request_id.ids
            )

    _request_lot_unique = models.Constraint(
        "UNIQUE(request_id, lot_id)", "Один дополнительный мешок нельзя добавить в заявку дважды."
    )


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
        digits=WEIGHT_DIGITS,
    )
    started_at = fields.Datetime(string="Начало")
    finished_at = fields.Datetime(string="Окончание")
    duration_hours = fields.Float(string="Время, ч", compute="_compute_duration_hours")
    received_weight_g = fields.Float(string="Фактически сдано, г", compute="_compute_received_weight_g", digits=WEIGHT_DIGITS)
    worker_id = fields.Many2one("hr.employee", string="Работник", related="request_id.worker_id", store=True)
    company_id = fields.Many2one("res.company", string="Компания", related="request_id.company_id", store=True)
    note = fields.Text(string="Комментарий")

    @api.depends("started_at", "finished_at")
    def _compute_duration_hours(self):
        now = fields.Datetime.now()
        for line in self:
            end_at = line.finished_at or now
            if line.started_at and end_at:
                line.duration_hours = (end_at - line.started_at).total_seconds() / 3600.0
            else:
                line.duration_hours = 0.0

    @api.depends("request_id.movement_ids.kind", "request_id.movement_ids.weight_g", "request_id.movement_ids.operation_ids")
    def _compute_received_weight_g(self):
        for line in self:
            movements = line.request_id.movement_ids.filtered(
                lambda movement, operation=line.operation_id: movement.kind == "receipt" and operation in movement.operation_ids
            )
            line.received_weight_g = sum(movements.mapped("weight_g"))

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


