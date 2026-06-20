def _create_inventory_indexes(cr):
    cr.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS cabochon_stone_lot_one_active_defect_per_location
            ON cabochon_stone_lot (location_id, company_id)
         WHERE is_defect_lot AND state = 'available'
        """
    )
    cr.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS cabochon_production_request_source_lot_unique
            ON cabochon_production_request (source_lot_id)
         WHERE state != 'cancelled'
        """
    )


def post_init_hook(env):
    _create_inventory_indexes(env.cr)
