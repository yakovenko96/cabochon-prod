def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
        """,
        [table, column],
    )
    return bool(cr.fetchone())


def _backfill_reference(cr, table, text_column, id_column, reference_table):
    if not _column_exists(cr, table, text_column) or not _column_exists(cr, table, id_column):
        return
    cr.execute(
        f"""
        INSERT INTO {reference_table} (name, active, create_uid, create_date, write_uid, write_date)
        SELECT DISTINCT trim(src.{text_column}), TRUE, 1, now(), 1, now()
          FROM {table} src
         WHERE src.{id_column} IS NULL
           AND src.{text_column} IS NOT NULL
           AND trim(src.{text_column}) != ''
           AND NOT EXISTS (
               SELECT 1 FROM {reference_table} ref WHERE ref.name = trim(src.{text_column})
           )
        """
    )
    cr.execute(
        f"""
        UPDATE {table} src
           SET {id_column} = ref.id
          FROM {reference_table} ref
         WHERE src.{id_column} IS NULL
           AND src.{text_column} IS NOT NULL
           AND trim(src.{text_column}) != ''
           AND ref.name = trim(src.{text_column})
        """
    )


def _merge_defect_lots(cr):
    cr.execute(
        """
        WITH grouped AS (
            SELECT location_id, company_id, MIN(id) AS keep_id,
                   SUM(initial_weight_g) AS initial_weight_g,
                   SUM(current_weight_g) AS current_weight_g
              FROM cabochon_stone_lot
             WHERE is_defect_lot AND state = 'available'
             GROUP BY location_id, company_id
        )
        UPDATE cabochon_stone_lot lot
           SET initial_weight_g = grouped.initial_weight_g,
               current_weight_g = grouped.current_weight_g
          FROM grouped
         WHERE lot.id = grouped.keep_id
        """
    )
    cr.execute(
        """
        WITH grouped AS (
            SELECT location_id, company_id, MIN(id) AS keep_id
              FROM cabochon_stone_lot
             WHERE is_defect_lot AND state = 'available'
             GROUP BY location_id, company_id
        )
        UPDATE cabochon_stone_lot lot
           SET current_weight_g = 0.0, state = 'consumed'
          FROM grouped
         WHERE lot.is_defect_lot
           AND lot.state = 'available'
           AND lot.location_id = grouped.location_id
           AND lot.company_id = grouped.company_id
           AND lot.id != grouped.keep_id
        """
    )


def _deduplicate_request_source_lots(cr):
    cr.execute(
        """
        WITH ranked AS (
            SELECT id, source_lot_id,
                   row_number() OVER (PARTITION BY source_lot_id ORDER BY id) AS row_number
              FROM cabochon_production_request
             WHERE state != 'cancelled' AND source_lot_id IS NOT NULL
        ), replacements AS (
            SELECT ranked.id AS request_id,
                   (
                       SELECT movement.new_lot_id
                         FROM cabochon_manufacturing_movement movement
                        WHERE movement.request_id = ranked.id
                          AND movement.kind = 'issue'
                          AND movement.new_lot_id IS NOT NULL
                          AND movement.new_lot_id != ranked.source_lot_id
                        ORDER BY movement.id
                        LIMIT 1
                   ) AS replacement_lot_id
              FROM ranked
             WHERE ranked.row_number > 1
        )
        UPDATE cabochon_production_request request
           SET source_lot_id = replacements.replacement_lot_id
          FROM replacements
         WHERE request.id = replacements.request_id
           AND replacements.replacement_lot_id IS NOT NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM cabochon_production_request other
                WHERE other.id != request.id
                  AND other.state != 'cancelled'
                  AND other.source_lot_id = replacements.replacement_lot_id
           )
        """
    )


def migrate(cr, version):
    _backfill_reference(cr, "cabochon_stone_lot", "color", "color_id", "cabochon_color")
    _backfill_reference(cr, "cabochon_stone_lot", "stone_size", "stone_size_id", "cabochon_size")
    _backfill_reference(cr, "cabochon_stone_lot", "shape", "shape_id", "cabochon_shape")
    _backfill_reference(cr, "cabochon_stone_lot", "form_type", "form_type_id", "cabochon_form_type")
    _backfill_reference(cr, "cabochon_material_transfer_line", "color", "color_id", "cabochon_color")
    _backfill_reference(cr, "cabochon_material_transfer_line", "stone_size", "stone_size_id", "cabochon_size")
    _backfill_reference(cr, "cabochon_material_transfer_line", "shape", "shape_id", "cabochon_shape")
    _backfill_reference(cr, "cabochon_material_transfer_line", "form_type", "form_type_id", "cabochon_form_type")

    if _column_exists(cr, "cabochon_material_transfer_line", "defect_weight_g"):
        cr.execute(
            """
            UPDATE cabochon_material_transfer_line
               SET made_defect_weight_g = defect_weight_g
             WHERE COALESCE(defect_weight_g, 0.0) != 0.0
               AND COALESCE(detected_defect_weight_g, 0.0) = 0.0
               AND COALESCE(made_defect_weight_g, 0.0) = 0.0
            """
        )

    _merge_defect_lots(cr)
    _deduplicate_request_source_lots(cr)
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
