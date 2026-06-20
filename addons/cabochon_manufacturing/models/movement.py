from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class CabochonManufacturingMovement(models.Model):
    _name = "cabochon.manufacturing.movement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Журнал движений изготовления кабошонов"
    _order = "movement_date desc, id desc"

    name = fields.Char(string="Номер", default="Новый", readonly=True, copy=False)
    kind = fields.Selection(
        [
            ("receipt", "Приход"),
            ("issue", "Выдача"),
            ("defect", "Брак"),
            ("loss", "Потеря"),
            ("correction", "Корректировка"),
        ],
        string="Вид движения",
        required=True,
        tracking=True,
    )
    defect_kind = fields.Selection(
        [("detected", "Выявленный брак"), ("made", "Сделанный брак")],
        string="Тип брака",
    )
    request_id = fields.Many2one("cabochon.production.request", string="Заявка", ondelete="restrict")
    transfer_id = fields.Many2one("cabochon.material.transfer", string="Документ", ondelete="restrict")
    lot_id = fields.Many2one("cabochon.stone.lot", string="Исходный мешок", ondelete="restrict")
    new_lot_id = fields.Many2one("cabochon.stone.lot", string="Новый мешок", ondelete="restrict")
    operation_ids = fields.Many2many(
        "cabochon.manufacturing.operation",
        "cabochon_movement_operation_rel",
        "movement_id",
        "operation_id",
        string="Операции",
    )
    primary_operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        compute="_compute_primary_operation_id",
        store=True,
        readonly=False,
        string="Операция для отчетов",
    )
    report_lot_id = fields.Many2one(
        "cabochon.stone.lot",
        compute="_compute_report_lot_id",
        store=True,
        string="Мешок для отчетов",
    )
    report_lot_extraction_year = fields.Integer(
        string="Год добычи мешка",
        related="report_lot_id.extraction_year",
        store=True,
        readonly=True,
        aggregator=False,
    )
    report_lot_extraction_month = fields.Selection(
        string="Месяц добычи мешка",
        related="report_lot_id.extraction_month",
        store=True,
        readonly=True,
    )
    source_weight_before_g = fields.Float(
        string="Исходный вес до операции, г",
        digits=(16, 4),
        readonly=True,
        aggregator=False,
    )
    loss_norm_percent = fields.Float(
        string="Норма потерь, %",
        compute="_compute_loss_quality",
        store=True,
    )
    loss_percent = fields.Float(
        string="Факт потерь, %",
        compute="_compute_loss_quality",
        store=True,
    )
    loss_over_norm_percent = fields.Float(
        string="Отклонение от нормы, %",
        compute="_compute_loss_quality",
        store=True,
    )
    is_loss_over_norm = fields.Boolean(
        string="Потери выше нормы",
        compute="_compute_loss_quality",
        store=True,
    )
    source_location_id = fields.Many2one("cabochon.manufacturing.location", string="Откуда", ondelete="restrict")
    destination_location_id = fields.Many2one("cabochon.manufacturing.location", string="Куда", ondelete="restrict")
    worker_id = fields.Many2one("hr.employee", string="Работник", ondelete="restrict")
    manager_id = fields.Many2one("hr.employee", string="Ответственный", ondelete="restrict")
    weight_g = fields.Float(string="Вес, г", digits=(16, 4), required=True)
    movement_date = fields.Datetime(string="Дата движения", default=fields.Datetime.now, required=True)
    correction_of_id = fields.Many2one("cabochon.manufacturing.movement", string="Корректирует", ondelete="restrict")
    note = fields.Text(string="Комментарий")
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
                vals["name"] = sequence.next_by_code("cabochon.manufacturing.movement") or "Новый"
        movements = super().create(vals_list)
        movements.filtered(lambda movement: movement.is_loss_over_norm)._notify_loss_over_norm()
        return movements

    @api.depends("operation_ids")
    def _compute_primary_operation_id(self):
        for movement in self:
            movement.primary_operation_id = movement.operation_ids.sorted("sequence")[-1:] if movement.operation_ids else False

    @api.depends("kind", "lot_id", "new_lot_id")
    def _compute_report_lot_id(self):
        for movement in self:
            movement.report_lot_id = (
                movement.new_lot_id
                if movement.kind in ("receipt", "defect") and movement.new_lot_id
                else movement.lot_id or movement.new_lot_id
            )

    @api.depends("kind", "weight_g", "source_weight_before_g", "primary_operation_id.expected_loss_percent")
    def _compute_loss_quality(self):
        for movement in self:
            norm = movement.primary_operation_id.expected_loss_percent or 0.0
            fact = 0.0
            if movement.kind == "loss" and movement.source_weight_before_g:
                fact = movement.weight_g / movement.source_weight_before_g * 100.0
            over_norm = fact - norm
            movement.loss_norm_percent = norm if movement.kind == "loss" else 0.0
            movement.loss_percent = fact
            movement.loss_over_norm_percent = over_norm if over_norm > 0 else 0.0
            movement.is_loss_over_norm = bool(movement.kind == "loss" and over_norm > 0)

    def _notify_loss_over_norm(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id("cabochon.production.request")
        today = fields.Date.context_today(self)
        for movement in self.filtered(lambda item: item.request_id.technologist_id.user_id):
            request = movement.request_id
            user = request.technologist_id.user_id
            existing = self.env["mail.activity"].sudo().search(
                [
                    ("res_model_id", "=", model_id),
                    ("res_id", "=", request.id),
                    ("activity_type_id", "=", activity_type.id),
                    ("user_id", "=", user.id),
                    ("summary", "=", "Потери выше нормы"),
                ],
                limit=1,
            )
            if existing:
                continue
            request.sudo().with_context(cabochon_activity_system_update=True).activity_schedule(
                activity_type_id=activity_type.id,
                date_deadline=today,
                summary="Потери выше нормы",
                note=(
                    "По заявке есть потери выше нормы операции. "
                    f"Факт: {movement.loss_percent:.2f}%, норма: {movement.loss_norm_percent:.2f}%."
                ),
                user_id=user.id,
            )

    def write(self, vals):
        raise UserError("Движения нельзя менять. Для исправления создайте корректирующее движение.")

    def unlink(self):
        raise UserError("Движения нельзя удалять. Для исправления создайте корректировку.")

    def action_open_correction_wizard(self):
        self.ensure_one()
        report_lot = self.report_lot_id or self.new_lot_id or self.lot_id
        if not self.env["cabochon.movement.correction.wizard"]._user_can_correct_lot(report_lot):
            raise UserError("У вас нет права корректировать этот мешок на его текущем складе.")
        return {
            "type": "ir.actions.act_window",
            "name": "Корректировка движения",
            "res_model": "cabochon.movement.correction.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_correction_of_id": self.id,
                "default_lot_id": report_lot.id if report_lot else False,
            },
        }


