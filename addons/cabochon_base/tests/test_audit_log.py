from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCabochonAuditLog(TransactionCase):
    def test_logs_reference_change(self):
        color = self.env["cabochon.color"].create({"name": "Audit color"})

        color.write({"description": "Updated"})

        log = self.env["cabochon.audit.log"].search(
            [
                ("action", "=", "write"),
                ("model_name", "=", "cabochon.color"),
                ("record_id", "=", color.id),
                ("changed_fields", "ilike", "description"),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn("description: False", log.old_values)
        self.assertIn("description: Updated", log.new_values)
