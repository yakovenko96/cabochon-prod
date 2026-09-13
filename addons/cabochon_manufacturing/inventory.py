"""Transaction guards for aggregate positions, including positions not created yet."""

import json


def lock_position(env, namespace, attributes):
    key = json.dumps([namespace, *attributes], separators=(",", ":"))
    # Updating a persistent row makes concurrent REPEATABLE READ transactions
    # restart with a fresh snapshot through Odoo's serialization retry handler.
    env.cr.execute(
        "INSERT INTO cabochon_inventory_guard (key, revision) VALUES (%s, 1) "
        "ON CONFLICT (key) DO UPDATE SET revision = cabochon_inventory_guard.revision + 1",
        [key],
    )
