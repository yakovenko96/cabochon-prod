from odoo import SUPERUSER_ID, api
from odoo.addons.cabochon_manufacturing.hooks import _create_inventory_indexes


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Conflicting old reservations must be reviewed on a restored copy. Raising
    # aborts the upgrade transaction without merging or deleting business data.
    env["cabochon.production.request"].search([("state", "!=", "cancelled")])._reserve_source_lots()
    _create_inventory_indexes(cr)
