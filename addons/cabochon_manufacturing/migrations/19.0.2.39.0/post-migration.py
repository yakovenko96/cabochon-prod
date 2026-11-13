from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # On upgrade, initialize the view after all new movement columns exist.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["cabochon.contractor.report"].init()
