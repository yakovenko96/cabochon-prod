from odoo import api, fields, models
from odoo.exceptions import UserError

AUDITED_MODELS = {
    "cabochon.color",
    "cabochon.form.type",
    "cabochon.manufacturing.location",
    "cabochon.manufacturing.movement",
    "cabochon.manufacturing.operation",
    "cabochon.material.transfer",
    "cabochon.material.transfer.line",
    "cabochon.production.request",
    "cabochon.production.request.operation.line",
    "cabochon.shape",
    "cabochon.size",
    "cabochon.stone.lot",
    "hr.employee",
}


class CabochonAuditLog(models.Model):
    """Immutable journal of business changes in the Cabochon modules."""

    _name = "cabochon.audit.log"
    _description = "Журнал действий Кабошонов"
    _order = "action_date desc, id desc"

    action_date = fields.Datetime(string="Когда", required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one("res.users", string="Кто", required=True, index=True, ondelete="restrict")
    action = fields.Selection(
        [
            ("create", "Создание"),
            ("write", "Изменение"),
            ("unlink", "Удаление"),
        ],
        string="Действие",
        required=True,
        index=True,
    )
    model_name = fields.Char(string="Модель", required=True, index=True)
    model_description = fields.Char(string="Описание модели")
    record_id = fields.Integer(string="ID записи", index=True)
    record_name = fields.Char(string="Запись")
    changed_fields = fields.Text(string="Поля")
    old_values = fields.Text(string="Было")
    new_values = fields.Text(string="Стало")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("skip_cabochon_audit"):
            raise UserError("Журнал действий заполняется автоматически.")
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get("skip_cabochon_audit"):
            raise UserError("Журнал действий нельзя редактировать.")
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get("skip_cabochon_audit"):
            raise UserError("Журнал действий нельзя удалять.")
        return super().unlink()


class CabochonAuditBase(models.AbstractModel):
    """Record create/write/delete operations for Cabochon business records."""

    _inherit = "base"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._cabochon_audit_should_track_model():
            for record, vals in zip(records, vals_list, strict=False):
                if record._cabochon_audit_should_track_record():
                    record._cabochon_audit_log("create", new_values=record._cabochon_audit_values(vals))
        return records

    def write(self, vals):
        audit_snapshots = {}
        if self._cabochon_audit_should_track_model() and vals:
            field_names = [name for name in vals if name in self._fields]
            tracked_records = self.filtered(lambda item: item._cabochon_audit_should_track_record())
            if self._name == "hr.employee" and "cabochon_allowed_operation_ids" in vals:
                tracked_records |= self
            for record in tracked_records:
                audit_snapshots[record.id] = {
                    "record": record,
                    "old_values": record._cabochon_audit_values(field_names),
                }
        result = super().write(vals)
        for snapshot in audit_snapshots.values():
            record = snapshot["record"]
            if record.exists():
                record._cabochon_audit_log(
                    "write",
                    old_values=snapshot["old_values"],
                    new_values=record._cabochon_audit_values(vals),
                )
        return result

    def unlink(self):
        audit_values = []
        if self._cabochon_audit_should_track_model():
            for record in self.filtered(lambda item: item._cabochon_audit_should_track_record()):
                audit_values.append(
                    {
                        "model_name": record._name,
                        "model_description": record._description,
                        "record_id": record.id,
                        "record_name": record._cabochon_audit_display_name(),
                        "old_values": record._cabochon_audit_values(record._fields),
                    }
                )
        result = super().unlink()
        for values in audit_values:
            self._cabochon_audit_create_log("unlink", **values)
        return result

    def _cabochon_audit_should_track_model(self):
        return (
            self._name in AUDITED_MODELS
            and not self.env.context.get("skip_cabochon_audit")
            and self._cabochon_audit_log_model_ready()
        )

    def _cabochon_audit_log_model_ready(self):
        try:
            self.env["cabochon.audit.log"]
        except KeyError:
            return False
        self.env.cr.execute("SELECT to_regclass('cabochon_audit_log')")
        return bool(self.env.cr.fetchone()[0])

    def _cabochon_audit_should_track_record(self):
        self.ensure_one()
        if self._name == "hr.employee":
            return bool(
                "cabochon_allowed_operation_ids" in self._fields
                and self.sudo().cabochon_allowed_operation_ids
            )
        return True

    def _cabochon_audit_log(self, action, old_values=False, new_values=False):
        self.ensure_one()
        self._cabochon_audit_create_log(
            action,
            model_name=self._name,
            model_description=self._description,
            record_id=self.id,
            record_name=self._cabochon_audit_display_name(),
            old_values=old_values,
            new_values=new_values,
        )

    def _cabochon_audit_create_log(
        self,
        action,
        model_name,
        model_description,
        record_id,
        record_name,
        old_values=False,
        new_values=False,
    ):
        old_values = old_values or {}
        new_values = new_values or {}
        changed_fields = sorted(set(old_values) | set(new_values))
        self.env["cabochon.audit.log"].sudo().with_context(skip_cabochon_audit=True).create(
            {
                "action_date": fields.Datetime.now(),
                "user_id": self.env.context.get("cabochon_audit_user_id", self.env.user.id),
                "action": action,
                "model_name": model_name,
                "model_description": model_description,
                "record_id": record_id,
                "record_name": record_name,
                "changed_fields": "\n".join(changed_fields),
                "old_values": self._cabochon_audit_format_values(old_values),
                "new_values": self._cabochon_audit_format_values(new_values),
            }
        )

    def _cabochon_audit_values(self, fields_or_vals):
        if isinstance(fields_or_vals, dict):
            field_names = [name for name in fields_or_vals if name in self._fields]
        else:
            field_names = [name for name in fields_or_vals if name in self._fields]
        return {name: self._cabochon_audit_value(name) for name in field_names}

    def _cabochon_audit_value(self, field_name):
        self.ensure_one()
        field = self._fields[field_name]
        if field.type == "binary":
            return "<binary>"
        value = self[field_name]
        if field.type == "many2one":
            return value.display_name if value else False
        if field.type in ("one2many", "many2many"):
            names = value[:20].mapped("display_name")
            suffix = "..." if len(value) > 20 else ""
            return ", ".join(names) + suffix
        if field.type in ("date", "datetime"):
            return fields.Datetime.to_string(value) if value else False
        return str(value) if value not in (False, None) else False

    def _cabochon_audit_format_values(self, values):
        return "\n".join(f"{name}: {value}" for name, value in sorted(values.items()))

    def _cabochon_audit_display_name(self):
        self.ensure_one()
        try:
            return self.display_name
        except Exception:
            return f"{self._name},{self.id}"
