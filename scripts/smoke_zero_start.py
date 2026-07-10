# ruff: noqa: F821
from datetime import timedelta
from uuid import uuid4

from odoo import fields

suffix = uuid4().hex[:8]
raw_lot_name = f"SMOKE-RAW-{suffix}"
finished_lot_name = f"SMOKE-FIN-{suffix}"


def first(recordset, label):
    record = recordset[:1]
    assert record, f"Missing {label}"
    return record


company = env.company
admin_user = env.ref("base.user_admin").sudo()
admin_group = env.ref("cabochon_base.group_cabochon_admin").sudo()
admin_user.write({"group_ids": [(4, admin_group.id)]})

location_model = env["cabochon.manufacturing.location"].sudo()
operation_model = env["cabochon.manufacturing.operation"].sudo()
employee_model = env["hr.employee"].sudo()

raw_location = env.ref("cabochon_manufacturing.location_raw").sudo()
prepared_location = env.ref("cabochon_manufacturing.location_prepared").sudo()
semi_finished_location = env.ref("cabochon_manufacturing.location_semi_finished").sudo()
finished_location = env.ref("cabochon_manufacturing.location_finished").sudo()

tumble_wash = env.ref("cabochon_manufacturing.operation_tumble_wash").sudo()
grinding = env.ref("cabochon_manufacturing.operation_grinding_polishing").sudo()
press = env.ref("cabochon_manufacturing.operation_press").sudo()
tubes = env.ref("cabochon_manufacturing.operation_tubes").sudo()
assert all((raw_location, prepared_location, semi_finished_location, finished_location, tumble_wash, grinding))

manager = employee_model.create({"name": f"Smoke Warehouse Manager {suffix}"})
technologist = employee_model.create({"name": f"Smoke Technologist {suffix}"})
worker = employee_model.create(
    {
        "name": f"Smoke Worker {suffix}",
        "cabochon_allowed_operation_ids": [(6, 0, operation_model.search([("active", "=", True)]).ids)],
    }
)
admin_employee = employee_model.search([("user_id", "=", admin_user.id)], limit=1)
if not admin_employee:
    admin_employee = employee_model.create({"name": "Smoke Admin Employee", "user_id": admin_user.id})

(raw_location | prepared_location | semi_finished_location | finished_location).write({"manager_id": manager.id})

supplier = env["cabochon.supplier"].sudo().create({"name": f"Smoke Supplier {suffix}"})
customer = env["cabochon.finished.customer"].sudo().create({"name": f"Smoke Customer {suffix}"})
fraction = env["cabochon.fraction"].sudo().create({"name": f"Smoke Fraction {suffix}", "wash_loss_percent": 3.0})
year_model = env["cabochon.extraction.year"].sudo()
year = year_model.search([("year", "=", 2026)], limit=1) or year_model.create({"year": 2026})
color = env["cabochon.color"].sudo().create({"name": f"Smoke Color {suffix}"})
shape = env["cabochon.shape"].sudo().create(
    {"name": f"Smoke Shape {suffix}", "use_for_press": True, "use_for_machine": True, "use_for_cutting": True}
)
form_type = env["cabochon.form.type"].sudo().create({"name": f"Smoke Form Type {suffix}"})
size = env["cabochon.size"].sudo().create(
    {
        "name": f"Smoke Size {suffix}",
        "use_for_sorting": True,
        "use_for_tubes": True,
        "use_for_press": True,
        "use_for_machine": True,
        "use_for_cutting": True,
        "use_for_drilling": True,
    }
)

prepared_tube_wizard = env["cabochon.external.receipt.wizard"].with_user(admin_user).new(
    {"location_id": prepared_location.id, "source_operation_id": tubes.id}
)
prepared_tube_wizard._compute_receipt_form_state()
assert set(prepared_tube_wizard.eligible_source_operation_ids.mapped("code")) == {
    "manual_sorting",
    "auto_separator",
    "tubes",
    "tumble_wash",
    "toluene_wash",
}
assert prepared_tube_wizard.show_size_fields and not prepared_tube_wizard.show_color_fields
assert all(prepared_tube_wizard.eligible_stone_size_ids.mapped("use_for_tubes"))

semi_finished_press_wizard = env["cabochon.external.receipt.wizard"].with_user(admin_user).new(
    {"location_id": semi_finished_location.id, "source_operation_id": press.id}
)
semi_finished_press_wizard._compute_receipt_form_state()
assert semi_finished_press_wizard.show_size_fields and semi_finished_press_wizard.show_shape_fields
assert not semi_finished_press_wizard.show_color_fields
assert all(semi_finished_press_wizard.eligible_stone_size_ids.mapped("use_for_press"))
assert all(semi_finished_press_wizard.eligible_shape_ids.mapped("use_for_press"))

