from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero

from .constants import (
    DEFECT_LOT_SUFFIX_BY_LOCATION_CODE,
    OPERATION_CODE_SUFFIXES,
    SORT_OPERATION_TYPES,
)

MACHINE_OPERATION_CODES = {"cnc", "cabochon_machine", "ball_machine"}
RETURN_LOSS_OPERATION_CODES = {"cnc", "stone_preparation", "cabochon_machine"}
CUTTING_OPERATION_CODES = {"cutting"}
TUBE_OPERATION_CODES = {"tubes"}
WEIGHT_DIGITS = (16, 1)


class CabochonMaterialTransfer(models.Model):
    _name = "cabochon.material.transfer"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Выдача/сдача материалов по изготовлению"
    _order = "state_order, transfer_date desc, id desc"

    name = fields.Char(string="Номер", default="Новый", copy=False, readonly=True)
    transfer_type = fields.Selection(
        [("issue", "Выдача работнику"), ("receipt", "Сдача от работника")],
        string="Тип",
        required=True,
        default="issue",
        tracking=True,
    )
    request_id = fields.Many2one("cabochon.production.request", string="Заявка", ondelete="restrict", tracking=True)
    worker_id = fields.Many2one("hr.employee", string="Работник", ondelete="restrict", tracking=True)
    manager_id = fields.Many2one(
        "hr.employee",
        string="Кладовщик/приемщик",
        ondelete="restrict",
        tracking=True,
    )
    operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_transfer_operation_rel",
        "transfer_id",
        "operation_id",
        string="Операции",
    )
    primary_operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        compute="_compute_primary_operation_id",
        store=True,
        string="Операция для отчетов",
    )
    transfer_date = fields.Datetime(string="Дата и время", default=fields.Datetime.now, required=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Ожидает менеджера"),
            ("manager_confirmed", "Ожидает работника"),
            ("confirmed", "Подтверждено"),
        ],
        default="draft",
        string="Статус",
        readonly=True,
        required=True,
        tracking=True,
    )
    state_order = fields.Integer(string="Порядок статуса", compute="_compute_state_order", store=True)
    manager_confirmed_by_id = fields.Many2one(
        "res.users", string="Подтвердил со стороны склада", readonly=True, copy=False
    )
    worker_confirmed_by_id = fields.Many2one(
        "res.users", string="Подтвердил со стороны работника", readonly=True, copy=False
    )
    admin_action_note = fields.Text(string="Административная отметка", readonly=True, copy=False)
    line_ids = fields.One2many("cabochon.material.transfer.line", "transfer_id", string="Строки")
    weight_before_g = fields.Float(string="Оставшееся сырье, г", digits=WEIGHT_DIGITS)
    total_weight_g = fields.Float(string="Фактический вес, г", compute="_compute_totals", store=True, digits=WEIGHT_DIGITS)
    total_defect_weight_g = fields.Float(string="Брак, г", compute="_compute_totals", store=True, digits=WEIGHT_DIGITS)
    total_detected_defect_weight_g = fields.Float(
        string="Выявленный брак, г", compute="_compute_totals", store=True, digits=WEIGHT_DIGITS
    )
    total_made_defect_weight_g = fields.Float(
        string="Сделанный брак, г", compute="_compute_totals", store=True, digits=WEIGHT_DIGITS
    )
    total_lost_weight_g = fields.Float(string="Потери, г", compute="_compute_totals", store=True, digits=WEIGHT_DIGITS)
    total_return_loss_weight_g = fields.Float(
        string="Возвратные потери, г", compute="_compute_totals", store=True, digits=WEIGHT_DIGITS
    )
    is_final_receipt = fields.Boolean(string="Окончательная сдача")
    show_sort_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_tube_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_press_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_machine_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_color_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_size_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_shape_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_form_type_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_cutting_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    show_return_loss_fields = fields.Boolean(compute="_compute_receipt_field_visibility")
    can_worker_confirm = fields.Boolean(compute="_compute_can_worker_confirm")
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
        for vals in vals_list:
            if vals.get("name", "Новый") == "Новый":
                vals["name"] = sequence.next_by_code("cabochon.material.transfer") or "Новый"
        transfers = super().create(vals_list)
        for transfer in transfers.filtered(lambda item: not item.manager_id):
            manager = transfer._get_warehouse_manager()
            if manager:
                transfer.sudo().manager_id = manager.id
        transfers._notify_manager_activity()
        return transfers

    @api.depends(
        "line_ids.weight_g",
        "line_ids.defect_weight_g",
        "line_ids.detected_defect_weight_g",
        "line_ids.made_defect_weight_g",
        "line_ids.lost_weight_g",
        "line_ids.return_loss_weight_g",
    )
    def _compute_totals(self):
        for transfer in self:
            transfer.total_weight_g = sum(transfer.line_ids.mapped("weight_g"))
            transfer.total_defect_weight_g = sum(transfer.line_ids.mapped("defect_weight_g"))
            transfer.total_detected_defect_weight_g = sum(transfer.line_ids.mapped("detected_defect_weight_g"))
            transfer.total_made_defect_weight_g = sum(transfer.line_ids.mapped("made_defect_weight_g"))
            transfer.total_lost_weight_g = sum(transfer.line_ids.mapped("lost_weight_g"))
            transfer.total_return_loss_weight_g = sum(transfer.line_ids.mapped("return_loss_weight_g"))

    @api.depends("state")
    def _compute_state_order(self):
        for transfer in self:
            transfer.state_order = {"draft": 0, "manager_confirmed": 1, "confirmed": 9}.get(transfer.state, 5)

    @api.depends("operation_ids")
    def _compute_primary_operation_id(self):
        for transfer in self:
            transfer.primary_operation_id = transfer.operation_ids.sorted("sequence")[-1:] if transfer.operation_ids else False

    @api.depends("transfer_type", "operation_ids.code")
    def _compute_receipt_field_visibility(self):
        for transfer in self:
            codes = set(transfer.operation_ids.mapped("code"))
            is_receipt = transfer.transfer_type == "receipt"
            transfer.show_sort_fields = is_receipt and bool(codes & {"manual_sorting", "auto_separator"})
            transfer.show_tube_fields = is_receipt and bool(codes & TUBE_OPERATION_CODES)
            transfer.show_press_fields = is_receipt and "press" in codes
            transfer.show_machine_fields = is_receipt and bool(codes & MACHINE_OPERATION_CODES)
            transfer.show_cutting_fields = is_receipt and bool(codes & CUTTING_OPERATION_CODES)
            transfer.show_color_fields = is_receipt
            transfer.show_size_fields = (
                transfer.show_sort_fields
                or transfer.show_tube_fields
                or transfer.show_press_fields
                or transfer.show_machine_fields
                or transfer.show_cutting_fields
                or "drilling" in codes
            )
            transfer.show_shape_fields = transfer.show_press_fields or transfer.show_machine_fields or transfer.show_cutting_fields
            transfer.show_form_type_fields = transfer.show_machine_fields
            transfer.show_return_loss_fields = is_receipt and bool(codes & RETURN_LOSS_OPERATION_CODES)

    @api.depends_context("uid")
    def _compute_can_worker_confirm(self):
        is_admin = self.env.user.has_group("cabochon_base.group_cabochon_admin")
        for transfer in self:
            transfer.can_worker_confirm = bool(is_admin or transfer.worker_id.user_id == self.env.user)

    def write(self, vals):
        internal_fields = {"state", "manager_confirmed_by_id", "worker_confirmed_by_id", "admin_action_note"}
        if set(vals) - internal_fields and any(record.state != "draft" for record in self):
            raise UserError("Выдачу/сдачу после подтверждения менеджером нельзя менять.")
        result = super().write(vals)
        if {"manager_id", "state", "transfer_type", "request_id"}.intersection(vals):
            self._clear_manager_activities()
            self._notify_manager_activity()
        return result

    def unlink(self):
        if any(record.state != "draft" for record in self):
            raise UserError("Выдачу/сдачу после подтверждения менеджером нельзя удалить.")
        self._clear_manager_activities()
        self._clear_worker_activities()
        return super().unlink()

    @api.onchange("request_id", "transfer_type", "operation_ids")
    def _onchange_request_id(self):
        if self.request_id:
            self.worker_id = self.request_id.worker_id
            self.operation_ids = self.request_id.operation_ids
            self.weight_before_g = self._default_weight_before()
        self.manager_id = self._get_warehouse_manager()

    @api.onchange("line_ids")
    def _onchange_line_ids(self):
        for transfer in self.filtered(lambda item: item.transfer_type != "issue"):
            transfer._set_receipt_loss_weights()

    def action_manager_confirm(self):
        for transfer in self:
            transfer._lock_for_update()
            if transfer.state != "draft":
                continue
            transfer._validate_before_manager_confirm()
            admin_note = transfer._admin_manager_action_note()
            transfer.with_context(cabochon_transfer_internal_update=True).write(
                {
                    "state": "manager_confirmed",
                    "manager_confirmed_by_id": self.env.user.id,
                    "admin_action_note": transfer._append_admin_action_note(admin_note),
                }
            )
            transfer._clear_manager_activities()
            transfer._notify_worker_activity()

    def action_worker_confirm(self):
        for transfer in self:
            transfer._lock_for_update()
            if transfer.state != "manager_confirmed":
                continue
            if (
                not self.env.user.has_group("cabochon_base.group_cabochon_admin")
                and transfer.worker_id.user_id != self.env.user
            ):
                raise UserError("Финально подтвердить документ может только назначенный работник или администратор.")
            transfer.sudo().with_context(
                cabochon_transfer_internal_update=True,
                cabochon_admin_worker_action_note=transfer._admin_worker_action_note(),
            )._execute_confirmed_transfer()

    def action_worker_reject_receipt(self):
        for transfer in self:
            transfer._lock_for_update()
            if transfer.state != "manager_confirmed" or transfer.transfer_type == "issue":
                continue
            if (
                not self.env.user.has_group("cabochon_base.group_cabochon_admin")
                and transfer.worker_id.user_id != self.env.user
            ):
                raise UserError("Отказаться от сдачи может только назначенный работник или администратор.")
            transfer.with_context(cabochon_transfer_internal_update=True).write(
                {
                    "state": "draft",
                    "manager_confirmed_by_id": False,
                }
            )
            transfer._clear_worker_activities()
            transfer._notify_manager_activity()
            transfer.message_post(body="Работник отказался от сдачи. Документ возвращен менеджеру для исправления.")

    def action_confirm(self):
        return self.action_manager_confirm()

    def _execute_confirmed_transfer(self):
        for transfer in self:
            if transfer.transfer_type == "issue":
                transfer._confirm_issue()
            else:
                transfer._confirm_receipt()
            admin_note = self.env.context.get("cabochon_admin_worker_action_note")
            transfer.with_context(cabochon_transfer_internal_update=True).write(
                {
                    "state": "confirmed",
                    "worker_confirmed_by_id": self.env.user.id,
                    "admin_action_note": transfer._append_admin_action_note(admin_note),
                }
            )
            transfer._clear_worker_activities()

    def _admin_manager_action_note(self):
        self.ensure_one()
        if not self.env.user.has_group("cabochon_base.group_cabochon_admin"):
            return False
        if self.manager_id.user_id == self.env.user:
            return False
        action = "выдал материалы" if self.transfer_type == "issue" else "принял сдачу"
        manager = self.manager_id.display_name if self.manager_id else "ответственного кладовщика"
        return f"Администратор {self.env.user.display_name} {action} за {manager}."

    def _admin_worker_action_note(self):
        self.ensure_one()
        if not self.env.user.has_group("cabochon_base.group_cabochon_admin"):
            return False
        if self.worker_id.user_id == self.env.user:
            return False
        action = "принял выдачу" if self.transfer_type == "issue" else "сдал материалы"
        worker = self.worker_id.display_name if self.worker_id else "работника"
        return f"Администратор {self.env.user.display_name} {action} за {worker}."

    def _append_admin_action_note(self, note):
        self.ensure_one()
        if not note:
            return self.admin_action_note
        notes = [item for item in (self.admin_action_note, note) if item]
        return "\n".join(notes)

    def _lock_for_update(self):
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM cabochon_material_transfer WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset(["state"])

    def _notify_manager_activity(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        today = fields.Date.context_today(self)
        for transfer in self.filtered(lambda item: item.state == "draft" and item.manager_id.user_id):
            user = transfer.manager_id.user_id
            title = "Нужно выдать материалы" if transfer.transfer_type == "issue" else "Нужно принять сдачу"
            existing = self.env["mail.activity"].sudo().search(
                [
                    ("res_model_id", "=", model_id),
                    ("res_id", "=", transfer.id),
                    ("activity_type_id", "=", activity_type.id),
                    ("user_id", "=", user.id),
                    ("summary", "=", title),
                ],
                limit=1,
            )
            if existing:
                continue
            transfer.sudo().with_context(cabochon_activity_system_update=True).activity_schedule(
                activity_type_id=activity_type.id,
                date_deadline=today,
                summary=title,
                note="Появился документ, ожидающий подтверждения ответственным менеджером склада.",
                user_id=user.id,
            )

    def _clear_manager_activities(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        activities = self.env["mail.activity"].sudo().search(
            [
                ("res_model_id", "=", model_id),
                ("res_id", "in", self.ids),
                ("activity_type_id", "=", activity_type.id),
                ("summary", "in", ("Нужно выдать материалы", "Нужно принять сдачу")),
            ]
        )
        activities.with_context(cabochon_activity_system_update=True).unlink()

    def _notify_worker_activity(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        today = fields.Date.context_today(self)
        for transfer in self.filtered(lambda item: item.state == "manager_confirmed" and item.worker_id.user_id):
            title = "Нужно принять выдачу" if transfer.transfer_type == "issue" else "Нужно подтвердить сдачу"
            existing = self.env["mail.activity"].sudo().search(
                [
                    ("res_model_id", "=", model_id),
                    ("res_id", "=", transfer.id),
                    ("activity_type_id", "=", activity_type.id),
                    ("user_id", "=", transfer.worker_id.user_id.id),
                    ("summary", "=", title),
                ],
                limit=1,
            )
            if not existing:
                transfer.sudo().with_context(cabochon_activity_system_update=True).activity_schedule(
                    activity_type_id=activity_type.id,
                    date_deadline=today,
                    summary=title,
                    note="Менеджер склада подтвердил документ. Требуется подтверждение работника.",
                    user_id=transfer.worker_id.user_id.id,
                )

    def _clear_worker_activities(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        activities = self.env["mail.activity"].sudo().search(
            [
                ("res_model_id", "=", model_id),
                ("res_id", "in", self.ids),
                ("activity_type_id", "=", activity_type.id),
                ("summary", "in", ("Нужно принять выдачу", "Нужно подтвердить сдачу")),
            ]
        )
        activities.with_context(cabochon_activity_system_update=True).unlink()

    def _validate_before_manager_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError("Добавьте строки.")
        if not self.worker_id:
            raise UserError("Укажите работника.")
        if not self.manager_id:
            raise UserError("Укажите ответственного менеджера склада.")
        if (
            not self.env.user.has_group("cabochon_base.group_cabochon_admin")
            and self.manager_id.user_id
            and self.manager_id.user_id != self.env.user
        ):
            raise UserError("Подтвердить документ может только назначенный менеджер склада или администратор.")
        if self.transfer_type != "issue":
            self._set_receipt_loss_weights()
        validation_lines = self.line_ids if self.transfer_type == "issue" else self._active_receipt_line_ids()
        if self.transfer_type != "issue" and not validation_lines:
            raise UserError("В сдаче укажите хотя бы одну строку с годным весом, браком или потерями.")
        for line in validation_lines.with_context(skip_receipt_auto_loss=True):
            line._validate_amounts()
        if self.transfer_type == "issue":
            lot_ids = self.line_ids.mapped("lot_id").ids
            if len(lot_ids) != len(set(lot_ids)):
                raise UserError("Один мешок нельзя указывать в выдаче несколько раз.")
            foreign_lots = self.line_ids.mapped("lot_id").filtered(
                lambda lot: lot.location_id.manager_id != self.manager_id
            )
            if foreign_lots:
                raise UserError("Все мешки выдачи должны находиться на складе назначенного менеджера.")
            if self.request_id:
                overweight_lines = self.line_ids.filtered(
                    lambda line: self._planned_issue_weight_for_line(line)
                    and float_compare(self._planned_issue_weight_for_line(line), line.lot_id.current_weight_g, precision_digits=4)
                    >= 0
                    and float_compare(line.weight_g, self._planned_issue_weight_for_line(line), precision_digits=4) > 0
                )
                if overweight_lines:
                    raise UserError("Фактический вес выдачи не может превышать вес, заявленный технологом, если заявлен весь мешок.")
        else:
            unavailable_lots = validation_lines.mapped("lot_id").filtered(
                lambda lot: lot.owner_employee_id != self.worker_id
                or lot.state != "issued"
                or float_compare(lot.current_weight_g, 0.0, precision_digits=4) <= 0
            )
            if unavailable_lots:
                names = ", ".join(unavailable_lots.mapped("display_name"))
                raise UserError(f"Нельзя принять сдачу: мешок уже не на руках у работника или без остатка: {names}.")
            foreign_lots = validation_lines.mapped("lot_id").filtered(
                lambda lot: lot.owner_employee_id and lot.owner_employee_id != self.worker_id
            )
            if foreign_lots:
                raise UserError("Работник может сдавать только мешки, выданные ему.")

    def _active_receipt_line_ids(self):
        self.ensure_one()
        if self.transfer_type == "issue":
            return self.line_ids
        return self.line_ids.filtered(
            lambda line: any(
                not float_is_zero(line[field_name], precision_digits=4)
                for field_name in (
                    "weight_g",
                    "detected_defect_weight_g",
                    "made_defect_weight_g",
                    "return_loss_weight_g",
                    "lost_weight_g",
                )
            )
            or (self.is_final_receipt and (line.lot_id or line.weight_before_g))
        )

    def _confirm_issue(self):
        employee_location = self._get_employee_location(self.worker_id)
        issued_lines = []
        lot_ids = self.line_ids.mapped("lot_id").ids
        if lot_ids:
            self.env.cr.execute(
                "SELECT id FROM cabochon_stone_lot WHERE id IN %s FOR UPDATE",
                [tuple(lot_ids)],
            )
            self.line_ids.mapped("lot_id").invalidate_recordset(["current_weight_g", "state", "location_id"])
        for line in self.line_ids:
            lot = line.sudo().lot_id
            if float_compare(lot.current_weight_g, line.weight_g, precision_digits=4) < 0:
                raise UserError(f"В мешке {lot.display_name} недостаточно веса.")
            source_location = lot.location_id
            issued_lot = lot
            original_weight = lot.current_weight_g
            planned_weight = self._planned_issue_weight_for_line(line)
            planned_weight = planned_weight or line.weight_g
            if float_compare(lot.current_weight_g, planned_weight, precision_digits=4) < 0:
                raise UserError(f"В мешке {lot.display_name} меньше заявленного технологом веса.")
            full_lot_requested = float_compare(planned_weight, lot.current_weight_g, precision_digits=4) >= 0
            if full_lot_requested:
                regular_remaining_weight = 0.0
                inventory_difference_weight = lot.current_weight_g - line.weight_g
            else:
                regular_remaining_weight = lot.current_weight_g - line.weight_g
                inventory_difference_weight = 0.0
            if float_compare(regular_remaining_weight, 0.0, precision_digits=4) > 0:
                issued_lot = self._create_remaining_lot(
                    lot,
                    line.weight_g,
                    employee_location,
                    state="issued",
                    owner_employee=self.worker_id,
                )
                lot.sudo().with_context(cabochon_inventory_movement=True).write(
                    {
                        "current_weight_g": regular_remaining_weight,
                        "state": "available",
                    }
                )
            else:
                lot.sudo().with_context(cabochon_inventory_movement=True).write(
                    {
                        "location_id": employee_location.id,
                        "owner_employee_id": self.worker_id.id,
                        "current_weight_g": line.weight_g,
                        "state": "issued",
                    }
                )
            if float_compare(inventory_difference_weight, 0.0, precision_digits=4) > 0:
                self._create_remaining_lot(
                    lot,
                    inventory_difference_weight,
                    source_location,
                    name=self._next_inventory_difference_lot_name(lot),
                    state="inventory_difference",
                )
            line_for_movement = line.with_context(cabochon_source_weight_before=original_weight)
            self.env["cabochon.manufacturing.movement"].sudo().create(
                self._movement_values(
                    line_for_movement,
                    "issue",
                    lot,
                    line.weight_g,
                    source_location,
                    employee_location,
                    issued_lot,
                )
            )
            line.with_context(cabochon_transfer_internal_update=True).new_lot_id = issued_lot
            issued_lines.append((issued_lot, line.weight_g))
        if self.request_id and self.request_id.state == "confirmed":
            now = self.transfer_date or fields.Datetime.now()
            self.request_id.sudo().write(
                {
                    "state": "in_progress",
                    "issued_at": self.request_id.issued_at or now,
                    "started_at": self.request_id.started_at or now,
                }
            )
            self.request_id.sudo()._start_next_operation_line(now)
            self.request_id.sudo()._ensure_receipt_transfer(issue_lines=issued_lines)

    def _planned_issue_weight_for_line(self, line):
        self.ensure_one()
        if not self.request_id or not line.lot_id:
            return line.weight_g
        if line.lot_id == self.request_id.source_lot_id:
            return self.request_id.planned_weight_g
        source_line = self.request_id.additional_source_line_ids.filtered(lambda item: item.lot_id == line.lot_id)[:1]
        return source_line.weight_g if source_line else line.weight_g

    def _create_remaining_lot(
        self,
        source_lot,
        weight_g,
        source_location,
        *,
        name=False,
        state="available",
        owner_employee=False,
    ):
        self.ensure_one()
        values = {
            "parent_id": source_lot.id,
            "supplier_id": source_lot.supplier_id.id if source_lot.supplier_id else False,
            "supplier_name": source_lot.supplier_name,
            "fraction": source_lot.fraction,
            "fraction_id": source_lot.fraction_id.id if source_lot.fraction_id else False,
            "extraction_year": source_lot.extraction_year,
            "extraction_year_id": source_lot.extraction_year_id.id if source_lot.extraction_year_id else False,
            "extraction_month": source_lot.extraction_month,
            "waybill_number": source_lot.waybill_number,
            "receipt_date": source_lot.receipt_date,
            "accepted_by_id": source_lot.accepted_by_id.id if source_lot.accepted_by_id else False,
            "location_id": source_location.id,
            "owner_employee_id": owner_employee.id if owner_employee else False,
            "initial_weight_g": weight_g,
            "current_weight_g": weight_g,
            "color_id": source_lot.color_id.id if source_lot.color_id else False,
            "color": source_lot.color,
            "stone_size_id": source_lot.stone_size_id.id if source_lot.stone_size_id else False,
            "stone_size": source_lot.stone_size,
            "shape_id": source_lot.shape_id.id if source_lot.shape_id else False,
            "shape": source_lot.shape,
            "form_type_id": source_lot.form_type_id.id if source_lot.form_type_id else False,
            "form_type": source_lot.form_type,
            "is_return_loss_lot": source_lot.is_return_loss_lot,
            "return_loss_operation_id": source_lot.return_loss_operation_id.id
            if source_lot.return_loss_operation_id
            else False,
            "is_defect_lot": source_lot.is_defect_lot,
            "state": state,
            "company_id": self.company_id.id,
        }
        if name:
            values["name"] = name
        return self.env["cabochon.stone.lot"].sudo().with_context(
            skip_initial_lot_movement=True
        ).create(values)

    def _next_inventory_difference_lot_name(self, source_lot):
        self.ensure_one()
        lot_model = self.env["cabochon.stone.lot"].sudo()
        base_name = f"{source_lot.name}-loss"
        name = base_name
        index = 2
        while lot_model.search_count(["|", ("name", "=", name), ("barcode", "=", name)]):
            name = f"{base_name}-{index}"
            index += 1
        return name

    def _confirm_receipt(self):
        destination = self._get_destination_location()
        defect_destination = self._get_defect_destination_location(destination)
        loss_destination = self._get_loss_destination_location()
        source_location = self._get_employee_location(self.worker_id)
        self._set_receipt_loss_weights()
        consumed_weight_by_lot = self._receipt_consumed_weight_by_lot()
        if consumed_weight_by_lot:
            self.env.cr.execute(
                "SELECT id FROM cabochon_stone_lot WHERE id IN %s FOR UPDATE",
                [tuple(consumed_weight_by_lot)],
            )
        for source_lot_id, consumed_weight in consumed_weight_by_lot.items():
            source_lot = self.env["cabochon.stone.lot"].sudo().browse(source_lot_id)
            source_lot.invalidate_recordset(["current_weight_g", "state"])
            if float_compare(source_lot.current_weight_g, consumed_weight, precision_digits=4) < 0:
                raise UserError(f"В мешке {source_lot.display_name} недостаточно веса для сдачи.")
        active_lines = self._active_receipt_line_ids()
        for line in active_lines:
            source_lot = line.sudo().lot_id or self.request_id.sudo().source_lot_id
            consumed_weight = line.weight_g + line.defect_weight_g + line.return_loss_weight_g + line.lost_weight_g
            new_lot = line._create_received_lot(destination)
            line.with_context(cabochon_transfer_internal_update=True).new_lot_id = new_lot
            if line.weight_g:
                self.env["cabochon.manufacturing.movement"].sudo().create(
                    self._movement_values(line, "receipt", source_lot, line.weight_g, source_location, destination, new_lot)
                )
            if line.detected_defect_weight_g:
                defect_lot = line._add_to_defect_lot(defect_destination, line.detected_defect_weight_g, source_lot)
                self.env["cabochon.manufacturing.movement"].sudo().create(
                    self._movement_values(
                        line,
                        "defect",
                        source_lot,
                        line.detected_defect_weight_g,
                        source_location,
                        defect_destination,
                        defect_lot,
                        defect_kind="detected",
                    )
                )
            if line.made_defect_weight_g:
                defect_lot = line._add_to_defect_lot(defect_destination, line.made_defect_weight_g, source_lot)
                self.env["cabochon.manufacturing.movement"].sudo().create(
                    self._movement_values(
                        line,
                        "defect",
                        source_lot,
                        line.made_defect_weight_g,
                        source_location,
                        defect_destination,
                        defect_lot,
                        defect_kind="made",
                    )
                )
            if line.lost_weight_g:
                self.env["cabochon.manufacturing.movement"].sudo().create(
                    self._movement_values(line, "loss", source_lot, line.lost_weight_g, source_location, loss_destination)
                )
            if line.return_loss_weight_g:
                return_loss_lot = line._add_to_return_loss_lot(loss_destination, line.return_loss_weight_g, source_lot)
                self.env["cabochon.manufacturing.movement"].sudo().create(
                    self._movement_values(
                        line,
                        "loss",
                        source_lot,
                        line.return_loss_weight_g,
                        source_location,
                        loss_destination,
                        return_loss_lot,
                    )
                )
            self._consume_receipt_line_source_lots(line, consumed_weight)
        if self.request_id and self.request_id.state in ("in_progress", "partially_done"):
            close_request = self.is_final_receipt or self.primary_operation_id.code in ("tumble_wash", "toluene_wash")
            if close_request:
                self.request_id.sudo()._finish_open_operation_lines(self.transfer_date)
            else:
                self.request_id.sudo()._start_next_operation_line(self.request_id.started_at or self.transfer_date)
            self.request_id.sudo().write(
                {
                    "state": "done" if close_request else "partially_done",
                    "started_at": self.request_id.started_at or self.transfer_date,
                    "first_receipt_at": self.request_id.first_receipt_at or self.transfer_date,
                    "closed_at": self.request_id.closed_at or self.transfer_date if close_request else self.request_id.closed_at,
                }
            )
            if close_request:
                self.request_id.sudo()._clear_overdue_activities()
                self.request_id.sudo()._clear_loss_over_norm_activities()
            else:
                self.request_id.sudo().with_context(exclude_receipt_transfer_id=self.id)._ensure_receipt_transfer()

    def _set_receipt_loss_weights(self):
        self.ensure_one()
        if self.transfer_type == "issue":
            return
        if not self.weight_before_g:
            self.weight_before_g = self._default_weight_before()
        grouped_lines = {}
        lines_to_process = self.line_ids.filtered(
            lambda line: any(
                not float_is_zero(line[field_name], precision_digits=4)
                for field_name in (
                    "weight_g",
                    "detected_defect_weight_g",
                    "made_defect_weight_g",
                    "return_loss_weight_g",
                )
            )
            or (self.is_final_receipt and (line.lot_id or line.weight_before_g))
        )
        for line in lines_to_process:
            source_lot = line.sudo().lot_id or self.request_id.sudo().source_lot_id
            source_lot_id = source_lot.id if source_lot else False
            grouped_lines.setdefault(source_lot_id, self.env["cabochon.material.transfer.line"])
            grouped_lines[source_lot_id] |= line
        for source_lot_id, lines in grouped_lines.items():
            source_lot = self.env["cabochon.stone.lot"].sudo().browse(source_lot_id)
            if not source_lot:
                for line in lines:
                    line.lost_weight_g = line._auto_loss_weight() if self.is_final_receipt else 0.0
                continue
            input_weight = self.weight_before_g if len(grouped_lines) == 1 else 0.0
            input_weight = (
                input_weight
                or max(lines.mapped("weight_before_g"))
                or self._issued_weight_for_lot(source_lot)
                or source_lot.current_weight_g
            )
            if not input_weight:
                input_weight = source_lot.initial_weight_g
            for line in lines.filtered(lambda item: not item.weight_before_g):
                line.weight_before_g = input_weight
            good_weight = sum(lines.mapped("weight_g"))
            defect_weight = sum(lines.mapped("defect_weight_g"))
            return_loss_weight = sum(lines.mapped("return_loss_weight_g"))
            if float_compare(good_weight + defect_weight + return_loss_weight, input_weight, precision_digits=4) > 0:
                raise UserError(
                    f"По мешку {source_lot.display_name} сумма годного веса и брака не может быть больше веса на входе."
                )
            loss_weight = input_weight - good_weight - defect_weight - return_loss_weight if self.is_final_receipt else 0.0
            if float_compare(loss_weight, 0.0, precision_digits=4) < 0:
                loss_weight = 0.0
            for line in lines:
                line.lost_weight_g = 0.0
            if not float_is_zero(loss_weight, precision_digits=4):
                lines.sorted("id")[-1:].lost_weight_g = loss_weight

    def _receipt_consumed_weight_by_lot(self):
        self.ensure_one()
        consumed_weight_by_lot = {}
        active_lines = self._active_receipt_line_ids()
        for line in active_lines:
            consumed_weight = line.weight_g + line.defect_weight_g + line.return_loss_weight_g + line.lost_weight_g
            mixed_lots = self._mixed_issue_lots_for_receipt_line(line)
            if mixed_lots:
                for source_lot, weight in self._distributed_consumed_weights(mixed_lots, consumed_weight):
                    consumed_weight_by_lot.setdefault(source_lot.id, 0.0)
                    consumed_weight_by_lot[source_lot.id] += weight
                continue
            source_lot = line.sudo().lot_id or self.request_id.sudo().source_lot_id
            if source_lot:
                consumed_weight_by_lot.setdefault(source_lot.id, 0.0)
                consumed_weight_by_lot[source_lot.id] += consumed_weight
        return consumed_weight_by_lot

    def _consume_receipt_line_source_lots(self, line, consumed_weight):
        mixed_lots = self._mixed_issue_lots_for_receipt_line(line)
        if mixed_lots:
            lots_and_weights = self._distributed_consumed_weights(mixed_lots, consumed_weight)
        else:
            source_lot = line.sudo().lot_id or self.request_id.sudo().source_lot_id
            lots_and_weights = [(source_lot, consumed_weight)] if source_lot else []
        for source_lot, weight in lots_and_weights:
            remaining_weight = source_lot.current_weight_g - weight
            source_lot.sudo().with_context(cabochon_inventory_movement=True).write(
                {
                    "current_weight_g": remaining_weight,
                    "state": "consumed" if float_is_zero(remaining_weight, precision_digits=4) else source_lot.state,
                }
            )

    def _mixed_issue_lots_for_receipt_line(self, line):
        self.ensure_one()
        if not self.request_id or not line.task_line_id:
            return self.env["cabochon.stone.lot"]
        issue_lines = self.request_id.issue_id.line_ids
        if len(issue_lines) <= 1:
            return self.env["cabochon.stone.lot"]
        return issue_lines.mapped("lot_id")

    def _distributed_consumed_weights(self, lots, consumed_weight):
        remaining = consumed_weight
        lots_and_weights = []
        for lot in lots:
            if float_is_zero(remaining, precision_digits=4):
                break
            lot.invalidate_recordset(["current_weight_g"])
            weight = min(lot.current_weight_g, remaining)
            if not float_is_zero(weight, precision_digits=4):
                lots_and_weights.append((lot, weight))
            remaining -= weight
        if lots and float_compare(remaining, 0.0, precision_digits=4) > 0:
            lots_and_weights.append((lots[-1], remaining))
        return lots_and_weights

    def _movement_values(self, line, kind, lot, weight, source_location, destination_location, new_lot=False, defect_kind=False):
        note_parts = [
            item
            for item in (
                line.note,
                self.admin_action_note,
                self.env.context.get("cabochon_admin_worker_action_note"),
            )
            if item
        ]
        return {
            "kind": kind,
            "defect_kind": defect_kind if kind == "defect" else False,
            "request_id": self.request_id.id if self.request_id else False,
            "transfer_id": self.id,
            "lot_id": lot.id if lot else False,
            "new_lot_id": new_lot.id if new_lot else False,
            "operation_ids": [(6, 0, self.operation_ids.ids)],
            "primary_operation_id": self.primary_operation_id.id if self.primary_operation_id else False,
            "source_location_id": source_location.id if source_location else False,
            "destination_location_id": destination_location.id if destination_location else False,
            "worker_id": self.worker_id.id if self.worker_id else False,
            "manager_id": self.manager_id.id if self.manager_id else False,
            "weight_g": weight,
            "source_weight_before_g": line.env.context.get("cabochon_source_weight_before")
            or line.weight_before_g
            or self.weight_before_g
            or (lot.current_weight_g if lot else 0.0)
            or (lot.initial_weight_g if lot else 0.0),
            "movement_date": self.transfer_date,
            "note": "\n".join(note_parts),
            "company_id": self.company_id.id,
        }

    def _default_weight_before(self):
        self.ensure_one()
        issued_weight = self._issued_weight_for_lot()
        if issued_weight:
            return issued_weight
        lot = self.request_id.source_lot_id
        if not lot:
            lot = self.line_ids[:1].lot_id
        if not lot:
            return 0.0
        return lot.current_weight_g or lot.initial_weight_g

    def _issued_weight_for_lot(self, lot=False):
        self.ensure_one()
        if not self.request_id or not self.request_id.issue_id:
            return 0.0
        if lot:
            lot = lot.sudo()
            if lot.owner_employee_id == self.worker_id and float_compare(lot.current_weight_g, 0.0, precision_digits=4) > 0:
                return lot.current_weight_g
        issued_lots = self._issued_lots_for_request()
        if lot:
            issued_lots = issued_lots.filtered(lambda item: item == lot)
        if issued_lots:
            return sum(issued_lots.mapped("current_weight_g"))
        issue_lines = self.request_id.issue_id.line_ids
        if lot:
            issue_lines = issue_lines.filtered(lambda line: line.lot_id == lot)
        return sum(issue_lines.mapped("weight_g"))

    def _issued_lots_for_request(self):
        self.ensure_one()
        if not self.request_id or not self.request_id.issue_id:
            return self.env["cabochon.stone.lot"]
        issue_lots = self.request_id.issue_id.line_ids.mapped("new_lot_id") | self.request_id.issue_id.line_ids.mapped("lot_id")
        return issue_lots.sudo().filtered(
            lambda lot: lot.owner_employee_id == self.worker_id
            and lot.state == "issued"
            and float_compare(lot.current_weight_g, 0.0, precision_digits=4) > 0
        )

    def _get_employee_location(self, employee):
        location = self.env["cabochon.manufacturing.location"].sudo().search(
            [("code", "=", "employee"), ("employee_id", "=", employee.id)],
            limit=1,
        )
        if location:
            return location
        return self.env["cabochon.manufacturing.location"].sudo().create(
            {
                "name": f"Личный склад: {employee.name}",
                "code": "employee",
                "employee_id": employee.id,
                "manager_id": employee.id,
            }
        )

    def _get_destination_location(self):
        self.ensure_one()
        if self.transfer_type == "receipt" and self.request_id:
            return self.request_id._get_receipt_destination_location()
        return self._get_destination_location_for_operations(self.operation_ids)

    @api.model
    def _get_destination_location_for_operations(self, operations):
        operation = operations.sorted("sequence")[-1:] if operations else False
        stage = operation.warehouse_stage if operation else "semi_finished"
        location = self.env["cabochon.manufacturing.location"].sudo().search([("code", "=", stage)], limit=1)
        if not location:
            raise UserError("Не найдена складская зона назначения.")
        return location

    def _get_warehouse_manager(self):
        self.ensure_one()
        if self.transfer_type == "issue":
            lot = self.request_id.sudo().source_lot_id if self.request_id else self.line_ids[:1].sudo().lot_id
            return lot.location_id.manager_id if lot else self.env["hr.employee"]
        destination = self._get_destination_location()
        return destination.manager_id

    def _get_loss_location(self):
        location = self.env["cabochon.manufacturing.location"].sudo().search([("code", "=", "loss")], limit=1)
        if not location:
            raise UserError("Не найдена зона потерь и списаний.")
        return location

    def _get_defect_destination_location(self, default_location):
        self.ensure_one()
        return default_location

    def _get_loss_destination_location(self):
        self.ensure_one()
        return self._get_loss_location()

    def _get_stage_location(self, code):
        location = self.env["cabochon.manufacturing.location"].sudo().search([("code", "=", code)], limit=1)
        if not location:
            raise UserError("Не найдена складская зона назначения.")
        return location


class CabochonMaterialTransferLine(models.Model):
    _name = "cabochon.material.transfer.line"
    _description = "Строка выдачи/сдачи материалов"
    _order = "id"

    transfer_id = fields.Many2one(
        "cabochon.material.transfer",
        string="Документ",
        required=True,
        ondelete="cascade",
    )
    transfer_type = fields.Selection(related="transfer_id.transfer_type", store=True, readonly=True)
    lot_id = fields.Many2one("cabochon.stone.lot", string="Исходный мешок", ondelete="restrict")
    new_lot_id = fields.Many2one("cabochon.stone.lot", string="Новый мешок", readonly=True, copy=False)
    task_line_id = fields.Many2one(
        "cabochon.production.request.task.line",
        string="Задача",
        ondelete="restrict",
        readonly=True,
        copy=False,
    )
    weight_before_g = fields.Float(string="Оставшееся сырье, г", digits=WEIGHT_DIGITS)
    weight_g = fields.Float(string="Фактический вес, г", digits=WEIGHT_DIGITS)
    detected_defect_weight_g = fields.Float(string="Выявленный брак, г", digits=WEIGHT_DIGITS)
    made_defect_weight_g = fields.Float(string="Сделанный брак, г", digits=WEIGHT_DIGITS)
    defect_weight_g = fields.Float(
        string="Брак итого, г", compute="_compute_defect_weight_g", store=True, readonly=False, digits=WEIGHT_DIGITS
    )
    lost_weight_g = fields.Float(string="Потери, г", digits=WEIGHT_DIGITS)
    return_loss_weight_g = fields.Float(string="Возвратные потери, г", digits=WEIGHT_DIGITS)
    sort_type = fields.Char(string="Тип сортировки")
    color_id = fields.Many2one("cabochon.color", string="Цвет", ondelete="restrict")
    stone_size_id = fields.Many2one("cabochon.size", string="Размер", ondelete="restrict")
    shape_id = fields.Many2one("cabochon.shape", string="Форма", ondelete="restrict")
    form_type_id = fields.Many2one("cabochon.form.type", string="Тип формы", ondelete="restrict")
    color = fields.Char(string="Цвет (текст)")
    stone_size = fields.Char(string="Размер (текст)")
    shape = fields.Char(string="Форма (текст)")
    form_type = fields.Char(string="Тип формы (текст)")
    operation_code = fields.Char(related="transfer_id.primary_operation_id.code", store=True, readonly=True)
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

    @api.depends("detected_defect_weight_g", "made_defect_weight_g")
    def _compute_defect_weight_g(self):
        for line in self:
            line.defect_weight_g = line.detected_defect_weight_g + line.made_defect_weight_g

    @api.depends("transfer_id.operation_ids.code")
    def _compute_eligible_reference_ids(self):
        size_model = self.env["cabochon.size"].sudo()
        shape_model = self.env["cabochon.shape"].sudo()
        form_type_model = self.env["cabochon.form.type"].sudo()
        for line in self:
            codes = set(line.transfer_id.operation_ids.mapped("code"))
            size_flags = []
            shape_flags = []
            if codes & {"manual_sorting", "auto_separator"}:
                size_flags.append("use_for_sorting")
            if codes & TUBE_OPERATION_CODES:
                size_flags.append("use_for_tubes")
            if "press" in codes:
                size_flags.append("use_for_press")
                shape_flags.append("use_for_press")
            if codes & CUTTING_OPERATION_CODES:
                size_flags.append("use_for_cutting")
                shape_flags.append("use_for_cutting")
            if codes & MACHINE_OPERATION_CODES:
                size_flags.append("use_for_machine")
                shape_flags.append("use_for_machine")
            if "drilling" in codes:
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

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        transfer_id = values.get("transfer_id") or self.env.context.get("default_transfer_id")
        if transfer_id:
            transfer = self.env["cabochon.material.transfer"].browse(transfer_id)
            self._add_receipt_defaults(values, transfer)
        return values

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._split_legacy_defect_value(vals)
            transfer = self.env["cabochon.material.transfer"]
            if vals.get("transfer_id"):
                transfer = transfer.browse(vals["transfer_id"])
            if (
                transfer
                and transfer.state != "draft"
                and not self.env.context.get("cabochon_transfer_internal_update")
            ):
                raise UserError("После подтверждения менеджером нельзя добавлять строки документа.")
            self._add_receipt_defaults(vals, transfer)
            self.env["cabochon.stone.lot"]._sync_reference_values(vals)
            self._add_auto_loss_to_values(vals)
        return super().create(vals_list)

    def write(self, vals):
        if (
            any(line.transfer_id.state != "draft" for line in self)
            and not self.env.context.get("cabochon_transfer_internal_update")
        ):
            raise UserError("После подтверждения менеджером строки документа нельзя менять.")
        vals = dict(vals)
        self._split_legacy_defect_value(vals)
        self.env["cabochon.stone.lot"]._sync_reference_values(vals)
        if self and "lost_weight_g" not in vals and self._loss_trigger_fields(vals):
            for line in self:
                line_vals = dict(vals)
                line._add_auto_loss_to_values(line_vals)
                super(CabochonMaterialTransferLine, line).write(line_vals)
            return True
        return super().write(vals)

    def unlink(self):
        if (
            any(line.transfer_id.state != "draft" for line in self)
            and not self.env.context.get("cabochon_transfer_internal_update")
        ):
            raise UserError("После подтверждения менеджером строки документа нельзя удалить.")
        return super().unlink()

    @api.onchange("lot_id")
    def _onchange_lot_id(self):
        if self.transfer_type != "issue" and self.lot_id and not self.weight_before_g:
            self.weight_before_g = (
                self.transfer_id._issued_weight_for_lot(self.lot_id)
                or self.transfer_id.weight_before_g
                or self.lot_id.current_weight_g
                or self.lot_id.initial_weight_g
            )
        self._onchange_receipt_weights()

    @api.onchange("transfer_id")
    def _onchange_transfer_id(self):
        values = {}
        self._add_receipt_defaults(values, self.transfer_id)
        for field_name, value in values.items():
            if not self[field_name]:
                self[field_name] = value

    @api.onchange("weight_before_g", "weight_g", "detected_defect_weight_g", "made_defect_weight_g", "return_loss_weight_g")
    def _onchange_receipt_weights(self):
        if self.transfer_type != "issue":
            self.lost_weight_g = self._auto_loss_weight() if self.transfer_id.is_final_receipt else 0.0

    @api.model
    def _add_receipt_defaults(self, vals, transfer):
        if not transfer or transfer.transfer_type != "receipt":
            return
        if not vals.get("lot_id"):
            lot = transfer.line_ids[:1].lot_id or transfer.request_id.source_lot_id
            if lot:
                vals["lot_id"] = lot.id
                vals.setdefault(
                    "weight_before_g",
                    transfer._issued_weight_for_lot(lot)
                    or transfer.weight_before_g
                    or lot.current_weight_g
                    or lot.initial_weight_g,
                )
                if transfer.show_color_fields and lot.color_id and not vals.get("color_id"):
                    vals["color_id"] = lot.color_id.id
        operation_code = transfer.primary_operation_id.code if transfer.primary_operation_id else False
        if operation_code in SORT_OPERATION_TYPES and not vals.get("sort_type"):
            vals["sort_type"] = SORT_OPERATION_TYPES[operation_code]

    @api.onchange("color_id")
    def _onchange_color_id(self):
        self.color = self.color_id.name if self.color_id else False

    @api.onchange("stone_size_id")
    def _onchange_stone_size_id(self):
        self.stone_size = self.stone_size_id.name if self.stone_size_id else False

    @api.onchange("shape_id")
    def _onchange_shape_id(self):
        self.shape = self.shape_id.name if self.shape_id else False

    @api.onchange("form_type_id")
    def _onchange_form_type_id(self):
        self.form_type = self.form_type_id.name if self.form_type_id else False

    def _auto_loss_weight(self):
        self.ensure_one()
        weight_before = self.weight_before_g or 0.0
        if float_is_zero(weight_before, precision_digits=4):
            return self.lost_weight_g
        loss = weight_before - (self.weight_g or 0.0) - (self.defect_weight_g or 0.0) - (self.return_loss_weight_g or 0.0)
        return loss if float_compare(loss, 0.0, precision_digits=4) > 0 else 0.0

    @api.model
    def _split_legacy_defect_value(self, vals):
        if "defect_weight_g" not in vals:
            return
        if "detected_defect_weight_g" not in vals and "made_defect_weight_g" not in vals:
            vals["made_defect_weight_g"] = vals.get("defect_weight_g") or 0.0
        vals.pop("defect_weight_g", None)

    def _set_auto_loss_weight(self):
        for line in self:
            if line.transfer_type != "issue" and not line.env.context.get("skip_receipt_auto_loss"):
                line.lost_weight_g = line._auto_loss_weight() if line.transfer_id.is_final_receipt else 0.0

    @api.model
    def _loss_trigger_fields(self, vals):
        return bool(
            {"lot_id", "weight_before_g", "weight_g", "detected_defect_weight_g", "made_defect_weight_g", "return_loss_weight_g"}.intersection(vals)
        )

    def _add_auto_loss_to_values(self, vals):
        transfer = self.transfer_id
        if vals.get("transfer_id"):
            transfer = self.env["cabochon.material.transfer"].browse(vals["transfer_id"])
        transfer_type = transfer.transfer_type or vals.get("transfer_type")
        if transfer_type == "issue" or "lost_weight_g" in vals:
            return
        weight_before = vals.get("weight_before_g", self.weight_before_g)
        if not weight_before and transfer:
            weight_before = transfer.weight_before_g
        if not weight_before and vals.get("lot_id"):
            lot = self.env["cabochon.stone.lot"].sudo().browse(vals["lot_id"])
            weight_before = transfer._issued_weight_for_lot(lot) if transfer else 0.0
            weight_before = weight_before or lot.current_weight_g or lot.initial_weight_g
            vals.setdefault("weight_before_g", weight_before)
        if not weight_before:
            return
        weight = vals.get("weight_g", self.weight_g) or 0.0
        detected_defect = vals.get("detected_defect_weight_g", self.detected_defect_weight_g) or 0.0
        made_defect = vals.get("made_defect_weight_g", self.made_defect_weight_g) or 0.0
        defect = detected_defect + made_defect
        return_loss = vals.get("return_loss_weight_g", self.return_loss_weight_g) or 0.0
        if not transfer.is_final_receipt:
            vals["lost_weight_g"] = 0.0
            return
        loss = weight_before - weight - defect - return_loss
        vals["lost_weight_g"] = loss if float_compare(loss, 0.0, precision_digits=4) > 0 else 0.0

    def _validate_amounts(self):
        self.ensure_one()
        if not self.env.context.get("skip_receipt_auto_loss"):
            self._set_auto_loss_weight()
        for field_name in ("weight_g", "detected_defect_weight_g", "made_defect_weight_g", "return_loss_weight_g", "lost_weight_g"):
            if float_compare(self[field_name], 0.0, precision_digits=4) < 0:
                raise UserError("Вес не может быть отрицательным.")
        if self.transfer_type == "issue" and not self.lot_id:
            raise UserError("В строке выдачи укажите мешок.")
        if self.transfer_type == "issue" and float_compare(self.weight_g, 0.0, precision_digits=4) <= 0:
            raise UserError("В строке выдачи укажите вес.")
        if self.transfer_type != "issue" and all(
            float_is_zero(self[field_name], precision_digits=4)
            for field_name in ("weight_g", "defect_weight_g", "return_loss_weight_g", "lost_weight_g")
        ):
            raise UserError("В строке сдачи укажите годный вес, брак или потери.")
        if self.transfer_type != "issue" and self.weight_before_g:
            consumed_weight = self.weight_g + self.defect_weight_g + self.return_loss_weight_g + self.lost_weight_g
            if float_compare(consumed_weight, self.weight_before_g, precision_digits=4) > 0:
                raise UserError("Сумма годного веса, брака и потерь не может быть больше исходного веса.")
        if self.return_loss_weight_g and not (set(self.transfer_id.operation_ids.mapped("code")) & RETURN_LOSS_OPERATION_CODES):
            raise UserError("Возвратные потери можно указывать только для ЧПУ, подготовки камня и кабошонерки.")
        if self.transfer_type == "receipt":
            self._validate_required_receipt_attributes()

    def _validate_required_receipt_attributes(self):
        self.ensure_one()
        if float_is_zero(
            self.weight_g + self.detected_defect_weight_g + self.made_defect_weight_g + self.return_loss_weight_g,
            precision_digits=4,
        ):
            return
        operation_code = self.transfer_id.primary_operation_id.code if self.transfer_id.primary_operation_id else False
        operation_codes = set(self.transfer_id.operation_ids.mapped("code"))
        if operation_code in ("manual_sorting", "auto_separator"):
            missing = []
            if not self.color_id:
                missing.append("цвет")
            if not self.stone_size_id:
                missing.append("размер")
            if missing:
                raise UserError(f"Для сдачи после сортировки заполните: {', '.join(missing)}.")
        if operation_codes & TUBE_OPERATION_CODES and not self.stone_size_id:
            raise UserError("Для сдачи после операции Трубы заполните размер трубы.")
        if "press" in operation_codes:
            missing = []
            if not self.shape_id:
                missing.append("форма")
            if not self.stone_size_id:
                missing.append("размер")
            if missing:
                raise UserError(f"Для сдачи после пресса заполните: {', '.join(missing)}.")
        if operation_codes & MACHINE_OPERATION_CODES:
            missing = []
            if not self.stone_size_id:
                missing.append("размер")
            if not self.form_type_id:
                missing.append("тип формы")
            if not self.shape_id:
                missing.append("форма")
            if missing:
                raise UserError(
                    f"Для сдачи после ЧПУ, кабошонерки или шарокрутки заполните: {', '.join(missing)}."
                )

        if operation_codes & CUTTING_OPERATION_CODES:
            missing = []
            if not self.shape_id:
                missing.append("форма")
            if not self.stone_size_id:
                missing.append("размер")
            if missing:
                raise UserError(f"Для сдачи после раскроя заполните: {', '.join(missing)}.")
        if "drilling" in operation_codes and not self.stone_size_id:
            raise UserError("Для сдачи после сверления заполните диаметр отверстия.")

    def _create_received_lot(self, destination):
        self.ensure_one()
        if float_is_zero(self.weight_g, precision_digits=4):
            return self.env["cabochon.stone.lot"]
        source_lot = self.lot_id or self.transfer_id.request_id.source_lot_id
        values = {
            "name": self._next_received_lot_name(source_lot),
            "parent_id": source_lot.id if source_lot else False,
            "source_lot_ids": [
                (6, 0, self.transfer_id.request_id.issue_id.line_ids.mapped("lot_id").ids)
            ]
            if self.transfer_id.request_id
            and len(self.transfer_id.request_id.issue_id.line_ids) > 1
            else False,
            "supplier_id": source_lot.supplier_id.id if source_lot and source_lot.supplier_id else False,
            "supplier_name": source_lot.supplier_name if source_lot else False,
            "fraction": source_lot.fraction if source_lot else False,
            "fraction_id": source_lot.fraction_id.id if source_lot and source_lot.fraction_id else False,
            "extraction_year": source_lot.extraction_year if source_lot else False,
            "extraction_year_id": source_lot.extraction_year_id.id if source_lot and source_lot.extraction_year_id else False,
            "extraction_month": source_lot.extraction_month if source_lot else False,
            "waybill_number": source_lot.waybill_number if source_lot else False,
            "accepted_by_id": self.transfer_id.manager_id.id if self.transfer_id.manager_id else False,
            "location_id": destination.id,
            "initial_weight_g": self.weight_g,
            "current_weight_g": self.weight_g,
            "color_id": self.color_id.id if self.color_id else source_lot.color_id.id if source_lot and source_lot.color_id else False,
            "color": self.color or (source_lot.color if source_lot else False),
            "stone_size_id": self.stone_size_id.id
            if self.stone_size_id
            else source_lot.stone_size_id.id
            if source_lot and source_lot.stone_size_id
            else False,
            "stone_size": self.stone_size or (source_lot.stone_size if source_lot else False),
            "shape_id": self.shape_id.id if self.shape_id else source_lot.shape_id.id if source_lot and source_lot.shape_id else False,
            "shape": self.shape or (source_lot.shape if source_lot else False),
            "form_type_id": self.form_type_id.id
            if self.form_type_id
            else source_lot.form_type_id.id
            if source_lot and source_lot.form_type_id
            else False,
            "form_type": self.form_type or (source_lot.form_type if source_lot else False),
            "company_id": self.transfer_id.company_id.id,
        }
        if destination.code == "finished":
            existing_lot = self._find_finished_lot_to_merge(values, destination)
            if existing_lot:
                existing_lot.with_context(cabochon_inventory_movement=True).write(
                    {
                        "initial_weight_g": existing_lot.initial_weight_g + self.weight_g,
                        "current_weight_g": existing_lot.current_weight_g + self.weight_g,
                    }
                )
                return existing_lot
        return self.env["cabochon.stone.lot"].sudo().create(values)

    def _find_finished_lot_to_merge(self, values, destination):
        self.ensure_one()
        domain = [
            ("location_id", "=", destination.id),
            ("company_id", "=", self.transfer_id.company_id.id),
            ("state", "=", "available"),
            ("is_defect_lot", "=", False),
        ]
        for field_name in ("color_id", "stone_size_id", "shape_id", "form_type_id"):
            value = values.get(field_name)
            domain.append((field_name, "=", value or False))
        return self.env["cabochon.stone.lot"].sudo().search(domain, order="id", limit=1)

    def _add_to_defect_lot(self, destination, weight_g, source_lot=False):
        self.ensure_one()
        if float_is_zero(weight_g, precision_digits=4):
            return self.env["cabochon.stone.lot"]
        operation = self.transfer_id.primary_operation_id
        shape = self.shape_id or (source_lot.shape_id if source_lot else False)
        form_type = self.form_type_id or (source_lot.form_type_id if source_lot else False)
        color = self.color_id or (source_lot.color_id if source_lot else False)
        lot_model = self.env["cabochon.stone.lot"].sudo()
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            [
                operation.id if operation else 0,
                (
                    (shape.id if shape else 0) * 1000000
                    + (form_type.id if form_type else 0) * 1000
                    + (color.id if color else 0)
                ),
            ],
        )
        defect_lot = lot_model.search(
            [
                ("location_id", "=", destination.id),
                ("company_id", "=", self.transfer_id.company_id.id),
                ("is_defect_lot", "=", True),
                ("defect_operation_id", "=", operation.id if operation else False),
                ("shape_id", "=", shape.id if shape else False),
                ("form_type_id", "=", form_type.id if form_type else False),
                ("color_id", "=", color.id if color else False),
                ("state", "=", "available"),
            ],
            order="id",
            limit=1,
        )
        if defect_lot:
            defect_lot.invalidate_recordset(["initial_weight_g", "current_weight_g"])
            defect_lot.with_context(cabochon_inventory_movement=True).write(
                {
                    "initial_weight_g": defect_lot.initial_weight_g + weight_g,
                    "current_weight_g": defect_lot.current_weight_g + weight_g,
                }
            )
            return defect_lot
        location_suffix = DEFECT_LOT_SUFFIX_BY_LOCATION_CODE.get(
            destination.code,
            destination.code.upper(),
        )
        operation_suffix = OPERATION_CODE_SUFFIXES.get(operation.code, operation.code.upper()) if operation else "NO-OP"
        shape_suffix = shape.name if shape else "NO-SHAPE"
        form_type_suffix = form_type.name if form_type else "NO-FORM"
        color_suffix = color.name if color else "NO-COLOR"
        name = f"БРАК-{location_suffix}-{operation_suffix}-{shape_suffix}-{form_type_suffix}-{color_suffix}"
        values = {
            "name": name,
            "accepted_by_id": self.transfer_id.manager_id.id if self.transfer_id.manager_id else False,
            "location_id": destination.id,
            "initial_weight_g": weight_g,
            "current_weight_g": weight_g,
            "shape_id": shape.id if shape else False,
            "shape": shape.name if shape else False,
            "form_type_id": form_type.id if form_type else False,
            "form_type": form_type.name if form_type else False,
            "color_id": color.id if color else False,
            "color": color.name if color else False,
            "is_defect_lot": True,
            "defect_operation_id": operation.id if operation else False,
            "company_id": self.transfer_id.company_id.id,
        }
        return lot_model.with_context(skip_initial_lot_movement=True).create(values)

    def _add_to_return_loss_lot(self, destination, weight_g, source_lot=False):
        self.ensure_one()
        if float_is_zero(weight_g, precision_digits=4):
            return self.env["cabochon.stone.lot"]
        operation = self.transfer_id.primary_operation_id
        if not operation or operation.code not in RETURN_LOSS_OPERATION_CODES:
            return self.env["cabochon.stone.lot"]
        color = self.color_id or (source_lot.color_id if source_lot else False)
        lot_model = self.env["cabochon.stone.lot"].sudo()
        lock_color_id = color.id if color else 0
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            [operation.id, lock_color_id],
        )
        return_loss_lot = lot_model.search(
            [
                ("location_id", "=", destination.id),
                ("company_id", "=", self.transfer_id.company_id.id),
                ("is_return_loss_lot", "=", True),
                ("return_loss_operation_id", "=", operation.id),
                ("color_id", "=", color.id if color else False),
                ("state", "=", "available"),
            ],
            order="id",
            limit=1,
        )
        if return_loss_lot:
            return_loss_lot.invalidate_recordset(["initial_weight_g", "current_weight_g"])
            return_loss_lot.with_context(cabochon_inventory_movement=True).write(
                {
                    "initial_weight_g": return_loss_lot.initial_weight_g + weight_g,
                    "current_weight_g": return_loss_lot.current_weight_g + weight_g,
                }
            )
            return return_loss_lot
        operation_suffix = OPERATION_CODE_SUFFIXES.get(operation.code, operation.code.upper())
        color_name = color.name if color else "NO-COLOR"
        values = {
            "name": f"RETURN-{operation_suffix}-{color_name}",
            "accepted_by_id": self.transfer_id.manager_id.id if self.transfer_id.manager_id else False,
            "location_id": destination.id,
            "initial_weight_g": weight_g,
            "current_weight_g": weight_g,
            "color_id": color.id if color else False,
            "color": color.name if color else False,
            "is_return_loss_lot": True,
            "return_loss_operation_id": operation.id,
            "company_id": self.transfer_id.company_id.id,
        }
        return lot_model.with_context(skip_initial_lot_movement=True).create(values)

    def _next_received_lot_name(self, source_lot, suffix=False):
        if not source_lot:
            return "Новый"
        lot_model = self.env["cabochon.stone.lot"].sudo()
        operation_suffix = "-".join(
            OPERATION_CODE_SUFFIXES.get(operation.code, operation.code.upper())
            for operation in self.transfer_id.operation_ids.sorted("sequence")
            if operation.code
        )
        parts = [source_lot.name]
        if operation_suffix:
            parts.append(operation_suffix)
        if suffix:
            parts.append(suffix)
        base_name = "-".join(parts)
        index = 1
        while lot_model.search_count(["|", ("name", "=", f"{base_name}-{index}"), ("barcode", "=", f"{base_name}-{index}")]):
            index += 1
        return f"{base_name}-{index}"


