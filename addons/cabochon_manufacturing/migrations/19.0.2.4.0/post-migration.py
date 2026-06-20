def migrate(cr, version):
    cr.execute("ALTER TABLE cabochon_fraction DROP COLUMN IF EXISTS sequence")
    cr.execute(
        """
        UPDATE cabochon_stone_lot lot
           SET name = CASE location.code
                          WHEN 'raw' THEN 'БРАК-С'
                          WHEN 'prepared' THEN 'БРАК-ПС'
                          WHEN 'semi_finished' THEN 'БРАК-ПФ'
                          WHEN 'finished' THEN 'БРАК-ГК'
                      END,
               barcode = CASE location.code
                             WHEN 'raw' THEN 'БРАК-С'
                             WHEN 'prepared' THEN 'БРАК-ПС'
                             WHEN 'semi_finished' THEN 'БРАК-ПФ'
                             WHEN 'finished' THEN 'БРАК-ГК'
                         END
          FROM cabochon_manufacturing_location location
         WHERE lot.location_id = location.id
           AND lot.is_defect_lot
           AND lot.state = 'available'
           AND location.code IN ('raw', 'prepared', 'semi_finished', 'finished')
        """
    )
