from datetime import timedelta

from odoo import fields
from odoo.addons.cabochon_base.internal import INTERNAL
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged("post_install", "-at_install")
class TestContractorAndToluene(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.raw, cls.prepared, cls.semi, cls.finished = (
            cls.env.ref("cabochon_manufacturing.location_" + name)
            for name in ("raw", "prepared", "semi_finished", "finished")
        )
        cls.wash = cls.env.ref("cabochon_manufacturing.operation_toluene_wash")
        cls.tumble = cls.env.ref("cabochon_manufacturing.operation_tumble_wash")
        cls.press = cls.env.ref("cabochon_manufacturing.operation_press")
        cls.grinding = cls.env.ref("cabochon_manufacturing.operation_grinding_polishing")
        cls.manager_user = cls._user("contractor_manager", "group_cabochon_manager")
        cls.worker_user = cls._user("toluene_worker", "group_cabochon_fixer")
        cls.other_manager_user = cls._user("contractor_other_manager", "group_cabochon_manager")
        cls.manager = cls.env["hr.employee"].create({"name": "Contractor manager", "user_id": cls.manager_user.id})
        cls.worker = cls.env["hr.employee"].create({
            "name": "Toluene worker", "user_id": cls.worker_user.id,
            "cabochon_allowed_operation_ids": [(6, 0, (cls.wash | cls.tumble).ids)],
        })
        (cls.raw | cls.prepared | cls.semi | cls.finished).manager_id = cls.manager
        cls.contractor = cls.env["res.partner"].create({"name": "Test contractor", "is_cabochon_contractor": True})
        cls.color = cls.env["cabochon.color"].create({"name": "Contractor color"})
        cls.size = cls.env["cabochon.size"].create({"name": "Contractor size", "use_for_press": True})
        cls.shape = cls.env["cabochon.shape"].create({"name": "Contractor shape", "use_for_press": True})
        cls.form_type = cls.env["cabochon.form.type"].create({"name": "Contractor type"})

    @classmethod
    def _user(cls, login, group):
        return cls.env["res.users"].create({
            "name": login, "login": login, "company_id": cls.env.company.id,
            "company_ids": [(6, 0, cls.env.company.ids)],
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.env.ref("cabochon_base." + group).id])],
        })

    def _lot(self, **values):
        return self.env["cabochon.stone.lot"].create({
            "location_id": self.raw.id, "initial_weight_g": 100, "current_weight_g": 100, **values,
        })

    def _issue(self, lot, weight=40, **values):
        return self.env["cabochon.contractor.issue.wizard"].with_user(self.manager_user).create({
            "contractor_id": self.contractor.id, "lot_id": lot.id, "weight_g": weight, **values,
        })

    def _request(self):
        request = self.env["cabochon.production.request"].create({
            "source_lot_id": self._lot().id, "planned_weight_g": 100,
            "worker_id": self.worker.id, "technologist_id": self.manager.id,
            "operation_ids": [(6, 0, self.wash.ids)], "deadline": fields.Datetime.now() + timedelta(days=1),
        })
        request.with_user(self.admin).action_confirm()
        request.issue_id.with_user(self.manager_user).action_manager_confirm()
        request.issue_id.with_user(self.worker_user).action_worker_confirm()
        return request

    def test_raw_issue_is_single_step_and_cannot_repeat(self):
        lot = self._lot()
        issue = self._issue(lot)
        issue.action_issue()
        self.assertEqual(lot.current_weight_g, 60)
        with self.assertRaises(UserError), self.cr.savepoint():
            issue.action_issue()
        self._issue(lot, 60).action_issue()
        self.assertEqual(lot.current_weight_g, 0)
        self.assertEqual(lot.state, "written_off")
        rows = self.env["cabochon.contractor.report"].with_user(self.manager_user).search([("contractor_id", "=", self.contractor.id)])
        self.assertEqual(sum(rows.mapped("issued_weight_g")), 100)
        self.assertEqual(sum(rows.mapped("received_weight_g")), 0)
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows.mapped("movement_id.request_id"))
        self.assertEqual(rows.mapped("movement_id.performed_by_id"), self.manager_user)

    def test_issue_rejects_processed_nonraw_defect_and_reserved_lots(self):
        for values in ({"location_id": self.prepared.id}, {"is_defect_lot": True}, {"is_return_loss_lot": True}):
            lot = self._lot(**values)
            with self.assertRaises(UserError), self.cr.savepoint():
                self._issue(lot).action_issue()
            self.assertEqual(lot.current_weight_g, 100)
        processed = self.env["cabochon.stone.lot"].with_context(cabochon_initial_operation_ids=self.tumble.ids).create({
            "location_id": self.raw.id, "initial_weight_g": 100, "current_weight_g": 100,
        })
        child = self._lot(parent_id=processed.id)
        for lot in (processed, child):
            with self.assertRaises(UserError), self.cr.savepoint():
                self._issue(lot).action_issue()
        reserved = self._lot()
        self.env["cabochon.production.request"].create({
            "source_lot_id": reserved.id, "planned_weight_g": 100,
            "worker_id": self.worker.id, "technologist_id": self.manager.id,
            "operation_ids": [(6, 0, self.tumble.ids)], "deadline": fields.Datetime.now(),
        })
        with self.assertRaises(UserError), self.cr.savepoint():
            self._issue(reserved).action_issue()

    def test_issue_rejects_invalid_weights_roles_and_foreign_partner(self):
        lot = self._lot()
        for weight in (0, -1, 101, float("nan")):
            with self.assertRaises(UserError), self.cr.savepoint():
                self._issue(lot, weight).action_issue()
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["cabochon.contractor.issue.wizard"].with_user(self.worker_user).create({
                "contractor_id": self.contractor.id, "lot_id": lot.id, "weight_g": 10,
            })
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["cabochon.contractor.issue.wizard"].with_user(self.other_manager_user).create({
                "contractor_id": self.contractor.id, "lot_id": lot.id, "weight_g": 10,
            }).action_issue()
        foreign = self.env["res.company"].create({"name": "Contractor foreign company"})
        partner = self.env["res.partner"].create({"name": "Foreign contractor", "company_id": foreign.id, "is_cabochon_contractor": True})
        with self.assertRaises(UserError), self.cr.savepoint():
            self._issue(lot, contractor_id=partner.id).action_issue()
        self.assertEqual(lot.current_weight_g, 100)
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env["cabochon.manufacturing.movement"].with_user(self.admin).with_context(cabochon_contractor_movement=True).create({
                "kind": "issue", "contractor_id": self.contractor.id, "lot_id": lot.id, "weight_g": 10,
            })

    def test_contractor_returns_any_stage_and_finished_merges_without_losing_partner(self):
        specifications = [
            (self.raw, {}), (self.prepared, {"source_operation_id": self.tumble.id}),
            (self.semi, {"source_operation_id": self.press.id, "stone_size_id": self.size.id, "shape_id": self.shape.id}),
            (self.finished, {"source_operation_id": self.grinding.id, "color_id": self.color.id,
                             "stone_size_id": self.size.id, "shape_id": self.shape.id, "form_type_id": self.form_type.id}),
        ]
        finished_id = False
        for location, values in specifications:
            wizard = self.env["cabochon.external.receipt.wizard"].with_user(self.manager_user).create({
                "receipt_source": "contractor", "contractor_id": self.contractor.id,
                "location_id": location.id, "initial_weight_g": 20, **values,
            })
            result = wizard.action_create_receipt()
            with self.assertRaises(UserError), self.cr.savepoint():
                wizard.action_create_receipt()
            if location == self.finished:
                finished_id = result["res_id"]
        other = self.env["res.partner"].create({"name": "Second contractor", "is_cabochon_contractor": True})
        extra = self.env["cabochon.external.receipt.wizard"].with_user(self.manager_user).create({
            "receipt_source": "contractor", "contractor_id": other.id,
            "location_id": self.finished.id, "initial_weight_g": 10, **specifications[-1][1],
        })
        self.assertEqual(extra.action_create_receipt()["res_id"], finished_id)
        self.assertEqual(self.env["cabochon.stone.lot"].browse(finished_id).current_weight_g, 30)
        report = self.env["cabochon.contractor.report"]
        self.assertEqual(sum(report.search([("contractor_id", "=", self.contractor.id)]).mapped("received_weight_g")), 80)
        self.assertEqual(sum(report.search([("contractor_id", "=", other.id)]).mapped("received_weight_g")), 10)
        self.assertEqual(report.search_count([("contractor_id", "in", (self.contractor | other).ids)]), 5)
        finished_row = report.search([("contractor_id", "=", other.id)])
        self.assertEqual(finished_row.location_id, self.finished)
        self.assertIn(self.shape.name, finished_row.material_description)
        self.assertIn(self.size.name, finished_row.material_description)

    def test_contractor_receipt_requires_partner_and_respects_stock_role(self):
        values = {"receipt_source": "contractor", "location_id": self.raw.id, "initial_weight_g": 10}
        wizard = self.env["cabochon.external.receipt.wizard"].with_user(self.manager_user).create(values)
        with self.assertRaises(UserError), self.cr.savepoint():
            wizard.action_create_receipt()
        wizard.contractor_id = self.contractor
        wizard.action_create_receipt()
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env["cabochon.external.receipt.wizard"].with_user(self.other_manager_user).create({
                **values, "contractor_id": self.contractor.id,
            }).action_create_receipt()

    def test_contractor_report_respects_company_and_worker_access(self):
        self._issue(self._lot()).action_issue()
        foreign = self.env["res.company"].create({"name": "Contractor report foreign"})
        foreign_lot = self._lot(company_id=foreign.id)
        self.env["cabochon.manufacturing.movement"].with_company(foreign).with_context(cabochon_contractor_movement=INTERNAL).create({
            "kind": "issue", "contractor_id": self.contractor.id, "lot_id": foreign_lot.id,
            "company_id": foreign.id, "source_location_id": self.raw.id, "weight_g": 10,
        })
        rows = self.env["cabochon.contractor.report"].with_user(self.manager_user).search([("contractor_id", "=", self.contractor.id)])
        self.assertEqual(len(rows), 1)
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["cabochon.contractor.report"].with_user(self.worker_user).search([])

    def test_toluene_is_counted_on_every_confirmed_receipt_once(self):
        request = self._request()
        first = request.receipt_ids.filtered(lambda transfer: transfer.transfer_type == "receipt")
        first.with_user(self.manager_user).write({"toluene_consumption_l": 2.5})
        first.line_ids.with_user(self.manager_user).write({"weight_g": 40})
        self.assertEqual(request.toluene_consumption_l, 0)
        first.with_user(self.manager_user).action_manager_confirm()
        self.assertEqual(request.toluene_consumption_l, 0)
        first.with_user(self.worker_user).action_worker_reject()
        self.assertFalse(first.toluene_consumption_recorded)
        first.with_user(self.manager_user).action_manager_confirm()
        first.with_user(self.worker_user).action_worker_confirm()
        self.assertEqual(request.toluene_consumption_l, 2.5)
        first.with_user(self.worker_user).action_worker_confirm()
        self.assertEqual(request.toluene_consumption_l, 2.5)
        second = request.receipt_ids.filtered(lambda transfer: transfer.transfer_type == "receipt" and transfer.state == "draft")
        second.with_user(self.manager_user).write({"is_final_receipt": True, "toluene_consumption_l": 1.25})
        second.line_ids.with_user(self.manager_user).write({"weight_g": 55})
        second.with_user(self.manager_user).action_manager_confirm()
        second.with_user(self.worker_user).action_worker_confirm()
        self.assertEqual(request.toluene_consumption_l, 3.75)
        self.assertEqual(request.state, "done")
        self.assertEqual(len(request.receipt_ids.filtered("toluene_consumption_recorded")), 2)
        with self.assertRaises(UserError), self.cr.savepoint():
            first.with_user(self.manager_user).write({"toluene_consumption_l": 999})

    def test_toluene_rejects_invalid_input_and_spoofed_confirmation(self):
        request = self._request()
        receipt = request.receipt_ids.filtered(lambda transfer: transfer.transfer_type == "receipt")
        for amount in (-0.1, float("nan")):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                receipt.with_user(self.manager_user).write({"toluene_consumption_l": amount})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["cabochon.material.transfer"].create({
                "transfer_type": "issue", "operation_ids": [(6, 0, self.wash.ids)], "toluene_consumption_l": 1,
            })
        with self.assertRaises(UserError), self.cr.savepoint():
            receipt.with_user(self.manager_user).write({"toluene_consumption_recorded": True})
        with self.assertRaises(UserError), self.cr.savepoint():
            receipt.with_user(self.manager_user).write({"is_toluene_wash": False})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["cabochon.material.transfer"].create({
                "transfer_type": "receipt", "operation_ids": [(6, 0, self.tumble.ids)], "toluene_consumption_l": 1,
            })

    def test_legacy_toluene_receipt_is_not_treated_as_recorded_zero(self):
        legacy = self.env["cabochon.material.transfer"].with_context(cabochon_transfer_internal_update=INTERNAL).create({
            "transfer_type": "receipt", "state": "confirmed", "worker_id": self.worker.id,
            "manager_id": self.manager.id, "operation_ids": [(6, 0, self.wash.ids)],
        })
        self.assertTrue(legacy.is_toluene_wash)
        self.assertFalse(legacy.toluene_consumption_recorded)
        action = self.env.ref("cabochon_manufacturing.action_toluene_consumption")
        self.assertFalse(self.env["cabochon.material.transfer"].search(safe_eval(action.domain) + [("id", "=", legacy.id)]))
