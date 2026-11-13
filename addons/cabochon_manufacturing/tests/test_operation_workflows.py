import logging
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

_logger = logging.getLogger(__name__)
TASK_CODES = {"press", "cutting", "cnc", "cabochon_machine", "ball_machine", "drilling"}


@tagged("post_install", "-at_install")
class TestOperationWorkflows(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.operations = cls.env["cabochon.manufacturing.operation"].search([])
        cls.raw, cls.prepared, cls.semi, cls.finished = (
            cls.env.ref("cabochon_manufacturing.location_" + stage)
            for stage in ("raw", "prepared", "semi_finished", "finished")
        )
        cls.manager_user = cls._user("sweep_manager", "group_cabochon_manager")
        cls.finished_user = cls._user("sweep_finished", "group_cabochon_finished_manager")
        cls.technologist_user = cls._user("sweep_technologist", "group_cabochon_workshop_manager")
        cls.worker_user = cls._user("sweep_worker", "group_cabochon_fixer")
        cls.manager = cls.env["hr.employee"].create({"name": "Sweep manager", "user_id": cls.manager_user.id})
        cls.finished_manager = cls.env["hr.employee"].create({"name": "Sweep finished", "user_id": cls.finished_user.id})
        cls.technologist = cls.env["hr.employee"].create({"name": "Sweep technologist", "user_id": cls.technologist_user.id})
        cls.worker = cls.env["hr.employee"].create({
            "name": "Sweep worker", "user_id": cls.worker_user.id,
            "cabochon_allowed_operation_ids": [(6, 0, cls.operations.ids)],
        })
        (cls.raw | cls.prepared | cls.semi).manager_id = cls.manager
        cls.finished.manager_id = cls.finished_manager
        cls.color = cls.env["cabochon.color"].create({"name": "Sweep color"})
        cls.shape = cls.env["cabochon.shape"].create({
            "name": "Sweep shape", "use_for_press": True, "use_for_cutting": True, "use_for_machine": True,
        })
        cls.form = cls.env["cabochon.form.type"].create({"name": "Sweep form"})
        cls.size = cls.env["cabochon.size"].create({
            "name": "Sweep size", "use_for_press": True, "use_for_cutting": True,
            "use_for_machine": True, "use_for_drilling": True, "use_for_sorting": True, "use_for_tubes": True,
        })

    @classmethod
    def _user(cls, login, group):
        return cls.env["res.users"].create({
            "name": login, "login": login, "company_id": cls.env.company.id,
            "company_ids": [(6, 0, cls.env.company.ids)],
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.env.ref("cabochon_base." + group).id])],
        })

    def _operation(self, code):
        return self.env.ref("cabochon_manufacturing.operation_" + code)

    def _source(self, code="press", **values):
        if code in {"tubes", "tumble_wash", "toluene_wash"}:
            operation_ids, location = [], self.raw
        elif code in {"manual_sorting", "auto_separator"}:
            operation_ids, location = self._operation("tumble_wash").ids, self.prepared
        else:
            operation_ids, location = self._operation("manual_sorting").ids, self.prepared
        return self.env["cabochon.stone.lot"].with_context(cabochon_initial_operation_ids=operation_ids).create({
            "location_id": location.id, "initial_weight_g": 100, "current_weight_g": 100,
            "extraction_year": 2026, "extraction_month": "1", "color_id": self.color.id, **values,
        })

    def _task_values(self, operation):
        values = {"operation_id": operation.id, "stone_size_id": self.size.id}
        if operation.code != "drilling":
            values["shape_id"] = self.shape.id
        if operation.code in {"cnc", "cabochon_machine", "ball_machine"}:
            values["form_type_id"] = self.form.id
        return values

    def _request(self, codes=("press",), lot=None, **values):
        operations = self.env["cabochon.manufacturing.operation"].browse()
        for code in codes:
            operations |= self._operation(code)
        lot = lot or self._source(codes[0])
        return self.env["cabochon.production.request"].with_user(self.technologist_user).create({
            "source_lot_id": lot.id, "planned_weight_g": 100,
            "worker_id": self.worker.id, "technologist_id": self.technologist.id,
            "operation_ids": [(6, 0, operations.ids)],
            "task_line_ids": [(0, 0, self._task_values(operation)) for operation in operations if operation.code in TASK_CODES],
            "deadline": fields.Datetime.now() + timedelta(days=1),
            "receipt_destination_stage": "finished" if operations.filtered("final_operation") else "semi_finished",
            **values,
        })

    def _confirm(self, transfer):
        transfer.with_user(transfer.manager_id.user_id).action_manager_confirm()
        transfer.with_user(self.worker_user).action_worker_confirm()

    def _start(self, request):
        request.action_confirm()
        self._confirm(request.issue_id)
        return request.receipt_ids.filtered(lambda transfer: transfer.transfer_type == "receipt" and transfer.state == "draft")

    def test_every_active_operation_posts_balanced_final_receipt(self):
        codes = self.operations.mapped("code")
        self.assertEqual(len(codes), 16)
        for code in codes:
            with self.subTest(operation=code):
                request = self._request((code,))
                receipt = self._start(request)
                manager = receipt.manager_id.user_id
                receipt.with_user(manager).write({"is_final_receipt": True})
                values = {"weight_g": 85, "detected_defect_weight_g": 2, "made_defect_weight_g": 3}
                if code not in TASK_CODES:
                    values.update({"color_id": self.color.id, "stone_size_id": self.size.id})
                if code == "cutting":
                    values["return_loss_weight_g"] = 3
                if code == "toluene_wash":
                    receipt.with_user(manager).write({"toluene_consumption_l": 0.5})
                receipt.line_ids.with_user(manager).write(values)
                self._confirm(receipt)
                self.assertEqual(request.state, "done")
                self.assertEqual(request.received_weight_g, 85)
                self.assertEqual(request.defect_weight_g, 5)
                self.assertEqual(request.lost_weight_g, 10)
                self.assertFalse(request._open_issued_lots_for_receipt())
                self.assertEqual(receipt.line_ids.new_lot_id.location_id, self.finished if self._operation(code).final_operation else self.env["cabochon.material.transfer"]._get_destination_location_for_operations(self._operation(code)))
                if code == "tubes":
                    self.assertFalse(receipt.line_ids.new_lot_id.color_id)
                _logger.info("OPERATION_CYCLE_OK %s", code)

    def test_full_route_from_raw_to_finished_preserves_lineage_and_weight(self):
        source = self._source("tubes")
        original = source
        codes = ("tubes", "tumble_wash", "manual_sorting", "press", "grinding_polishing")
        for code in codes:
            request = self._request((code,), source, planned_weight_g=source.current_weight_g)
            receipt = self._start(request)
            manager = receipt.manager_id.user_id
            receipt.with_user(manager).write({"is_final_receipt": True})
            values = {"weight_g": source.current_weight_g - 1}
            if code in {"tubes", "manual_sorting"}:
                values["stone_size_id"] = self.size.id
            if code == "manual_sorting":
                values["color_id"] = self.color.id
            receipt.line_ids.with_user(manager).write(values)
            self._confirm(receipt)
            source = receipt.line_ids.new_lot_id
        self.assertEqual(source.location_id, self.finished)
        self.assertEqual(source.current_weight_g, 95)
        self.assertIn(original.id, source._lineage_lot_ids())
        self.assertTrue(set(codes).issubset(source._completed_operation_codes()))

    def test_route_rejects_missing_preparation_and_exclusive_operations(self):
        raw = self._source("tubes")
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._request(("press",), raw)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._request(("tumble_wash", "toluene_wash"), raw)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._request(("press", "stone_preparation"), self._source("press"))

    def test_combined_tasks_accept_each_operations_own_attributes(self):
        request = self._request(("press", "cnc", "drilling"))
        receipt = self._start(request)
        receipt.with_user(self.finished_user).write({"is_final_receipt": True})
        self.assertEqual(len(receipt.line_ids), 3)
        for line in receipt.line_ids:
            line.with_user(self.finished_user).write({"weight_g": 30})
        self._confirm(receipt)
        self.assertEqual(request.received_weight_g, 90)
        self.assertEqual(request.lost_weight_g, 10)
        self.assertEqual(request.state, "done")

    def test_draft_shared_source_losses_refresh_on_edit_toggle_and_delete(self):
        request = self._request(("cutting", "cnc"))
        receipt = self._start(request)
        manager = self.manager_user
        receipt.with_user(manager).write({"is_final_receipt": True})
        cutting = receipt.line_ids.filtered(lambda line: line.task_operation_id.code == "cutting")
        machine = receipt.line_ids - cutting
        cutting.with_user(manager).write({"weight_g": 40, "return_loss_weight_g": 10})
        machine.with_user(manager).write({"weight_g": 40})
        self.assertEqual(receipt.total_lost_weight_g, 10)
        self.assertEqual(sum(receipt.line_ids.mapped("lost_weight_g")), 10)
        receipt.with_user(manager).write({"is_final_receipt": False})
        self.assertEqual(receipt.total_lost_weight_g, 0)
        receipt.with_user(manager).write({"is_final_receipt": True})
        self.assertEqual(receipt.total_lost_weight_g, 10)
        machine.with_user(manager).write({"weight_g": 30})
        self.assertEqual(receipt.total_lost_weight_g, 20)
        machine.with_user(self.admin).unlink()
        self.assertEqual(receipt.total_lost_weight_g, 50)
        self.assertFalse(request.movement_ids.filtered(lambda m: m.kind == "loss"))

    def test_tubes_multiple_sources_close_both_issued_lots(self):
        first, second = self._source("tubes"), self._source("tubes")
        request = self._request(("tubes",), first, additional_source_line_ids=[(0, 0, {"lot_id": second.id, "weight_g": 100})])
        receipt = self._start(request)
        receipt.with_user(self.manager_user).write({"is_final_receipt": True})
        receipt.line_ids.with_user(self.manager_user).write({"weight_g": 90, "stone_size_id": self.size.id})
        self._confirm(receipt)
        self.assertEqual(request.issued_weight_g, 200)
        self.assertEqual(request.received_weight_g, 180)
        self.assertEqual(request.lost_weight_g, 20)
        self.assertFalse(request._open_issued_lots_for_receipt())
        self.assertEqual(set(receipt.line_ids.new_lot_id.source_lot_ids.ids), {first.id, second.id})

    def test_partial_issue_receipts_use_issued_child_not_warehouse_remainder(self):
        source = self._source("press")
        request = self._request(("press",), source, planned_weight_g=50)
        receipt = self._start(request)
        child = request.issue_id.line_ids.new_lot_id
        self.assertNotEqual(child, source)
        self.assertEqual(source.current_weight_g, 50)
        self.assertEqual(child.current_weight_g, 50)
        receipt.with_user(self.manager_user).write({"is_final_receipt": True})
        receipt.line_ids.with_user(self.manager_user).write({"weight_g": 45})
        self._confirm(receipt)
        self.assertEqual(source.current_weight_g, 50)
        self.assertEqual(child.current_weight_g, 0)
        self.assertEqual(request.lost_weight_g, 5)

    def test_multi_source_partial_issue_preserves_all_parents(self):
        first, second = self._source("tubes"), self._source("tubes")
        request = self._request(("tubes",), first, planned_weight_g=50,
                                additional_source_line_ids=[(0, 0, {"lot_id": second.id, "weight_g": 50})])
        receipt = self._start(request)
        receipt.with_user(self.manager_user).write({"is_final_receipt": True})
        receipt.line_ids.with_user(self.manager_user).write({"weight_g": 45, "stone_size_id": self.size.id})
        self._confirm(receipt)
        self.assertEqual(first.current_weight_g, 50)
        self.assertEqual(second.current_weight_g, 50)
        self.assertEqual(request.received_weight_g, 90)
        self.assertEqual(request.lost_weight_g, 10)

    def test_receipt_form_is_readable_to_stock_manager_after_issue(self):
        receipt = self._start(self._request())
        self.env.invalidate_all()
        # Reading the issued source is required for the manager's receipt form.
        source = receipt.line_ids.sudo().lot_id
        source.with_user(self.manager_user).read(["current_weight_g", "completed_operation_ids"])

    def test_defect_recovery_can_be_processed_again(self):
        request = self._request(("press",))
        receipt = self._start(request)
        receipt.with_user(self.manager_user).write({"is_final_receipt": True})
        receipt.line_ids.with_user(self.manager_user).write({"weight_g": 80, "made_defect_weight_g": 10})
        self._confirm(receipt)
        defect = request.movement_ids.filtered(lambda m: m.kind == "defect").new_lot_id
        recovery = self.env["cabochon.defect.recovery.wizard"].with_user(self.manager_user).create({
            "defect_lot_id": defect.id, "weight_g": 10, "stone_size_id": self.size.id,
            "manager_id": self.manager.id, "destination_location_id": self.semi.id,
        })
        result = recovery.action_recover()
        recovered = self.env["cabochon.stone.lot"].browse(result["res_id"])
        following = self._request(("cnc",), recovered, planned_weight_g=10)
        next_receipt = self._start(following)
        next_receipt.with_user(self.manager_user).write({"is_final_receipt": True})
        next_receipt.line_ids.with_user(self.manager_user).write({"weight_g": 9})
        self._confirm(next_receipt)
        self.assertEqual(following.state, "done")
        self.assertEqual(following.received_weight_g, 9)

    def test_return_loss_can_enter_a_new_production_request(self):
        request = self._request(("cutting",))
        receipt = self._start(request)
        receipt.with_user(self.manager_user).write({"is_final_receipt": True})
        receipt.line_ids.with_user(self.manager_user).write({"weight_g": 80, "return_loss_weight_g": 10})
        self._confirm(receipt)
        returned = request.movement_ids.filtered(lambda m: m.kind == "loss" and m.new_lot_id).new_lot_id
        self.assertEqual(returned.location_id, self.semi)
        following = self._request(("press",), returned, planned_weight_g=10)
        next_receipt = self._start(following)
        next_receipt.with_user(self.manager_user).write({"is_final_receipt": True})
        next_receipt.line_ids.with_user(self.manager_user).write({"weight_g": 9})
        self._confirm(next_receipt)
        self.assertEqual(following.state, "done")

    def test_combined_cutting_posts_offcuts_under_cutting_and_reworks_only_via_press(self):
        request = self._request(("cutting", "cnc"))
        receipt = self._start(request)
        receipt.with_user(self.manager_user).write({"is_final_receipt": True})
        cutting = receipt.line_ids.filtered(lambda line: line.task_operation_id.code == "cutting")
        machine = receipt.line_ids - cutting
        cutting.with_user(self.manager_user).write({"weight_g": 40, "return_loss_weight_g": 10})
        machine.with_user(self.manager_user).write({"weight_g": 40})
        self.assertTrue(cutting.show_return_loss_fields)
        self.assertFalse(cutting.show_form_type_fields)
        self.assertFalse(machine.show_return_loss_fields)
        self.assertTrue(machine.show_form_type_fields)
        self._confirm(receipt)
        offcuts = request.movement_ids.filtered(lambda m: m.kind == "loss" and m.new_lot_id.is_return_loss_lot)
        self.assertEqual(offcuts.operation_ids, self._operation("cutting"))
        self.assertEqual(offcuts.new_lot_id.return_loss_operation_id, self._operation("cutting"))
        self.assertEqual(offcuts.new_lot_id.current_weight_g, 10)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._request(("cnc",), offcuts.new_lot_id, planned_weight_g=10)

    def test_receipt_rejects_other_requests_task_and_noncutting_offcuts(self):
        first, other = self._request(), self._request()
        receipt = self._start(first)
        line = receipt.line_ids.with_user(self.manager_user)
        line.write({"weight_g": 90, "task_line_id": other.task_line_ids.id})
        with self.assertRaises(UserError), self.cr.savepoint():
            receipt.with_user(self.manager_user).action_manager_confirm()
        line.write({"task_line_id": first.task_line_ids.id, "return_loss_weight_g": 1})
        with self.assertRaises(UserError), self.cr.savepoint():
            receipt.with_user(self.manager_user).action_manager_confirm()
        self.assertEqual(first.state, "in_progress")

    def test_wash_form_does_not_require_sorting_attributes(self):
        receipt = self._start(self._request(("tumble_wash",)))
        self.assertTrue(receipt.line_ids.show_color_fields)
        self.assertFalse(receipt.line_ids.require_color_fields)
        self.assertFalse(receipt.line_ids.show_size_fields)

    def test_historical_manager_read_does_not_grant_write_or_unrelated_read(self):
        receipt = self._start(self._request())
        source = receipt.line_ids.sudo().lot_id
        self.env.invalidate_all()
        source.with_user(self.manager_user).read(["current_weight_g"])
        with self.assertRaises(AccessError), self.cr.savepoint():
            source.with_user(self.manager_user).write({"waybill_number": "Forbidden"})
        unrelated = self._source(location_id=self.finished.id)
        with self.assertRaises(AccessError), self.cr.savepoint():
            unrelated.with_user(self.manager_user).read(["current_weight_g"])

    def test_finished_issue_multiple_lines_is_atomic_and_keeps_estimated_quantity(self):
        lot = self._source(location_id=self.finished.id, standard_weight_g=2)
        model = self.env["cabochon.finished.issue.wizard"].with_user(self.finished_user)
        invalid = model.create({"manager_id": self.finished_manager.id, "line_ids": [
            (0, 0, {"lot_id": lot.id, "weight_g": 60}), (0, 0, {"lot_id": lot.id, "weight_g": 60}),
        ]})
        before = self.env["cabochon.manufacturing.movement"].search_count([("lot_id", "=", lot.id)])
        with self.assertRaises(UserError), self.cr.savepoint():
            invalid.action_confirm()
        self.assertEqual(lot.current_weight_g, 100)
        self.assertEqual(self.env["cabochon.manufacturing.movement"].search_count([("lot_id", "=", lot.id)]), before)
        valid = model.create({"manager_id": self.finished_manager.id, "line_ids": [
            (0, 0, {"lot_id": lot.id, "weight_g": 20}), (0, 0, {"lot_id": lot.id, "weight_g": 30}),
        ]})
        valid.action_confirm()
        self.assertEqual(lot.current_weight_g, 50)
        self.assertEqual(lot.estimated_quantity, 25)
        with self.assertRaises(UserError), self.cr.savepoint():
            valid.action_confirm()

    def test_correction_weight_preserves_history_and_rejects_overdraw(self):
        lot = self._source("tubes")
        initial = self.env["cabochon.manufacturing.movement"].search([("new_lot_id", "=", lot.id)])
        wizard = self.env["cabochon.movement.correction.wizard"].with_user(self.admin).create({
            "lot_id": lot.id, "delta_weight_g": -10, "reason": "Test weighing", "correction_of_id": initial.id,
        })
        wizard.action_apply()
        self.assertEqual(lot.current_weight_g, 90)
        self.assertEqual(initial.weight_g, 100)
        with self.assertRaises(UserError), self.cr.savepoint():
            wizard.action_apply()
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env["cabochon.movement.correction.wizard"].with_user(self.admin).create({
                "lot_id": lot.id, "delta_weight_g": -100, "reason": "Too much",
            }).action_apply()
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["cabochon.movement.correction.wizard"].with_user(self.manager_user).create({
                "lot_id": lot.id, "delta_weight_g": 1, "reason": "Not allowed",
            })

    def test_correction_moves_finished_position_and_clears_inapplicable_norm(self):
        lot = self._source("press", location_id=self.finished.id, standard_weight_g=2)
        self.env["cabochon.movement.correction.wizard"].with_user(self.admin).create({
            "lot_id": lot.id, "correction_type": "location", "destination_location_id": self.semi.id,
            "reason": "Return to processing",
        }).action_apply()
        self.assertEqual(lot.location_id, self.semi)
        self.assertEqual(lot.standard_weight_g, 0)
        self.assertEqual(lot.estimated_quantity, 0)

    def test_correction_rejects_foreign_or_empty_employee_zone(self):
        company = self.env["res.company"].create({"name": "Sweep other company"})
        foreign_employee = self.env["hr.employee"].create({"name": "Foreign worker", "company_id": company.id})
        foreign = self.env["cabochon.manufacturing.location"].create({"name": "Foreign employee", "code": "employee", "employee_id": foreign_employee.id})
        empty = self.env["cabochon.manufacturing.location"].create({"name": "Missing employee", "code": "employee"})
        lot = self._source("tubes")
        for destination in (foreign, empty):
            with self.assertRaises(UserError), self.cr.savepoint():
                self.env["cabochon.movement.correction.wizard"].with_user(self.admin).create({
                    "lot_id": lot.id, "correction_type": "location", "destination_location_id": destination.id,
                    "reason": "Invalid destination",
                }).action_apply()

    def test_notifications_follow_confirmation_and_only_assignee_can_finish(self):
        request = self._request(("tumble_wash",))
        request.action_confirm()
        issue = request.issue_id
        activity = issue.sudo().activity_ids.filtered(lambda a: a.user_id == self.manager_user)
        self.assertEqual(len(activity), 1)
        with self.assertRaises(AccessError), self.cr.savepoint():
            activity.with_user(self.worker_user).action_feedback()
        issue.with_user(self.manager_user).action_manager_confirm()
        self.assertFalse(issue.sudo().activity_ids.filtered(lambda a: a.user_id == self.manager_user))
        self.assertEqual(len(issue.sudo().activity_ids.filtered(lambda a: a.user_id == self.worker_user)), 1)
        issue.with_user(self.worker_user).action_worker_reject()
        self.assertFalse(issue.sudo().activity_ids.filtered(lambda a: a.user_id == self.worker_user))
        self.assertEqual(len(issue.sudo().activity_ids.filtered(lambda a: a.user_id == self.manager_user)), 1)

    def test_overdue_notification_is_unique_and_cleared_on_cancel(self):
        request = self._request(deadline=fields.Datetime.now() - timedelta(days=1))
        request.action_confirm()
        model = self.env["cabochon.production.request"].with_user(self.admin)
        model._cron_notify_overdue_requests()
        model._cron_notify_overdue_requests()
        activities = request.sudo().activity_ids.filtered(lambda activity: activity.summary == "Просрочена заявка на изготовление")
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities.user_id, self.technologist_user)
        request.action_cancel()
        self.assertFalse(request.sudo().activity_ids)

    def test_reference_catalogs_and_employee_operation_access(self):
        size = self.env["cabochon.size"].with_user(self.technologist_user).create({"name": "Sweep catalog", "use_for_cutting": True})
        size.write({"description": "Updated"})
        size.write({"active": False})
        with self.assertRaises(AccessError), self.cr.savepoint():
            size.with_user(self.worker_user).write({"active": True})
        access = self.env["cabochon.employee.operation.access"].with_user(self.technologist_user).browse(self.worker.id)
        access.write({"cabochon_allowed_operation_ids": [(6, 0, self._operation("press").ids)]})
        self.assertEqual(self.worker.cabochon_allowed_operation_ids, self._operation("press"))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._request(("tumble_wash",))

    def test_role_assignment_removes_other_cabochon_roles(self):
        employee = self.worker.with_user(self.admin)
        employee.cabochon_role = "admin"
        self.assertTrue(self.worker_user.has_group("cabochon_base.group_cabochon_admin"))
        employee.cabochon_role = "manager"
        self.assertTrue(self.worker_user.has_group("cabochon_base.group_cabochon_manager"))
        self.assertFalse(self.worker_user.has_group("cabochon_base.group_cabochon_admin"))
        self.assertFalse(self.worker_user.has_group("cabochon_base.group_cabochon_workshop_manager"))

    def test_label_html_renders_and_scanner_obeys_record_rules(self):
        lot = self._source("tubes")
        html, _kind = self.env["ir.actions.report"].with_user(self.manager_user)._render_qweb_html(
            "cabochon_manufacturing.action_report_cabochon_lot_label", [lot.id],
        )
        self.assertIn(lot.name.encode(), html)
        scanner = self.env["cabochon.scan.lot"].with_user(self.manager_user).create({"code": lot.barcode})
        self.assertEqual(scanner.action_open()["res_id"], lot.id)
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env["cabochon.scan.lot"].with_user(self.worker_user).create({"code": lot.barcode}).action_open()

    def test_visible_menu_views_and_report_queries_for_each_role(self):
        menu_ids = self.env["ir.model.data"].search([
            ("module", "in", ["cabochon_base", "cabochon_manufacturing"]), ("model", "=", "ir.ui.menu"),
        ]).mapped("res_id")
        for user in (self.admin, self.technologist_user, self.manager_user, self.finished_user, self.worker_user):
            menus = self.env["ir.ui.menu"].with_user(user)
            visible = menus._visible_menu_ids()
            actions = menus.browse([menu_id for menu_id in menu_ids if menu_id in visible]).mapped("action")
            count = 0
            for action in actions:
                if not action or action.type != "ir.actions.act_window":
                    continue
                with self.subTest(role=user.login, action=action.name):
                    model = self.env[action.res_model].with_user(user)
                    views = [(False, kind) for kind in action.view_mode.split(",")]
                    model.get_views(views, {"toolbar": True})
                    model.search_read([], ["display_name"], limit=3)
                    if not model._auto:
                        measure = next((name for name, field in model._fields.items()
                                        if field.type in {"float", "monetary"} and field.store), None)
                        if measure:
                            model._read_group([], aggregates=[measure + ":sum"])
                    count += 1
            self.assertGreater(count, 0)
            _logger.info("ROLE_MENU_VIEWS_OK %s %s", user.login, count)
