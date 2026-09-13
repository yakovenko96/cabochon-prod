# ruff: noqa: F821
"""Run through Odoo shell on a disposable Cabochon*Test database only.

Unlike TransactionCase this script commits fixtures to exercise independent
PostgreSQL transactions. Never run against production or a valuable copy.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

from odoo import SUPERUSER_ID, api, fields
from odoo.exceptions import ValidationError
from psycopg2.errors import DeadlockDetected, SerializationFailure

if not (env.cr.dbname.startswith("Cabochon") and env.cr.dbname.endswith("Test")):
    raise RuntimeError("Use a disposable Cabochon*Test database; fixtures will be committed.")

registry = env.registry
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


def concurrently(actions):
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
            except ValidationError:
                return "reserved"

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
print("CONCURRENCY_OK: one finished position (20 g); exactly one reservation succeeded")