class CabochonMovementCorrectionWizard(models.TransientModel):
    _name = "cabochon.movement.correction.wizard"
    _description = "Мастер корректировки движения Кабошонов"

    correction_type = fields.Selection(
        [
            ("weight", "Корректировка веса"),
            ("location", "Корректировка склада"),
        ],
        string="Тип корректировки",
        default="weight",
        required=True,
    )
    correction_of_id = fields.Many2one(
        "cabochon.manufacturing.movement",
        string="Корректирует движение",
        ondelete="restrict",
    )
    lot_id = fields.Many2one(
        "cabochon.stone.lot",
        string="Мешок",
        required=True,
        ondelete="restrict",
    )
    current_weight_g = fields.Float(string="Текущий вес, г", related="lot_id.current_weight_g", readonly=True)
    current_location_id = fields.Many2one(
        "cabochon.manufacturing.location",
        string="Текущий склад",
        related="lot_id.location_id",
        readonly=True,
    )
    delta_weight_g = fields.Float(string="Изменение веса, г", digits=(16, 4))
    destination_location_id = fields.Many2one(
        "cabochon.manufacturing.location",
        string="Новый склад",
        ondelete="restrict",
    )
    reason = fields.Text(string="Причина", required=True)

    def action_apply(self):
        self.ensure_one()
        self._check_correction_scope()
        if self.correction_type == "weight":
            self._apply_weight_correction()
        else:
            self._apply_location_correction()
        return {"type": "ir.actions.act_window_close"}

    @api.model
    def _user_allowed_correction_location_codes(self):
        user = self.env.user
        if user.has_group("cabochon_base.group_cabochon_admin"):
            return {"raw", "prepared", "semi_finished", "finished", "employee", "loss"}
        allowed_codes = set()
        if user.has_group("cabochon_base.group_cabochon_manager"):
            allowed_codes.update({"raw", "prepared", "semi_finished"})
        if user.has_group("cabochon_base.group_cabochon_finished_manager"):
            allowed_codes.add("finished")
        return allowed_codes

    @api.model
    def _user_can_correct_lot(self, lot):
        if not lot:
            return False
        return self._user_can_correct_location(lot.location_id)

    @api.model
    def _user_can_correct_location(self, location):
        if not location:
            return False
        allowed_codes = self._user_allowed_correction_location_codes()
        if location.code not in allowed_codes:
            return False
        if self.env.user.has_group("cabochon_base.group_cabochon_admin"):
            return True
        return bool(self.env.user.employee_id and location.manager_id == self.env.user.employee_id)

    def _check_correction_scope(self):
        if not self._user_can_correct_location(self.lot_id.location_id):
            raise UserError("У вас нет права корректировать мешок на этом складе.")
        if self.correction_type == "location" and not self._user_can_correct_location(self.destination_location_id):
            raise UserError("У вас нет права переносить мешок на указанный склад.")

    def _apply_weight_correction(self):
        if float_is_zero(self.delta_weight_g, precision_digits=4):
            raise UserError("Укажите ненулевое изменение веса.")
        new_weight = self.lot_id.current_weight_g + self.delta_weight_g
        if float_compare(new_weight, 0.0, precision_digits=4) < 0:
            raise UserError("Корректировка не может сделать текущий вес мешка отрицательным.")
        source_location = self.lot_id.location_id
        self.lot_id.with_context(cabochon_inventory_movement=True).write(
            {
                "current_weight_g": new_weight,
                "state": self._state_for_location(source_location, new_weight),
            }
        )
        self._create_correction_movement(
            weight_g=self.delta_weight_g,
            source_location=source_location,
            destination_location=source_location,
            note_prefix="Корректировка веса",
        )

    def _apply_location_correction(self):
        if not self.destination_location_id:
            raise UserError("Укажите новый склад.")
        source_location = self.lot_id.location_id
        destination_location = self.destination_location_id
        owner_employee = destination_location.employee_id if destination_location.code == "employee" else False
        self.lot_id.with_context(cabochon_inventory_movement=True).write(
            {
                "location_id": destination_location.id,
                "owner_employee_id": owner_employee.id if owner_employee else False,
                "state": self._state_for_location(destination_location, self.lot_id.current_weight_g),
            }
        )
        self._create_correction_movement(
            weight_g=self.lot_id.current_weight_g,
            source_location=source_location,
            destination_location=destination_location,
            note_prefix="Корректировка склада",
        )

    def _create_correction_movement(self, weight_g, source_location, destination_location, note_prefix):
        manager = self.env.user.employee_id
        movement_values = {
            "kind": "correction",
            "correction_of_id": self.correction_of_id.id if self.correction_of_id else False,
            "lot_id": self.lot_id.id,
            "source_location_id": source_location.id if source_location else False,
            "destination_location_id": destination_location.id if destination_location else False,
            "manager_id": manager.id if manager else False,
            "weight_g": weight_g,
            "movement_date": fields.Datetime.now(),
            "note": f"{note_prefix}: {self.reason}",
            "company_id": self.lot_id.company_id.id,
        }
        return self.env["cabochon.manufacturing.movement"].sudo().create(movement_values)

    def _state_for_location(self, location, weight_g):
        if float_is_zero(weight_g, precision_digits=4):
            return "consumed"
        if location.code == "employee":
            return "issued"
        if location.code == "loss":
            return "written_off"
        return "available"


