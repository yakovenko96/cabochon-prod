from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCabochonManufacturingFlow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager_user = cls._create_user("cabochon_test_manager", "cabochon_base.group_cabochon_manager")
        cls.worker_user = cls._create_user("cabochon_test_worker", "cabochon_base.group_cabochon_fixer")
        cls.technologist_user = cls._create_user(
            "cabochon_test_technologist",
            "cabochon_base.group_cabochon_workshop_manager",
        )
        cls.admin_user = cls._create_user("cabochon_test_admin", "cabochon_base.group_cabochon_admin")
        employee_model = cls.env["hr.employee"].sudo()
        cls.manager = employee_model.create({"name": "Test manager", "user_id": cls.manager_user.id})
        cls.worker = employee_model.create({"name": "Test worker", "user_id": cls.worker_user.id})
        cls.technologist = employee_model.create(
            {"name": "Test technologist", "user_id": cls.technologist_user.id}
        )
        cls.raw_location = cls.env.ref("cabochon_manufacturing.location_raw").sudo()
        cls.prepared_location = cls.env.ref("cabochon_manufacturing.location_prepared").sudo()
        cls.semi_finished_location = cls.env.ref("cabochon_manufacturing.location_semi_finished").sudo()
        cls.finished_location = cls.env.ref("cabochon_manufacturing.location_finished").sudo()
        cls.loss_location = cls.env.ref("cabochon_manufacturing.location_loss").sudo()
        (
            cls.raw_location
            | cls.prepared_location
            | cls.semi_finished_location
            | cls.finished_location
            | cls.loss_location
        ).manager_id = cls.manager
        cls.wash_operation = cls.env.ref("cabochon_manufacturing.operation_tumble_wash").sudo()
        cls.final_operation = cls.env.ref("cabochon_manufacturing.operation_grinding_polishing").sudo()
        cls.sort_operation = cls.env.ref("cabochon_manufacturing.operation_manual_sorting").sudo()
        cls.press_operation = cls.env.ref("cabochon_manufacturing.operation_press").sudo()
        cls.worker.cabochon_allowed_operation_ids = cls.wash_operation

    @classmethod
    def _create_user(cls, login, group_xmlid):
        user = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": login,
                "login": login,
                "email": f"{login}@example.com",
                "group_ids": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )
        cls.env.ref(group_xmlid).write({"user_ids": [Command.link(user.id)]})
        return user

    def _create_lot(self, weight=100.0):
        return self.env["cabochon.stone.lot"].sudo().create(
            {
                "location_id": self.raw_location.id,
                "accepted_by_id": self.manager.id,
                "initial_weight_g": weight,
                "current_weight_g": weight,
            }
        )

    def _create_request(self, lot, weight=10.0):
        return self.env["cabochon.production.request"].with_user(self.technologist_user).create(
            {
                "technologist_id": self.technologist.id,
                "worker_id": self.worker.id,
                "operation_ids": [Command.set(self.wash_operation.ids)],
                "source_lot_id": lot.id,
                "planned_weight_g": weight,
                "deadline": fields.Datetime.now() + timedelta(days=1),
            }
        )

    def test_source_lot_can_only_be_used_once(self):
        lot = self._create_lot()
        self._create_request(lot)

        with self.assertRaises(ValidationError):
            self._create_request(lot)

    def test_extraction_year_uses_single_visible_value(self):
        extraction_year = self.env["cabochon.extraction.year"].sudo().create({"year": 2028})
        self.assertEqual(extraction_year.name, "2028")

        extraction_year.write({"year": 2029})
        self.assertEqual(extraction_year.name, "2029")

    def test_fraction_has_no_sequence_and_months_have_names(self):
        self.assertNotIn("sequence", self.env["cabochon.fraction"]._fields)
        month_labels = dict(
            self.env["cabochon.stone.lot"]._fields["extraction_month"]._description_selection(
                self.env
            )
        )
        self.assertEqual(month_labels["1"], "Январь")
        self.assertEqual(month_labels["12"], "Декабрь")

    def test_warehouse_manager_can_open_cabochon_work_views(self):
        self.assertNotIn("stock_location_id", self.env["cabochon.manufacturing.location"]._fields)
        lot = self._create_lot()
        request = self._create_request(lot)
        manager_requests = self.env["cabochon.production.request"].with_user(self.manager_user).search_read(
            [("id", "=", request.id)],
            ["name", "source_lot_id", "worker_id", "operation_ids"],
        )

        self.assertEqual(manager_requests[0]["id"], request.id)
        self.assertEqual(
            self.env["cabochon.stone.lot"].with_user(self.manager_user).search_count([("id", "=", lot.id)]),
            1,
        )
        action_model = self.env["ir.actions.actions"].with_user(self.manager_user)
        request_action = action_model._for_xml_id("cabochon_manufacturing.action_cabochon_request")
        transfer_action = action_model._for_xml_id("cabochon_manufacturing.action_cabochon_managed_transfer")
        self.assertEqual(request_action["res_model"], "cabochon.production.request")
        self.assertEqual(transfer_action["res_model"], "cabochon.material.transfer")

    def test_double_confirmation_freezes_lines_and_issues_lot(self):
        lot = self._create_lot()
        request = self._create_request(lot)
        request.with_user(self.technologist_user).action_confirm()
        issue = request.issue_id

        issue.with_user(self.manager_user).action_manager_confirm()
        self.assertEqual(issue.state, "manager_confirmed")
        self.assertEqual(issue.manager_confirmed_by_id, self.manager_user)
        with self.assertRaises(UserError):
            issue.line_ids.with_user(self.manager_user).write({"weight_g": 9.0})

        issue.with_user(self.worker_user).action_worker_confirm()
        self.assertEqual(issue.state, "confirmed")
        self.assertEqual(issue.worker_confirmed_by_id, self.worker_user)
        self.assertEqual(request.state, "in_progress")
        self.assertEqual(lot.state, "issued")
        self.assertEqual(lot.current_weight_g, 10.0)

    def test_admin_can_confirm_both_sides_and_is_recorded(self):
        request = self._create_request(self._create_lot())
        request.with_user(self.technologist_user).action_confirm()

        request.issue_id.with_user(self.admin_user).action_manager_confirm()
        request.issue_id.with_user(self.admin_user).action_worker_confirm()

        self.assertEqual(request.issue_id.manager_confirmed_by_id, self.admin_user)
        self.assertEqual(request.issue_id.worker_confirmed_by_id, self.admin_user)

    def test_press_request_accepts_multiple_source_lots_and_tracks_mixed_origin(self):
        lots = self._create_lot() | self._create_lot()
        for lot in lots:
            self.env["cabochon.manufacturing.movement"].sudo().create(
                {
                    "kind": "receipt",
                    "new_lot_id": lot.id,
                    "operation_ids": [Command.set((self.wash_operation | self.sort_operation).ids)],
                    "destination_location_id": self.raw_location.id,
                    "weight_g": lot.current_weight_g,
                }
            )
        self.worker.with_user(self.admin_user).write(
            {"cabochon_allowed_operation_ids": [Command.set(self.press_operation.ids)]}
        )
        request = self.env["cabochon.production.request"].with_user(self.technologist_user).create(
            {
                "technologist_id": self.technologist.id,
                "worker_id": self.worker.id,
                "operation_ids": [Command.set(self.press_operation.ids)],
                "source_lot_id": lots[0].id,
                "planned_weight_g": 10.0,
                "additional_source_line_ids": [
                    Command.create({"lot_id": lots[1].id, "weight_g": 15.0})
                ],
                "deadline": fields.Datetime.now() + timedelta(days=1),
            }
        )
        request.with_user(self.technologist_user).action_confirm()
        self.assertEqual(len(request.issue_id.line_ids), 2)

        request.issue_id.with_user(self.admin_user).action_manager_confirm()
        request.issue_id.with_user(self.admin_user).action_worker_confirm()
        receipt = request.receipt_ids.filtered(lambda item: item.transfer_type == "receipt")[:1]
        shape = self.env["cabochon.shape"].sudo().create({"name": "Тестовая форма"})
        size = self.env["cabochon.size"].sudo().create({"name": "Тестовый размер"})
        for line in receipt.line_ids:
            line.with_user(self.admin_user).write(
                {"weight_g": line.weight_before_g, "shape_id": shape.id, "stone_size_id": size.id}
            )
        receipt.with_user(self.admin_user).action_manager_confirm()
        receipt.with_user(self.admin_user).action_worker_confirm()

        mixed_sources = request.issue_id.line_ids.mapped("new_lot_id")
        for result_lot in receipt.line_ids.mapped("new_lot_id"):
            self.assertEqual(result_lot.source_lot_ids, mixed_sources)

    def test_defect_weight_accumulates_in_one_location_lot(self):
        transfer = self.env["cabochon.material.transfer"].sudo().create(
            {
                "transfer_type": "receipt",
                "worker_id": self.worker.id,
                "manager_id": self.manager.id,
            }
        )
        line = self.env["cabochon.material.transfer.line"].sudo().create({"transfer_id": transfer.id})
        before = self.env["cabochon.stone.lot"].sudo().search(
            [
                ("location_id", "=", self.raw_location.id),
                ("company_id", "=", transfer.company_id.id),
                ("is_defect_lot", "=", True),
                ("state", "=", "available"),
            ],
            limit=1,
        )
        before_weight = before.current_weight_g

        first = line._add_to_defect_lot(self.raw_location, 1.25)
        second = line._add_to_defect_lot(self.raw_location, 0.75)

        self.assertEqual(first, second)
        self.assertEqual(second.name, "БРАК-С")
        self.assertAlmostEqual(second.current_weight_g, before_weight + 2.0, places=4)
        self.assertEqual(
            self.env["cabochon.stone.lot"].sudo().search_count(
                [
                    ("location_id", "=", self.raw_location.id),
                    ("company_id", "=", transfer.company_id.id),
                    ("is_defect_lot", "=", True),
                    ("state", "=", "available"),
                ]
            ),
            1,
        )

    def test_inventory_difference_lot_stays_on_warehouse(self):
        lot = self._create_lot(weight=1500.0)
        request = self._create_request(lot, weight=1500.0)
        request.with_user(self.technologist_user).action_confirm()
        issue = request.issue_id
        issue.line_ids.with_user(self.manager_user).write({"weight_g": 1490.0})
        issue.with_user(self.manager_user).action_manager_confirm()
        issue.with_user(self.worker_user).action_worker_confirm()

        difference_lot = self.env["cabochon.stone.lot"].sudo().search(
            [("parent_id", "=", lot.id), ("state", "=", "inventory_difference")],
            limit=1,
        )
        self.assertEqual(difference_lot.name, f"{lot.name}-loss")
        self.assertEqual(difference_lot.current_weight_g, 10.0)
        self.assertEqual(difference_lot.location_id, self.raw_location)

        next_request = self.env["cabochon.production.request"].new({})
        next_request.operation_ids = self.wash_operation
        next_request._compute_eligible_lot_ids()
        self.assertNotIn(difference_lot, next_request.eligible_lot_ids)

    def test_completed_operations_are_listed_on_lot(self):
        lot = self._create_lot()
        self.env["cabochon.manufacturing.movement"].sudo().create(
            {
                "kind": "receipt",
                "lot_id": lot.id,
                "new_lot_id": lot.id,
                "operation_ids": [Command.set(self.wash_operation.ids)],
                "source_location_id": self.raw_location.id,
                "destination_location_id": self.prepared_location.id,
                "weight_g": 100.0,
            }
        )

        self.assertEqual(lot.completed_operation_ids, self.wash_operation)

    def test_final_operation_loss_uses_loss_location(self):
        transfer = self.env["cabochon.material.transfer"].sudo().create(
            {
                "transfer_type": "receipt",
                "worker_id": self.worker.id,
                "manager_id": self.manager.id,
                "operation_ids": [Command.set(self.final_operation.ids)],
            }
        )

        self.assertEqual(transfer._get_loss_destination_location(), self.loss_location)

    def test_only_admin_can_change_operation_admissions(self):
        with self.assertRaises(AccessError):
            self.worker.with_user(self.technologist_user).write(
                {"cabochon_allowed_operation_ids": [Command.set(self.wash_operation.ids)]}
            )

        self.worker.with_user(self.admin_user).write(
            {"cabochon_allowed_operation_ids": [Command.set(self.wash_operation.ids)]}
        )
        self.assertEqual(self.worker.cabochon_allowed_operation_ids, self.wash_operation)

        audit_log = self.env["cabochon.audit.log"].sudo().search(
            [
                ("model_name", "=", "hr.employee"),
                ("record_id", "=", self.worker.id),
                ("action", "=", "write"),
            ],
            order="id desc",
            limit=1,
        )
        self.assertEqual(audit_log.user_id, self.admin_user)
        self.assertIn("cabochon_allowed_operation_ids", audit_log.changed_fields)

    def test_manager_as_worker_is_in_technologist_and_quality_reports(self):
        self.manager.with_user(self.admin_user).write(
            {"cabochon_allowed_operation_ids": [Command.set(self.wash_operation.ids)]}
        )
        lot = self._create_lot()
        request = self.env["cabochon.production.request"].with_user(self.technologist_user).create(
            {
                "technologist_id": self.technologist.id,
                "worker_id": self.manager.id,
                "operation_ids": [Command.set(self.wash_operation.ids)],
                "source_lot_id": lot.id,
                "planned_weight_g": 10.0,
                "deadline": fields.Datetime.now() + timedelta(days=1),
            }
        )
        request.with_user(self.technologist_user).action_confirm()
        request.issue_id.with_user(self.manager_user).action_manager_confirm()
        request.issue_id.with_user(self.manager_user).action_worker_confirm()

        load_row = self.env["cabochon.worker.load.report"].sudo().search(
            [("worker_id", "=", self.manager.id), ("company_id", "=", request.company_id.id)],
            limit=1,
        )
        quality_row = self.env["cabochon.worker.operation.quality.report"].sudo().search(
            [
                ("worker_id", "=", self.manager.id),
                ("operation_id", "=", self.wash_operation.id),
                ("company_id", "=", request.company_id.id),
            ],
            limit=1,
        )
        self.assertEqual(load_row.worker_id, self.manager)
        self.assertEqual(quality_row.worker_id, self.manager)
        self.assertEqual(quality_row.issued_weight_g, 10.0)

    def test_defect_report_action_has_no_legacy_domain(self):
        action = self.env.ref("cabochon_manufacturing.action_cabochon_defect_report").sudo()
        self.assertEqual(action.domain, "[]")
        self.env["cabochon.worker.operation.quality.report"].sudo()._read_group(
            [],
            groupby=["worker_id", "operation_id"],
            aggregates=["defect_weight_g:sum", "lost_weight_g:sum"],
        )
