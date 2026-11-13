# ruff: noqa: F821
"""Run through Odoo shell on a disposable Cabochon*Test database only.

Unlike TransactionCase this script commits fixtures to exercise independent
PostgreSQL transactions. Never run against production or a valuable copy.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

from psycopg2.errors import DeadlockDetected, SerializationFailure

from odoo import SUPERUSER_ID, api, fields
from odoo.exceptions import UserError

if not (env.cr.dbname.startswith("Cabochon") and env.cr.dbname.endswith("Test")):
    raise RuntimeError("Use a disposable Cabochon*Test database; fixtures will be committed.")

registry = env.registry
actor_id = env.ref("base.user_admin").id
suffix = uuid4().hex[:10]
company_id = env.company.id
raw = env.ref("cabochon_manufacturing.location_raw")
finished = env.ref("cabochon_manufacturing.location_finished")
wash = env.ref("cabochon_manufacturing.operation_tumble_wash")
tubes = env.ref("cabochon_manufacturing.operation_tubes")
employee = env["hr.employee"].create({"name": "Concurrency " + suffix, "cabochon_allowed_operation_ids": [(6, 0, (wash | tubes).ids)]})
raw.manager_id = employee
finished.manager_id = employee
lots = env["cabochon.stone.lot"].create([
    {"name": f"CONCURRENT-{suffix}-{index}", "location_id": raw.id,
     "initial_weight_g": 100, "current_weight_g": 100, "extraction_year": 2026, "extraction_month": "1"}
    for index in range(4)
])
shape = env["cabochon.shape"].create({"name": "Concurrency " + suffix})
transfers = env["cabochon.material.transfer"].create([
    {"transfer_type": "receipt", "manager_id": employee.id, "worker_id": employee.id,
     "line_ids": [(0, 0, {"lot_id": lot.id, "weight_g": 10, "shape_id": shape.id})]}
    for lot in lots[:2]
])
line_ids = transfers.mapped("line_ids").ids
destination_id, employee_id, wash_id, tubes_id = finished.id, employee.id, wash.id, tubes.id
shared_id, other_id = lots[2:].ids
shape_id = shape.id
env.cr.commit()


def concurrently(actions, rejected="reserved"):
    barrier = Barrier(len(actions))

    def run(action):
        for attempt in range(5):
            try:
                with registry.cursor() as cr:
                    local = api.Environment(cr, SUPERUSER_ID, {"allowed_company_ids": [company_id]})
                    if attempt == 0:
                        barrier.wait(timeout=20)
                    result = action(local)
                    cr.commit()
                    return result
            except (SerializationFailure, DeadlockDetected):
                if attempt == 4:
                    raise
            except UserError:
                return rejected

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


def receive(local, line_id):
    line = local["cabochon.material.transfer.line"].browse(line_id)
    return line._create_received_lot(local["cabochon.manufacturing.location"].browse(destination_id)).id


positions = concurrently([lambda local, line_id=line_id: receive(local, line_id) for line_id in line_ids])
assert len(set(positions)) == 1, positions
with registry.cursor() as cr:
    local = api.Environment(cr, SUPERUSER_ID, {})
    position = local["cabochon.stone.lot"].browse(positions[0])
    assert position.current_weight_g == 20, position.current_weight_g


def reserve(local, additional=False):
    values = {
        "source_lot_id": other_id if additional else shared_id, "planned_weight_g": 100,
        "worker_id": employee_id, "technologist_id": employee_id,
        "operation_ids": [(6, 0, [tubes_id if additional else wash_id])],
        "deadline": fields.Datetime.now() + timedelta(days=1),
    }
    if additional:
        values["additional_source_line_ids"] = [(0, 0, {"lot_id": shared_id, "weight_g": 100})]
    return local["cabochon.production.request"].create(values).id


reservations = concurrently([lambda local: reserve(local), lambda local: reserve(local, True)])
assert reservations.count("reserved") == 1, reservations
env.invalidate_all()
prepared = env.ref("cabochon_manufacturing.location_prepared")
prepared.manager_id = employee
issue_lot = env["cabochon.stone.lot"].create({
    "name": "CONCURRENT-ISSUE-" + suffix, "location_id": raw.id,
    "initial_weight_g": 100, "current_weight_g": 100,
})
issues = env["cabochon.material.transfer"].create([
    {"transfer_type": "issue", "manager_id": employee_id, "worker_id": employee_id,
     "operation_ids": [(6, 0, [wash_id])],
     "line_ids": [(0, 0, {"lot_id": issue_lot.id, "weight_g": 100})]}
    for _index in range(2)
])
issues.with_user(actor_id).action_manager_confirm()
issue_ids, issue_lot_id = issues.ids, issue_lot.id
env.cr.commit()


def accept_issue(local, transfer_id):
    local["cabochon.material.transfer"].browse(transfer_id).with_user(actor_id).action_worker_confirm()
    return "issued"


issued_results = concurrently([
    lambda local, transfer_id=transfer_id: accept_issue(local, transfer_id)
    for transfer_id in issue_ids
], rejected="rejected")
assert sorted(issued_results) == ["issued", "rejected"], issued_results
with registry.cursor() as cr:
    local = api.Environment(cr, SUPERUSER_ID, {})
    movement = local["cabochon.manufacturing.movement"].search([
        ("lot_id", "=", issue_lot_id), ("kind", "=", "issue"),
    ])
    assert sum(movement.mapped("weight_g")) == 100

env.invalidate_all()
cancel_lot = env["cabochon.stone.lot"].create({
    "name": "CONCURRENT-CANCEL-" + suffix, "location_id": raw.id,
    "initial_weight_g": 100, "current_weight_g": 100,
})
cancel_request = env["cabochon.production.request"].create({
    "source_lot_id": cancel_lot.id, "planned_weight_g": 100,
    "worker_id": employee_id, "technologist_id": employee_id,
    "operation_ids": [(6, 0, [wash_id])],
    "deadline": fields.Datetime.now() + timedelta(days=1),
})
cancel_request.with_user(actor_id).action_confirm()
cancel_request.issue_id.with_user(actor_id).action_manager_confirm()
cancel_request_id, cancel_issue_id = cancel_request.id, cancel_request.issue_id.id
env.cr.commit()


def cancel(local):
    local["cabochon.production.request"].browse(cancel_request_id).with_user(actor_id).action_cancel()
    return "cancelled"


cancel_results = concurrently([
    cancel, lambda local: accept_issue(local, cancel_issue_id),
], rejected="rejected")
assert cancel_results.count("rejected") == 1, cancel_results
with registry.cursor() as cr:
    local = api.Environment(cr, SUPERUSER_ID, {})
    request = local["cabochon.production.request"].browse(cancel_request_id)
    assert (request.state == "cancelled" and not request.movement_ids) or (
        request.state == "in_progress" and request.issue_id.state == "confirmed"
    )

env.invalidate_all()
contractor = env["res.partner"].create({"name": "Concurrent contractor " + suffix, "is_cabochon_contractor": True})
contractor_lot = env["cabochon.stone.lot"].create({
    "name": "CONCURRENT-CONTRACTOR-" + suffix, "location_id": raw.id,
    "initial_weight_g": 100, "current_weight_g": 100,
})
contractor_wizards = env["cabochon.contractor.issue.wizard"].with_user(actor_id).create([
    {"contractor_id": contractor.id, "lot_id": contractor_lot.id, "weight_g": 100}
    for _index in range(2)
])
contractor_wizard_ids, contractor_lot_id = contractor_wizards.ids, contractor_lot.id
env.cr.commit()


def issue_to_contractor(local, wizard_id):
    local["cabochon.contractor.issue.wizard"].browse(wizard_id).with_user(actor_id).action_issue()
    return "issued"


contractor_results = concurrently([
    lambda local, wizard_id=wizard_id: issue_to_contractor(local, wizard_id)
    for wizard_id in contractor_wizard_ids
], rejected="rejected")
assert sorted(contractor_results) == ["issued", "rejected"], contractor_results
with registry.cursor() as cr:
    local = api.Environment(cr, SUPERUSER_ID, {})
    movements = local["cabochon.manufacturing.movement"].search([
        ("lot_id", "=", contractor_lot_id), ("contractor_id", "=", contractor.id),
    ])
    assert sum(movements.mapped("weight_g")) == 100
    assert local["cabochon.stone.lot"].browse(contractor_lot_id).current_weight_g == 0

print("CONCURRENCY_OK: finished merge; reservation; single issue; cancellation vs acceptance; contractor issue")