external_wizard = env["cabochon.external.receipt.wizard"].with_user(admin_user).create(
    {
        "supplier_id": supplier.id,
        "location_id": raw_location.id,
        "lot_name": raw_lot_name,
        "fraction_id": fraction.id,
        "extraction_year_id": year.id,
        "extraction_month": "1",
        "initial_weight_g": 1000.0,
    }
)
external_wizard.action_create_receipt()
raw_lot = first(env["cabochon.stone.lot"].sudo().search([("name", "=", raw_lot_name)]), "raw lot")
assert raw_lot.location_id == raw_location and raw_lot.current_weight_g == 1000.0

request = env["cabochon.production.request"].sudo().create(
    {
        "technologist_id": technologist.id,
        "worker_id": worker.id,
        "operation_ids": [(6, 0, [tumble_wash.id])],
        "source_lot_id": raw_lot.id,
        "planned_weight_g": 1000.0,
        "deadline": fields.Datetime.now() + timedelta(days=1),
        "company_id": company.id,
    }
)
request.with_user(admin_user).action_confirm()
issue = request.issue_id.with_user(admin_user)
assert issue and issue.transfer_type == "issue" and issue.state == "draft"
assert request.confirmed_at and not issue.transfer_date
issue.action_manager_confirm()
assert issue.manager_confirmed_at and not issue.transfer_date
issue.action_worker_confirm()
assert issue.state == "confirmed" and request.state == "in_progress"
assert issue.transfer_date and issue.worker_confirmed_at
assert request.issued_at == issue.transfer_date and request.started_at == issue.transfer_date

receipt = first(
    request.receipt_ids.filtered(lambda transfer: transfer.transfer_type == "receipt" and transfer.state == "draft"),
    "receipt transfer",
)
receipt = receipt.with_user(admin_user)
receipt.write({"is_final_receipt": True})
line = first(receipt.line_ids, "receipt line")
line.write(
    {
        "weight_g": 900.0,
        "detected_defect_weight_g": 50.0,
        "made_defect_weight_g": 25.0,
    }
)
receipt.action_manager_confirm()
assert receipt.manager_confirmed_at and not receipt.transfer_date
receipt.action_worker_confirm()
assert receipt.state == "confirmed" and request.state == "done"
assert receipt.transfer_date and receipt.worker_confirmed_at
assert request.first_receipt_at == receipt.transfer_date and request.closed_at == receipt.transfer_date

defect_lot = first(
    env["cabochon.stone.lot"].sudo().search(
        [("is_defect_lot", "=", True), ("state", "=", "available"), ("current_weight_g", ">", 0)]
    ),
    "defect lot",
)
recovery_wizard = env["cabochon.defect.recovery.wizard"].with_user(admin_user).create(
    {
        "defect_lot_id": defect_lot.id,
        "weight_g": 10.0,
        "stone_size_id": size.id,
        "manager_id": manager.id,
        "destination_location_id": semi_finished_location.id,
        "company_id": company.id,
    }
)
recovery_wizard.action_recover()
recovered_lot = first(
    env["cabochon.stone.lot"].sudo().search([("parent_id", "=", defect_lot.id), ("stone_size_id", "=", size.id)]),
    "recovered lot",
)
assert recovered_lot.location_id == semi_finished_location and recovered_lot.current_weight_g == 10.0

finished_receipt = env["cabochon.external.receipt.wizard"].with_user(admin_user).create(
    {
        "location_id": finished_location.id,
        "source_operation_id": grinding.id,
        "lot_name": finished_lot_name,
        "fraction_id": fraction.id,
        "color_id": color.id,
        "stone_size_id": size.id,
        "shape_id": shape.id,
        "form_type_id": form_type.id,
        "initial_weight_g": 100.0,
    }
)
finished_receipt.action_create_receipt()
finished_lot = first(env["cabochon.stone.lot"].sudo().search([("name", "=", finished_lot_name)]), "finished lot")
assert finished_lot.location_id == finished_location
finished_lot.write({"standard_weight_g": 2.5})
assert round(finished_lot.estimated_quantity, 2) == 40.0

finished_issue = env["cabochon.finished.issue.wizard"].with_user(admin_user).create(
    {
        "customer_id": customer.id,
        "manager_id": manager.id,
        "line_ids": [(0, 0, {"lot_id": finished_lot.id, "weight_g": 20.0})],
        "company_id": company.id,
    }
)
finished_issue.action_confirm()
finished_lot.invalidate_recordset(["current_weight_g", "state"])
assert finished_lot.current_weight_g == 80.0 and finished_lot.state == "available"

assert env["cabochon.worker.load.report"].sudo().search_count([]) >= 0
assert env["cabochon.worker.operation.quality.report"].sudo().search_count([]) >= 0

print("SMOKE_ZERO_START_OK")
