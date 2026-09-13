from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestInventoryIntegrity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.company = cls.env.company
        cls.raw = cls.env.ref("cabochon_manufacturing.location_raw")
        cls.prepared = cls.env.ref("cabochon_manufacturing.location_prepared")
        cls.finished = cls.env.ref("cabochon_manufacturing.location_finished")
        cls.semi = cls.env.ref("cabochon_manufacturing.location_semi_finished")
        cls.wash = cls.env.ref("cabochon_manufacturing.operation_tumble_wash")
        cls.press = cls.env.ref("cabochon_manufacturing.operation_press")
        cls.grinding = cls.env.ref("cabochon_manufacturing.operation_grinding_polishing")
        cls.worker_user = cls._make_user("integrity_worker", "group_cabochon_fixer")
        cls.manager_user = cls._make_user("integrity_manager", "group_cabochon_manager")
        cls.finished_user = cls._make_user("integrity_finished", "group_cabochon_finished_manager")
        cls.worker = cls.env["hr.employee"].create({"name": "Test worker", "user_id": cls.worker_user.id, "cabochon_allowed_operation_ids": [(6, 0, (cls.wash | cls.press | cls.grinding).ids)]})
        cls.manager = cls.env["hr.employee"].create({"name": "Test manager", "user_id": cls.manager_user.id})
        cls.finished_manager = cls.env["hr.employee"].create({"name": "Test finished", "user_id": cls.finished_user.id})
        (cls.raw | cls.prepared | cls.semi).write({"manager_id": cls.manager.id})
        cls.finished.manager_id = cls.finished_manager
        cls.size = cls.env["cabochon.size"].create({"name": "Integrity size", "use_for_press": True})

    @classmethod
    def _make_user(cls, login, group):
        return cls.env["res.users"].create({
            "name": login, "login": login, "company_id": cls.company.id,
            "company_ids": [(6, 0, cls.company.ids)],
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.env.ref("cabochon_base." + group).id])],
        })

    def _lot(self, **values):
        return self.env["cabochon.stone.lot"].create({
            "location_id": self.raw.id, "initial_weight_g": 100, "current_weight_g": 100,
            **values,
        })

    def _request(self, lot=None):
        lot = lot or self._lot()
        return self.env["cabochon.production.request"].create({
            "source_lot_id": lot.id, "planned_weight_g": 100,
            "worker_id": self.worker.id, "technologist_id": self.manager.id,
            "operation_ids": [(6, 0, self.wash.ids)],
            "deadline": fields.Datetime.now() + timedelta(days=1),
        })

    def test_worker_can_reject_without_document_write_permission(self):
        request = self._request()
        request.with_user(self.admin).action_confirm()
        issue = request.issue_id
        with self.assertRaises(AccessError), self.cr.savepoint():
            issue.with_user(self.worker_user).write({"weight_before_g": 200})
        issue.with_user(self.manager_user).action_manager_confirm()
        issue.with_user(self.worker_user).action_worker_reject()
        self.assertEqual(issue.state, "draft")
        self.assertFalse(issue.manager_confirmed_at)
        self.assertFalse(request.movement_ids)
        issue.with_user(self.manager_user).action_manager_confirm()
        issue.with_user(self.worker_user).action_worker_confirm()
        self.assertEqual(issue.state, "confirmed")
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_user(self.admin).action_close()

    def test_client_cannot_change_confirmations_or_lines(self):
        request = self._request()
        request.with_user(self.admin).action_confirm()
        issue = request.issue_id.with_user(self.manager_user)
        with self.assertRaises(UserError), self.cr.savepoint():
            issue.with_context(cabochon_transfer_internal_update=True).write({"state": "confirmed"})
        issue.action_manager_confirm()
        with self.assertRaises(UserError), self.cr.savepoint():
            issue.line_ids.with_context(cabochon_transfer_internal_update=True).write({"weight_g": 50})
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_context(cabochon_request_internal_update=True).write({"state": "done"})
        with self.assertRaises(UserError), self.cr.savepoint():
            request.source_lot_id.with_context(cabochon_inventory_movement=True).write({"current_weight_g": 999})
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env["cabochon.material.transfer"].with_context(default_state="confirmed").create({"manager_id": self.manager.id})

    def test_draft_deletion_releases_reservation(self):
        request = self._request()
        lot = request.source_lot_id
        request.unlink()
        self.assertFalse(lot.reserved_request_id)

    def test_scan_and_company_rules_do_not_expose_other_company(self):
        foreign_company = self.env["res.company"].create({"name": "Integrity other company"})
        lot = self._lot(company_id=foreign_company.id, location_id=self.finished.id)
        self.assertFalse(self.env["cabochon.stone.lot"].with_user(self.finished_user).search([("id", "=", lot.id)]))
        scanner = self.env["cabochon.scan.lot"].with_user(self.finished_user).create({"code": lot.barcode})
        with self.assertRaises(UserError), self.cr.savepoint():
            scanner.action_open()
        own = self._lot(location_id=self.finished.id)
        scanner.code = own.barcode
        self.assertEqual(scanner.action_open()["res_id"], own.id)

    def test_employee_access_write_checks_acl(self):
        access = self.env["cabochon.employee.operation.access"].with_user(self.worker_user).browse(self.worker.id)
        with self.assertRaises(AccessError), self.cr.savepoint():
            access.write({"cabochon_allowed_operation_ids": [(6, 0, self.press.ids)]})

    def test_audit_cannot_be_suppressed_or_attributed_to_other_user(self):
        lot = self._lot(location_id=self.finished.id)
        lot.with_user(self.finished_user).with_context(skip_cabochon_audit=True, cabochon_audit_user_id=self.admin.id).write({"standard_weight_g": 2})
        log = self.env["cabochon.audit.log"].search([("model_name", "=", lot._name), ("record_id", "=", lot.id), ("action", "=", "write")], order="id desc", limit=1)
        self.assertEqual(log.user_id, self.finished_user)

    def test_finished_issue_once_and_actual_user(self):
        lot = self._lot(location_id=self.finished.id)
        wizard = self.env["cabochon.finished.issue.wizard"].with_user(self.finished_user).create({
            "manager_id": self.finished_manager.id,
            "line_ids": [(0, 0, {"lot_id": lot.id, "weight_g": 20})],
        })
        wizard.action_confirm()
        self.assertEqual(lot.current_weight_g, 80)
        with self.assertRaises(UserError), self.cr.savepoint():
            wizard.action_confirm()
        self.assertEqual(lot.current_weight_g, 80)
        movement = self.env["cabochon.manufacturing.movement"].search([("lot_id", "=", lot.id), ("kind", "=", "issue")])
        self.assertEqual(movement.performed_by_id, self.finished_user)

    def test_norm_snapshot_does_not_change_with_catalog(self):
        self.wash.expected_loss_percent = 5
        lot = self._lot()
        movement = self.env["cabochon.manufacturing.movement"].create({
            "kind": "loss", "lot_id": lot.id, "weight_g": 10, "source_weight_before_g": 100,
            "operation_ids": [(6, 0, self.wash.ids)],
        })
        self.assertAlmostEqual(movement.loss_norm_percent, 5)
        self.wash.expected_loss_percent = 20
        self.assertAlmostEqual(movement.loss_norm_percent, 5)

    def test_partial_then_final_receipt_preserves_balance(self):
        lot = self.env["cabochon.stone.lot"].with_context(cabochon_initial_operation_ids=self.press.ids).create({
            "location_id": self.semi.id, "initial_weight_g": 100, "current_weight_g": 100,
        })
        request = self.env["cabochon.production.request"].create({
            "source_lot_id": lot.id, "planned_weight_g": 100, "worker_id": self.worker.id,
            "technologist_id": self.manager.id, "operation_ids": [(6, 0, self.grinding.ids)],
            "deadline": fields.Datetime.now() + timedelta(days=1),
        })
        request.with_user(self.admin).action_confirm()
        request.issue_id.with_user(self.manager_user).action_manager_confirm()
        request.issue_id.with_user(self.worker_user).action_worker_confirm()
        receipt = request.receipt_ids.filtered(lambda item: item.transfer_type == "receipt")
        receipt.line_ids.with_user(self.manager_user).write({"weight_g": 30})
        receipt.with_user(self.manager_user).action_manager_confirm()
        receipt.with_user(self.worker_user).action_worker_confirm()
        self.assertEqual(request.state, "partially_done")
        self.assertEqual(lot.current_weight_g, 70)
        final = request.receipt_ids.filtered(lambda item: item.transfer_type == "receipt" and item.state == "draft")
        final.with_user(self.manager_user).write({"is_final_receipt": True})
        final.line_ids.with_user(self.manager_user).write({"weight_g": 60})
        final.with_user(self.manager_user).action_manager_confirm()
        final.with_user(self.worker_user).action_worker_confirm()
        self.assertEqual(request.state, "done")
        self.assertEqual(lot.current_weight_g, 0)
        self.assertEqual(request.received_weight_g, 90)
        self.assertEqual(request.lost_weight_g, 10)
        self.assertEqual(len(request.movement_ids.filtered(lambda item: item.kind == "receipt")), 2)

    def test_defect_can_accumulate_after_full_recovery(self):
        transfer = self.env["cabochon.material.transfer"].create({"transfer_type": "receipt", "worker_id": self.worker.id, "manager_id": self.manager.id, "operation_ids": [(6, 0, self.press.ids)]})
        line = self.env["cabochon.material.transfer.line"].create({"transfer_id": transfer.id})
        defect = line._add_to_defect_lot(self.semi, 10)
        wizard = self.env["cabochon.defect.recovery.wizard"].with_user(self.admin).create({"defect_lot_id": defect.id, "weight_g": 10, "stone_size_id": self.size.id, "manager_id": self.manager.id, "destination_location_id": self.semi.id})
        wizard.action_recover()
        next_defect = line._add_to_defect_lot(self.semi, 5)
        self.assertNotEqual(next_defect.barcode, defect.barcode)
        self.assertEqual(next_defect.current_weight_g, 5)

    def test_reservation_is_shared_by_primary_and_additional_sources(self):
        request = self._request()
        other = self._request()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["cabochon.production.request.source.line"].create({"request_id": other.id, "lot_id": request.source_lot_id.id, "weight_g": 10})
        request.with_user(self.admin).action_cancel()
        self.assertFalse(request.source_lot_id.reserved_request_id)

    def test_quality_uses_request_issue_basis_for_task_defect(self):
        request = self._request()
        model = self.env["cabochon.manufacturing.movement"]
        common = {"request_id": request.id, "worker_id": self.worker.id, "lot_id": request.source_lot_id.id}
        model.create({**common, "kind": "issue", "weight_g": 100, "operation_ids": [(6, 0, (self.press | self.grinding).ids)]})
        model.create({**common, "kind": "defect", "weight_g": 10, "operation_ids": [(6, 0, self.press.ids)]})
        self.env.flush_all()
        row = self.env["cabochon.worker.operation.quality.report"].search([("request_id", "=", request.id), ("defect_weight_g", ">", 0)])
        self.assertAlmostEqual(row.defect_percent, 10)
