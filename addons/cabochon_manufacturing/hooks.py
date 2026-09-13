def _create_inventory_indexes(cr):
    cr.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS cabochon_finished_position_unique
        ON cabochon_stone_lot (location_id, company_id, COALESCE(color_id, 0),
            COALESCE(stone_size_id, 0), COALESCE(shape_id, 0), COALESCE(form_type_id, 0))
        WHERE is_finished_stock AND state = 'available'
    """)
    cr.execute(
        """
        DROP INDEX IF EXISTS cabochon_stone_lot_one_active_defect_per_location
        """
    )
    cr.execute(
        """
        DROP INDEX IF EXISTS cabochon_stone_lot_one_active_defect_per_location_operation
        """
    )
    cr.execute(
        """
        DROP INDEX IF EXISTS cabochon_stone_lot_one_active_defect_per_location_operation_shape
        """
    )
    cr.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS cabochon_stone_lot_one_active_defect_per_attributes
            ON cabochon_stone_lot (
                location_id,
                company_id,
                COALESCE(defect_operation_id, 0),
                COALESCE(shape_id, 0),
                COALESCE(form_type_id, 0),
                COALESCE(color_id, 0)
            )
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
    env["cabochon.worker.load.report"].init()
    env["cabochon.worker.operation.quality.report"].init()
    env["cabochon.integrity.report"].init()
