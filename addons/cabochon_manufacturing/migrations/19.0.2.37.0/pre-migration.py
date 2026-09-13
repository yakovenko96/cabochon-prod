def migrate(cr, version):
    # Historical norms were not recorded. Preserve the norm available at upgrade
    # time and explicitly label it as reconstructed, never as an original fact.
    cr.execute("ALTER TABLE cabochon_manufacturing_movement ADD COLUMN IF NOT EXISTS applied_loss_norm_percent double precision")
    cr.execute("ALTER TABLE cabochon_manufacturing_movement ADD COLUMN IF NOT EXISTS norm_snapshot_migrated boolean")
    cr.execute("""
        WITH norms AS (
            SELECT movement.id,
                   CASE WHEN operation.code IN ('tumble_wash', 'toluene_wash') AND fraction.wash_loss_percent > 0
                        THEN fraction.wash_loss_percent ELSE COALESCE(operation.expected_loss_percent, 0) END AS norm
            FROM cabochon_manufacturing_movement movement
            LEFT JOIN cabochon_movement_operation_rel rel ON rel.movement_id = movement.id
            LEFT JOIN cabochon_manufacturing_operation operation ON operation.id = rel.operation_id
            LEFT JOIN cabochon_stone_lot lot ON lot.id = COALESCE(movement.lot_id, movement.new_lot_id)
            LEFT JOIN cabochon_fraction fraction ON fraction.id = lot.fraction_id
        ), snapshot AS (
            SELECT id, CASE WHEN BOOL_OR(norm >= 100) THEN 100
                ELSE (1 - EXP(SUM(LN(GREATEST(1 - norm / 100.0, 0.0000000001))))) * 100 END AS norm
            FROM norms GROUP BY id
        )
        UPDATE cabochon_manufacturing_movement movement
           SET applied_loss_norm_percent = snapshot.norm, norm_snapshot_migrated = TRUE
          FROM snapshot WHERE snapshot.id = movement.id AND movement.applied_loss_norm_percent IS NULL
    """)
