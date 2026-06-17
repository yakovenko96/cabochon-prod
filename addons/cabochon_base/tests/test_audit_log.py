from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCabochonAuditLog(TransactionCase):
    def test_logs_write_when_product_leaves_cabochon_scope(self):
        product = self.env["product.template"].create(
            {
                "name": "Audit scope stone",
                "default_code": "AUDIT-SCOPE-STONE",
                "is_cabochon_stone": True,
                "cabochon_standard_weight_g": 1.0,
                "cabochon_weight_tolerance_percent": 5.0,
            }
        )

        product.write({"is_cabochon_stone": False})

        log = self.env["cabochon.audit.log"].search(
            [
                ("action", "=", "write"),
                ("model_name", "=", "product.template"),
                ("record_id", "=", product.id),
                ("changed_fields", "ilike", "is_cabochon_stone"),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn("is_cabochon_stone: True", log.old_values)
        self.assertIn("is_cabochon_stone: False", log.new_values)
