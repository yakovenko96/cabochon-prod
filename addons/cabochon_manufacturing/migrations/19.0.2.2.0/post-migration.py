def migrate(cr, version):
    cr.execute(
        "ALTER TABLE cabochon_manufacturing_location "
        "DROP COLUMN IF EXISTS stock_location_id"
    )
