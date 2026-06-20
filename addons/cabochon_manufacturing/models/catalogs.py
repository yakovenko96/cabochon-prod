from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CabochonManufacturingOperation(models.Model):
    _name = "cabochon.manufacturing.operation"
    _description = "Операция изготовления кабошонов"
    _order = "sequence, name"

    name = fields.Char(string="Операция", required=True, translate=True)
    code = fields.Char(string="Код", required=True)
    sequence = fields.Integer(string="Последовательность", default=10)
    warehouse_stage = fields.Selection(
        [
            ("raw", "Сырье"),
            ("prepared", "Подготовленное сырье"),
            ("semi_finished", "Полуфабрикаты"),
            ("finished", "Готовые камни"),
        ],
        string="Основная зона",
        required=True,
        default="semi_finished",
    )
    final_operation = fields.Boolean(string="Финальная операция")
    expected_loss_percent = fields.Float(string="Норма потерь, %", digits=(16, 4))
    active = fields.Boolean(default=True)

    _operation_code_unique = models.Constraint(
        "UNIQUE(code)",
        "Код операции должен быть уникальным.",
    )

    @api.constrains("expected_loss_percent")
    def _check_expected_loss_percent(self):
        for operation in self:
            if operation.expected_loss_percent < 0 or operation.expected_loss_percent > 100:
                raise ValidationError("Норма потерь должна быть от 0 до 100%.")

    def write(self, vals):
        result = super().write(vals)
        if "expected_loss_percent" in vals:
            movements = self.env["cabochon.manufacturing.movement"].sudo().search(
                [("kind", "=", "loss"), ("primary_operation_id", "in", self.ids)]
            )
            movements.mapped("request_id")._sync_loss_over_norm_activities()
        return result


class CabochonExtractionYear(models.Model):
    _name = "cabochon.extraction.year"
    _description = "Год добычи камней"
    _order = "year desc"
    _rec_name = "name"

    name = fields.Char(string="Служебное название", required=True, readonly=True)
    year = fields.Integer(string="Год добычи", required=True)
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("year") and not vals.get("name"):
                vals["name"] = str(vals["year"])
            elif vals.get("name") and not vals.get("year"):
                vals["year"] = self._parse_year(vals["name"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("year") and "name" not in vals:
            vals["name"] = str(vals["year"])
        elif vals.get("name") and "year" not in vals:
            vals["year"] = self._parse_year(vals["name"])
        return super().write(vals)

    @api.model
    def _parse_year(self, value):
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise ValidationError("Год добычи должен быть числом.") from error

    @api.constrains("year")
    def _check_year(self):
        for record in self:
            if record.year < 1900 or record.year > 2100:
                raise ValidationError("Проверьте год добычи.")

    _year_unique = models.Constraint(
        "UNIQUE(year)",
        "Год добычи должен быть уникальным.",
    )


class CabochonFraction(models.Model):
    _name = "cabochon.fraction"
    _description = "Фракция камней"
    _order = "name"

    name = fields.Char(string="Фракция", required=True)
    active = fields.Boolean(default=True)

    _fraction_name_unique = models.Constraint(
        "UNIQUE(name)",
        "Фракция должна быть уникальной.",
    )


class CabochonManufacturingLocation(models.Model):
    _name = "cabochon.manufacturing.location"
    _description = "Складская зона изготовления кабошонов"
    _order = "sequence, name"

    name = fields.Char(string="Зона", required=True)
    code = fields.Selection(
        [
            ("raw", "Склад сырья"),
            ("prepared", "Склад подготовленного сырья"),
            ("semi_finished", "Склад полуфабрикатов"),
            ("finished", "Склад готовых камней"),
            ("employee", "Личный склад работника"),
            ("loss", "Потери и списания"),
        ],
        string="Тип зоны",
        required=True,
    )
    employee_id = fields.Many2one("hr.employee", string="Работник", ondelete="restrict")
    manager_id = fields.Many2one("hr.employee", string="Ответственный менеджер", ondelete="restrict")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _location_code_employee_unique = models.Constraint(
        "UNIQUE(code, employee_id)",
        "Для одного работника может быть только одна зона каждого типа.",
    )


