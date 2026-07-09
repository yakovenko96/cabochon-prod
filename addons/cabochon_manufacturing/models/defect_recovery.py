from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero

WEIGHT_DIGITS = (16, 1)


class CabochonDefectRecoveryWizard(models.TransientModel):
    _name = "cabochon.defect.recovery.wizard"
    _description = "Обратное преобразование брака в полуфабрикат"

    defect_lot_id = fields.Many2one(
        "cabochon.stone.lot",
        string="Мешок брака",
        required=True,
        domain=[
            ("is_defect_lot", "=", True),
            ("state", "=", "available"),
            ("current_weight_g", ">", 0),
        ],
        ondelete="restrict",
    )
    available_weight_g = fields.Float(
        string="Доступно, г",
        related="defect_lot_id.current_weight_g",
        readonly=True,
        digits=WEIGHT_DIGITS,
    )
    defect_operation_id = fields.Many2one(
        "cabochon.manufacturing.operation",
        string="Операция брака",
        related="defect_lot_id.defect_operation_id",
        readonly=True,
    )
    shape_id = fields.Many2one(
        "cabochon.shape",
        string="Форма",
        related="defect_lot_id.shape_id",
        readonly=True,
    )
    weight_g = fields.Float(string="Вес к возврату, г", required=True, digits=WEIGHT_DIGITS)
    recovery_date = fields.Datetime(string="Дата возврата", default=fields.Datetime.now, required=True)
    manager_id = fields.Many2one(
        "hr.employee",
        string="Ответственный",
        default=lambda self: self.env.user.sudo().employee_id,
        required=True,
        ondelete="restrict",
    )
    destination_location_id = fields.Many2one(
        "cabochon.manufacturing.location",
        string="Склад возврата",
        default=lambda self: self.env["cabochon.manufacturing.location"].sudo().search(
            [("code", "=", "semi_finished")],
            limit=1,
        ),
        required=True,
        domain=[("code", "=", "semi_finished")],
        ondelete="restrict",
    )
    new_lot_name = fields.Char(string="ID нового мешка")
    note = fields.Text(string="Комментарий")
    company_id = fields.Many2one(
        "res.company",
        string="Компания",
        required=True,
        default=lambda self: self.env.company,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        defect_lot_id = values.get("defect_lot_id") or self.env.context.get("default_defect_lot_id")
        if defect_lot_id and "weight_g" in fields_list and not values.get("weight_g"):
            lot = self.env["cabochon.stone.lot"].sudo().browse(defect_lot_id)
            values["weight_g"] = lot.current_weight_g
        return values

    def action_recover(self):
        self.ensure_one()
        defect_lot = self.defect_lot_id.sudo()
        destination = self.destination_location_id.sudo()
        if not defect_lot.is_defect_lot or defect_lot.state != "available":
            raise UserError("Выберите доступный сводный мешок брака.")
        if destination.code != "semi_finished":
            raise UserError("Брак можно вернуть только на склад полуфабрикатов.")
        if not self._user_can_recover_to(destination):
            raise UserError("Возвращать брак в полуфабрикаты может ответственный за склад полуфабрикатов или администратор.")
        if float_compare(self.weight_g, 0.0, precision_digits=4) <= 0:
            raise UserError("Вес к возврату должен быть больше нуля.")
        if self.new_lot_name and self.env["cabochon.stone.lot"].sudo().search_count(
            ["|", ("name", "=", self.new_lot_name), ("barcode", "=", self.new_lot_name)]
        ):
            raise UserError(f"Мешок с ID {self.new_lot_name} уже существует.")
        self.env.cr.execute(
            "SELECT id FROM cabochon_stone_lot WHERE id = %s FOR UPDATE",
            [defect_lot.id],
        )
        defect_lot.invalidate_recordset(["current_weight_g", "state"])
        if float_compare(self.weight_g, defect_lot.current_weight_g, precision_digits=4) > 0:
            raise UserError("Вес к возврату не может превышать остаток мешка брака.")

        new_lot = self._create_recovered_lot(defect_lot, destination)
        remaining_weight = defect_lot.current_weight_g - self.weight_g
        defect_lot.with_context(cabochon_inventory_movement=True).write(
            {
                "current_weight_g": remaining_weight,
                "state": "consumed" if float_is_zero(remaining_weight, precision_digits=4) else "available",
            }
        )
        self._create_recovery_movement(defect_lot, new_lot, destination)
        return {
            "type": "ir.actions.act_window",
            "name": "Остаток на складе",
            "res_model": "cabochon.stone.lot",
            "res_id": new_lot.id,
            "view_mode": "form",
            "target": "current",
        }

    def _user_can_recover_to(self, destination):
        self.ensure_one()
        if self.env.user.has_group("cabochon_base.group_cabochon_admin"):
            return True
        return bool(destination.manager_id.user_id == self.env.user)

    def _create_recovered_lot(self, defect_lot, destination):
        values = {
            "name": self.new_lot_name or self._next_recovered_lot_name(defect_lot),
            "parent_id": defect_lot.id,
            "supplier_id": defect_lot.supplier_id.id if defect_lot.supplier_id else False,
            "supplier_name": defect_lot.supplier_name,
            "fraction": defect_lot.fraction,
            "fraction_id": defect_lot.fraction_id.id if defect_lot.fraction_id else False,
            "extraction_year": defect_lot.extraction_year,
            "extraction_year_id": defect_lot.extraction_year_id.id if defect_lot.extraction_year_id else False,
            "extraction_month": defect_lot.extraction_month,
            "waybill_number": defect_lot.waybill_number,
            "accepted_by_id": self.manager_id.id if self.manager_id else False,
            "location_id": destination.id,
            "initial_weight_g": self.weight_g,
            "current_weight_g": self.weight_g,
            "color_id": defect_lot.color_id.id if defect_lot.color_id else False,
            "color": defect_lot.color,
            "shape_id": defect_lot.shape_id.id if defect_lot.shape_id else False,
            "shape": defect_lot.shape,
            "form_type_id": defect_lot.form_type_id.id if defect_lot.form_type_id else False,
            "form_type": defect_lot.form_type,
            "company_id": self.company_id.id,
        }
        return self.env["cabochon.stone.lot"].sudo().with_context(skip_initial_lot_movement=True).create(values)

    def _create_recovery_movement(self, defect_lot, new_lot, destination):
        operation_ids = [defect_lot.defect_operation_id.id] if defect_lot.defect_operation_id else []
        note_parts = ["Обратное преобразование брака в полуфабрикат"]
        if self.note:
            note_parts.append(self.note)
        return self.env["cabochon.manufacturing.movement"].sudo().create(
            {
                "kind": "recovery",
                "lot_id": defect_lot.id,
                "new_lot_id": new_lot.id,
                "operation_ids": [(6, 0, operation_ids)],
                "primary_operation_id": defect_lot.defect_operation_id.id if defect_lot.defect_operation_id else False,
                "source_location_id": defect_lot.location_id.id,
                "destination_location_id": destination.id,
                "manager_id": self.manager_id.id if self.manager_id else False,
                "weight_g": self.weight_g,
                "movement_date": self.recovery_date,
                "note": "; ".join(note_parts),
                "company_id": self.company_id.id,
            }
        )

    def _next_recovered_lot_name(self, defect_lot):
        lot_model = self.env["cabochon.stone.lot"].sudo()
        base_name = f"{defect_lot.name}-REC"
        index = 1
        name = f"{base_name}-{index}"
        while lot_model.search_count(["|", ("name", "=", name), ("barcode", "=", name)]):
            index += 1
            name = f"{base_name}-{index}"
        return name
